"""Translation logic: SMILES -> ResultItem, backed by the Orthonym engine.

Derivation logic (verified against the live orthonym package):

1. Validate with RDKit first. If it can't parse, status="error".
2. Otherwise call the shared, process-wide PRIMARY Orthonym(style="pin",
   general_fallback=True) namer's `name_tiered(smiles)` and classify it
   (see `classify` below).
3. If the primary pass did NOT abstain, use its result as-is.
4. If the primary pass DID abstain (tier `abstain`), escalate: run the SAME
   `name_tiered(smiles)` call against a SECOND, more aggressive namer --
   Orthonym(style="pin", general_fallback=True,
   general_fallback_unverified=True, allow_aromatic_general=True) -- and
   classify ITS result instead. This escalated pass may still land on a
   verified fallback (`systematic_verified`), a genuinely OPSIN-unverified name (`best_effort` ->
   "best_effort"), or it may still abstain -- whichever it actually
   produces is what ships.

Tier -> status mapping used for BOTH namers (`classify`). The tier names are
Orthonym's own, from `Orthonym.name_tiered`'s docstring:
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

These replaced an earlier T1/T3/T4/T5 scheme. The T-codes are HISTORY: they
do not exist in the engine, in any response, or in any comparison in this
codebase, and the names above are the only vocabulary in use. Every remaining
T-code in this repository is a historical reference in a comment explaining a
past bug, and is marked as such -- writing a T-code as if it were live is a
real hazard, not a stylistic one: it is what produced the hardcoded "T5" bug
recorded further down this file, and it caught out a later reader again while
these very comments were being corrected. `classify`'s final `raise` is what
caught that rename, and is what will catch the next one.

Note that "best_effort" is NOT what a molecule gets just because it needed
the escalated/second-pass namer -- a molecule that abstains on the primary
pass but round-trip-verifies on the escalated pass is a "fallback"
(`systematic_verified`),
same as if the primary pass had found it directly. "best_effort" is
reserved specifically for tier `best_effort` on whichever pass produced the final
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
    proof independent of Orthonym's own internal SELF-01 gate (SELF-01 runs
    inside name_tiered() and only ever surfaces as the tier/is_pin verdict,
    never the re-derived SMILES itself). This calls
    orthonym.validation.opsin_roundtrip.opsin_parse(name) directly --
    Orthonym's OWN public wrapper around the SAME vendored jar +
    in-process JVM bridge already wired up for SELF-01 (backend/vendor/
    opsin-resources/, see place_opsin_resources.py) -- rather than a
    separate package with its own bundled jar. One jar, one JVM, one source
    of truth for "what does OPSIN say," reused for both the internal gate
    and this visible proof.

The Orthonym namers are expensive to construct, so exactly one instance of
each is built at module import time and reused across all requests/SMILES.
"""

from typing import Optional

from rdkit import Chem
from rdkit.Chem.inchi import MolToInchiKey

from orthonym import Orthonym
from orthonym.validation.opsin_roundtrip import opsin_parse

from .depiction import mol_to_svg_data_uri
from .schemas import VERIFIED_STATUSES, ResultItem

# Constructed once per process and reused across all requests. This is
# REQUIRED for both correctness (general_fallback=True is what enables
# fallback/`systematic_verified`/`best_effort` results at all -- the bare default only ever produces
# PIN-or-abstain) and performance (namer construction is not free).
_namer = Orthonym(style="pin", general_fallback=True)


def get_primary_namer() -> Orthonym:
    """The same primary namer /api/translate uses. Exposed so other
    endpoints (e.g. /api/explain) name a molecule identically to how
    /api/translate would -- a fresh Orthonym() with different flags would
    silently produce a different name for the same input.
    """
    return _namer

