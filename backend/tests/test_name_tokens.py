"""The matcher decides every span in the feature, so it is tested as a pure
function over fabricated tokens -- no JVM, no OPSIN, fast enough to assert
every shape the census found.

Token streams below are real: they were measured from
app.opsin_tokenizer.tokenize on the named molecule.
"""

import pytest

from app.name_tokens import Run, Tok, assign_runs


def toks(*pairs):
    """Build a token list from (text, category), assigning offsets by
    walking the concatenation -- which is what tokenize guarantees.
    """
    out, cursor = [], 0
    for text, category in pairs:
        out.append(Tok(text, category, cursor, cursor + len(text)))
        cursor += len(text)
    return out


def test_a_single_token_part_takes_that_token_exactly():
    tokens = toks(("ethan", "alkaneStem"), ("ol", "suffix"))
    runs = assign_runs(tokens, ["ethan"])
    assert runs is not None
    assert (runs[0].start, runs[0].end) == (0, 5)


def test_a_multi_token_label_spans_the_whole_run():
    """benzo[a]pyrene. OPSIN merges benzo + [a] + pyren into ONE element
    valued 'benzo[a]pyren', so the label is three raw tokens wide. The old
    anchor scan tested equality against a SINGLE token and withheld all 40
    names of this class.
    """
    tokens = toks(
        ("benzo", "benzo"), ("[a]", "fusionBracket"),
        ("pyren", "trivialRing"), ("e", "e"),
    )
    runs = assign_runs(tokens, ["benzo[a]pyren"])
    assert runs is not None
    assert len(runs) == 1
    assert (runs[0].start, runs[0].end) == (0, 14)
    assert runs[0].consumed == (0, 1, 2)
    assert runs[0].fillers == (3,)


def test_a_leading_locant_and_multiplier_are_fillers_inside_the_run():
    """1,1'-biphenyl. The label is 'biphenyl' but the stream spells
    1,1'- | bi | phenyl, and the locant must fall inside the run so the
    locant span can be recovered from it later.
    """
    tokens = toks(
        ("1,1'-", "locant"), ("bi", "ringAssemblyMultiplier"),
        ("phenyl", "trivialRingSubstituent"),
    )
    runs = assign_runs(tokens, ["biphenyl"])
    assert runs is not None
    assert (runs[0].start, runs[0].end) == (0, 13)
    assert 0 in runs[0].fillers


def test_three_multiplied_clones_share_one_run():
    """Caffeine. _collect_parts walks the POST-buildFragment tree, where a
    multiplied substituent is already cloned once per locant, so 'methyl'
    arrives as THREE parts -- while the name spells it once, distinguished
    by the locant token 1,3,7-. One run, three part indices.
    """
    tokens = toks(
        ("1,3,7-", "locant"), ("tri", "diOrTri"),
        ("meth", "alkaneStemTrivial"), ("yl", "inlineSuffix"),
        ("-", "interSubstituentHyphen"),
    )
    runs = assign_runs(tokens, ["methyl", "methyl", "methyl"])
    assert runs is not None
    assert len(runs) == 1
    assert runs[0].part_indices == (0, 1, 2)
    assert (runs[0].start, runs[0].end) == (0, 16)


def test_the_same_text_at_two_places_gets_two_runs():
    """DDT's shape. Grouping these by text was the S2a defect: one span
    covered only the first occurrence, so the second occurrence's letters
    were named by text no span covered, and the claims guard threw the whole
    name away. Two occurrences must give two runs.
    """
    tokens = toks(
        ("chloro", "substituent"), ("-", "hyphen"),
        ("ethan", "alkaneStem"), ("-", "hyphen"),
        ("chloro", "substituent"),
    )
    runs = assign_runs(tokens, ["chloro", "ethan", "chloro"])
    assert runs is not None
    assert len(runs) == 3
    assert runs[0].part_indices == (0,)
    assert runs[2].part_indices == (2,)
    assert runs[0].start < runs[2].start


def test_two_adjacent_same_text_parts_written_separately_get_two_runs():
    """Adjacent parts sharing a text are only clones of one multiplied
    substituent when a single locant group of that size decorates them.
    Here each 'chloro' is written out with its own locant, so a guard that
    always merged adjacent equal texts would swallow the second occurrence.
    """
    tokens = toks(
        ("2-", "locant"), ("chloro", "substituent"), ("-", "hyphen"),
        ("3-", "locant"), ("chloro", "substituent"), ("-", "hyphen"),
        ("ethan", "alkaneStem"),
    )
    runs = assign_runs(tokens, ["chloro", "chloro", "ethan"])
    assert runs is not None
    assert [r.part_indices for r in runs] == [(0,), (1,), (2,)]


