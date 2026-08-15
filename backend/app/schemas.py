"""Pydantic request/response models for the STITCH API.

Field names and shapes are fixed by the STITCH API contract — do not
rename or restructure these without updating the contract and the
frontend that depends on it.
"""

from typing import Literal, Optional

from pydantic import BaseModel


Status = Literal["pin", "fallback", "best_effort", "abstain", "error"]
Tier = Literal["T1", "T3", "T4", "T5"]
ExpectedStatus = Literal["pin", "fallback", "abstain"]


class TranslateRequest(BaseModel):
    smiles: list[str]


class ResultItem(BaseModel):
    smiles: str
    status: Status
    name: Optional[str] = None
    tier: Optional[Tier] = None
    formula: Optional[str] = None
    limit_code: Optional[str] = None
    error: Optional[str] = None
    # Populated for status in (pin, fallback, best_effort); null for
    # abstain/error. See app/depiction.py.
    depiction_svg: Optional[str] = None
    # Visible OPSIN round-trip proof (independent of OpenSTOUT's own
    # internal SELF-01 gate -- uses OpenSTOUT's own opsin_parse(), the same
    # vendored jar/JVM as SELF-01). Populated for status in (pin, fallback,
    # best_effort); null for abstain/error.
    roundtrip_smiles: Optional[str] = None
    roundtrip_match: Optional[bool] = None


class TranslateResponse(BaseModel):
    results: list[ResultItem]


class HealthResponse(BaseModel):
    status: str


class ExampleItem(BaseModel):
    label: str
    smiles: str
    expected_status: ExpectedStatus


class ExamplesResponse(BaseModel):
    examples: list[ExampleItem]


class IupacToSmilesResponse(BaseModel):
    smiles: Optional[str] = None
    depiction_svg: Optional[str] = None
    error: Optional[str] = None


SegmentKind = Literal["suffix", "substituent", "rest", "undecomposed"]


class ExplainSegment(BaseModel):
    label: str
    kind: SegmentKind
    explanation: str
    # RDKit atom indices for this segment, valid against `svg`'s atom-N /
    # bond-N CSS classes (same Mol object used for both). Always non-empty
    # when present -- a segment with nothing to highlight is not emitted.
    atom_indices: list[int]
    # [start, end) character offsets into ExplainResponse.name this segment
    # corresponds to, for pairing the highlighted structure with the exact
    # substring of the name that names it. Null when that pairing couldn't
    # be established as safely as the structural match itself -- the
    # structure highlight is never withheld just because this is.
    name_range: Optional[list[int]] = None


class ExplainResponse(BaseModel):
    smiles: str
    name: Optional[str] = None
    # Raw inline SVG markup (NOT a data: URI) -- meant to be inlined
    # directly into the page DOM so the frontend can style individual
    # atom-N/bond-N elements on hover. Null when name/svg could not be
    # produced (see `error`).
    svg: Optional[str] = None
    total_atoms: int = 0
    segments: list[ExplainSegment] = []
    error: Optional[str] = None
