from types import SimpleNamespace

import pytest
from rdkit import Chem

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
    # Filtered to kind == "substituent": a methyl segment's children now also
    # include TOKEN siblings ("tri", the "1,3,7-" locant token itself), which
    # carry locant=None and would otherwise blow up the sort below.
    locants = sorted(
        c["locant"] for s in subs for c in s["children"] if c["kind"] == "substituent"
    )
    assert locants == ["1", "3", "7"]


def test_caffeine_suffix_children_are_c2_and_c6():
    result = explain_name(CAFFEINE)
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")
    # Filtered to kind == "suffix" for the same reason as above.
    locants = sorted(c["locant"] for c in suffix["children"] if c["kind"] == "suffix")
    assert locants == ["2", "6"]


def test_caffeine_suffix_is_labelled_dione_and_described_as_carbonyl():
    result = explain_name(CAFFEINE)
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")
    assert suffix["label"] == "dione"
    assert "C=O" in suffix["explanation"]


def test_caffeine_child_text_never_fabricates_an_atom_label():
    # CRITICAL 2, asserted on the ACTUAL RENDERED STRING. describe_locant was
    # handed the OWNED atom's element while writing a sentence about parent
    # numbering, so it printed atoms that are not there. Verified before the
    # fix, both contradicting the spec appendix verbatim:
    #   substituent child 1 -> "Position 1 - the C1 atom."
    #                          position 1 is ring N1; C is the methyl
    #                          carbon's own element
    #   suffix child 2      -> "Position 2 - the group hangs off O2."
    #                          it hangs off C2; O is the suffix oxygen's
    #                          own element
    result = explain_name(CAFFEINE)
    substituent = next(s for s in result["segments"] if s["kind"] == "substituent")
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")

    sub_text = {c["locant"]: c["explanation"] for c in substituent["children"]}
    assert "C1" not in sub_text["1"], sub_text["1"]
    assert "C3" not in sub_text["3"], sub_text["3"]
    assert "C7" not in sub_text["7"], sub_text["7"]
    assert "1" in sub_text["1"]

    suf_text = {c["locant"]: c["explanation"] for c in suffix["children"]}
    assert "O2" not in suf_text["2"], suf_text["2"]
    assert "O6" not in suf_text["6"], suf_text["6"]
    assert "2" in suf_text["2"]


def test_no_child_anywhere_in_the_corpus_claims_an_atom_it_does_not_own():
    # Generalises the two caffeine cases above. A child sentence may name an
    # atom only in the form <Element><locant>. For every child that owns
    # atoms, assert none of the elements present in the molecule is written
    # against this child's locant unless a real atom the child highlights
    # actually is that element at that locant.
    for name in GOLDEN_NAMES:
        result = explain_name(name)
        if result["error"]:
            continue
        mol = Chem.MolFromSmiles(result["smiles"])
        for segment in result["segments"]:
            for child in segment["children"]:
                locant = child["locant"]
                if child["kind"] not in ("substituent", "suffix"):
                    continue
                for atom in mol.GetAtoms():
                    claim = f"{atom.GetSymbol()}{locant}"
                    assert claim not in child["explanation"], (
                        f"{name}: {segment['label']} child {locant} claims "
                        f"{claim!r}: {child['explanation']!r}"
                    )


def test_caffeine_locant_to_atom_association_is_pinned():
    # The reviewer's finding was that the locant->atom association could be
    # SCRAMBLED and all 75 tests still passed, because nothing pinned a
    # concrete index. These are the exact indices, cross-checked against the
    # returned SMILES with RDKit: each methyl child is one carbon, each
    # dione child is one oxygen.
    result = explain_name(CAFFEINE)
    mol = Chem.MolFromSmiles(result["smiles"])
    substituent = next(s for s in result["segments"] if s["kind"] == "substituent")
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")

    # Filtered to their own locant-bearing kind: token siblings ("tri", the
    # "1,3,7-"/"2,6-" locant tokens themselves) carry locant=None and would
    # otherwise collide into a spurious {None: []} entry.
    methyls = {
        c["locant"]: c["atom_indices"]
        for c in substituent["children"] if c["kind"] == "substituent"
    }
    assert methyls == {"1": [0], "3": [12], "7": [11]}
    for indices in methyls.values():
        assert mol.GetAtomWithIdx(indices[0]).GetSymbol() == "C"

    diones = {
        c["locant"]: c["atom_indices"]
        for c in suffix["children"] if c["kind"] == "suffix"
    }
    assert diones == {"2": [13], "6": [10]}
    for indices in diones.values():
        assert mol.GetAtomWithIdx(indices[0]).GetSymbol() == "O"


