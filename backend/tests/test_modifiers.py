from rdkit import Chem

from app.explain import explain_name
from app.opsin_decompose import decompose
from tests.conftest import CAFFEINE

# A substituent-scoped indicated hydrogen: the "1H-" belongs to INDOLE, which
# is a substituent here, NOT to the propanoic acid parent.
TRYPTOPHAN = "2-amino-3-(1H-indol-3-yl)propanoic acid"
# Every one of this name's three modifiers is substituent-scoped (the
# 2,3-dihydro-1H- all belongs to the indene ring), and its parent is a
# two-carbon ethanone. Before the fix, "1" and "2" resolved onto the ethanone
# and "3" was dropped without a trace.
INDANONE = "1-(2,3-dihydro-1H-inden-5-yl)ethan-1-one"


def test_caffeine_modifiers_are_captured_with_locants():
    result = decompose(CAFFEINE)
    assert sorted((m.kind, m.locant) for m in result.modifiers) == [
        ("hydro", "3"),
        ("hydro", "7"),
        ("indicatedHydrogen", "1"),
    ]


def test_modifier_scope_distinguishes_parent_from_substituent():
    # The whole of Critical 1 in one assertion. A bare locant is meaningless
    # without the numbering it is written in; these two names both produce a
    # modifier at locant "1", and they mean different atoms in different
    # fragments. Verified against the pinned jar by dumping each modifier's
    # element path: caffeine's sit under word/root, tryptophan's under
    # word/bracket/substituent.
    assert {(m.locant, m.scope) for m in decompose(CAFFEINE).modifiers} == {
        ("3", "root"), ("7", "root"), ("1", "root"),
    }
    assert [(m.locant, m.scope) for m in decompose(TRYPTOPHAN).modifiers] == [
        ("1", "substituent"),
    ]
    assert {m.scope for m in decompose(INDANONE).modifiers} == {"substituent"}


def test_benzene_has_no_modifiers():
    assert decompose("benzene").modifiers == ()


def test_caffeine_exposes_a_modifier_segment_owning_no_atoms():
    result = explain_name(CAFFEINE)
    modifiers = [s for s in result["segments"] if s["kind"] == "modifier"]
    assert len(modifiers) == 1
    assert modifiers[0]["owns_atoms"] is False
    assert modifiers[0]["atom_indices"] == []
    assert sorted(c["locant"] for c in modifiers[0]["children"]) == ["1", "3", "7"]


def test_modifier_highlights_ring_atoms_owned_by_the_parent():
    result = explain_name(CAFFEINE)
    modifier = next(s for s in result["segments"] if s["kind"] == "modifier")
    parent = next(s for s in result["segments"] if s["kind"] == "parent")
    assert modifier["highlight_atoms"], "a modifier must still highlight something"
    assert set(modifier["highlight_atoms"]) <= set(parent["atom_indices"])


def test_caffeine_modifier_children_pin_the_exact_ring_nitrogen_each_names():
    # The suite's blind spot was WHICH atom a locant points at: the previous
    # invariant ("modifier highlight is a subset of parent atoms") is
    # satisfied by any parent atom, so the locant->atom association could be
    # scrambled and every test still passed. This pins it to concrete atom
    # indices, and independently checks the element with RDKit against the
    # returned SMILES -- not against the decomposition that produced them.
    result = explain_name(CAFFEINE)
    mol = Chem.MolFromSmiles(result["smiles"])
    modifier = next(s for s in result["segments"] if s["kind"] == "modifier")
    by_locant = {c["locant"]: c for c in modifier["children"]}

    assert by_locant["1"]["highlight_atoms"] == [1]
    assert by_locant["3"]["highlight_atoms"] == [3]
    assert by_locant["7"]["highlight_atoms"] == [7]
    for locant in ("1", "3", "7"):
        index = by_locant[locant]["highlight_atoms"][0]
        assert mol.GetAtomWithIdx(index).GetSymbol() == "N", (
            f"caffeine's {locant}H must sit on a ring nitrogen, got "
            f"{mol.GetAtomWithIdx(index).GetSymbol()}{index}"
        )
        assert f"N{locant}" in by_locant[locant]["explanation"]


def test_modifier_children_are_locant_sorted():
    result = explain_name(CAFFEINE)
    modifier = next(s for s in result["segments"] if s["kind"] == "modifier")
    assert [c["locant"] for c in modifier["children"]] == ["1", "3", "7"]


def test_a_substituents_indicated_hydrogen_is_never_put_on_a_parent_atom():
    # CRITICAL 1, reproduced. Tryptophan's "1H-" belongs to indole, a
    # SUBSTITUENT. Before the fix it resolved against the parent skeleton and
    # rendered as: [modifier] child 1 -> atoms=[2] "the C1 atom carries a
    # hydrogen here" -- atom 2 being a propanoic acid carbon, a confident
    # highlight of the wrong fragment entirely.
    result = explain_name(TRYPTOPHAN)
    assert result["error"] is None
    parent = next(s for s in result["segments"] if s["kind"] == "parent")
    parent_atoms = set(parent["atom_indices"])
    assert 2 in parent_atoms, "guard: atom 2 must still be a parent atom"

    modifier = next(s for s in result["segments"] if s["kind"] == "modifier")
    assert modifier["highlight_atoms"] == [], (
        "indole's 1H must not highlight any parent atom"
    )
    for child in modifier["children"]:
        assert child["kind"] == "unmapped", child
        assert child["highlight_atoms"] == [], child
        assert child["atom_indices"] == [], child
        # The exact wrong answer this test exists to forbid.
        assert "C1 atom" not in child["explanation"], child["explanation"]


def test_an_unresolvable_modifier_is_reported_not_dropped():
    # IMPORTANT 3 / spec section 6. This name's "3" used to vanish with no
    # trace at all -- explain.py did a bare `continue`. All three of its
    # modifiers are substituent-scoped, so all three must now be VISIBLE as
    # unmapped rather than invisible or silently mapped onto the ethanone.
    result = explain_name(INDANONE)
    assert result["error"] is None
    modifier = next(s for s in result["segments"] if s["kind"] == "modifier")
    assert sorted(c["locant"] for c in modifier["children"]) == ["1", "2", "3"]
    assert {c["kind"] for c in modifier["children"]} == {"unmapped"}
    assert modifier["highlight_atoms"] == []


def test_children_have_distinct_locants():
    from tests.conftest import GOLDEN_NAMES

    for name in GOLDEN_NAMES:
        result = explain_name(name)
        if result["error"]:
            continue
        for segment in result["segments"]:
            locants = [c["locant"] for c in segment["children"]]
            assert len(locants) == len(set(locants)), (
                f"{name}: {segment['label']} repeats a locant: {locants}"
            )
