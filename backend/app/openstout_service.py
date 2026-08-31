"""Translation logic: SMILES -> ResultItem, backed by the OpenSTOUT engine.

Derivation logic (verified against the live openstout package):

1. Validate with RDKit first. If it can't parse, status="error".
2. Otherwise call the shared, process-wide PRIMARY OpenSTOUT(style="pin",
   general_fallback=True) namer's `name_tiered(smiles)` and classify it
   (see `classify` below).
3. If the primary pass did NOT abstain, use its result as-is.
4. If the primary pass DID abstain (tier T5), escalate: run the SAME
   `name_tiered(smiles)` call against a SECOND, more aggressive namer --
   OpenSTOUT(style="pin", general_fallback=True,
   general_fallback_unverified=True, allow_aromatic_general=True) -- and
   classify ITS result instead. This escalated pass may still land on a
   verified fallback (T3), a genuinely OPSIN-unverified name (T4 ->
   "best_effort"), or it may still abstain (T5) -- whichever it actually
   produces is what ships.

Tier -> status mapping used for BOTH namers (`classify`). The tier names are
OpenSTOUT's own, from `OpenSTOUT.name_tiered`'s docstring:
  - "pin_verified"        -> "pin"
  - "systematic_verified" -> "fallback"     (RT-verified via the general
    engine, or a trivial-retained name)
  - "best_effort"         -> "best_effort"  (engine, E1-only, NOT RT-verified
    -- requires the general_fallback_unverified opt-in, so it only appears on
    the escalated pass)
  - "abstain"             -> "abstain"      (name is ALWAYS reported as null,
    because an abstain row's own "name" field, when non-null, is a
    recognized failure placeholder like "unknown organic compound" and must
    never be surfaced as a real name)
  - "pin_unverified"      -> "best_effort"  (reserved upstream for
    systematic-PIN certification; an UNVERIFIED pin must never be shown as a
    verified one, so it degrades to the honest unverified status)

These replaced an earlier T1/T3/T4/T5 scheme. No T-code exists in the engine
any more, and `classify`'s final `raise` is what caught the rename.

Note that "best_effort" is NOT what a molecule gets just because it needed
the escalated/second-pass namer -- a molecule that abstains on the primary
pass but round-trip-verifies on the escalated pass is a "fallback" (T3),
same as if the primary pass had found it directly. "best_effort" is
reserved specifically for tier T4 on whichever pass produced the final
result.

When the final status is "abstain" (both passes exhausted), formula/
limit_code come from the LAST row computed (the escalated pass's row) --
these are derived deterministically from the molecule via RDKit, not from
which namer produced them, so either row would give the same values; using
the last one computed is simplest.

For every non-abstain, non-error result (pin/fallback/best_effort) two
extra things are computed and attached:
  - depiction_svg: a 2D structure rendering of the input SMILES
    (app/depiction.py).
  - roundtrip_smiles / roundtrip_match: a SECOND, visible OPSIN round-trip
    proof independent of OpenSTOUT's own internal SELF-01 gate (SELF-01 runs
    inside name_tiered() and only ever surfaces as the tier/is_pin verdict,
    never the re-derived SMILES itself). This calls
    openstout.validation.opsin_roundtrip.opsin_parse(name) directly --
    OpenSTOUT's OWN public wrapper around the SAME vendored jar +
    in-process JVM bridge already wired up for SELF-01 (backend/vendor/
    opsin-resources/, see place_opsin_resources.py) -- rather than a
    separate package with its own bundled jar. One jar, one JVM, one source
    of truth for "what does OPSIN say," reused for both the internal gate
    and this visible proof.

The OpenSTOUT namers are expensive to construct, so exactly one instance of
each is built at module import time and reused across all requests/SMILES.
"""

from typing import Optional

from rdkit import Chem

from openstout import OpenSTOUT
from openstout.validation.opsin_roundtrip import opsin_parse

from .depiction import mol_to_svg_data_uri
from .schemas import ResultItem

# Constructed once per process and reused across all requests. This is
# REQUIRED for both correctness (general_fallback=True is what enables
# fallback/T3/T4 results at all -- the bare default only ever produces
# PIN-or-abstain) and performance (namer construction is not free).
_namer = OpenSTOUT(style="pin", general_fallback=True)


def get_primary_namer() -> OpenSTOUT:
    """The same primary namer /api/translate uses. Exposed so other
    endpoints (e.g. /api/explain) name a molecule identically to how
    /api/translate would -- a fresh OpenSTOUT() with different flags would
    silently produce a different name for the same input.
    """
    return _namer

# Second, more aggressive namer used ONLY to escalate molecules the primary
# namer abstained on (tier T5). general_fallback_unverified=True lets the
# general engine ship a name even when its own round-trip check fails
# (tier T4, surfaced as "best_effort"); allow_aromatic_general=True widens
# what the general engine will attempt on aromatic systems. Built once at
# import time for the same reasons as `_namer`.
_escalated_namer = OpenSTOUT(
    style="pin",
    general_fallback=True,
    general_fallback_unverified=True,
    allow_aromatic_general=True,
)