def test_a_root_that_names_no_suffix_is_not_split_into_one_called_suffix():
    # MINOR 7. "phenol" is a single retained <group> token naming the ring
    # AND its OH; the locant split still separates the oxygen (it carries
    # only the element-symbol locant "O"), but there are no <suffix> tokens
    # to take a name from, so the label fell through to the literal word
    # "suffix", which names nothing. No honest label exists, so the atoms
    # stay with the parent that does name them.
    result = explain_name("phenol")
    assert result["error"] is None
    labels = [s["label"] for s in result["segments"]]
    assert "suffix" not in labels, labels
    parent = next(s for s in result["segments"] if s["kind"] == "parent")
    assert len(parent["atom_indices"]) == result["total_atoms"]


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


# Replaces `pytest.skip(f"OPSIN cannot parse {name}")` at the head of the
# three parametrized invariant tests below (audit item
# explain-tests-skip-silently).
#
# Those three tests are parametrized over all 10 GOLDEN_NAMES, so the skip
# disarmed 30 assertions -- and it disarmed them precisely when name
# decomposition broke, which is the only time they matter. run-tests.sh exits
# 0 on "30 skipped", so the regression most likely to break /explain was also
# the one guaranteed to go unnoticed. conftest.py states the opposite policy
# in its own Redis comment: "a silently skipped integrity test is the same as
# no test."
#
# What these three protect is not cosmetic: they are what stops /explain and
# /teach highlighting the WRONG atoms for a part of a name -- a visibly
# incorrect chemistry claim, on the feature that exists to prove the engine
# is honest.
#
# All 10 names parse today (measured). If upstream ever legitimately drops
# one, this fails loudly and the corpus gets edited on purpose -- which is
# the review moment you want, not one to skip past.
_CORPUS_MUST_PARSE = (
    "GOLDEN_NAMES entry {name!r} no longer decomposes: {error}. "
    "These names are the fixed corpus the /explain invariants are measured "
    "against -- if OPSIN or the reflection shim genuinely changed, fix the "
    "cause or edit the corpus deliberately. Do not skip: skipping here "
    "disarms 30 assertions at exactly the moment they would have caught it."
)


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_owning_segments_partition_all_heavy_atoms(name):
    result = explain_name(name)
    assert not result["error"], _CORPUS_MUST_PARSE.format(name=name, error=result["error"])
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
    assert not result["error"], _CORPUS_MUST_PARSE.format(name=name, error=result["error"])
    for segment in result["segments"]:
        if not segment["owns_atoms"]:
            assert segment["atom_indices"] == []


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_children_are_subsets_of_their_parent(name):
    result = explain_name(name)
    assert not result["error"], _CORPUS_MUST_PARSE.format(name=name, error=result["error"])
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
    from app.orthonym_service import get_primary_namer

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
    from app.orthonym_service import get_primary_namer

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
    # atom counts, so Orthonym naming changes cannot make it brittle.
    from app.explain import explain_molecule
    from app.orthonym_service import get_primary_namer

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


def test_every_golden_name_still_decomposes():
    """Report a broken corpus ONCE, with the full list, instead of as ten
    near-identical failures across three parametrized tests.

    This is also the test that fails first and most legibly if the OPSIN
    reflection shim breaks -- opsin_decompose reaches into OPSIN's
    package-private parse tree, which is inherently version-fragile, and a
    vendor refresh is exactly when that happens.
    """
    broken = {
        name: explain_name(name)["error"]
        for name in GOLDEN_NAMES
        if explain_name(name)["error"]
    }
    assert not broken, f"{len(broken)} of {len(GOLDEN_NAMES)} golden names no longer decompose: {broken}"


def test_a_fusion_name_exposes_its_tokens_as_hoverable_children():
    from app.explain import explain_name

    payload = explain_name("benzo[a]pyrene")
    parent = next(s for s in payload["segments"] if s["kind"] == "parent")
    texts = [c["label"] for c in parent["children"]]
    assert "[a]" in texts
    bracket = next(c for c in parent["children"] if c["label"] == "[a]")
    assert bracket["owns_atoms"] is False
    assert bracket["atom_indices"] == []
    assert bracket["name_range"] is not None


def test_token_children_never_nest_deeper_than_one_level():
    """frontend/src/lib/nameTargets.js walks segment then child only. A
    grandchild would be silently unhoverable.
    """
    from app.explain import explain_name
    from tests.fixtures.explain_corpus import CURATED

    for _axis, name in CURATED:
        payload = explain_name(name)
        for segment in payload["segments"]:
            for child in segment["children"]:
                assert child["children"] == [], (name, child["label"])
