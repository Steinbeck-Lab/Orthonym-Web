"""Per-class coverage gate.

The census script (`backend/scripts/explain_census.py`) measures all 544 names
in `tests/fixtures/explain_corpus.FULL` on demand; this file asserts the
curated ~50-name subset (`CURATED`) inside the suite, so every documented
nomenclature class has a named test that cannot silently re-open.

**The plan's definition of done was not reached, and this file does not
pretend otherwise.** The spec asked for zero fully-inert (`SPANS_NONE`) names.
Measured against the full 544-name corpus, right now:

    CLEAN 277   SPANS_NONE 157   SPANS_PARTIAL 106   ENGINE_ERROR 2
    UNMAPPED 12   ATOM_GAP 0

`SPANS_NONE` is 157, not 0. The two largest contributors are both *named*
residue, not unexplained gaps:

* Lossy OPSIN labels, where a token OPSIN itself duplicates (e.g. the `az`
  token in `[1,2,4]triazolo[4,3-a]pyridine`) mean the merged part text is no
  longer any ordered concatenation of the raw token stream, so there is no
  substring of the name left to point the span at. Withholding is correct
  here -- guessing would show a wrong highlight -- and this is the class the
  design spec calls out as expected residue.
* The "claims guard" in `app/explain.py`, which withholds a multiplicative
  substituent's span whenever grouping it by TEXT (rather than by each raw
  occurrence) would make it claim atoms its span does not cover -- measured
  directly (Ruling 25, `.superpowers/sdd/2026-09-09-explain-token-parts/
  progress.md`, Ruling 25 -- that path is gitignored, so it is not in a
  clone) at **+55 names** if regrouped per-occurrence. That regrouping
  changes what a segment means (payload-contract work) and was scoped out of
  this plan as a follow-on project; it is not a defect this gate should treat
  as a regression.

Given that, this file gates two kinds of things differently, on purpose:

1. Invariants that hold TODAY, asserted exactly as the brief specified them,
   unweakened: `ATOM_GAP` is always 0, and every `ENGINE_ERROR` is one of the
   two names OPSIN 2.9.0 itself cannot parse (`OPSIN_CANNOT_PARSE`).
2. The shortfall, gated at its MEASURED FLOOR/CEILING rather than at the
   unmet aspirational target. These numbers are WATERMARKS, not goals: a red
   test here means a name that used to explain cleanly (or used to at least
   show *something*) no longer does. The fix is to restore the coverage, not
   to edit the number down to match the new, worse reality -- that would
   convert a real regression into a silently-accepted one, which is the one
   thing this file exists to prevent. Progress (a name moving from
   SPANS_NONE/PARTIAL to CLEAN) never fails these tests and never requires
   editing them; only a regression does.

Measured 2026-09-11 against `CURATED` (49 names), at the same tip as the
FULL-corpus run quoted above. The two tables cannot be compared row for row
-- CURATED is a separate 49-name list, not a slice of the 544 (see
`tests/fixtures/explain_corpus.py`) -- so "same tip", not "same numbers".
"""

import collections

import pytest

from scripts.explain_census import classify
from tests.fixtures.explain_corpus import CURATED, OPSIN_CANNOT_PARSE


@pytest.fixture(scope="module")
def rows():
    from app.explain import explain_name

    return [
        {"axis": axis, "name": name, "outcome": classify(explain_name(name))}
        for axis, name in CURATED
    ]


@pytest.fixture(scope="module")
def by_axis(rows):
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row["axis"]].append(row)
    return grouped


# --- Real invariants: hold today, asserted exactly as the brief specified. ---


def test_only_the_two_genuinely_unparseable_names_error(rows):
    """ENGINE_ERROR is exclusive to names OPSIN 2.9.0 itself cannot parse.
    Measured: zero CURATED names error at all, so this holds vacuously today
    -- it stays a hard assertion because a NEW error appearing here (from a
    name that used to at least decompose) is unambiguously a regression.
    """
    errored = {r["name"] for r in rows if "ENGINE_ERROR" in r["outcome"]}
    assert errored <= OPSIN_CANNOT_PARSE, errored - OPSIN_CANNOT_PARSE


def test_no_atom_gap_anywhere(rows):
    """Owning parts must still cover every heavy atom. This is the
    invariant Task 6's referential children must not have broken. Measured
    ATOM_GAP is 0 across all 544 names, not just CURATED.
    """
    gaps = [r["name"] for r in rows if "ATOM_GAP" in r["outcome"]]
    assert gaps == [], gaps


# --- The shortfall: gated at the measured floor/ceiling, not the unmet goal. ---

