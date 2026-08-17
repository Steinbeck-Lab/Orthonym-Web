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


SegmentKind = Literal[
    "substituent", "parent", "suffix", "modifier", "stereo", "unmapped"
]


class ExplainSegment(BaseModel):
    label: str
    kind: SegmentKind
    # Owning parts (substituent/parent/suffix) hold a disjoint slice of the
    # molecule's heavy atoms; together they cover it. Referential parts
    # (modifier/stereo) own nothing -- "3,7-dihydro-1H-" adds no atoms, it
    # only records where hydrogens sit on atoms the parent already owns.
    # Conflating the two breaks the partition invariant, so it is explicit.
    owns_atoms: bool = True
    # The single locant this segment corresponds to, for child segments
    # ("7" -> N7). None for a top-level part.
    locant: Optional[str] = None
    explanation: str
    # Atoms this segment OWNS. Empty when owns_atoms is False.
    atom_indices: list[int] = []
    # Atoms to light up on hover. May overlap other segments -- a suffix
    # owns only its oxygen but highlights the whole C=O so it reads right.
    highlight_atoms: list[int] = []
    # [start, end) character offsets into ExplainResponse.name.
    name_range: Optional[list[int]] = None
    children: list["ExplainSegment"] = []


ExplainSegment.model_rebuild()


class ExplainResponse(BaseModel):
    smiles: str
    name: Optional[str] = None
    # Raw inline SVG markup (NOT a data: URI) -- meant to be inlined
    # directly into the page DOM so the frontend can style individual
    # atom-N/bond-N elements on hover. Null when name/svg could not be
    # produced (see `error`).
    svg: Optional[str] = None
    # Pixel coordinates of every heavy atom within `svg`'s own viewBox,
    # indexed by atom index. Produced by the SAME MolDraw2D instance that
    # rendered `svg`, so the two cannot drift. Empty when svg is None.
    atom_points: list[list[float]] = []
    total_atoms: int = 0
    segments: list[ExplainSegment] = []
    error: Optional[str] = None
