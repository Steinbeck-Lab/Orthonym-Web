"""Pydantic request/response models for the Orthonym API.

Field names and shapes are fixed by the Orthonym API contract — do not
rename or restructure these without updating the contract and the
frontend that depends on it.
"""

from typing import Literal, Optional

from pydantic import BaseModel


Status = Literal["pin", "fallback", "best_effort", "abstain", "error"]


# The two statuses that ASSERT an OPSIN round-trip actually happened.
#
# One definition, because it is one invariant: orthonym_service refuses to
# SERVE such a row without proof, and name_cache refuses to PERSIST one. Those
# were separate hand-copied sets, and adding a future verified tier to one and
# not the other reproduces exactly the C3 bug the pair exists to close, in
# whichever half was missed. schemas is the only module both already import.
#
# frontend/src/lib/statuses.js keeps its own copy -- it cannot import
# Python -- the same accepted cross-language mirror as NAMED_STATUSES there.
VERIFIED_STATUSES = frozenset({"pin", "fallback"})
# The Orthonym engine's own tier labels, from Orthonym.name_tiered's docstring. The
# earlier T1/T3/T4/T5 codes were replaced upstream by these names; there is
# no T-code anywhere in the engine any more. `pin_unverified` is a name in PIN
# form that only a breadth producer built; it round-trips, but its preferred
# status is not certified. name_tiered's docstring still calls it reserved,
# but the engine assigns it, and classify() maps it to "fallback" -- never to
# "pin". Every tier ships as the engine gave it (orthonym_service.py).
Tier = Literal[
    "pin_verified",
    "systematic_verified",
    "best_effort",
    "abstain",
    "pin_unverified",
]
ExpectedStatus = Literal["pin", "fallback", "abstain"]


class TranslateRequest(BaseModel):
    smiles: list[str]
    # Best-effort mode. True (the default, and the app's shipped behaviour)
    # lets a molecule the primary namer abstained on be retried against the
    # escalated namer, which may return a best-effort name from the general
    # engine (engine tier `best_effort`, surfaced as status "best_effort").
    # False stops after the primary pass, so such a molecule comes back as an
    # honest abstain instead. (The primary pass can still give tier
    # best_effort to some composer names; see orthonym_service.)
    best_effort: bool = True
    # OPSIN round-trip verification. True (the default, and the app's shipped
    # behaviour) parses every produced name back through OPSIN and compares
    # full InChIKeys, which is what earns a result the "pin" or "fallback"
    # status. False skips that check.
    #
    # Turning it off does NOT quietly relax the statuses -- it costs every name
    # its verified status, automatically, through the machinery that was
    # already there: with no round trip, `roundtrip_smiles` is None, and
    # orthonym_service's existing downgrade demotes any verified status to
    # "best_effort", keeping the engine's tier (or, with best_effort=False, to
    # an honest abstain). So the
    # switch cannot produce a name that CLAIMS more than was checked. That is
    # the point of exposing it at all: PRODUCT.md principle 1 says determinism
    # must be provable, and being able to turn the proof off and watch every
    # claim downgrade is a stronger demonstration than a paragraph saying so.
    verify: bool = True


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
    # Visible OPSIN round-trip proof (independent of the engine's own
    # internal SELF-01 gate -- uses the engine's own opsin_parse(), the same
    # vendored jar/JVM as SELF-01). Populated whenever that check ran on a
    # named row; null for abstain/error, and on a best_effort row demoted
    # because no round trip ran.
    roundtrip_smiles: Optional[str] = None
    roundtrip_match: Optional[bool] = None


class TranslateResponse(BaseModel):
    results: list[ResultItem]


class HealthResponse(BaseModel):
    status: str
    # Whether at least one Celery worker has reported a live JVM. See
    # app.redis_store.any_worker_has_opsin -- this is what "OK" versus
    # "DEGRADED" is actually reporting on, and what makes every naming
    # endpoint 503 rather than serving a name whose tier SELF-01 never checked.
    opsin: str


class ExampleItem(BaseModel):
    label: str
    smiles: str
    expected_status: ExpectedStatus


class ExamplesResponse(BaseModel):
    examples: list[ExampleItem]