def classify(row: dict) -> tuple[str, Optional[str], str]:
    """Map one `name_tiered()` row to (status, name, tier).

    Valid for the output of EITHER namer -- see module docstring for the
    tier -> status contract.
    """
    tier = row["tier"]

    if tier == "abstain":
        return "abstain", None, tier
    if tier == "pin_verified":
        return "pin", row["name"], tier
    if tier == "systematic_verified":
        # RT-verified via the general engine or a trivial-retained name --
        # which is exactly what STITCH means by "fallback".
        return "fallback", row["name"], tier
    if tier == "best_effort":
        return "best_effort", row["name"], tier
    if tier == "pin_unverified":
        # Reserved upstream for systematic-PIN certification. A PIN whose
        # round trip has NOT been confirmed must never be shown as a
        # verified PIN, so it ships as the honest "a real name, but
        # OPSIN-unverified" status instead.
        return "best_effort", row["name"], tier

    # This guard earned its keep: it is what caught the upstream rename from
    # T1/T3/T4/T5 to these names, instead of a wrong tier reaching a user.
    raise ValueError(f"Unexpected name_tiered() row, cannot classify: {row!r}")


def _roundtrip_check(name: str, mol: Chem.Mol) -> tuple[Optional[str], Optional[bool]]:
    """Round-trip `name` back through OPSIN (via OpenSTOUT's own opsin_parse,
    the same vendored jar/JVM as the internal SELF-01 gate) and compare the
    result to `mol` (the already-parsed input molecule) via RDKit
    canonicalization.

    Returns (roundtrip_smiles, roundtrip_match):
      - (None, None) if opsin_parse returned None (OPSIN could not
        interpret the name, or the jar/JVM is unavailable).
      - (raw_smiles, False) if OPSIN returned something but RDKit can't
        parse it, or it doesn't canonically match the input.
      - (raw_smiles, True) if it canonically matches the input.
    """
    raw = opsin_parse(name)
    if not raw:
        return None, None

    roundtrip_mol = Chem.MolFromSmiles(raw)
    if roundtrip_mol is None:
        return raw, False

    original_canonical = Chem.MolToSmiles(mol, canonical=True)
    roundtrip_canonical = Chem.MolToSmiles(roundtrip_mol, canonical=True)
    return raw, original_canonical == roundtrip_canonical


def translate_one(smiles: str, best_effort: bool = True) -> ResultItem:
    """Translate a single SMILES string into a ResultItem.

    `best_effort` gates the escalation described in the module docstring.
    When False the escalated namer is never consulted, so no OPSIN-
    unverified name (T4 / "best_effort") can ever be produced and a
    molecule the primary namer abstained on ships as an honest abstain.
    Note that turning it off also forfeits the T3 fallbacks the escalated
    pass would have round-trip-VERIFIED -- the escalation is one call, and
    its two possible good outcomes cannot be separated before it runs.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ResultItem(
            smiles=smiles,
            status="error",
            name=None,
            tier=None,
            formula=None,
            limit_code=None,
            error="Could not parse this SMILES string",
            depiction_svg=None,
            roundtrip_smiles=None,
            roundtrip_match=None,
        )

    row = _namer.name_tiered(smiles)
    status, name, tier = classify(row)

    if status == "abstain" and best_effort:
        # Primary pass abstained -- escalate. `row` is reassigned so that,
        # if this ALSO abstains, the formula/limit_code populated below
        # come from this (the last-computed) row.
        row = _escalated_namer.name_tiered(smiles)
        status, name, tier = classify(row)

    if status == "abstain":
        return ResultItem(
            smiles=smiles,
            status="abstain",
            name=None,
            # `tier` from classify(), never a hardcoded constant: hardcoding
            # "T5" here is what made every abstain 500 after the upstream
            # tier rename, even though classify() itself had been updated.
            tier=tier,
            formula=row.get("formula"),
            limit_code=row.get("limit_code"),
            error=None,
            depiction_svg=None,
            roundtrip_smiles=None,
            roundtrip_match=None,
        )

    # status in ("pin", "fallback", "best_effort"): a real name shipped.
    depiction_svg = mol_to_svg_data_uri(mol)
    roundtrip_smiles, roundtrip_match = _roundtrip_check(name, mol)

    return ResultItem(
        smiles=smiles,
        status=status,
        name=name,
        tier=tier,
        formula=None,
        limit_code=None,
        error=None,
        depiction_svg=depiction_svg,
        roundtrip_smiles=roundtrip_smiles,
        roundtrip_match=roundtrip_match,
    )


def translate_many(smiles_list: list[str], best_effort: bool = True) -> list[ResultItem]:
    """Translate each SMILES string, preserving input order."""
    return [translate_one(s, best_effort=best_effort) for s in smiles_list]