# Second, more aggressive namer used ONLY to escalate molecules the primary
# namer abstained on (tier `abstain`). general_fallback_unverified=True lets the
# general engine ship a name even when its own round-trip check fails
# (tier `best_effort`, surfaced as "best_effort"); allow_aromatic_general=True widens
# what the general engine will attempt on aromatic systems. Built once at
# import time for the same reasons as `_namer`.
_escalated_namer = Orthonym(
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
        # which is exactly what Orthonym means by "fallback".
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
    """Round-trip `name` back through OPSIN (via Orthonym's own opsin_parse,
    the same vendored jar/JVM as the internal SELF-01 gate) and compare the
    result to `mol` (the already-parsed input molecule) by FULL STANDARD
    INCHIKEY.

    The comparison used to be canonical SMILES, and it produced false
    alarms on a very ordinary class of molecule. Measured: zwitterionic
    glycine, `[NH3+]CC(=O)[O-]`, is named "glycine" -- correctly -- and OPSIN
    reads that name back as the neutral `NCC(=O)O`. Two different canonical
    SMILES, so the round trip was reported as a MISMATCH beside a name that
    is right, on a result still labelled a verified PIN. It was the only
    mismatch in 56 verified results over a set chosen to stress exactly this.

    The full InChIKey is the comparison that answers the question actually
    being asked ("did the name come back as this compound?"), and it is what
    Orthonym's own SELF-01 uses for its stricter tiers. Measured on the
    three cases that matter:

        pair                          canonical SMILES   skeleton   full key
        glycine zwitterion / neutral  differ (false)     same       SAME
        acetone keto / enol           differ             differ     differ
        (2S)- / (2R)-butan-2-ol       differ             SAME       differ

    So canonical SMILES cries wolf, the InChIKey skeleton block alone would
    MISS a stereo inversion (which is a naming error), and the full key
    catches both real errors while accepting the protonation difference.
    InChI normalises that difference because it is the same compound.

    Returns (roundtrip_smiles, roundtrip_match):
      - (None, None) if opsin_parse returned None (OPSIN could not
        interpret the name, or the jar/JVM is unavailable). This is the
        state that downgrades a verified tier.
      - (raw_smiles, False) if OPSIN returned something RDKit cannot parse,
        an InChIKey cannot be computed for either side, or the keys differ.
      - (raw_smiles, True) if the full InChIKeys agree.

    The SMILES OPSIN produced is still what gets shown: the visible proof
    has to be the thing OPSIN actually said, not a hash of it.
    """
    raw = opsin_parse(name)
    if not raw:
        return None, None

    roundtrip_mol = Chem.MolFromSmiles(raw)
    if roundtrip_mol is None:
        return raw, False

    original_key = _inchikey(mol)
    roundtrip_key = _inchikey(roundtrip_mol)
    if original_key is None or roundtrip_key is None:
        # RDKit's InChI support can decline a molecule (unusual valences,
        # some organometallics). Falling back to canonical SMILES keeps a
        # verdict available rather than reporting None, which would read as
        # "OPSIN was unreachable" and wrongly downgrade the tier.
        return raw, Chem.MolToSmiles(mol, canonical=True) == Chem.MolToSmiles(
            roundtrip_mol, canonical=True
        )
    return raw, original_key == roundtrip_key


def _inchikey(mol: Chem.Mol) -> Optional[str]:
    """The full standard InChIKey, or None if RDKit will not compute one.

    RDKit logs and returns an empty string rather than raising for some
    inputs, so an empty result is normalised to None here -- two empty
    strings would otherwise compare equal and read as a passing round trip.
    """
    try:
        key = MolToInchiKey(mol)
    except Exception:  # noqa: BLE001 - a declined molecule is not an error
        return None
    return key or None


def _abstain_item(smiles: str, tier: str, row: dict) -> ResultItem:
    """The honest "no name" result.

    Built in two places -- the primary/escalated pass abstaining, and a
    verified tier being downgraded for a caller who refused unverified names
    -- and they must not drift: this is the bottom rung of the confidence
    ladder, and the two differing would mean the same molecule reports
    differently depending on which route reached the same conclusion.

    `tier` comes from classify(), never a hardcoded constant. Hardcoding "T5"
    here is what made every abstain 500 after the upstream tier rename, even
    though classify() itself had been updated.
    """
    return ResultItem(
        smiles=smiles,
        status="abstain",
        name=None,
        tier=tier,
        formula=row.get("formula"),
        limit_code=row.get("limit_code"),
        error=None,
        depiction_svg=None,
        roundtrip_smiles=None,
        roundtrip_match=None,
    )


def translate_one(smiles: str, best_effort: bool = True) -> ResultItem:
    """Translate a single SMILES string into a ResultItem.

    `best_effort` gates the escalation described in the module docstring.
    When False the escalated namer is never consulted, so no OPSIN-
    unverified name ("best_effort") can ever be produced and a
    molecule the primary namer abstained on ships as an honest abstain.
    Note that turning it off also forfeits the `systematic_verified` fallbacks the escalated
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
        return _abstain_item(smiles, tier, row)

    # status in ("pin", "fallback", "best_effort"): a real name shipped.
    depiction_svg = mol_to_svg_data_uri(mol)
    roundtrip_smiles, roundtrip_match = _roundtrip_check(name, mol)

    if status in VERIFIED_STATUSES and roundtrip_smiles is None:
        # Final review report, C3, backend half. SELF-01 uses the same
        # opsin_parse() as the round-trip check above, so a null
        # roundtrip_smiles on a verified tier can only mean OPSIN was
        # unreachable: SELF-01 failed OPEN and let an unverified candidate
        # through wearing a verified label. name_cache already refuses to
        # PERSIST such a row for its 7-day TTL -- but declining to cache a
        # lie is not the same as declining to tell it, and the frontend
        # renders "pin" with the double rule that means round-trip
        # confirmed.
        #
        # The name itself is real, so it survives; only the claim about it
        # is corrected, down to the tier that claims no verification at all.
        # Except for a caller who passed best_effort=False: they refused
        # OPSIN-unverified names outright, and handing them one here would
        # reintroduce through the back door exactly what the gate above
        # keeps out the front. For them the honest answer is abstain.
        if not best_effort:
            return _abstain_item(smiles, tier, row)
        status = "best_effort"

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
