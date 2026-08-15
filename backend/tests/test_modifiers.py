from app.explain import explain_name
from app.opsin_decompose import decompose
from tests.conftest import CAFFEINE


def test_caffeine_modifiers_are_captured_with_locants():
    result = decompose(CAFFEINE)
    assert sorted((m.kind, m.locant) for m in result.modifiers) == [
        ("hydro", "3"),
        ("hydro", "7"),
        ("indicatedHydrogen", "1"),
    ]


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