def test_a_run_does_not_grow_left_over_the_hyphen_its_neighbour_took():
    """interSubstituentHyphen is both a trailing and a leading category. The
    methyl run takes it on its right; the benzene run must not take it back
    on its left, or the two overlap and the whole name is withheld.
    """
    tokens = toks(
        ("meth", "alkaneStemTrivial"), ("yl", "inlineSuffix"),
        ("-", "interSubstituentHyphen"), ("benzen", "trivialRing"),
    )
    runs = assign_runs(tokens, ["meth", "benzen"])
    assert runs is not None
    assert [(r.start, r.end) for r in runs] == [(0, 7), (7, 13)]


def test_a_run_does_not_grow_right_over_the_next_runs_own_anchor():
    """'e' is a trailing category, but here it is also the next part's own
    anchor token. Growing right past the next anchor start would hand the
    same token to both runs.
    """
    tokens = toks(("eth", "alkaneStem"), ("e", "e"))
    runs = assign_runs(tokens, ["eth", "e"])
    assert runs is not None
    assert [(r.start, r.end) for r in runs] == [(0, 3), (3, 4)]


def test_runs_never_overlap_and_always_increase():
    tokens = toks(
        ("meth", "alkaneStemTrivial"), ("yl", "inlineSuffix"),
        ("-", "hyphen"), ("benzen", "trivialRing"),
    )
    runs = assign_runs(tokens, ["methyl", "benzen"])
    assert runs is not None
    for earlier, later in zip(runs, runs[1:]):
        assert earlier.end <= later.start


def test_a_label_that_is_not_a_subsequence_withholds_everything():
    """[1,2,4]triazolo[4,3-a]pyridine merges to 'azazazol[4,3-a]pyridin' --
    OPSIN DUPLICATES the az token, so the label is not any ordered
    concatenation of the stream. The named residue in the spec. It must
    return None for the whole name, never a partial guess.
    """
    tokens = toks(
        ("[", "bracket"), ("1,2,4", "locant"), ("]", "bracket"),
        ("tri", "diOrTri"), ("az", "hwHeteroAtom"),
        ("ol", "hantzschWidmanSuffix"), ("o", "o"),
        ("[4,3-a]", "fusionBracket"), ("pyridin", "trivialRing"),
        ("e", "e"),
    )
    assert assign_runs(tokens, ["azazazol[4,3-a]pyridin"]) is None


def test_no_tokens_withholds():
    assert assign_runs([], ["ethan"]) is None


def test_no_parts_withholds():
    """Nothing to anchor on, so nothing can be proven. Returning an empty
    list here would read as success to every caller.
    """
    assert assign_runs(toks(("ethan", "alkaneStem")), []) is None


def test_purin_does_not_reach_back_over_the_modifier_region():
    """Regression for fix round 1: caffeine's REAL token stream (measured
    from opsin_tokenizer.tokenize on
    "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione"), which the first draft
    of this module got wrong even though all 9 fabricated-stream tests above
    passed against it.

    Part texts here are the bare stems `token_for` builds ('meth', 'purin',
    'one'), not the merged 'methyl'/'purine'/'dione'. Between 'meth' and
    'purin' sits an entire second locanted modifier run
    (3,7-di|hydro|-|1H-) that belongs to NEITHER part. The first draft's
    unbounded interior skip let 'purin' reach across all of it and swallow
    the whole region as filler -- 'purin' does occur, standalone, nowhere
    else in the stream, so the only way to satisfy it at all was to skip
    everything in between. The fix requires the CONTIGUOUS run for 'purin'
    to start exactly at its own token (index 10, offset 31) and grow right
    only over `_TRAILING` categories (picking up the elided 'e' to read
    "purine"), never left across `bigCapitalH`, which is not in `_LEADING`.
    """
    tokens = toks(
        ("1,3,7-", "locant"), ("tri", "diOrTri"),
        ("meth", "alkaneStemTrivial"), ("yl", "inlineSuffix"),
        ("-", "interSubstituentHyphen"), ("3,7-", "locant"),
        ("di", "diOrTri"), ("hydro", "hydro"),
        ("-", "hyphen"), ("1H-", "bigCapitalH"),
        ("purin", "trivialRing"), ("e", "e"),
        ("-", "hyphen"), ("2,6-", "locant"),
        ("di", "diOrTri"), ("one", "nonAcidStemSuffix"),
    )
    name = "".join(t.text for t in tokens)
    assert name == "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione"

    runs = assign_runs(tokens, ["meth", "purin", "one"])

    assert runs is not None
    assert len(runs) == 3
    meth_run, purin_run, one_run = runs

    # The bug: 'purin' must not extend left of its own token (offset 31),
    # swallowing the modifier region between 'meth' and 'purin'.
    assert purin_run.start == 31
    assert name[purin_run.start:purin_run.end] == "purine"

    # The modifier region itself belongs to neither run -- it is a separate
    # referential part this module does not produce, and is left uncovered.
    assert name[meth_run.end:purin_run.start] == "3,7-dihydro-1H-"

    assert name[meth_run.start:meth_run.end] == "1,3,7-trimethyl-"
    assert name[one_run.start:one_run.end] == "-2,6-dione"

    # The suffix run's OWN left-growth recovers the plain hyphen that
    # 'purin's right-growth deliberately left behind, so "-2,6-dione" is
    # whole -- not stolen by the previous run, not dropped by this one.
    for earlier, later in zip(runs, runs[1:]):
        assert earlier.end <= later.start


