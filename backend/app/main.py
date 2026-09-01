"""Orthonym backend: FastAPI app exposing the Orthonym naming engine.

Endpoints (see Orthonym API contract):
  POST /api/translate
  GET  /api/health
  GET  /api/examples
  GET  /api/iupac-to-smiles
  GET  /api/explain
  GET  /api/explain-name
"""

import logging

from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import redis_store
from .core.config import get_settings
from .inputs import InputFormat
from .inputs import parse as parse_molecules
from .jobs_api import admit_and_dispatch, prepared_payload
from .jobs_api import router as jobs_router
from .jvm_guard import require_a_live_jvm
from .ratelimit import check_fast_allowed, check_job_allowed, client_ip
from .schemas import (
    ExamplesResponse,
    ExplainResponse,
    HealthResponse,
    IupacToSmilesResponse,
    JobEnvelope,
    ResultItem,
    TranslateRequest,
    TranslateResponse,
)
from .tasks import explain_iupac_name, explain_smiles, name_to_smiles, translate_fast

# Verified live against the real Orthonym engine -- do not invent
# different examples.
EXAMPLES = [
    {
        "label": "Ethanol — a confirmed PIN",
        "smiles": "CCO",
        "expected_status": "pin",
    },
    {
        "label": "(2S)-butan-2-ol — stereochemistry, still a PIN",
        "smiles": "C[C@H](O)CC",
        "expected_status": "pin",
    },
    {
        "label": "A fused polycyclic — real name, not a verified PIN",
        "smiles": "C1CC2CCC1(CC2)C3CCC4(CCC5(CCCC5C4C3)C)C",
        "expected_status": "fallback",
    },
    {
        # This example has been replaced twice, both times because Orthonym
        # got BETTER and started naming the molecule that used to abstain:
        #   1. "CC(C)(C)C1=CC2=C(C=C1)C1(C)CCC(C)(C)C2(C)C1" -- began
        #      escalating to a verified fallback.
        #   2. "CC1(C)CCC(C)(C)C12c1ccccc1C1(CCCC1)C2" (spiro-fused) -- named
        #      as 2,2,5,5-tetra(methan-1-yl)dispiro[...] after the 2026-08-31
        #      vendor refresh.
        # So an ORGANIC honest-abstain example is a moving target. Uranium
        # trioxide is stable in that role for a structural reason rather than
        # a coverage gap: Orthonym targets organic nomenclature, and it
        # refuses here instead of guessing. Verified live to abstain on BOTH
        # the primary and the escalated namer.
        "label": "Uranium trioxide — outside organic nomenclature, honest abstain",
        "smiles": "O=[U](=O)=O",
        "expected_status": "abstain",
    },
]

# Nothing else in this app configures logging, so without this, plain
# logger.info()/logger.exception() calls anywhere in the process are
# silently dropped -- Python's logging module only falls back to a stderr
# "lastResort" handler at WARNING+ when no handler is configured anywhere
# in the hierarchy. Explicit INFO-level config is what actually makes
# "fails loudly, not silently" true. This process no longer runs any
# OPSIN startup check of its own (OPSIN only lives in Celery workers now,
# via celery_app._start_child_jvm) -- this still matters for eager-mode
# test runs, which execute task bodies (and their logger calls) inline in
# this same process.
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI(title="Orthonym backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _limit_translate_body_size(request: Request, call_next):
    """/api/translate has no body-size limit otherwise: MAX_BATCH_SIZE only
    bounds the molecule COUNT, checked after FastAPI has already read and
    JSON-parsed the whole body into TranslateRequest -- a single 100 MB
    SMILES string was accepted (round 1 review, Important). This mirrors
    _read_input's declared-Content-Length guard for file uploads, and
    inherits the same caveat: Content-Length is client-supplied and may be
    absent under chunked transfer, or a lie -- an honest common case, not a
    hard guarantee, exactly the tradeoff already accepted there.

    A middleware, not a check inside translate() itself, because FastAPI
    parses `body: TranslateRequest` before the route handler runs at all --
    by the time our own code could inspect anything, the oversized body has
    already been buffered and parsed.
    """
    if request.url.path == "/api/translate":
        settings = get_settings()
        declared = request.headers.get("content-length")
        if declared and declared.isdigit():
            if int(declared) > settings.max_file_size_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "Body is larger than the "
                            f"{settings.MAX_FILE_SIZE_MB} MB limit"
                        )
                    },
                )
    return await call_next(request)


