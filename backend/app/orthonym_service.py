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
   verified fallback (`systematic_verified` or `pin_unverified`), a
   best-effort name from the general engine (`best_effort` -> "best_effort"),
   or it may still abstain -- whichever it actually produces is what ships.

Tier -> status mapping used for BOTH namers (`classify`). The tier names are
the Orthonym engine's own. Since engine 1.0.0 EVERY name of every tier has
passed the engine's own OPSIN round trip before it is emitted -- except a
name OPSIN cannot read at all (exact-match list names such as metal
tetrapyrrole complexes and retained natural-product parents, and a few
by-design SELF-01 carve-outs). So the tier says HOW the name was built, not
whether it round-trips:
  - "pin_verified"        -> "pin"          (the strict PIN path built and
    verified it)
  - "pin_unverified"      -> "fallback"     (a name in PIN form that only a
    breadth producer built; it round-trips, but the engine does not certify
    its preferred status. Assigned on EITHER pass -- the primary namer has
    general_fallback=True -- whatever name_tiered's own docstring says)
  - "systematic_verified" -> "fallback"     (a verified systematic name that
    is not the PIN, or a trivial-retained name)
  - "best_effort"         -> "best_effort"  (the general engine built it, or
    built part of it; it round-trips too. Mostly from the escalated pass, but
    NOT only: the primary pass gives it to a composer name that carries a
    general-tier ring prefix, e.g. OC(=O)CC12CC3CC(O)(CC(C3)C1)C2, so
    best_effort=False does not rule it out)
  - "abstain"             -> "abstain"      (name is ALWAYS reported as null,
    because an abstain row's own "name" field, when non-null, is a
    recognized failure placeholder like "unknown organic compound" and must
    never be surfaced as a real name)
`tier` always ships as the engine gave it. A missing round trip of this
app's own (translate_one, below) moves `status` alone.

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
pass but gets a `systematic_verified` or `pin_unverified` name on the
escalated pass is a "fallback", same as if the primary pass had found it
directly. Status "best_effort" comes from tier `best_effort`, or from
translate_one demoting a verified status whose visible round trip did not
run (that row keeps the engine's tier).

When the final status is "abstain" (both passes exhausted), formula/
limit_code come from the LAST row computed (the escalated pass's row) --
these are derived deterministically from the molecule via RDKit, not from
which namer produced them, so either row would give the same values; using
the last one computed is simplest.

For every non-abstain, non-error result (pin/fallback/best_effort) two
extra things are computed and attached (the round trip only when `verify` is
on and RDKit read the input):
  - depiction_svg: a 2D structure rendering of the input SMILES
    (app/depiction.py).
  - roundtrip_smiles / roundtrip_match: a SECOND, visible OPSIN round-trip
    proof independent of the engine's own internal SELF-01 gate (SELF-01 runs
    inside name_tiered() and only ever surfaces as the tier/is_pin verdict,
    never the re-derived SMILES itself). This calls
    orthonym.validation.opsin_roundtrip.opsin_parse(name) directly --
    the engine's OWN public wrapper around the SAME vendored jar +
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

from . import cdk_bridge
from .depiction import structure_svg_data_uri
from .schemas import VERIFIED_STATUSES, WITHHELD_UNCHECKED, ResultItem

# Constructed once per process and reused across all requests. This is
# REQUIRED for both correctness (general_fallback=True is what enables the
# fallback tiers, `systematic_verified` and `pin_unverified`, at all -- the
# bare default only ever produces PIN-or-abstain) and performance (namer
# construction is not free).
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
# general engine ship names the primary namer holds back (tier `best_effort`,
# surfaced as "best_effort"; they still pass the engine's full round trip
# before they ship); allow_aromatic_general=True widens
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
    if tier in ("systematic_verified", "pin_unverified"):
        # The two "fallback" tiers: verified, preferred status not certified.
        # systematic_verified is a verified systematic name that is not the PIN,
        # or a trivial-retained name. pin_unverified is a name in PIN form that
        # only a breadth producer built: it round-trips, but the engine does not
        # certify its preferred status, so it is never a "pin". Assigned today,
        # on the primary pass too; name_tiered's docstring still calls it
        # reserved.
        return "fallback", row["name"], tier
    if tier == "best_effort":
        return "best_effort", row["name"], tier

    # This guard earned its keep: it is what caught the upstream rename from
    # T1/T3/T4/T5 to these names, instead of a wrong tier reaching a user.
    raise ValueError(f"Unexpected name_tiered() row, cannot classify: {row!r}")


def _roundtrip_check(name: str, mol: Chem.Mol) -> tuple[Optional[str], Optional[bool]]:
    """Round-trip `name` back through OPSIN (via the engine's own opsin_parse,
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
    the engine's own SELF-01 uses for its stricter tiers. Measured on the
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
        state that demotes a verified status (the tier stays the engine's).
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
        # "OPSIN was unreachable" and wrongly demote the status.
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


def _abstain_item(
    smiles: str, tier: str, row: dict, limit_code: Optional[str] = None
) -> ResultItem:
    """The honest "no name" result.

    Built in two places -- the primary/escalated pass abstaining, and a
    verified status being demoted for a caller who refused best-effort names
    -- and they must not drift: this is the bottom rung of the confidence
    ladder, and the two differing would mean the same molecule reports
    differently depending on which route reached the same conclusion.

    `tier` comes from classify(), never a hardcoded constant. Hardcoding "T5"
    here is what made every abstain 500 after the upstream tier rename, even
    though classify() itself had been updated.

    `limit_code` overrides the engine's own reason, for the one abstain the
    app forces itself (WITHHELD_UNCHECKED).
    """
    return ResultItem(
        smiles=smiles,
        status="abstain",
        name=None,
        tier=tier,
        formula=row.get("formula"),
        limit_code=limit_code or row.get("limit_code"),
        error=None,
        depiction_svg=None,
        roundtrip_smiles=None,
        roundtrip_match=None,
    )


def translate_one(
    smiles: str, best_effort: bool = True, depict: bool = True, verify: bool = True
) -> ResultItem:
    """Translate a single SMILES string into a ResultItem.

    `depict` exists because the BATCH path throws the picture away. `name_one`
    (app.tasks) returns "the ResultItem fields a BatchRow needs, minus
    depiction_svg", and `name_cache` excludes it too -- so every batch molecule
    was drawing an SVG that nothing ever read. Free when the renderer was RDKit
    (measured at 0.0 ms against the naming cost, which is why nobody noticed);
    not free now that CDK draws. Measured on a warm JVM over 5 molecules x 3
    reps: 7.67 ms/molecule with the picture, 5.46 ms without -- **2.2 ms of
    pure waste per row, ~22 s on a full 10,000-molecule job**. Callers that
    actually read the picture leave it True.

    `verify` runs the OPSIN round-trip check. Turning it off does not make a
    name look better than it is: the check is what produces `roundtrip_smiles`,
    and the downgrade below already treats a missing round trip as "this
    status's claim is not backed", so every verified status falls to
    `best_effort` (the engine's tier is kept as it came). The
    saving is real but modest -- measured 0.60 ms/molecule, ~6 s on a full
    10,000-molecule job -- and it is exposed mainly so the proof can be turned
    off and SEEN to matter.

    `best_effort` gates the escalation described in the module docstring.
    When False the escalated namer is never consulted, so a molecule the
    primary namer abstained on ships as an honest abstain. It does NOT rule
    out tier "best_effort": the primary pass assigns it too (module
    docstring), and that row ships as status best_effort. Note that turning
    it off also forfeits the fallbacks (`systematic_verified`,
    `pin_unverified`) the escalated pass would have found -- the escalation
    is one call, and its possible outcomes cannot be separated before it
    runs.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None and cdk_bridge.parse_smiles(smiles) is None:
        # Neither toolkit can read it. Only now is it really unparseable.
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
    # `mol` may still be None here: CDK's valence and aromaticity models are
    # more permissive than RDKit's, so it reads structures RDKit refuses
    # (measured: pentavalent nitrogen written without charges, N-oxides written
    # as N(=O), some organometallics). Continuing without a Mol is deliberate.
    # The namer takes the SMILES STRING, not a Mol, so it can still be asked --
    # and CDK can still draw the picture. What we lose is the round-trip check,
    # which needs RDKit to compute an InChIKey for the input; that loss is
    # handled below and costs the molecule its verified status, honestly.
    #
    # Measured, not hoped for: these almost all end in an abstain, and an
    # abstain carries no depiction by design (_abstain_item), so the gain here
    # is the VERDICT, not a picture. "I read your structure and declined to name
    # it" is true; "Could not parse this SMILES string" was not. The picture for
    # such a molecule reaches the user through GET /api/depict, which draws any
    # SMILES either toolkit can read.

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
    depiction_svg = structure_svg_data_uri(smiles, mol) if depict else None
    # No Mol means no InChIKey for the input, so there is nothing to compare
    # OPSIN's re-parse AGAINST. (None, None) is the right answer, not (raw,
    # False): "I could not check" is not "I checked and it differs".
    roundtrip_smiles, roundtrip_match = (
        _roundtrip_check(name, mol) if (verify and mol is not None) else (None, None)
    )

    if status in VERIFIED_STATUSES and roundtrip_smiles is None:
        # Final review report, C3, backend half. Several causes reach here, and
        # all mean the same thing about the CLAIM: no round trip of this app's
        # own backs the label. The caller turned `verify` off; or RDKit could
        # not read the input (the CDK branch at the top of this function), so
        # there is no InChIKey to compare against; or OPSIN cannot read the
        # name back (an exact-match list name or a by-design SELF-01
        # carve-out); or OPSIN was unreachable,
        # in which case SELF-01 (the same opsin_parse()) failed OPEN too.
        # name_cache already refuses to PERSIST a verified status with no
        # round trip -- but declining to cache a claim is not the same as
        # declining to make it, and the frontend renders "pin" with the double
        # rule that means round-trip confirmed.
        #
        # The name itself is real, so it survives; only the claim about it is
        # corrected, down to the status that claims no round trip at all.
        # Except for a caller who passed best_effort=False: they refused
        # best-effort names outright, and handing them a best_effort row here
        # would reintroduce through the back door exactly what the gate above
        # keeps out the front. For them the honest answer is abstain.
        #
        # That abstain is the caller's settings speaking, not the engine: a
        # name existed. `withheld_unchecked` says so, and keeps the
        # frontend's "Report SMILES on GitHub" (lib/github.js) off a molecule the
        # engine named perfectly well.
        if not best_effort:
            return _abstain_item(smiles, tier, row, limit_code=WITHHELD_UNCHECKED)
        # STATUS only. `tier` stays the engine's own verdict on how the name
        # was built: this app's check not running does not change it. (This
        # block used to rewrite the tier to pin_unverified / best_effort, but
        # pin_unverified is a real engine tier for a round-tripping PIN-form
        # name, not a spelling of "not checked".) The frontend reads a
        # best_effort status with no roundtrip_smiles as "not checked here".
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
