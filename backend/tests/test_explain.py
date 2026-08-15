from types import SimpleNamespace

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


def test_a_symmetric_molecule_unmaps_only_the_disputed_parts():
    # CCO above has a UNIQUE substructure match, so it never exercises the
    # all-matches-agree check at all -- an implementation that ignored
    # `matches` entirely would pass those two tests. Ibuprofen does exercise
    # it: its isobutyl group has two chemically-equivalent terminal methyls,
    # so the match against OPSIN's re-parse is not unique and different
    # matches disagree about which carbon is which. The disputed parts must
    # go `unmapped` and their siblings must SURVIVE -- per-part failure is
    # the entire bug this task removes. Asserted as behaviour, not as exact
    # atom counts, so OpenSTOUT naming changes cannot make it brittle.
    from app.explain import explain_molecule
    from app.openstout_service import get_primary_namer

    result = explain_molecule(
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O", namer=get_primary_namer()
    )
    assert result["error"] is None, result["error"]

    kinds = [s["kind"] for s in result["segments"]]
    assert "unmapped" in kinds, f"expected a disputed part, got {kinds}"

    mapped = [s for s in result["segments"] if s["kind"] != "unmapped"]
    assert mapped, "every part was unmapped -- one symmetry blanked the rest"
    for segment in mapped:
        assert segment["atom_indices"], f"{segment['label']} owns no atoms"
        for index in segment["atom_indices"]:
            assert 0 <= index < result["total_atoms"]

    for segment in result["segments"]:
        if segment["kind"] == "unmapped":
            assert segment["owns_atoms"] is False
            assert segment["atom_indices"] == []
            assert segment["highlight_atoms"] == []


class _SubstructureNamer:
    """A namer returning a name that describes only PART of the molecule.

    Not hypothetical plumbing: `explain_molecule` accepts any namer, and this
    is the cheapest way to reach the branch where OPSIN's re-parse is smaller
    than the user's own molecule.
    """

    def __init__(self, name: str):
        self._name = name

    def name_with_tree(self, smiles: str):
        return SimpleNamespace(name=self._name, tree=None)


def test_a_name_covering_only_part_of_the_molecule_maps_nothing():
    # "ethanol" substructure-matches into diethyl ether, so the match
    # SUCCEEDS while accounting for only 3 of the 5 heavy atoms. Without a
    # size guard every segment maps happily and the two leftover atoms belong
    # to no segment at all -- not even an `unmapped` one -- so they vanish
    # from the explanation silently. The old "rest" bucket used to absorb
    # them; nothing does now.
    from app.explain import explain_molecule

    result = explain_molecule("CCOCC", namer=_SubstructureNamer("ethanol"))
    assert result["total_atoms"] == 5
    assert result["segments"], "parts must still be reported, just unmapped"
    assert {s["kind"] for s in result["segments"]} == {"unmapped"}
    for segment in result["segments"]:
        assert segment["owns_atoms"] is False
        assert segment["atom_indices"] == []
