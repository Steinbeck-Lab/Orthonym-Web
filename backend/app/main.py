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

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from orthonym.validation.opsin_roundtrip import opsin_parse
from rdkit import Chem

from . import opsin_decompose
from .jobs_api import router as jobs_router
from .depiction import mol_to_svg_data_uri
from .explain import explain_molecule, explain_name
from .orthonym_service import get_primary_namer, translate_many
from .schemas import (
    ExamplesResponse,
    ExplainResponse,
    HealthResponse,
    IupacToSmilesResponse,
    TranslateRequest,
    TranslateResponse,
)

MAX_SMILES_PER_REQUEST = 50

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
        # NOTE: an earlier version of this example used
        # "CC(C)(C)C1=CC2=C(C=C1)C1(C)CCC(C)(C)C2(C)C1", which DID abstain
        # under the single-namer design. Under the three-tier escalation
        # added for T5-abstain handling (see orthonym_service.py), that
        # molecule's primary-pass abstain now escalates to a verified T3
        # "fallback" name -- exactly the intended behavior, but it means
        # that SMILES is no longer an honest-abstain example. This
        # spiro-fused system was verified live to still abstain on BOTH
        # the primary and the escalated namer.
        "label": "A spiro-fused ring system — honest abstain",
        "smiles": "CC1(C)CCC(C)(C)C12c1ccccc1C1(CCCC1)C2",
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


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="OK")


@app.get("/api/examples", response_model=ExamplesResponse)
def examples() -> ExamplesResponse:
    return ExamplesResponse(examples=EXAMPLES)


@app.post("/api/translate", response_model=TranslateResponse)
def translate(request: TranslateRequest) -> TranslateResponse:
    non_blank = [s for s in request.smiles if s.strip()]
    batch = non_blank[:MAX_SMILES_PER_REQUEST]
    results = translate_many(batch, best_effort=request.best_effort)
    return TranslateResponse(results=results)


@app.get("/api/iupac-to-smiles", response_model=IupacToSmilesResponse)
def iupac_to_smiles(name: str = Query(..., min_length=1)) -> IupacToSmilesResponse:
    raw_smiles = opsin_parse(name)
    if not raw_smiles:
        return IupacToSmilesResponse(
            smiles=None,
            depiction_svg=None,
            error="Could not parse this name via OPSIN",
        )

    mol = Chem.MolFromSmiles(raw_smiles)
    if mol is None:
        return IupacToSmilesResponse(
            smiles=None,
            depiction_svg=None,
            error="Could not parse this name via OPSIN",
        )

    return IupacToSmilesResponse(
        smiles=raw_smiles,
        depiction_svg=mol_to_svg_data_uri(mol),
        error=None,
    )


@app.get("/api/explain", response_model=ExplainResponse)
def explain(smiles: str = Query(..., min_length=1)) -> ExplainResponse:
    result = explain_molecule(smiles, namer=get_primary_namer())
    return ExplainResponse(**result)


@app.get("/api/explain-name", response_model=ExplainResponse)
def explain_by_name(name: str = Query(..., min_length=1)) -> ExplainResponse:
    return ExplainResponse(**explain_name(name))
