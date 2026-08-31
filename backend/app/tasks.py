"""The Celery tasks. Every OPSIN call in Orthonym now happens in one of these.

Two shapes rather than one: the fast path runs a whole small list in a
single task, and the batch path splits into chunks with a chord. A chord for
ten molecules would add a poll cycle for nothing, and a single task for
10,000 would report no progress and hold one worker for an hour.
"""

from __future__ import annotations

import logging

from celery import chord
from celery.exceptions import SoftTimeLimitExceeded

from app import name_cache, redis_store
from app.celery_app import celery_app
from app.orthonym_service import translate_one
from app.schemas import BatchRow

logger = logging.getLogger(__name__)


class _ChunkTimedOut(Exception):
    """The soft time limit fired mid-chunk. Carries the rows already built.

    SoftTimeLimitExceeded cannot be relied on to surface by itself. billiard
    raises it at whatever bytecode is executing -- almost always inside
    name_one, which is ~100% of a chunk's wall time -- and it subclasses
    Exception DIRECTLY (verified: its MRO is SoftTimeLimitExceeded,
    Exception, BaseException, object). So a per-molecule `except Exception`
    swallows the timeout, records one misleading "Naming failed" row, and
    lets the loop keep naming past the limit; the signal fires once, so
    nothing stops it until the HARD limit SIGKILLs the child before
    write_chunk runs -- losing the entire chunk, which is the exact outcome
    the timeout handling exists to prevent.

    Carrying `rows` matters too: they are real results, and the frame
    holding them is about to be discarded.
    """

    def __init__(self, rows: list[dict], failed: int, remaining: list[dict]):
        super().__init__("chunk exceeded its soft time limit")
        self.rows = rows
        self.failed = failed
        self.remaining = remaining


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
    prepared: list[dict], best_effort: bool
) -> tuple[list[dict], int]:
    """Name a list of already-parsed molecules. Returns (rows, failed).

    Each item carries its own absolute `index` alongside raw_input, input_id
    and smiles (None when parsing already failed). The index comes from the
    data, never from arithmetic over the caller's chunk position -- that is
    what keeps a short final chunk correctly numbered, and it means this
    function needs no start offset at all.

    A molecule that raises is recorded as an error row: one bad molecule
    must not lose the other 24 in its chunk.
    """
    rows: list[dict] = []
    failed = 0
    for offset, item in enumerate(prepared):
        index = item["index"]
        if item["smiles"] is None:
            rows.append(
                _error_row(index, item["raw_input"], item["input_id"], item["error"])
            )
            failed += 1
            continue
        try:
            named = name_one(item["smiles"], best_effort)
        except SoftTimeLimitExceeded as exc:
            # MUST come before the broad handler: SoftTimeLimitExceeded
            # subclasses Exception, so `except Exception` would swallow the
            # timeout and the loop would run on past the limit until the
            # hard limit killed the child mid-chunk.
            raise _ChunkTimedOut(rows, failed, list(prepared[offset:])) from exc
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


def _timed_out_rows(timeout: _ChunkTimedOut) -> tuple[list[dict], int]:
    """Keep what was actually named; mark only the rest as timed out.

    Discarding the whole chunk would lose real results, and leaving the rest
    out would let the job report a short row count for a reason no row
    explains.
    """
    rows = list(timeout.rows)
    failed = timeout.failed
    for item in timeout.remaining:
        row = _error_row(
            item["index"], item["raw_input"], item["input_id"], "Timed out"
        )
        row["limit_code"] = "timeout"
        rows.append(row)
        failed += 1
    return rows, failed


def _close_job(job_id: str, n_chunks: int) -> int:
    """Assemble the chunks and decide done-versus-failed. The ONE place that does.

    Both the fast path and the chord callback go through here, because the
    rule is the product's central honesty guarantee and must not have two
    implementations: a job never reports "done" over an incomplete result
    list.

    Idempotent. task_acks_late=True makes redelivery real, and assemble_rows
    deletes the chunk keys as it goes -- so a second, naive close would find
    nothing, wipe a finished job's rows and flip it to failed.
    """
    meta = redis_store.read_job_meta(job_id)
    if meta is None:
        # The meta hash aged out or was evicted, so the declared total is
        # unknown and completeness cannot be verified. Deliberately writes
        # NO status: HSET would recreate the hash carrying only that one
        # field, and a later read would KeyError on `total` and answer 500
        # where the design promises 410.
        logger.error(
            "Job %s: meta hash missing at close, so completeness cannot be "
            "verified. Leaving it absent rather than resurrecting a partial "
            "hash that would make /api/jobs/{id} raise instead of 410.",
            job_id,
        )
        return 0

    total = int(meta.get("total", 0))
    already = redis_store.rows_length(job_id)
    if meta.get("status") == "done" and already == total:
        logger.info(
            "Job %s is already closed with %s rows; redelivered close ignored.",
            job_id,
            already,
        )
        return already

    written = redis_store.assemble_rows(job_id, n_chunks)
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


@celery_app.task(name="app.tasks.translate_job_inline")
def translate_job_inline(
    job_id: str, prepared: list[dict], best_effort: bool
) -> list[dict]:
    """Fast path: name a small list in one task and close it here.

    Closes through _close_job, not by setting "done" directly. This is the
    DEFAULT path for anything up to FAST_PATH_MAX_MOLECULES, so an
    unchecked "done" here would be the most-travelled route to a job that
    claims completeness over an incomplete result list.
    """
    redis_store.set_job_status(job_id, "running")
    try:
        rows, failed = _name_prepared(prepared, best_effort)
    except _ChunkTimedOut as timeout:
        rows, failed = _timed_out_rows(timeout)
    redis_store.write_chunk(job_id, 0, rows)
    redis_store.bump_job_done(job_id, done=len(rows), failed=failed)
    _close_job(job_id, n_chunks=1)
    return rows


@celery_app.task(name="app.tasks.run_chunk")
def run_chunk(
    job_id: str, index: int, prepared: list[dict], best_effort: bool
) -> int:
    """One chunk of a batch job. Writes its own key and bumps the counter."""
    redis_store.set_job_status(job_id, "running")
    try:
        rows, failed = _name_prepared(prepared, best_effort)
    except _ChunkTimedOut as timeout:
        rows, failed = _timed_out_rows(timeout)

    redis_store.write_chunk(job_id, index, rows)
    redis_store.bump_job_done(job_id, done=len(rows), failed=failed)
    return len(rows)


@celery_app.task(name="app.tasks.finalize_job")
def finalize_job(chunk_counts: list[int], job_id: str, n_chunks: int) -> int:
    """Chord callback: order the chunks, clean up, close the job.

    `chunk_counts` is unused but required: Celery's chord contract passes the
    header's results as the callback's first positional argument.
    """
    return _close_job(job_id, n_chunks)


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
