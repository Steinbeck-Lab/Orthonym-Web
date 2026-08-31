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
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import opsin_decompose, redis_store
from .core.config import get_settings
from .jobs_api import router as jobs_router
from .ratelimit import check_fast_allowed, client_ip
from .schemas import (
    ExamplesResponse,
    ExplainResponse,
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
# logger.info()/logger.exception() calls (e.g. opsin_decompose's startup
# and failure diagnostics) are silently dropped -- Python's logging module
# only falls back to a stderr "lastResort" handler at WARNING+ when no
# handler is configured anywhere in the hierarchy. Explicit INFO-level
# config is what actually makes "fails loudly, not silently" true.
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Orthonym backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.on_event("startup")
def _verify_opsin_internals() -> None:
    # opsin_decompose reflects into OPSIN's package-private internals to
    # get per-substituent atom highlighting on the Explain page (see that
    # module's docstring). It always degrades safely on its own if the API
    # shape has changed -- this just makes that check happen loudly at boot
    # instead of silently on whichever request first needs it.
    ok = opsin_decompose.self_check()
    logging.getLogger(__name__).info(
        "Explain name decomposition: %s",
        "available" if ok else "disabled (see preceding log for why)",
    )


def _require_a_live_jvm() -> None:
    """Orthonym's SELF-01 gate fails OPEN without a JVM, shipping a
    fallback labelled as a verified PIN. Serving names in that state would
    break PRODUCT.md principle 3, so we refuse instead.
    """
    if not redis_store.any_worker_has_opsin():
        raise HTTPException(
            status_code=503,
            detail=(
                "No worker currently has a live JVM, so OPSIN cannot verify "
                "any name. Refusing rather than serving names with an "
                "unverified confidence tier. See /api/health."
            ),
        )


@app.get("/api/health")
def health() -> dict[str, str]:
    opsin_ok = redis_store.any_worker_has_opsin()
    return {
        "status": "OK" if opsin_ok else "DEGRADED",
        "opsin": "available" if opsin_ok else "no worker has a live JVM",
    }


@app.get("/api/examples", response_model=ExamplesResponse)
def examples() -> ExamplesResponse:
    return ExamplesResponse(examples=EXAMPLES)


@app.post("/api/translate")
def translate(request: Request, body: TranslateRequest):
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    _require_a_live_jvm()

    non_blank = [s for s in body.smiles if s.strip()]
    if not non_blank:
        raise HTTPException(status_code=400, detail="No SMILES strings given")
    if len(non_blank) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Input exceeds the {settings.MAX_BATCH_SIZE}-molecule limit",
        )

    # Above the fast limit this is a job, not a request: hand back an
    # envelope and let the caller poll. Nothing is silently truncated any
    # more -- the old MAX_SMILES_PER_REQUEST dropped molecule 51 in silence.
    if len(non_blank) > settings.FAST_PATH_MAX_MOLECULES:
        from .jobs_api import prepared_payload
        from .inputs import ParsedMolecule
        from .tasks import dispatch_batch

        molecules = [
            ParsedMolecule(
                index=i, raw_input=s, input_id=None, smiles=s, error=None
            )
            for i, s in enumerate(non_blank)
        ]
        job_id = uuid.uuid4().hex
        redis_store.create_job(job_id, len(molecules), "smiles_list", ip)
        dispatch_batch(
            job_id, prepared_payload(molecules), body.best_effort, settings.BATCH_CHUNK_SIZE
        )
        return JobEnvelope(
            job_id=job_id, molecule_count=len(molecules), status="queued"
        )

    results = translate_fast.apply_async(
        args=[non_blank, body.best_effort], queue="fast"
    ).get(timeout=settings.FAST_PATH_TIMEOUT)
    return TranslateResponse(results=[ResultItem.model_validate(r) for r in results])


@app.get("/api/iupac-to-smiles", response_model=IupacToSmilesResponse)
def iupac_to_smiles(
    request: Request, name: str = Query(..., min_length=1)
) -> IupacToSmilesResponse:
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    _require_a_live_jvm()

    result = name_to_smiles.apply_async(
        args=[name], queue="fast"
    ).get(timeout=settings.FAST_PATH_TIMEOUT)
    return IupacToSmilesResponse(**result)


@app.get("/api/explain", response_model=ExplainResponse)
def explain(
    request: Request, smiles: str = Query(..., min_length=1)
) -> ExplainResponse:
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    _require_a_live_jvm()

    result = explain_smiles.apply_async(
        args=[smiles], queue="fast"
    ).get(timeout=settings.FAST_PATH_TIMEOUT)
    return ExplainResponse(**result)


@app.get("/api/explain-name", response_model=ExplainResponse)
def explain_by_name(
    request: Request, name: str = Query(..., min_length=1)
) -> ExplainResponse:
    settings = get_settings()
    ip = client_ip(request)
    check_fast_allowed(ip)
    _require_a_live_jvm()

    result = explain_iupac_name.apply_async(
        args=[name], queue="fast"
    ).get(timeout=settings.FAST_PATH_TIMEOUT)
    return ExplainResponse(**result)
