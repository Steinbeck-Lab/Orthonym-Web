"""The Celery tasks. Every OPSIN call in Orthonym now happens in one of these.

Two shapes rather than one: the fast path runs a whole small list in a
single task, and the batch path splits into chunks with a chord. A chord for
ten molecules would add a poll cycle for nothing, and a single task for
10,000 would report no progress and hold one worker for an hour.
"""

from __future__ import annotations

import logging

from celery import chord

from app import name_cache, redis_store
from app.celery_app import celery_app
from app.orthonym_service import translate_one
from app.schemas import BatchRow

logger = logging.getLogger(__name__)


def name_one(smiles: str, best_effort: bool) -> dict:
    """Name one molecule, consulting the cache first.

    Returns the ResultItem fields a BatchRow needs, minus depiction_svg.
    The fast path and the batch path share this, so a molecule named by a
    batch answers instantly on Home and vice versa.
    """
    cached = name_cache.get_cached(smiles, best_effort)
    if cached is not None:
        item = cached
    else:
        item = translate_one(smiles, best_effort=best_effort)
        name_cache.put_cached(item, best_effort)
    return {
        "smiles": item.smiles,
        "name": item.name,
        "status": item.status,
        "roundtrip_smiles": item.roundtrip_smiles,
        "roundtrip_match": item.roundtrip_match,
        "formula": item.formula,
        "limit_code": item.limit_code,
        "error": item.error,
    }


def _row(index: int, raw_input: str, input_id: str | None, named: dict) -> dict:
    return BatchRow(
        index=index,
        input=raw_input,
        input_id=input_id,
        smiles=named["smiles"],
        name=named["name"],
        status=named["status"],
        roundtrip_smiles=named["roundtrip_smiles"],
        roundtrip_match=named["roundtrip_match"],
        formula=named["formula"],
        limit_code=named["limit_code"],
        error=named["error"],
    ).model_dump()


def _error_row(index: int, raw_input: str, input_id: str | None, message: str) -> dict:
    return BatchRow(
        index=index,
        input=raw_input,
        input_id=input_id,
        status="error",
        error=message,
    ).model_dump()


def _name_prepared(
    prepared: list[dict], start_index: int, best_effort: bool
) -> tuple[list[dict], int]:
    """Name a list of already-parsed molecules. Returns (rows, failed).

    `prepared` items carry raw_input, input_id and smiles (None when parsing
    already failed). A molecule that raises is recorded as an error row: one
    bad molecule must not lose the other 24 in its chunk.
    """
    rows: list[dict] = []
    failed = 0
    for offset, item in enumerate(prepared):
        index = start_index + offset
        if item["smiles"] is None:
            rows.append(
                _error_row(index, item["raw_input"], item["input_id"], item["error"])
            )
            failed += 1
            continue
        try:
            named = name_one(item["smiles"], best_effort)
        except Exception as exc:  # noqa: BLE001 - one molecule, not the chunk
            logger.exception("Naming failed for %s", item["smiles"])
            rows.append(
                _error_row(
                    index,
                    item["raw_input"],
                    item["input_id"],
                    f"Naming failed: {exc}",
                )
            )
            failed += 1
            continue
        rows.append(_row(index, item["raw_input"], item["input_id"], named))
        if named["status"] == "error":
            failed += 1
    return rows, failed


@celery_app.task(name="app.tasks.translate_job_inline")
def translate_job_inline(
    job_id: str, prepared: list[dict], best_effort: bool
) -> list[dict]:
    """Fast path: name a small list in one task and finalise it here."""
    redis_store.set_job_status(job_id, "running")
    rows, failed = _name_prepared(prepared, 0, best_effort)
    redis_store.write_chunk(job_id, 0, rows)
    redis_store.bump_job_done(job_id, done=len(rows), failed=failed)
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.set_job_status(job_id, "done")
    return rows


@celery_app.task(
    name="app.tasks.run_chunk",
    bind=True,
    autoretry_for=(),
)
def run_chunk(
    self, job_id: str, index: int, prepared: list[dict], best_effort: bool
) -> int:
    """One chunk of a batch job. Writes its own key and bumps the counter."""
    from celery.exceptions import SoftTimeLimitExceeded

    redis_store.set_job_status(job_id, "running")
    # Take the index from the data, never from index * chunk_size: the last
    # chunk of an uneven split is short, so the arithmetic would be wrong.
    start_index = prepared[0]["index"] if prepared else 0
    try:
        rows, failed = _name_prepared(prepared, start_index, best_effort)
    except SoftTimeLimitExceeded:
        # The whole chunk ran out of time. Record every molecule in it as a
        # timeout rather than letting the job look complete with rows missing.
        rows = [
            _error_row(
                item["index"], item["raw_input"], item["input_id"], "Timed out"
            )
            for item in prepared
        ]
        for row in rows:
            row["limit_code"] = "timeout"
        failed = len(rows)

    redis_store.write_chunk(job_id, index, rows)
    redis_store.bump_job_done(job_id, done=len(rows), failed=failed)
    return len(rows)


@celery_app.task(name="app.tasks.finalize_job")
def finalize_job(chunk_counts: list[int], job_id: str, n_chunks: int) -> int:
    """Chord callback: order the chunks, clean them up, close the job.

    A job whose assembled row count is short of its declared total is marked
    "failed", not "done". assemble_rows already logs which chunk keys went
    missing; reporting "done" over an incomplete result list is the one thing
    spec section 10 forbids.
    """
    written = redis_store.assemble_rows(job_id, n_chunks)

    meta = redis_store.read_job_meta(job_id) or {}
    total = int(meta.get("total", 0))
    if written < total:
        redis_store.set_job_status(job_id, "failed")
        logger.error(
            "Job %s assembled %s of %s rows and is INCOMPLETE -- marked "
            "failed. See the preceding assemble_rows error for which chunks "
            "were missing.",
            job_id,
            written,
            total,
        )
        return written

    redis_store.set_job_status(job_id, "done")
    logger.info("Job %s finalised: %s rows from %s chunks", job_id, written, n_chunks)
    return written


def dispatch_batch(
    job_id: str, prepared: list[dict], best_effort: bool, chunk_size: int
) -> int:
    """Split into chunks and fire the chord. Returns the chunk count."""
    chunks = [
        prepared[i : i + chunk_size] for i in range(0, len(prepared), chunk_size)
    ]
    header = [
        run_chunk.s(job_id, index, chunk, best_effort)
        for index, chunk in enumerate(chunks)
    ]
    chord(header)(finalize_job.s(job_id, len(chunks)))
    return len(chunks)
