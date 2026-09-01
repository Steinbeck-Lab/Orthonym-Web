"""The batch job endpoints.

Kept in its own router rather than main.py: six endpoints plus CSV
streaming would double that file, and these share nothing with the
single-molecule endpoints except the settings object.
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rdkit import Chem

from app import redis_store
from app.core.config import get_settings
from app.depiction import mol_to_svg_data_uri
from app.inputs import TooManyMolecules, parse, parse_preview_sample, sniff
from app.jvm_guard import require_a_live_jvm
from app.ratelimit import (
    check_and_register_job,
    check_depict_allowed,
    check_download_allowed,
    check_fast_allowed,
    check_job_allowed,
    check_poll_allowed,
    client_ip,
    release_job,
)
from app.schemas import (
    BatchRow,
    DepictResponse,
    JobEnvelope,
    JobResultsResponse,
    JobStatusResponse,
    ParsePreviewResponse,
    ParsePreviewRow,
)
from app.tasks import dispatch_batch, mark_job_failed, translate_job_inline

router = APIRouter()

PREVIEW_SAMPLE = 5

CSV_COLUMNS = [
    "index",
    "input",
    "input_id",
    "smiles",
    "name",
    "status",
    "roundtrip_smiles",
    "roundtrip_match",
    "formula",
    "limit_code",
    "error",
]


class TextPayload(BaseModel):
    text: str
    best_effort: bool = True


async def _read_input(
    request: Request, file: UploadFile | None, best_effort: bool = True
) -> tuple[bytes, bool]:
    """Accept either a multipart file or a JSON {"text": ...} body.

    Size is checked before the bytes are handed on, so an oversized upload
    is rejected rather than parsed.

    A multipart request with no `file` part has already had its body stream
    consumed by the time FastAPI resolves `file` to None, so falling through
    to request.json() raises a bare RuntimeError ("Stream consumed"). An
    empty or non-JSON body raises JSONDecodeError, and JSON missing "text"
    raises pydantic's ValidationError. All three would otherwise surface as
    a raw 500, so they are caught here and reported as an honest 400 -- this
    is a trust boundary, and a malformed request is the caller's mistake to
    be told about, not the server's to crash on.
    """
    settings = get_settings()

    # Reject on the declared length BEFORE reading, so an oversized upload
    # costs a header rather than 500 MB of process memory. The post-read
    # check below still stands: Content-Length is client-supplied and may be
    # absent (chunked transfer) or a lie.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        if int(declared) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Body is larger than the {settings.MAX_FILE_SIZE_MB} MB "
                    "limit"
                ),
            )

    if file is not None:
        data = await file.read()
        if len(data) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File is larger than the {settings.MAX_FILE_SIZE_MB} MB limit"
                ),
            )
        # best_effort comes from the multipart form, not a hardcoded True
        # (audit item upload-forces-best-effort). best_effort=False is the
        # caller saying "only names OPSIN round-trip verified; abstain rather
        # than guess" -- the JSON branch below has always honoured it, and a
        # file uploader could not say it at all, so they silently received
        # OPSIN-unverified names with nothing recording that their request had
        # been overridden. The default stays True, matching TextPayload's, so
        # nothing changes for a caller who sends no field.
        return data, best_effort

    try:
        body = await request.json()
        payload = TextPayload.model_validate(body)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Expected a file upload or a JSON body with a 'text' field",
        ) from exc

    data = payload.text.encode("utf-8")
    if len(data) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Input is larger than the {settings.MAX_FILE_SIZE_MB} MB limit",
        )
    return data, payload.best_effort


def _parse_or_400(data: bytes, max_molecules: int):
    fmt = sniff(data)
    try:
        molecules = parse(data, fmt, max_molecules)
    except TooManyMolecules as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Input exceeds the {exc.limit}-molecule limit",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not read this {fmt.value}: {exc}"
        ) from exc
    if not molecules:
        raise HTTPException(
            status_code=400,
            detail=f"No molecules found in this {fmt.value} input",
        )
    return fmt, molecules


def prepared_payload(molecules) -> list[dict]:
    """The wire form a task receives: JSON-serialisable, index preserved."""
    return [
        {
            "index": m.index,
            "raw_input": m.raw_input,
            "input_id": m.input_id,
            "smiles": m.smiles,
            "error": m.error,
        }
        for m in molecules
    ]


def admit_and_dispatch(
    ip: str, molecules, fmt: str, best_effort: bool
) -> str:
    """Admit, register, and dispatch one batch job as a single unit.

    The ONLY place that creates and dispatches a batch job -- POST
    /api/jobs and POST /api/translate's over-the-fast-limit and
    ratelimit-timeout branches all call this, so there is no path that
    dispatches without admitting (round 1 review, Critical 2), and no path
    that admits without the hourly cap either (round 2 review, finding 1:
    /api/translate's job branch used to call NEITHER check_job_allowed NOR
    register_job -- measured at 30 jobs of up to 10,000 molecules admitted
    against a cap of 3/hour that only POST /api/jobs was ever charged
    against).

    Job meta is created BEFORE the atomic admission check, not after: a
    concurrent admission call from the SAME ip self-heals stale members by
    treating "no meta yet" the same as "meta expired long ago" (see
    ratelimit._ADMIT_JOB_SCRIPT), so creating the meta first (status
    "queued", not done/failed, present) is what keeps that self-heal from
    evicting a job that is still being admitted. If admission is then
    rejected, the now-orphaned meta hash is deleted immediately rather than
    left to expire on its own TTL.

    The caller MUST already have called check_job_allowed(ip) BEFORE doing
    any expensive parsing to build `molecules` (round 3 review, finding 1):
    doing that check in HERE instead would put it after the exact
    expensive work every caller does to produce `molecules` in the first
    place, which is what let a 46-second RDKit parse run to completion
    before a 429 in the previous round. This function only does the
    ATOMIC, TOCTOU-safe concurrent-cap registration
    (check_and_register_job) -- the hourly cap and the cheap concurrent
    pre-check both already happened, earlier, in the caller.
    """
    settings = get_settings()
    job_id = uuid.uuid4().hex
    redis_store.create_job(job_id, len(molecules), fmt, ip)
    try:
        check_and_register_job(ip, job_id)
    except HTTPException:
        redis_store.get_redis().delete(redis_store.job_meta_key(job_id))
        raise

    try:
        prepared = prepared_payload(molecules)
        if len(prepared) <= settings.FAST_PATH_MAX_MOLECULES:
            # link_error, matching what dispatch_batch already wires onto
            # every chord header AND its body (final review report, I5).
            # This is the DEFAULT route -- every job at or under
            # FAST_PATH_MAX_MOLECULES -- and write_chunk, bump_job_done and
            # _close_job are all unguarded inside translate_job_inline, so a
            # raise in any of them used to strand the job at "running" until
            # the 24h TTL turned it into a 404 and permanently burn one of
            # that IP's two concurrent slots. The batch path recovered from
            # exactly that failure; the more-travelled path did not.
            translate_job_inline.apply_async(
                args=[job_id, prepared, best_effort],
                queue="fast",
                link_error=mark_job_failed.s(job_id),
            )
        else:
            dispatch_batch(job_id, prepared, best_effort, settings.BATCH_CHUNK_SIZE)
    except Exception:
        # A dispatch failure after a successful admission (a broker
        # hiccup, say) must not leave a registered slot behind forever:
        # its meta says "queued" -- non-terminal -- so self-healing would
        # never prune it, and nothing else ever will either (round 2
        # review, Also-fix).
        release_job(ip, job_id)
        redis_store.get_redis().delete(redis_store.job_meta_key(job_id))
        raise
    return job_id


@router.post("/api/parse-preview", response_model=ParsePreviewResponse)
async def parse_preview(
    request: Request, file: UploadFile | None = File(default=None)
) -> ParsePreviewResponse:
    """Round 3 review, finding 1 (the priority): this used to RDKit-parse
    the WHOLE upload just to show 5 rows and a count. Measured: a 7.07 MB
    body of 10,000 large molecules cost 45.9 s of GIL-held RDKit here, with
    no job quota consumed at all (this endpoint never creates a job) --
    ~2,750 s of that per minute per IP at the default rate cap. It needs
    exactly PREVIEW_SAMPLE records parsed plus a total count, and the count
    does not need RDKit at all: app.inputs.count_molecules is a STRUCTURAL
    count (line count for a SMILES list or CSV, `$$$$` occurrences for an
    SDF), so `molecule_count` stays honest without paying for a full parse.
    """
    check_fast_allowed(client_ip(request))
    data, _ = await _read_input(request, file)
    fmt = sniff(data)
    try:
        sample_molecules, total = parse_preview_sample(data, fmt, PREVIEW_SAMPLE)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not read this {fmt.value}: {exc}"
        ) from exc
    if not sample_molecules and total == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No molecules found in this {fmt.value} input",
        )
    sample = [
        ParsePreviewRow(
            index=m.index,
            input=m.raw_input,
            input_id=m.input_id,
            smiles=m.smiles,
            error=m.error,
        )
        for m in sample_molecules
    ]
    # Only the sample is ever parsed now, so an error further into the file
    # than PREVIEW_SAMPLE records is no longer visible here -- previewing
    # is genuinely "the first few, plus a count," not a full validation
    # pass. /api/jobs still does the full parse and reports every error.
    errors = [m.error for m in sample_molecules if m.error]
    return ParsePreviewResponse(
        format=fmt.value,
        molecule_count=total,
        sample=sample,
        errors=errors,
    )


@router.post("/api/jobs", response_model=JobEnvelope)
async def create_job(
    request: Request,
    file: UploadFile | None = File(default=None),
    best_effort: bool = Form(default=True),
) -> JobEnvelope:
    settings = get_settings()
    ip = client_ip(request)
    # check_fast_allowed BEFORE require_a_live_jvm (round 5 review, finding
    # 1): moving require_a_live_jvm ahead of check_job_allowed (below) left
    # it as the only gate reachable before EITHER limiter during a JVM
    # outage, so a caller could hit it an unbounded number of times per
    # second -- cheap (one Redis HGETALL, ~0.165 ms) but no longer capped
    # at all. /api/translate already gates the same way (check_fast_allowed
    # first, then require_a_live_jvm), so this matches that shape. Two
    # different limiters now guard this one endpoint deliberately, not
    # redundantly: check_fast_allowed (60/min) bounds the rate of ANY call
    # here, including ones we are about to refuse for our own reasons
    # (a JVM outage is not the caller's fault, so it must not cost them an
    # hourly job-quota unit -- see check_job_allowed below); check_job_allowed
    # (hourly) is the actual job-submission budget, charged only once a
    # request has passed the JVM check and is genuinely trying to submit
    # a batch.
    check_fast_allowed(ip)
    # require_a_live_jvm BEFORE check_job_allowed (round 4 review, finding
    # 2): check_job_allowed increments the hourly counter unconditionally,
    # so a caller during a JVM outage would otherwise burn one of their 20
    # hourly units on every retry before ever reaching the 503 -- and
    # since /api/translate already gated on the JVM first, the SAME outage
    # cost /api/translate callers nothing while it locked /api/jobs callers
    # out of batch submission for up to an hour after service recovered.
    # This produces the artefact users keep (results.csv), same as any
    # single-molecule naming endpoint -- it was the one naming path that
    # never checked this at all (round 2 review, Also-fix). It is also
    # cheap now (one HGETALL, round 3 review, finding 3), so checking it
    # first costs nothing extra: a request we are going to refuse for our
    # OWN reasons should not cost the caller quota.
    require_a_live_jvm()
    # Before reading or parsing anything: a 429'd caller should not have
    # already made the server read up to 50 MB and RDKit-parse up to
    # 10,000 molecules first (round 1 review, Important; round 3 review,
    # finding 1: an earlier version of this called a concurrent-cap-only
    # pre-check here and left the hourly cap to admit_and_dispatch, AFTER
    # the parse below -- measured at 46 s of RDKit work before a 429).
    # check_job_allowed is the full, authoritative concurrent+hourly
    # admission gate; admit_and_dispatch only does the atomic
    # TOCTOU-safe registration now, since this already ran.
    check_job_allowed(ip)

    data, best_effort = await _read_input(request, file, best_effort)
    fmt, molecules = _parse_or_400(data, settings.MAX_BATCH_SIZE)

    job_id = admit_and_dispatch(ip, molecules, fmt.value, best_effort)
    return JobEnvelope(
        job_id=job_id, molecule_count=len(molecules), status="queued"
    )


def _meta_or_error(job_id: str) -> dict[str, str]:
    meta = redis_store.read_job_meta(job_id)
    if meta is not None:
        return meta
    # No meta. If rows survive, the meta key aged out: the job existed and
    # is gone, which is 410, not 404. This is why there is no "expired"
    # status value -- there is nothing left to report a status from.
    if redis_store.get_redis().exists(redis_store.job_rows_key(job_id)):
        raise HTTPException(status_code=410, detail="This job has expired")
    raise HTTPException(status_code=404, detail="No such job")


def _require_complete_meta(job_id: str) -> dict[str, str]:
    """A meta hash with every field, or 410.

    A partial hash is reachable: any writer that HSETs a single field into an
    evicted key recreates it carrying only that field. Indexing it directly
    would raise KeyError and answer 500 where the design promises 410, so a
    hash missing its `total` is treated as gone rather than trusted.
    """
    meta = _meta_or_error(job_id)
    required = ("status", "total", "done", "failed", "created", "expires")
    if not all(field in meta for field in required):
        raise HTTPException(
            status_code=410,
            detail="This job's record is incomplete or has expired",
        )
    return meta


def _actual_status(job_id: str, meta: dict[str, str]) -> str:
    """The rule tasks._close_job already enforces at WRITE time (an
    assembled row count short of `total` means the job failed, never
    "done"), applied again here at READ time.

    stitch:job:{id}:rows (redis_store.job_rows_key) is TTL'd, and
    docker-compose.yml runs `--maxmemory-policy volatile-lru`, which makes
    every TTL'd key an eviction candidate at any moment regardless of its
    remaining TTL -- so a job can close honestly as "done" and still have
    its rows key evicted minutes later. Without this, job_status and
    job_results_csv would go on reporting "done" over what is by then an
    empty result list: a header-only CSV byte-indistinguishable from a
    complete zero-row download, which is exactly the artefact the 409
    running-job gate below exists to prevent (final review report, C4).

    ONE function, called from both read endpoints, so the rule cannot
    drift between them the way it drifted between _close_job and these two
    in the first place.
    """
    status = meta["status"]
    if status == "done" and redis_store.rows_length(job_id) < int(meta["total"]):
        return "failed"
    return status


@router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(request: Request, job_id: str) -> JobStatusResponse:
    # Polling is the intended usage pattern (round 3 review, finding 4):
    # its own, larger budget, not check_fast_allowed's -- see
    # check_poll_allowed's docstring.
    check_poll_allowed(client_ip(request))
    meta = _require_complete_meta(job_id)
    status = _actual_status(job_id, meta)
    response = JobStatusResponse(
        job_id=job_id,
        status=status,
        total=int(meta["total"]),
        done=int(meta["done"]),
        failed=int(meta["failed"]),
        created_at=int(meta["created"]),
        expires_at=int(meta["expires"]),
    )
    if status in ("done", "failed"):
        # Release the slot once the job is finished, so a user is not held
        # to their concurrent-job cap by work that has already completed.
        release_job(meta.get("ip", "unknown"), job_id)
    return response


@router.get("/api/jobs/{job_id}/results", response_model=JobResultsResponse)
def job_results(
    request: Request,
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JobResultsResponse:
    check_poll_allowed(client_ip(request))
    meta = _require_complete_meta(job_id)
    rows = redis_store.read_rows(job_id, offset, limit)
    return JobResultsResponse(
        job_id=job_id,
        offset=offset,
        limit=limit,
        total=int(meta["total"]),
        # What a caller can actually page through. On a failed job this is
        # SHORT of `total`, and a client paginating to `total` would
        # otherwise never terminate on row count alone.
        retrievable=redis_store.rows_length(job_id),
        rows=[BatchRow.model_validate(r) for r in rows],
    )


# Excel and Sheets treat a cell opening with any of these as a formula, and
# `input` and `error` are verbatim user text. A pasted line starting "=cmd|..."
# would become live on open. Prefixing with an apostrophe is the standard
# mitigation and survives a round trip as data.
_FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    if isinstance(value, str) and value.startswith(_FORMULA_LEADERS):
        return "'" + value
    return value


@router.get("/api/jobs/{job_id}/results.csv")
def job_results_csv(request: Request, job_id: str) -> StreamingResponse:
    """The finished job as CSV. Only for a job that has actually finished.

    A mid-run download would hand back a header-only or half-length file
    that is byte-indistinguishable from a complete one, and this is the
    artefact users keep -- so a job still queued or running is refused
    rather than served short. A `failed` job IS served, because its partial
    rows are real results, but the status header and the filename say so.

    The same is true of a "done" job whose rows key was evicted after the
    fact (see _actual_status): its rows are gone the same way a genuinely
    failed job's are short, so it is served through the SAME -partial /
    X-STITCH-Job-Status machinery rather than refused outright (final
    review report, C4).
    """
    check_download_allowed(client_ip(request))
    meta = _require_complete_meta(job_id)
    status = _actual_status(job_id, meta)
    if status not in ("done", "failed"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"This job is {status}; its results are not complete yet. "
                "Poll the job until it reports done."
            ),
        )
    suffix = "-partial" if status == "failed" else ""

    def generate():
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        yield buffer.getvalue()
        # Stream page by page: a 10,000-row job is never held in memory.
        for row in redis_store.iter_all_rows(job_id):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow({k: _csv_safe(v) for k, v in row.items()})
            yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="stitch-{job_id}{suffix}.csv"'
            ),
            "X-STITCH-Job-Status": status,
        },
    )


@router.delete("/api/jobs/{job_id}")
def delete_job(request: Request, job_id: str) -> dict[str, str]:
    # No ownership check exists (or can, without accounts -- see
    # ratelimit.py's module docstring): a job id appearing in a shared
    # results.csv URL lets anyone holding it delete that job. A rate limit
    # is the one thing available short of accounts (round 2 review,
    # finding 2).
    check_fast_allowed(client_ip(request))
    meta = _meta_or_error(job_id)
    status = meta.get("status")
    if status not in ("done", "failed"):
        # Refuse outright, rather than deleting everything but skipping
        # just the slot release: this job's chunks are still running (or
        # queued) somewhere and keep consuming OPSIN regardless of this
        # call -- Celery task ids are not tracked anywhere a delete could
        # revoke them from -- and deleting the meta hash while leaving the
        # slot registered does not actually protect the cap either, since
        # check_and_register_job's self-heal treats a MISSING meta exactly
        # like a finished one and frees the slot on the very next
        # admission regardless (round 2 review, finding 2, measured: a
        # submit-then-delete loop against a cap of 2 admitted 10 jobs in a
        # row, all already dispatched, this way). Refusing the whole
        # delete until the job reaches a terminal state is what actually
        # closes the loop.
        raise HTTPException(
            status_code=409,
            detail=(
                f"This job is {status}; wait for it to finish (or fail) "
                "before deleting it."
            ),
        )
    release_job(meta.get("ip", "unknown"), job_id)

    # Explicit keys, never a glob built from a path parameter. Job ids are
    # server-generated uuid4 hex today, but scan_iter(match=f"...{job_id}*")
    # is one oddly-named id away from deleting other jobs, and the trailing
    # star also matches longer ids that merely share a prefix.
    client = redis_store.get_redis()
    total = int(meta.get("total", 0)) or 1
    chunk_size = get_settings().BATCH_CHUNK_SIZE
    n_chunks = -(-total // chunk_size)  # ceil, so every chunk key is covered
    client.delete(
        redis_store.job_meta_key(job_id),
        redis_store.job_rows_key(job_id),
        *(redis_store.job_chunk_key(job_id, i) for i in range(n_chunks)),
    )
    return {"job_id": job_id, "status": "deleted"}


# A real SMILES for anything this UI depicts is far shorter. The bound
# matters because MolFromSmiles (ring perception) and the draw call
# (2D coordinate generation) run synchronously in the WEB process, RDKit's
# Boost.Python wrappers do not release the GIL, and this endpoint has no
# time limit -- so one pathological input would stall every request.
MAX_DEPICT_SMILES = 4000

# check_depict_allowed's 1,200/minute is a request-COUNT budget; it is not
# a cost bound, because per-call cost is not uniform. Measured (round 2
# review, finding 3), all within MAX_DEPICT_SMILES: ethanol draws in
# 0.2 ms; a ~2,400-heavy-atom fused system draws in 16,724 ms (parsing
# alone is only 5-80 ms even at that size -- essentially ALL of the cost is
# 2D coordinate generation); a 4,000-carbon chain and a large fused
# cyclopropane system each ran past 25 s and had to be killed. At
# 1,200/minute one IP is otherwise authorised to request roughly 20
# calls/second of multi-second, GIL-holding work. A few hundred heavy
# atoms comfortably covers every molecule this UI actually shows (caffeine
# is 14; the natural products and drug-like structures the demo depicts
# are well under 100) -- nothing legitimate needs more, so this is checked
# right after parsing, before the expensive draw call.
MAX_DEPICT_ATOMS = 300


@router.get("/api/depict", response_model=DepictResponse)
def depict(
    request: Request,
    smiles: str = Query(..., min_length=1, max_length=MAX_DEPICT_SMILES),
    response: Response = None,  # noqa: B008 - FastAPI injects this
) -> DepictResponse:
    """One molecule's 2D structure. Pure RDKit: no JVM, no worker, no queue.

    This is what lets a batch results table draw a row on demand, since
    batch rows deliberately carry no depiction. That also means a 1,000-row
    table makes 1,000 calls here, so the response is cacheable: the same
    SMILES always renders the same picture, and the renderer is
    deterministic. check_depict_allowed, not check_fast_allowed: this
    endpoint's own legitimate traffic pattern (one call per visible row) is
    exactly what check_fast_allowed's 60/minute budget would mistake for
    abuse. That budget bounds request COUNT, not per-call cost -- see
    MAX_DEPICT_ATOMS above for the latter.
    """
    check_depict_allowed(client_ip(request))
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return DepictResponse(
            depiction_svg=None, error="Could not parse this SMILES string"
        )
    if mol.GetNumAtoms() > MAX_DEPICT_ATOMS:
        # 200-with-error, not a 400 (round 3 review, finding 5): a per-row
        # caller in a results table had to handle two different shapes for
        # "cannot draw this" depending on WHY. One shape lets a row show
        # the reason inline the same way an unparseable SMILES already
        # does, instead of branching on status code first.
        return DepictResponse(
            depiction_svg=None,
            error=(
                f"Too many atoms to depict ({mol.GetNumAtoms()} > "
                f"{MAX_DEPICT_ATOMS})"
            ),
        )
    if response is not None:
        response.headers["Cache-Control"] = "public, max-age=86400"
    return DepictResponse(depiction_svg=mol_to_svg_data_uri(mol), error=None)