class IupacToSmilesResponse(BaseModel):
    # OPSIN's own output, kept verbatim. NOT replaced by the canonical form:
    # the string a tool actually produced is information, and normalising it
    # away silently loses it. Same reasoning as commit 170174b's as-typed
    # decision on the naming direction.
    smiles: Optional[str] = None
    # RDKit's canonical form of the same molecule, so a caller can compare.
    canonical_smiles: Optional[str] = None
    # All four below are Optional and default to None because none of them is
    # total: RDKit's InChI writer declines some inputs, and 2D coordinate
    # generation can fail. A molecule that loses one identifier still returns
    # the others rather than becoming an error row.
    inchi: Optional[str] = None
    inchikey: Optional[str] = None
    # 2D V2000 molblock, the payload of the SDF download.
    molblock: Optional[str] = None
    depiction_svg: Optional[str] = None
    error: Optional[str] = None


SegmentKind = Literal[
    "substituent", "parent", "suffix", "modifier", "stereo", "unmapped", "token"
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


# "cancelled" is terminal like done/failed: redis_store.begin_chunk refuses to
# start another chunk for any of the three. There is still deliberately no
# "expired" -- an expired job's meta key is gone, so there is nothing left to
# report a status from (see section 10 of the design spec).
JobState = Literal["queued", "running", "done", "failed", "cancelled"]


class BatchRow(BaseModel):
    """One molecule's result inside a batch job.

    Deliberately NOT a ResultItem: no depiction_svg. At roughly 5 kB per
    row an SVG would make a 5,000-row job 25-50 MB in Redis instead of
    2-5 MB. The frontend fetches a picture per row from /api/depict.
    """

    index: int
    input: str
    input_id: Optional[str] = None
    smiles: Optional[str] = None
    name: Optional[str] = None
    status: Status
    roundtrip_smiles: Optional[str] = None
    roundtrip_match: Optional[bool] = None
    formula: Optional[str] = None
    limit_code: Optional[str] = None
    error: Optional[str] = None


class JobEnvelope(BaseModel):
    """Returned when work did not finish inside FAST_PATH_TIMEOUT, and by
    POST /api/jobs. Callers tell it apart from a completed response by the
    presence of job_id.
    """

    job_id: str
    molecule_count: int
    status: JobState
    # The ONLY time this is ever returned. Whoever submitted the job holds it;
    # anyone who is merely shown a results URL does not, which is the whole
    # point (audit item delete-no-ownership). Without accounts this is the
    # available notion of ownership: possession of a secret the server issued
    # once, to the submitter, over the same response.
    owner_token: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobState
    total: int
    done: int
    failed: int
    # Rows so far, by confidence tier -- keys are Status values. Reported
    # SEPARATELY from `failed` and never summed into it: `failed` is a row
    # the engine could not produce, while an "abstain" is the engine
    # correctly declining to guess. A tier with no rows is absent rather
    # than 0, so "none yet" and "counted, none found" stay distinguishable.
    counts: dict[str, int] = {}
    created_at: int
    expires_at: int
    # The switches the job was named with (redis_store.create_job). None for
    # a job created before they were recorded.
    best_effort: Optional[bool] = None
    verify: Optional[bool] = None


class JobResultsResponse(BaseModel):
    job_id: str
    offset: int
    limit: int
    # The DECLARED molecule count from submission.
    total: int
    # The rows actually retrievable. Equals `total` on a done job; short of
    # it on a failed one. Paginate against this, not `total`.
    retrievable: int
    rows: list[BatchRow]


class DepictResponse(BaseModel):
    depiction_svg: Optional[str] = None
    error: Optional[str] = None


class ParsePreviewRow(BaseModel):
    """One molecule as PARSED, before anything has been named.

    Deliberately NOT a BatchRow: it has no `status`. A preview row has no
    tier, and borrowing the tier vocabulary would put "the engine honestly
    refused" (abstain) and "naming was never attempted" into the same value
    of the one field PRODUCT.md forbids conflating -- and the frontend would
    draw the abstain rule under a molecule nothing has judged yet.
    """

    index: int
    input: str
    input_id: Optional[str] = None
    smiles: Optional[str] = None
    error: Optional[str] = None


class ParsePreviewResponse(BaseModel):
    """A count and a SAMPLE, not a validation.

    `molecule_count` is structural and covers the whole input, but `sample`
    and `errors` come from parsing only the first PREVIEW_SAMPLE records
    (app.jobs_api). An empty `errors` therefore means "no errors in the first
    few", NOT "this file is clean" -- a UI that presents it as the latter will
    tell a user their file is fine and then fail on row 6.

    Audit item parse-preview-partial-validation: README and the design spec
    both described this endpoint as validating the upload, which it has never
    done.
    """

    format: str
    molecule_count: int
    # First 5 of each, so a 10,000-molecule paste does not return 10,000 rows
    # before the user has agreed to run anything.
    sample: list[ParsePreviewRow]
    errors: list[str]
