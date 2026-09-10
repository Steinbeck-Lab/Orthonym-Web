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
