"""Per-class coverage gate.

The census script (`backend/scripts/explain_census.py`) measures all 544 names
in `tests/fixtures/explain_corpus.FULL` on demand; this file asserts the
49-name `CURATED` list inside the suite, so every documented nomenclature
class has a named test that cannot silently re-open. `CURATED` is a SEPARATE
list, not a subset of `FULL` -- 14 of its 49 names appear nowhere in `FULL`
(see that fixture's own docstring), so the two tables are never comparable
row for row.

**The plan's definition of done was not reached, and this file does not
pretend otherwise.** The spec asked for zero fully-inert (`SPANS_NONE`) names.
Measured against the full 544-name corpus, right now (after the per-occurrence
regrouping follow-on -- see below):

    CLEAN 311   SPANS_NONE 111   SPANS_PARTIAL 117   ENGINE_ERROR 2
    UNMAPPED 12   ATOM_GAP 0

`SPANS_NONE` is 111, not 0. The largest remaining contributor is *named*
residue, not an unexplained gap: lossy OPSIN labels, where a token OPSIN
itself duplicates (e.g. the `az` token in `[1,2,4]triazolo[4,3-a]pyridine`)
mean the merged part text is no longer any ordered concatenation of the raw
token stream, so there is no substring of the name left to point the span at.
Withholding is correct here -- guessing would show a wrong highlight -- and
this is the class the design spec calls out as expected residue.

The other named contributor, as of the previous measurement in this
docstring, was the "claims guard" in `app/explain.py`: it withheld a
multiplicative substituent's span whenever grouping it by TEXT (rather than
by each raw occurrence) would make it claim atoms its span did not cover --
measured then (Ruling 25 in `.superpowers/sdd/2026-09-09-explain-token-parts/
progress.md` -- a gitignored path, so it is not in a clone) at **+55 names**
recoverable by regrouping per-occurrence. That follow-on
(`.superpowers/sdd/followon-regroup/`) is what produced the numbers above:
`_build_segments` now groups substituent parts by the RUN they belong to (one
written occurrence) rather than by shared text, so a segment's atoms and its
own span are the same thing by construction and the old claims guard has no
condition left to catch -- it was measured, removed, and its dead-code test
converted to an end-to-end check
(`test_a_ring_stem_that_looks_like_a_multiplier_is_not_counted_as_one` in
`test_name_range.py`). Of the +55, 51 names actually recovered (some CLEAN,
some SPANS_PARTIAL at the CHILD level -- e.g. a locant child whose text sits
outside its own run after a `bis`/`tris` block-collapse), 1 was a wash (still
withheld, for an unrelated pre-existing reason), 2 were superseded by a
narrower multi-root fix bundled with the same change (`calcium carbonate`,
`potassium permanganate`, previously CLEAN and now still CLEAN via a
corrected suffix-anchor check), and 1 pre-existing CLEAN name regressed to
SPANS_NONE (`3a,7a-dimethyl-hexahydro-4,7-epoxyisobenzofuran-1,3-dione`) --
a PRE-EXISTING gap in `name_tokens.py`'s `_LEADING`/`_group_locant_matches`
(the `alphaBetaStereochemLocant` category, e.g. "3a,7a-", was never
recognised as a locant there) that this follow-on's per-part feeding exposes
but does not itself cause; it fails closed (never a wrong span) and is
reported, not fixed, as out of this follow-on's scope. See
`.superpowers/sdd/followon-regroup/report.md` for the full measurement.

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

# Minimum CLEAN count per axis, re-measured against CURATED on 2026-09-11
# after the per-occurrence regrouping follow-on (see this module's own
# docstring). Two floors moved UP from the previous measurement (tip
# 81c0db7), both progress, never edited down to paper over a regression:
#
# * `golden` 2 -> 3: `1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane` (DDT)
#   is CURATED's own worked example of the class-A shape (a `bis` prefix
#   cloning a block of parts) this follow-on recovers -- see
#   `test_ddt_gets_two_chloro_segments_one_per_written_occurrence` in
#   `test_name_range.py`.
# * `multiplicative-nested` 0 -> 2: two of this axis's `bis`/`tris`-prefixed
#   names now derive runs via `collapse_cloned_blocks`, closing part of the
#   exact shortfall this file's docstring named.
#
# The other two axes named as zero-clean shortfall before this follow-on --
# `esters-salts-amides` and `long-chains-polyenes` -- measure zero clean
# still; nothing in per-occurrence regrouping touches their residue (mostly
# multi-root suffix-anchor and lossy-label cases), so their floors are
# unchanged. Every other floor also measures unchanged and stays as is.
CLEAN_FLOOR_BY_AXIS = {
    "golden": 3,
    "baseline-chains": 1,
    "monocycles": 3,
    "retained-fused": 3,
    "fusion-bracket": 4,
    "ring-assembly-primed": 3,
    "multiplicative-nested": 2,
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


# The exact CURATED names measured SPANS_NONE on 2026-09-11, RE-MEASURED
# after the per-occurrence regrouping follow-on -- 8 of 49, down from 10.
# Two names LEFT this set as part of that follow-on and needed no edit here
# (the removal itself is the record): `1,1,1-trichloro-2,2-bis(4-
# chlorophenyl)ethane` (DDT) and `tris(2-chloroethyl) phosphate` are now
# CLEAN, each recovered by `collapse_cloned_blocks` folding a `bis`/`tris`-
# cloned block back to the one written occurrence that names it (see
# `.superpowers/sdd/followon-regroup/report.md`). What remains is lossy
# OPSIN labels (duplicated tokens, e.g. `[1,2,4]triazolo[4,3-a]pyridine`) and
# the multi-root suffix-anchor limitation (`sodium acetate`) -- neither is
# per-occurrence-regrouping's residue; both are recorded, separate follow-on
# work. It is a CEILING, not a target: a name leaving this set (getting
# fixed) needs no edit here and never fails the test below; a name NOT in
# this set showing up as SPANS_NONE is a genuine new regression.
KNOWN_SPANS_NONE_CURATED = frozenset({
    "[1,2,4]triazolo[4,3-a]pyridine",
    "1,1'-bi(cyclohexane)",
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