app.include_router(jobs_router)


def _timeout_504(settings) -> HTTPException:
    """For the three endpoints with no job store behind them: a JobEnvelope
    here would be a lie (round 1 review, Critical 4, a deliberate departure
    from the brief's "return a union" wording for these three -- recorded
    here, not silently decided).
    """
    return HTTPException(
        status_code=504,
        detail=(
            f"This request exceeded the {settings.FAST_PATH_TIMEOUT}s "
            "limit and there is no job to poll for it here. Please retry."
        ),
    )


def _canonicalize(smiles_list: list[str], max_molecules: int):
    """Route /api/translate's job-dispatch branches through the same
    canonicalization and per-row error handling as every other input path
    (app.inputs.parse), rather than hand-building ParsedMolecule(smiles=s)
    from the raw string. The bypass gave the same molecule two different
    cache entries (canonical vs. as-typed) and different error text
    depending on which endpoint submitted it (round 1 review, Important).
    """
    data = "\n".join(smiles_list).encode("utf-8")
    return parse_molecules(data, InputFormat.SMILES_LIST, max_molecules)


# /api/health and /api/examples below are the ONLY two endpoints with no rate
# limiter, and that is deliberate rather than an oversight (audit item NB-6).
# Both are a single Redis read or a constant, they take no user input, and a
# health check that can 429 is worse than useless to the thing monitoring it.
# Every endpoint that costs anything -- naming, jobs, polling, depiction,
# download -- is limited; see app/ratelimit.py.
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Typed rather than a bare dict (round 1 review, Important: this had
    # drifted into dead code -- HealthResponse existed in schemas.py but
    # was unused). Chose to update the model over deleting it: schemas.py
    # is where every other response shape lives, and an OpenAPI consumer
    # should see the "opsin" field documented like any other.
    opsin_ok = redis_store.any_worker_has_opsin()
    return HealthResponse(
        status="OK" if opsin_ok else "DEGRADED",
        opsin="available" if opsin_ok else "no worker has a live JVM",
    )


@app.get("/api/examples", response_model=ExamplesResponse)
def examples() -> ExamplesResponse:
    return ExamplesResponse(examples=EXAMPLES)


@app.post("/api/translate", response_model=TranslateResponse | JobEnvelope)
def translate(request: Request, body: TranslateRequest):
    settings = get_settings()
    ip = client_ip(request)
    # Before the blank-list short-circuit below, not after (round 2
    # review, finding 4): a request with an all-blank `smiles` list used to
    # return before this ran at all, making /api/translate an unlimited-
    # rate endpoint for anyone who padded the body with whitespace instead
    # of real SMILES. The 200-with-empty-results CONTRACT is unchanged --
    # only its place relative to the rate limit moved.
    check_fast_allowed(ip)

    non_blank = [s for s in body.smiles if s.strip()]
    if not non_blank:
        # Restored (round 1 review, Important): this used to be, and
        # frontend/src/lib/api.js still assumes it is, a normal 200 with no
        # results, not a 400. An empty submission does no naming work at
        # all, so it still skips the live-JVM gate below.
        return TranslateResponse(results=[])

    require_a_live_jvm()

    if len(non_blank) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Input exceeds the {settings.MAX_BATCH_SIZE}-molecule limit",
        )

    # Above the fast limit this is a job, not a request: hand back an
    # envelope and let the caller poll. Nothing is silently truncated any
    # more -- the old MAX_SMILES_PER_REQUEST dropped molecule 51 in silence.
    if len(non_blank) > settings.FAST_PATH_MAX_MOLECULES:
        # Before _canonicalize, not after (round 3 review, finding 1,
        # measured: a caller over cap paid the full RDKit canonicalization
        # cost -- 48.1 s in the reviewer's measurement -- regardless of
        # whether they were admitted or 429'd, since the job-cap check
        # used to live inside admit_and_dispatch, strictly after this).
        check_job_allowed(ip)
        molecules = _canonicalize(non_blank, settings.MAX_BATCH_SIZE)
        job_id, owner_token = admit_and_dispatch(
            ip, molecules, "smiles_list", body.best_effort
        )
        return JobEnvelope(
            job_id=job_id,
            molecule_count=len(molecules),
            status="queued",
            owner_token=owner_token,
        )

    # Crash-loop fix (final review): this branch used to hand raw,
    # unbounded user text straight to translate_fast -> translate_one ->
    # Chem.MolFromSmiles/MolToSmiles with no length check at all, unlike
    # the two job-dispatch branches above, which already route through
    # _canonicalize. Chem.MolToSmiles SIGSEGVs RDKit's C++ stack at
    # roughly 30,000 atoms (measured: clean at 20k, crash at 30k and
    # 50k) -- and because task_acks_late=True and
    # task_reject_on_worker_lost=True (celery_app.py), a SIGKILLed task
    # is REQUEUED, so one oversized SMILES could crash-loop the fast
    # queue forever. Canonicalizing here applies
    # MAX_MOLECULE_SMILES_LENGTH (app.inputs) before any RDKit call, on
    # every molecule, on every path -- closing this and, as a side
    # effect, deferred item I3(c) (the fast path previously had no
    # per-record length bound at all).
    molecules = _canonicalize(non_blank, settings.MAX_BATCH_SIZE)
    prepared = prepared_payload(molecules)
    try:
        async_result = translate_fast.apply_async(
            args=[prepared, body.best_effort], queue="fast"
        )
        results = async_result.get(timeout=settings.FAST_PATH_TIMEOUT)
    except CeleryTimeoutError:
        # translate_fast itself is NOT revoked -- the caller polls the job
        # below instead (round 1 review, Critical 4). Its eventual result,
        # if it ever finishes, is simply discarded once nothing is waiting
        # on it any more; this is the accepted "abandoned tasks are not
        # revoked" tradeoff, applied here rather than left unhandled.
        # `molecules` is already canonicalized above -- no need to pay for
        # it twice.
        check_job_allowed(ip)
        job_id, owner_token = admit_and_dispatch(
            ip, molecules, "smiles_list", body.best_effort
        )
        return JobEnvelope(
            job_id=job_id,
            molecule_count=len(molecules),
            status="queued",
            owner_token=owner_token,
        )
    # Forget the backend entry. Celery's redis backend SETEXs every result for
    # JOB_RESULT_TTL_SECONDS (24 h) and .get() never removes it -- and
    # translate_fast's results are full ResultItems, depiction_svg included.
    # Measured data-URI sizes are 11.6 KB (aspirin) to 46.4 KB (a taxane), so
    # leaving them there quietly reinstates most of the 7-day cache bloat that
    # excluding the picture from name_cache was meant to remove. Nobody reads a
    # fast-path result twice: the caller is holding it.
    try:
        async_result.forget()
    except Exception:  # noqa: BLE001 - cleanup must not fail a served request
        logger.debug("Could not forget fast-path result", exc_info=True)
    return TranslateResponse(results=[ResultItem.model_validate(r) for r in results])


