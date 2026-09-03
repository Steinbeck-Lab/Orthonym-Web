"""The Celery tasks. Every OPSIN call in Orthonym now happens in one of these.

Two shapes rather than one: the fast path runs a whole small list in a
single task, and the batch path splits into chunks with a chord. A chord for
ten molecules would add a poll cycle for nothing, and a single task for
10,000 would report no progress and hold one worker for an hour.
"""

from __future__ import annotations

import dataclasses
import logging

from celery import chord
from celery.exceptions import SoftTimeLimitExceeded

from app import name_cache, redis_store
from app.celery_app import celery_app
from app.orthonym_service import translate_one
from app.schemas import BatchRow, ResultItem

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
        # depict=False: the dict below drops depiction_svg and name_cache
        # excludes it, so drawing one here would be measured waste (see
        # translate_one). The fast path draws its own, from the same cache.
        item = translate_one(smiles, best_effort=best_effort, depict=False)
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

    Also releases the job's per-IP concurrent-job slot here, as the fast
    path: a caller who submits and never polls GET /api/jobs/{id} (the
    only other release point, along with DELETE) would otherwise hold that
    slot until the job's TTL expired. This is not the ONLY thing that can
    release it, though -- when `meta` itself is missing (below) there is no
    `ip` on hand to release from at all, which is exactly what
    check_and_register_job's self-healing exists to cover instead.
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

    ip = meta.get("ip", "unknown")
    total = int(meta.get("total", 0))
    already = redis_store.rows_length(job_id)
    if meta.get("status") == "done" and already == total:
        logger.info(
            "Job %s is already closed with %s rows; redelivered close ignored.",
            job_id,
            already,
        )
        # Idempotent: release_job's own SREM is a no-op if this job's slot
        # was already freed by the FIRST close. Covers the leak class no
        # errback reaches -- translate_job_inline has none, and this is the
        # fast path's own terminal state, not a chord callback.
        redis_store.remove_ip_job(ip, job_id)
        return already

    written = redis_store.assemble_rows(job_id, n_chunks)
    if written < total:
        redis_store.set_job_status(job_id, "failed")
        redis_store.remove_ip_job(ip, job_id)
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
    redis_store.remove_ip_job(ip, job_id)
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

    Guarded by begin_chunk, same primitive as run_chunk (final review
    report, I1 -- this task had the identical unconditional
    set_job_status(job_id, "running") run_chunk had, on the DEFAULT path
    for every job at or under FAST_PATH_MAX_MOLECULES). Without it, a
    redelivered execution (task_acks_late=True makes this real) that dies
    between that status flip and write_chunk would leave an ALREADY-done
    job stuck at "running" forever: assemble_rows already deleted this
    job's only chunk key on the first, successful close, so there is
    nothing to rebuild from, _close_job never runs on the crashed
    attempt, and "it self-heals via _close_job at the end" does not hold
    for an attempt that never reaches its own end -- even though the
    job's real rows are still sitting there, complete, in
    orthonym:job:{id}:rows. begin_chunk closes this by never touching the
    status at all once the job is genuinely terminal.
    """
    if not redis_store.begin_chunk(job_id):
        logger.info(
            "Job %s already terminal; ignoring redelivered fast-path task",
            job_id,
        )
        # A caller polling .get() on this task should still see the real
        # result, not an empty list: the job's actual rows are still in
        # Redis, and the only reason this attempt exists at all is a
        # redelivery of a task that already ran to completion once.
        return list(redis_store.iter_all_rows(job_id))
    try:
        rows, failed = _name_prepared(prepared, best_effort)
    except _ChunkTimedOut as timeout:
        rows, failed = _timed_out_rows(timeout)
    redis_store.write_chunk(job_id, 0, rows)
    redis_store.bump_job_done(job_id, index=0, done=len(rows), failed=failed)
    _close_job(job_id, n_chunks=1)
    return rows


@celery_app.task(name="app.tasks.run_chunk")
def run_chunk(
    job_id: str, index: int, prepared: list[dict], best_effort: bool
) -> int:
    """One chunk of a batch job. Writes its own key and bumps the counter.

    Two redelivery guards (task_acks_late=True makes redelivery real,
    final review report I1): begin_chunk refuses to reopen a job that has
    already reached "done"/"failed" (the chord body fires once and will
    not fire again, so nothing else would ever close it a second time),
    and bump_job_done's own per-chunk marker stops the SAME chunk being
    counted twice even when begin_chunk's status check can't help -- e.g.
    a redelivery that arrives BEFORE the job closes.
    """
    if not redis_store.begin_chunk(job_id):
        logger.info(
            "Job %s already terminal; ignoring redelivered chunk %s",
            job_id,
            index,
        )
        return 0

    try:
        rows, failed = _name_prepared(prepared, best_effort)
    except _ChunkTimedOut as timeout:
        rows, failed = _timed_out_rows(timeout)

    redis_store.write_chunk(job_id, index, rows)
    redis_store.bump_job_done(job_id, index=index, done=len(rows), failed=failed)
    return len(rows)


@celery_app.task(name="app.tasks.finalize_job")
def finalize_job(chunk_counts: list[int], job_id: str, n_chunks: int) -> int:
    """Chord callback: order the chunks, clean up, close the job.

    `chunk_counts` is unused but required: Celery's chord contract passes the
    header's results as the callback's first positional argument.
    """
    return _close_job(job_id, n_chunks)


@celery_app.task(name="app.tasks.mark_job_failed")
def mark_job_failed(request, exc, traceback, job_id: str) -> None:
    """Errback: give a job that blew up a terminal state.

    Without this, a raising chunk leaves the job at "running" forever --
    Celery skips a chord's body when a header task fails, so finalize_job
    never runs and a caller polls a progress bar that will not move until the
    24-hour TTL turns it into a 404. Honest, but useless.

    Also releases the job's per-IP concurrent-job slot, same reasoning as
    _close_job -- a caller who never polls should not stay charged against
    their cap for a job that has already reached a terminal state.
    """
    logger.error("Job %s failed with %r; marking it failed", job_id, exc)
    redis_store.set_job_status(job_id, "failed")
    meta = redis_store.read_job_meta(job_id)
    if meta is not None:
        redis_store.remove_ip_job(meta.get("ip", "unknown"), job_id)


def _fast_error_item(smiles: str, message: str) -> dict:
    """An error row for the FAST path, shaped as a ResultItem.

    NOT _error_row: that builds a BatchRow, whose `smiles` is Optional and
    which carries none of ResultItem's fields. main.py validates every row
    translate_fast returns with ResultItem.model_validate, so a BatchRow here
    raises a pydantic ValidationError and 500s the whole request -- which is
    exactly the failure the per-molecule guard exists to prevent, arriving by
    a different route.

    `smiles` echoes the input back rather than being None, matching what
    translate_one itself does for an unparseable string and what this same
    loop does for an already-failed parse.
    """
    return ResultItem(
        smiles=smiles,
        status="error",
        name=None,
        tier=None,
        formula=None,
        limit_code=None,
        error=message,
        depiction_svg=None,
        roundtrip_smiles=None,
        roundtrip_match=None,
    ).model_dump()


@celery_app.task(name="app.tasks.translate_fast")
def translate_fast(prepared: list[dict], best_effort: bool) -> list[dict]:
    """The single-molecule path: full ResultItems, picture included.

    Separate from the batch tasks because the response must stay
    byte-compatible with today's TranslateResponse, which includes
    depiction_svg -- the one thing batch rows deliberately omit.

    `prepared` is app.jobs_api.prepared_payload's wire form (index,
    raw_input, input_id, smiles, error) -- the SAME shape run_chunk and
    translate_job_inline take -- not a bare list of raw strings. Final
    review, crash-loop fix: this used to receive raw user text and hand it
    straight to translate_one -> Chem.MolFromSmiles/MolToSmiles with no
    length check, unlike every other path, which routes through
    app.inputs._canonical_or_error (MAX_MOLECULE_SMILES_LENGTH) first.
    Chem.MolToSmiles SIGSEGVs at roughly 30,000 atoms, and
    task_reject_on_worker_lost=True requeues a SIGKILLed task, so one
    oversized SMILES could crash-loop this queue forever. The caller
    (app.main.translate) now canonicalizes with app.main._canonicalize
    before dispatch, so an item with `smiles: None` here already failed
    that check (or failed to parse) and must never reach RDKit at all.
    """
    from app.depiction import structure_svg_data_uri
    from rdkit import Chem

    rows = []
    for item in prepared:
        if item["smiles"] is None:
            # Already-canonical-or-error, same convention translate_one
            # itself uses for an unparseable string: echo the raw input
            # back as `smiles`, no RDKit call.
            rows.append(
                ResultItem(
                    smiles=item["raw_input"],
                    status="error",
                    name=None,
                    tier=None,
                    formula=None,
                    limit_code=None,
                    error=item["error"],
                    depiction_svg=None,
                    roundtrip_smiles=None,
                    roundtrip_match=None,
                ).model_dump()
            )
            continue

        smiles = item["smiles"]
        try:
            cached = name_cache.get_cached(smiles, best_effort)
            result_item = cached if cached is not None else translate_one(
                smiles, best_effort=best_effort
            )
            if cached is None:
                name_cache.put_cached(result_item, best_effort)
        except SoftTimeLimitExceeded:
            # MUST precede the broad handler: SoftTimeLimitExceeded subclasses
            # Exception DIRECTLY, so `except Exception` would swallow Celery's
            # timeout, this loop would run on past the limit, and the hard
            # limit would kill the worker mid-request with nothing written.
            # _name_prepared orders its handlers the same way for the same
            # reason.
            raise
        except Exception as exc:  # noqa: BLE001 - one molecule, not the request
            # Matches _name_prepared's contract on the batch path (final
            # review report, I4): one molecule that raises must not lose the
            # others. Without this the fast path had no guard at all, so a
            # single raise reached the client as a bare 500 with no detail --
            # main.py catches only CeleryTimeoutError -- on Home, the main
            # product surface, while the batch path degraded honestly to a
            # per-row error. The last upstream tier rename made classify()
            # raise on live rows; the next one will too.
            logger.exception("Naming failed for %s", smiles)
            rows.append(_fast_error_item(smiles, f"Naming failed: {exc}"))
            continue
        if result_item.depiction_svg is None and result_item.status in (
            "pin",
            "fallback",
            "best_effort",
        ):
            # A cached item was stored without its picture; redraw it here so
            # the response shape never varies by cache hit or miss.
            #
            # No `if mol is not None` gate any more. structure_svg_data_uri
            # draws from the SMILES STRING with CDK first and only reaches for
            # the Mol as its RDKit fallback, so gating on RDKit excluded exactly
            # the CDK-only molecules the fallback exists for -- engine knowledge
            # leaking back into the caller. The Mol is still parsed because the
            # fallback genuinely needs one in a JVM-less process; measured at
            # 0.027 ms/row, which is why it is not worth deferring.
            svg = structure_svg_data_uri(
                result_item.smiles, Chem.MolFromSmiles(result_item.smiles)
            )
            if svg is not None:
                result_item = result_item.model_copy(update={"depiction_svg": svg})
        rows.append(result_item.model_dump())
    return rows


@celery_app.task(name="app.tasks.explain_smiles")
def explain_smiles(smiles: str) -> dict:
    from app.explain import explain_molecule
    from app.orthonym_service import get_primary_namer

    return explain_molecule(smiles, namer=get_primary_namer())


@celery_app.task(name="app.tasks.explain_iupac_name")
def explain_iupac_name(name: str) -> dict:
    from app.explain import explain_name

    return explain_name(name)


@celery_app.task(name="app.tasks.name_to_smiles")
def name_to_smiles(name: str) -> dict:
    from orthonym.validation.opsin_roundtrip import opsin_parse
    from rdkit import Chem

    from app.depiction import structure_svg_data_uri

    raw = opsin_parse(name)
    mol = Chem.MolFromSmiles(raw) if raw else None
    if mol is None:
        return {
            "smiles": None,
            "depiction_svg": None,
            "error": "Could not parse this name via OPSIN",
        }
    return {
        "smiles": raw,
        "depiction_svg": structure_svg_data_uri(raw, mol),
        "error": None,
    }


def dispatch_batch(
    job_id: str, prepared: list[dict], best_effort: bool, chunk_size: int
) -> int:
    """Split into chunks and fire the chord. Returns the chunk count."""
    chunks = [
        prepared[i : i + chunk_size] for i in range(0, len(prepared), chunk_size)
    ]
    errback = mark_job_failed.s(job_id)
    header = [
        run_chunk.s(job_id, index, chunk, best_effort).on_error(errback)
        for index, chunk in enumerate(chunks)
    ]
    chord(header)(finalize_job.s(job_id, len(chunks)).on_error(errback))
    return len(chunks)

@celery_app.task(name="app.tasks.parse_input")
def parse_input(data: bytes, max_molecules: int) -> dict:
    """Sniff and parse an uploaded body, in a WORKER rather than the web process.

    Spec section 13a / audit item parse-cost-aggregate. Parsing is RDKit work,
    and RDKit's Boost.Python wrappers do not release the GIL, so doing it in
    the web process blocks every other request on that process for its whole
    duration -- FastAPI's threadpool does not help.

    MEASURED, which is what settled the design. Cost scales with molecule
    SIZE, not count: 10,000 short SMILES parse in 0.14 s, while 1,000 at
    MAX_MOLECULE_SMILES_LENGTH take 29.1 s -- so a full 10,000-molecule upload
    of large molecules is roughly 290 s of GIL-held CPU from ONE request that
    is entirely within its quota. The count caps never bounded this because
    they count molecules.

    The caller BLOCKS on this rather than being handed a job envelope, which
    is what keeps the contract intact: a malformed file still returns a
    synchronous 400 naming the problem, instead of being accepted and failing
    asynchronously ten seconds later with no way to say why. The web process
    waits on I/O, releasing the GIL, so what moves is the CPU and not the
    user's experience.

    Returns a plain dict rather than raising, because an HTTPException cannot
    cross the broker: the web process re-raises the right status from `error`.
    """
    from app.inputs import TooManyMolecules, parse, sniff

    fmt = sniff(data)
    try:
        molecules = parse(data, fmt, max_molecules)
    except TooManyMolecules as exc:
        return {"error": "too_many", "limit": exc.limit, "fmt": fmt.value}
    except ValueError as exc:
        return {"error": "unreadable", "detail": str(exc), "fmt": fmt.value}
    if not molecules:
        return {"error": "empty", "fmt": fmt.value}
    return {
        "error": None,
        "fmt": fmt.value,
        "molecules": [dataclasses.asdict(m) for m in molecules],
    }
