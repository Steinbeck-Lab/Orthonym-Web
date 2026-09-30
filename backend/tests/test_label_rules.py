"""Token ownership and the token-kind table, on stored traces (no JVM)."""

import pytest

from app.label_rules import (
    CONTEXTUAL, CORE, GLUE, PREFIX, balance, indicated_h_items, is_known, locant_items,
    stereo_items,
)
from app.opsin_trace import WrittenToken
from app.token_owner import Owner, adopt_orphan_tokens, assign_owners, innermost_bracket, written_brackets
from tests.fixtures.traces import load_traces

TRACES = load_traces()
IBUPROFEN = "2-[4-(2-methylpropyl)phenyl]propanoic acid"
CAFFEINE = "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione"


def _tok(t, text, start_at=0):
    return next(tok for tok in t.tokens if tok.span[0] >= start_at and t.text[tok.span[0]:tok.span[1]] == text)


# -- the table ----------------------------------------------------------------

def test_every_corpus_kind_is_in_the_table():
    kinds = {tok.kind for t in TRACES.values() for tok in t.tokens}
    missing = sorted(k for k in kinds if not is_known(k))
    assert missing == [], f"add these OPSIN kinds to label_rules: {missing}"


def test_the_four_roles_are_disjoint():
    assert not (CORE & PREFIX) and not (CORE & CONTEXTUAL) and not (CORE & GLUE)
    assert not (PREFIX & CONTEXTUAL) and not (PREFIX & GLUE) and not (CONTEXTUAL & GLUE)


# -- item splitters -------------------------------------------------------------

def test_locant_items():
    assert locant_items("1,3,7-x", (0, 6)) == [("1", (0, 1)), ("3", (2, 3)), ("7", (4, 5))]
    assert locant_items("N,N-x", (0, 4)) == [("N", (0, 1)), ("N", (2, 3))]
    assert locant_items("4a,5-x", (0, 5)) == [("4a", (0, 2)), ("5", (3, 4))]


def test_indicated_h_items():
    assert indicated_h_items("1H,3H-x", (0, 6)) == [("1", (0, 2)), ("3", (3, 5))]
    assert indicated_h_items("3aH-x", (0, 4)) == [("3a", (0, 3))]


def test_stereo_items():
    assert stereo_items("(2S,3R)-x", (0, 8)) == [("2S", (1, 3)), ("3R", (4, 6))]
    assert stereo_items("rel-(1R,2S)-x", (0, 12)) == [("1R", (5, 7)), ("2S", (8, 10))]
    assert stereo_items("L-x", (0, 2)) == [("L", (0, 1))]
    assert stereo_items("trans-x", (0, 6)) == [("trans", (0, 5))]
    assert stereo_items("3,17beta-diol", (0, 9)) == [("3", (0, 1)), ("17beta", (2, 8))]


def test_balance_pulls_in_a_bare_bracket():
    text = "[1,2,4]triazolo[4,3-a]pyridine"
    assert balance(text, (1, len(text))) == (0, len(text))


# -- ownership -------------------------------------------------------------------

def test_written_brackets_match():
    t = TRACES[IBUPROFEN]
    assert written_brackets(t.tokens) == [(5, 21), (2, 28)]
    assert innermost_bracket(written_brackets(t.tokens), 7) == (5, 21)
    assert innermost_bracket(written_brackets(t.tokens), 0) is None


def test_a_bracket_locant_belongs_to_its_bracket_not_the_first_substituent():
    t = TRACES[IBUPROFEN]
    owners = assign_owners(t.tokens)
    assert owners[_tok(t, "2-").index] == Owner("bracket", (2, 28))
    assert owners[_tok(t, "4-").index] == Owner("bracket", (5, 21))
    methyl_key = _tok(t, "meth").owner
    assert owners[_tok(t, "2-", start_at=6).index] == Owner("part", methyl_key)


def test_the_hydro_prefix_belongs_to_the_ring_opsin_moved_it_into():
    t = TRACES[CAFFEINE]
    owners = assign_owners(t.tokens)
    ring = _tok(t, "purin").owner
    for text in ("3,7-", "di", "hydro", "1H-"):
        assert owners[_tok(t, text, start_at=16).index] == Owner("part", ring), text