@app.get("/api/iupac-to-smiles", response_model=IupacToSmilesResponse)
def iupac_to_smiles(
    request: Request, name: str = Query(..., min_length=1)
) -> IupacToSmilesResponse:
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    require_a_live_jvm()

    try:
        result = name_to_smiles.apply_async(
            args=[name], queue="fast"
        ).get(timeout=settings.FAST_PATH_TIMEOUT)
    except CeleryTimeoutError as exc:
        raise _timeout_504(settings) from exc
    return IupacToSmilesResponse(**result)


@app.get("/api/explain", response_model=ExplainResponse)
def explain(
    request: Request, smiles: str = Query(..., min_length=1)
) -> ExplainResponse:
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    require_a_live_jvm()

    try:
        result = explain_smiles.apply_async(
            args=[smiles], queue="fast"
        ).get(timeout=settings.FAST_PATH_TIMEOUT)
    except CeleryTimeoutError as exc:
        raise _timeout_504(settings) from exc
    return ExplainResponse(**result)


@app.get("/api/explain-name", response_model=ExplainResponse)
def explain_by_name(
    request: Request, name: str = Query(..., min_length=1)
) -> ExplainResponse:
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    require_a_live_jvm()

    try:
        result = explain_iupac_name.apply_async(
            args=[name], queue="fast"
        ).get(timeout=settings.FAST_PATH_TIMEOUT)
    except CeleryTimeoutError as exc:
        raise _timeout_504(settings) from exc
    return ExplainResponse(**result)
