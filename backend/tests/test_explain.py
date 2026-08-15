import pytest

from app.explain import explain_name
from tests.conftest import CAFFEINE, GOLDEN_NAMES


def test_caffeine_is_no_longer_one_undecomposed_blob():
    result = explain_name(CAFFEINE)
    assert result["error"] is None
    kinds = {s["kind"] for s in result["segments"]}
    assert "unmapped" not in kinds
    assert {"substituent", "parent", "suffix"} <= kinds


def test_caffeine_has_three_methyls_at_1_3_and_7():
    result = explain_name(CAFFEINE)
    subs = [s for s in result["segments"] if s["kind"] == "substituent"]
    locants = sorted(c["locant"] for s in subs for c in s["children"])
    assert locants == ["1", "3", "7"]


def test_caffeine_suffix_children_are_c2_and_c6():
    result = explain_name(CAFFEINE)
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")
    assert sorted(c["locant"] for c in suffix["children"]) == ["2", "6"]


def test_caffeine_suffix_is_labelled_dione_and_described_as_carbonyl():
    result = explain_name(CAFFEINE)
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")
    assert suffix["label"] == "dione"
    assert "C=O" in suffix["explanation"]


def test_parent_labels_are_clean_stems_not_stem_plus_suffix():
    # Regression guard: root.text concatenates every token, so an unstripped
    # label renders as "purinoneone" / "hexol" / "ethol" / "propic acid".
    for name, expected in [
        (CAFFEINE, "purin"),
        ("4-tert-butylcyclohexan-1-ol", "hex"),
        ("ethanol", "eth"),
        ("benzene", "benzen"),
    ]:
        result = explain_name(name)
        parent = next(s for s in result["segments"] if s["kind"] == "parent")
        assert parent["label"] == expected, f"{name}: got {parent['label']!r}"


def test_an_alcohol_is_never_described_as_a_carbonyl():
    # Regression guard for the hardcoded-"one" defect: the suffix name must
    # come from the molecule's own suffix tokens, not a literal.
    result = explain_name("4-tert-butylcyclohexan-1-ol")
    suffixes = [s for s in result["segments"] if s["kind"] == "suffix"]
    assert suffixes, "an -ol name must produce a suffix segment"
    assert "C=O" not in suffixes[0]["explanation"]
    assert "-OH" in suffixes[0]["explanation"]


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_owning_segments_partition_all_heavy_atoms(name):
    result = explain_name(name)
    if result["error"]:
        pytest.skip(f"OPSIN cannot parse {name}")
    covered = set()
    for segment in result["segments"]:
        if not segment["owns_atoms"]:
            continue
        indices = set(segment["atom_indices"])
        assert not (indices & covered), f"{segment['label']} overlaps"
        covered |= indices
    assert covered == set(range(result["total_atoms"]))


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_referential_segments_own_no_atoms(name):
    result = explain_name(name)
    if result["error"]:
        pytest.skip(f"OPSIN cannot parse {name}")
    for segment in result["segments"]:
        if not segment["owns_atoms"]:
            assert segment["atom_indices"] == []


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_children_are_subsets_of_their_parent(name):
    result = explain_name(name)
    if result["error"]:
        pytest.skip(f"OPSIN cannot parse {name}")
    for segment in result["segments"]:
        owned = set(segment["atom_indices"])
        for child in segment["children"]:
            assert set(child["atom_indices"]) <= owned


def test_unparseable_name_returns_a_clear_error():
    result = explain_name("not a chemical name at all")
    assert result["error"]
    assert result["segments"] == []


def test_structure_in_path_still_works_and_indices_are_in_range():
    # Every other test here exercises explain_name. explain_molecule is the
    # OTHER path this task rewrites -- it remaps OPSIN's atom indices onto
    # the USER's molecule -- and nothing else covers it. An out-of-range
    # index here is the signature of a broken remap.
    from app.explain import explain_molecule
    from app.openstout_service import get_primary_namer

    result = explain_molecule("CCO", namer=get_primary_namer())
    assert result["error"] is None, result["error"]
    assert result["segments"], "structure-in path produced no segments"
    for segment in result["segments"]:
        for index in segment["atom_indices"] + segment["highlight_atoms"]:
            assert 0 <= index < result["total_atoms"], (
                f"{segment['label']}: index {index} outside "
                f"0..{result['total_atoms'] - 1}"
            )


def test_structure_in_path_never_emits_a_retired_segment_kind():
    # The old implementation emitted kind="rest" and kind="undecomposed".
    # Both were removed from SegmentKind in Task 6; if either survives here
    # the response will fail schema validation at the API boundary.
    from app.explain import explain_molecule
    from app.openstout_service import get_primary_namer

    result = explain_molecule("CCO", namer=get_primary_namer())
    kinds = {s["kind"] for s in result["segments"]}
    assert not (kinds & {"rest", "undecomposed"}), kinds