# ---------------------------------------------------------------------------
# find_modifier_run: assign_runs itself never covers the hydro / indicated-
# hydrogen region -- it has no group text of its own to anchor on. These
# tests use the same real caffeine token stream as
# test_purin_does_not_reach_back_over_the_modifier_region above.
# ---------------------------------------------------------------------------


def _caffeine_tokens():
    return toks(
        ("1,3,7-", "locant"), ("tri", "diOrTri"),
        ("meth", "alkaneStemTrivial"), ("yl", "inlineSuffix"),
        ("-", "interSubstituentHyphen"), ("3,7-", "locant"),
        ("di", "diOrTri"), ("hydro", "hydro"),
        ("-", "hyphen"), ("1H-", "bigCapitalH"),
        ("purin", "trivialRing"), ("e", "e"),
        ("-", "hyphen"), ("2,6-", "locant"),
        ("di", "diOrTri"), ("one", "nonAcidStemSuffix"),
    )


def test_caffeines_modifier_run_covers_exactly_the_gap_between_its_neighbours():
    """The pin: caffeine's modifier run must be [16, 31) -- the region
    `assign_runs` itself leaves uncovered between the methyl run's [0, 16)
    and the purine run's [31, 37).
    """
    from app.name_tokens import find_modifier_run

    tokens = _caffeine_tokens()
    name = "".join(t.text for t in tokens)
    runs = assign_runs(tokens, ["meth", "purin", "one"])
    assert runs is not None

    modifier = find_modifier_run(tokens, runs)
    assert modifier is not None
    assert (modifier.start, modifier.end) == (16, 31)
    assert name[modifier.start:modifier.end] == "3,7-dihydro-1H-"


def test_the_modifier_run_does_not_walk_back_over_a_neighbours_hyphen():
    """Regression for the exact bug name_spans.py's own MODIFIER_KEY branch
    was fixed for: without the "already claimed" bound, growing left from
    the first mark walks back over the methyl run's own trailing hyphen
    (index 4) and produces [15, 31) against the methyl's [0, 16) -- an
    overlap.
    """
    from app.name_tokens import find_modifier_run

    tokens = _caffeine_tokens()
    runs = assign_runs(tokens, ["meth", "purin", "one"])
    assert runs is not None

    modifier = find_modifier_run(tokens, runs)
    assert modifier is not None
    methyl_run = runs[0]
    assert modifier.start >= methyl_run.end
    assert modifier.start == 16


def test_no_modifier_marks_returns_none():
    from app.name_tokens import find_modifier_run

    tokens = toks(("meth", "alkaneStemTrivial"), ("yl", "inlineSuffix"))
    runs = assign_runs(tokens, ["meth"])
    assert runs is not None
    assert find_modifier_run(tokens, runs) is None


def test_locant_subspans_walked_cursor_does_not_confuse_a_prefix_locant():
    """Moved from test_name_spans.py (Task 7): `_locant_subspans` now lives
    in this module, since `explain.py`'s `_locants_within` is its only live
    caller -- `name_spans.py` (deleted in this branch; read it at
    `9908574^`)'s own use was deleted with that module. (`_MULTIPLIER_
    CATEGORIES`/`_MULTIPLIER_VALUES`, mentioned here previously, moved to
    this module for the same reason but were later deleted outright, along
    with `explain.py`'s `_compute_claims`, once per-occurrence regrouping
    made the claims guard they served unreachable -- see the follow-on
    regroup report.)

    No golden name has a locant token where one locant is a prefix of the
    next (e.g. "11" then "1"), so this branch -- the walked cursor
    documented as preventing exactly this collision -- is otherwise never
    exercised. A naive `text.find(piece)` search (no cursor) would find "1"
    INSIDE "11" at index 0 instead of the real standalone "1" at index 3.
    """
    from app.name_tokens import _locant_subspans
    from app.opsin_tokenizer import Token

    token = Token(text="11,1-", category="locant", start=100, end=105)
    found = _locant_subspans(token)
    assert found["11"] == (100, 102)
    assert found["1"] == (103, 104)


def test_locant_subspans_keeps_the_first_of_a_repeated_locant():
    """A locant written twice in one token keeps its first span; a later
    occurrence overwriting it would point the locant child at the wrong
    characters.
    """
    from app.name_tokens import _locant_subspans
    from app.opsin_tokenizer import Token

    token = Token(text="1,3,1-", category="locant", start=10, end=16)
    assert _locant_subspans(token)["1"] == (10, 11)