def test_an_ending_follows_its_group_even_when_opsin_used_both_up():
    # "2,6-methano": meth, an, o are all used up and moved into the ring.
    t = TRACES["1,2,3,4,5,6-hexahydro-3,6,11-trimethyl-2,6-methano-3-benzazocin-8-ol"]
    owners = assign_owners(t.tokens)
    bridge = _tok(t, "meth", start_at=40)
    assert owners[_tok(t, "an", start_at=bridge.span[1]).index] == owners[bridge.index]


def test_a_used_up_suffix_stays_with_the_group_before_the_bracket_closes():
    t = TRACES["6-methoxy-2-[(4-methoxy-3,5-dimethylpyridin-2-yl)methylsulfinyl]-1H-benzimidazole"]
    owners = assign_owners(t.tokens)
    sulfin = _tok(t, "sulfin")
    assert owners[_tok(t, "yl", start_at=sulfin.span[1]).index] == Owner("part", sulfin.owner)


def test_a_core_token_never_belongs_to_a_bracket():
    t = WrittenToken
    tokens = [t(0, "ringAssemblyMultiplier", "bi", (0, 2)), t(1, "openbracket", "(", (2, 3)),
              t(2, "group", "cyclohex", (3, 11), owner=(0, 20)), t(3, "closebracket", ")", (11, 12))]
    assert assign_owners(tokens)[0] == Owner("part", (0, 20))


@pytest.mark.parametrize("name", sorted(TRACES))
def test_every_non_glue_token_has_an_owner(name):
    owners = assign_owners(TRACES[name].tokens)
    assert [i for i, o in owners.items() if o is None] == [], name


# -- Task 9 (ChEMBL census): a part OPSIN keeps no token of ---------------------------
SPIRO_NAMES = [
    "(2R,11'S,13'S)-11',13'-dimethyl-5,6'-dioxospiro[oxolane-2,14'-tetracyclo[8.7.0.0^4,9.0^13,17]heptadeca-4,9-diene]",
    "4'-(1,1-dimethylethan-1-yl)-6'-(4-nitrocyclohexa-1,3,5-trien-1-yl)spiro[1,3-dioxolane-2,10'-1-azabicyclo[4.3.1]decane]",
    "13'-hydroxy-5-methoxy-1,3,3-trimethylspiro[2,3-dihydro-1H-indole-2,5'-6-oxatricyclo[8.4.0.0^2,7]tetradeca-1,3,7,9,11,13-hexaene]",
]


@pytest.mark.parametrize("name", SPIRO_NAMES)
def test_a_spiro_skeleton_owns_the_tokens_opsin_kept_in_no_part(name):
    """OPSIN builds "spiro[...]" from its tokens and keeps none in the tree, so
    the root has a key and no token. Its used-up tokens used to fall backward to
    the substituent written before it ("methylspiro[...]" as one label)."""
    t = TRACES[name]
    root = next(p for p in t.parts if p.kind == "root")
    assert not any(tok.owner == root.span for tok in t.tokens)           # the premise
    before = assign_owners(t.tokens)
    spiro = _tok(t, "spiro")
    assert before[spiro.index] != Owner("part", root.span)                # the bug
    adopted = adopt_orphan_tokens(t)
    after = assign_owners(adopted.tokens)
    assert after[spiro.index] == Owner("part", root.span)
    inside = [tok for tok in adopted.tokens if tok.span[0] >= spiro.span[0] and tok.kind not in GLUE]
    assert inside and all(after[tok.index] == Owner("part", root.span) for tok in inside)
    assert adopt_orphan_tokens(adopted) == adopted                         # idempotent


def test_a_part_that_already_owns_a_token_never_adopts_more():
    t = TRACES[IBUPROFEN]
    assert adopt_orphan_tokens(t) is t
    t = TRACES[CAFFEINE]
    assert adopt_orphan_tokens(t) is t