# Minimum CLEAN count per axis, measured against CURATED on 2026-09-11
# (tip 81c0db7). Three axes are floored at 0 -- `multiplicative-nested`,
# `esters-salts-amides` and `long-chains-polyenes` -- because they measure 0
# clean names today; that is the truth, not an oversight, and is exactly the
# shortfall this module's docstring names. Floors are watermarks: lower one
# only if CURATED itself changes what it asks of that axis, never to paper
# over a regression.
CLEAN_FLOOR_BY_AXIS = {
    "golden": 2,
    "baseline-chains": 1,
    "monocycles": 3,
    "retained-fused": 3,
    "fusion-bracket": 4,
    "ring-assembly-primed": 3,
    "multiplicative-nested": 0,
    "von-baeyer-spiro": 3,
    "bridge-prefix": 1,
    "element-italic-locants": 2,
    "esters-salts-amides": 0,
    "stereodescriptors": 2,
    "long-chains-polyenes": 0,
    "charged-inorganic": 3,
    "real-drug-names": 1,
}


def test_clean_count_per_axis_does_not_regress(by_axis):
    """Four axes were at zero clean out of forty in the plan's own framing;
    measured today, three of CURATED's fifteen axes (`multiplicative-nested`,
    `esters-salts-amides`, `long-chains-polyenes`) are still at zero clean.
    That is a real, named shortfall -- this test does not hide it behind a
    passing assertion. What it DOES gate is regression: a currently-clean
    name silently going dark would drop its axis below the floor recorded
    above, and this fails loudly on that.

    A new axis appearing in CURATED with no floor recorded is also a
    failure here -- add its measured floor rather than letting it pass
    ungated.
    """
    assert set(by_axis) == set(CLEAN_FLOOR_BY_AXIS), (
        "CURATED axes and CLEAN_FLOOR_BY_AXIS keys have drifted apart",
        set(by_axis) ^ set(CLEAN_FLOOR_BY_AXIS),
    )
    shortfall = {}
    for axis, floor in CLEAN_FLOOR_BY_AXIS.items():
        clean = sum(1 for r in by_axis[axis] if "CLEAN" in r["outcome"])
        if clean < floor:
            shortfall[axis] = {"floor": floor, "measured": clean}
    assert shortfall == {}, shortfall


# The exact CURATED names measured SPANS_NONE on 2026-09-11 (tip 81c0db7) --
# 10 of 49. This is the residue named in the module docstring: lossy OPSIN
# labels (duplicated tokens, e.g. the fusion-bracket and multiplicative-nested
# entries below) and the claims-guard class the +55 follow-on owns. It is a
# CEILING, not a target: a name leaving this set (getting fixed) needs no
# edit here and never fails the test below; a name NOT in this set showing up
# as SPANS_NONE is a genuine new regression.
KNOWN_SPANS_NONE_CURATED = frozenset({
    "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane",
    "[1,2,4]triazolo[4,3-a]pyridine",
    "1,1'-bi(cyclohexane)",
    "2,2-bis(4-hydroxyphenyl)propane",
    "tris(2-chloroethyl) phosphate",
    "4,4'-methylenedianiline",
    "octadecanoic acid",
    "tetradecanoic acid",
    "nonadecane",
    "(9Z,12Z)-octadeca-9,12-dienoic acid",
    # Added by the final-review fix wave, and it is a TRADE, not a loss. This
    # name used to ship PARTIALLY spanned -- parent `sodium` and parent `acet`
    # both had spans while suffix `ate` had none -- which `_apply_name_spans`
    # calls impossible. Its suffix belongs to the SECOND root while
    # `suffix_key` reads only the first, so the suffix has no anchor. The
    # backend now withholds the whole name instead, which is the honest
    # answer; the frontend was already falling back, so no reader loses
    # anything they could previously see. Recovering it properly means keying
    # the suffix anchor to the root that produced the segment -- recorded
    # follow-on, not done here. `potassium benzoate` has the same shape but is
    # not in CURATED.
    "sodium acetate",
})


def test_spans_none_does_not_grow_beyond_the_known_residue(rows):
    """SPANS_NONE means nameTargets() returns [] and the whole name is dead
    text in the UI. The spec's bar was zero; the module docstring above
    states plainly that the bar was not cleared (157 of 544 in the full
    census). Rather than assert the unmet zero, this holds the line at the
    measured ceiling: any CURATED name that goes fully inert and is not
    already a documented member of KNOWN_SPANS_NONE_CURATED is a NEW
    regression and fails here.
    """
    dead = {r["name"] for r in rows if "SPANS_NONE" in r["outcome"]}
    new_dead = dead - KNOWN_SPANS_NONE_CURATED
    assert new_dead == set(), new_dead
