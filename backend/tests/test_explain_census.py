"""The census classifier is the yardstick every coverage number is measured
with, so it gets its own tests (synthetic traces, no JVM)."""

from app.opsin_trace import Trace, TraceAtom, TracePart, WrittenToken
from app.token_owner import Owner
from rdkit import Chem

from scripts import explain_census as census
from scripts.explain_census import classify, smiles_path_lost

T = Trace(text="ab-1H", smiles="CN", atoms=(TraceAtom(0, 1, "C", ("1",)), TraceAtom(1, 2, "N", ("2",))),
          tokens=(), parts=())


def _n(kind, span, owns=(), label="ab", parent=None, lights=(), line=""):
    return {"id": f"x{kind}{span}", "kind": kind, "span": span, "owns": list(owns), "label": label,
            "parent": parent, "lights": list(lights), "line": line}


def test_clean():
    assert classify(T, [_n("parent", [0, 2], [0, 1])], {}) == ["CLEAN"]


def test_part_unplaced_and_gap():
    out = classify(T, [_n("parent", None, [0])], {})
    assert "PART_UNPLACED" in out and "ATOM_GAP" in out


def test_overlap_crossing_and_bad_span():
    out = classify(T, [_n("parent", [0, 3], [0, 1]), _n("suffix", [2, 5], [1]), _n("token", [4, 9])], {})
    assert {"ATOM_OVERLAP", "CROSSING", "BAD_SPAN"} <= set(out)


def test_orphan_token():
    assert "ORPHAN_TOKEN" in classify(T, [_n("parent", [0, 2], [0, 1])], {0: None, 1: Owner("part", (0, 2))})


def test_hydro_locant_on_the_wrong_atom():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("indicated_h", [3, 5], label="1H", lights=[1])]
    assert "HYDRO_WRONG" in classify(T, nodes, {})


def test_stereo_without_a_parent_or_on_the_wrong_atom():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("stereo", [0, 1], label="2S", lights=[0])]
    out = classify(T, nodes, {})
    assert "STEREO_NO_PARENT" in out and "STEREO_WRONG_ATOM" in out


def test_a_mark_on_an_atom_that_is_not_a_stereocentre_is_wrong():
    t = Trace(text="(2S)-x", smiles="CO", atoms=(TraceAtom(0, 1, "C", ("2",)), TraceAtom(1, 2, "O", ("1",))),
              tokens=(), parts=())
    nodes = [_n("parent", [0, 2], [0, 1]), _n("stereo", [1, 3], label="2S", parent="p", lights=[0])]
    assert "STEREO_WRONG_ATOM" in classify(t, nodes, {})


def test_an_unlit_locant_is_reported():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("locant", [3, 4], label="1", lights=[])]
    assert "LOCANT_UNLIT" in classify(T, nodes, {})


def test_an_unlit_anomer_mark_is_by_design_not_reported():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("locant", [3, 4], label="alpha", lights=[])]
    assert "LOCANT_UNLIT" not in classify(T, nodes, {})


def _lit_case(smiles):
    """atom 0 = root, atom 1 = substituent S (child locant "2" below), atom 2 =
    substituent U; every atom but S carries locant 2."""
    t = Trace(text="a-b-c", smiles=smiles,
              atoms=(TraceAtom(0, 1, "C", ("2",)), TraceAtom(1, 2, "C", ("1",)), TraceAtom(2, 3, "C", ("2",))),
              tokens=(), parts=(TracePart(0, "root", (0, 1), None, (0,)),
                                TracePart(1, "substituent", (2, 3), None, (1,)),
                                TracePart(2, "substituent", (4, 5), None, (2,))))
    parent = _n("substituent", [2, 3], [1], label="b")
    nodes = [_n("parent", [0, 1], [0], label="a"), parent, _n("substituent", [4, 5], [2], label="c")]
    return t, nodes, parent


def test_a_locant_lighting_an_atom_of_an_unrelated_part_is_reported():
    t, nodes, parent = _lit_case("C.C.C")        # S is bonded to nothing
    nodes.append(_n("locant", [2, 3], label="2", parent=parent["id"], lights=[2]))
    assert "LIT_ATOM_FOREIGN" in classify(t, nodes, {})


def test_a_locant_lighting_the_bonded_parent_position_is_clean():
    t, nodes, parent = _lit_case("CC.C")         # S is bonded to the root atom that carries 2
    nodes.append(_n("locant", [2, 3], label="2", parent=parent["id"], lights=[0]))
    assert "LIT_ATOM_FOREIGN" not in classify(t, nodes, {})


def test_a_locant_lighting_its_own_atom_is_clean():
    t, nodes, parent = _lit_case("C.C.C")
    nodes.append(_n("locant", [2, 3], label="1", parent=parent["id"], lights=[1]))
    assert "LIT_ATOM_FOREIGN" not in classify(t, nodes, {})


def _chain_case(lights):
    """"3-x-oxy-root": the leading locant sits in front of substituent P (atom 2,
    carrying the number 3 itself), which is joined to the following substituent
    Q (atom 1), which is bonded to the root atom 0 that carries 3."""
    t = Trace(text="3-x-o-r", smiles="COC",
              atoms=(TraceAtom(0, 1, "C", ("3",)), TraceAtom(1, 2, "O", ("O",)), TraceAtom(2, 3, "C", ("3",))),
              tokens=(WrittenToken(0, "group", "x", (2, 3), (2, 3)),
                      WrittenToken(1, "group", "oxy", (4, 5), (4, 5))),
              parts=(TracePart(0, "root", (6, 7), None, (0,)),
                     TracePart(1, "substituent", (4, 5), None, (1,)),
                     TracePart(2, "substituent", (2, 3), None, (2,))))
    p = _n("substituent", [2, 3], [2], label="x")
    nodes = [_n("parent", [6, 7], [0], label="r"), _n("substituent", [4, 5], [1], label="o"), p,
             _n("locant", [0, 1], label="3", parent=p["id"], lights=lights)]
    return t, nodes


def test_a_chained_substituent_lighting_its_own_attachment_atom_is_reported():
    """The round-1 oseltamivir behaviour: "3-pentan-3-yloxy" lit pentan's own C3."""
    t, nodes = _chain_case([2])
    assert "LIT_ATOM_FOREIGN" in classify(t, nodes, {})


def test_a_chained_substituent_lighting_the_parent_position_is_clean():
    t, nodes = _chain_case([0])
    assert "LIT_ATOM_FOREIGN" not in classify(t, nodes, {})


# -- final review classes (synthetic, no JVM) ---------------------------------------------

def _words(text, smiles, atoms, tokens, parts=()):
    return Trace(text=text, smiles=smiles, atoms=tuple(atoms), tokens=tuple(tokens), parts=tuple(parts))


def test_a_functional_word_no_part_starts_at_is_swallowed():
    t = _words("ethyl ketone", "CC(=O)C",
               [TraceAtom(0, 1, "C", ("1",)), TraceAtom(1, 2, "C", ()), TraceAtom(2, 3, "O", ()), TraceAtom(3, 4, "C", ("1",))],
               [WrittenToken(0, "group", "eth", (0, 3), None), WrittenToken(1, "functionalGroup", "ketone", (6, 12), None)])
    swallowed = [_n("substituent", [0, 12], [0, 1, 2, 3], label="ethyl ketone")]
    assert "FUNCTION_SWALLOWED" in classify(t, swallowed, {})
    own = [_n("substituent", [0, 5], [0, 3], label="ethyl"), _n("suffix", [6, 12], [1, 2], label="ketone")]
    assert "FUNCTION_SWALLOWED" not in classify(t, own, {})


def test_a_plain_alkyl_owning_a_heteroatom_is_reported_and_an_isotopic_hydrogen_is_not():
    t = _words("methyl", "CO", [TraceAtom(0, 1, "C", ("1",)), TraceAtom(1, 2, "O", ())], [])
    assert "ALKYL_HETERO" in classify(t, [_n("substituent", [0, 6], [0, 1], label="methyl")], {})
    d = _words("methyl", "C[2H]", [TraceAtom(0, 1, "C", ("1",)), TraceAtom(1, 2, "H", ())], [])
    assert "ALKYL_HETERO" not in classify(d, [_n("substituent", [0, 6], [0, 1], label="methyl")], {})


def test_a_suffix_that_owns_a_hydrogen_is_reported():
    t = _words("ol", "OC", [TraceAtom(0, 1, "O", ("O",)), TraceAtom(1, 2, "H", ())], [])
    assert "SUFFIX_OWNS_H" in classify(t, [_n("suffix", [0, 2], [0, 1], label="ol")], {})
    assert "SUFFIX_OWNS_H" not in classify(t, [_n("suffix", [0, 2], [0], label="ol"), _n("parent", [0, 2], [1])], {})


def test_an_oxidation_number_must_light_the_part_written_before_it():
    t = _words("copper(II) sulfate", "[Cu+2].S", [TraceAtom(0, 1, "Cu", ()), TraceAtom(1, 2, "S", ())],
               [WrittenToken(0, "oxidationNumberSpecifier", "(ii)", (6, 10), None)])
    base = [_n("parent", [0, 6], [0], label="copper"), _n("parent", [11, 18], [1], label="sulfate")]
    ok = base + [_n("token", [6, 10], [], label="(II)", lights=[0])]
    wrong = base + [_n("token", [6, 10], [], label="(II)", lights=[1])]
    assert "OXIDATION_WRONG" not in classify(t, ok, {})
    assert "OXIDATION_WRONG" in classify(t, wrong, {})


ISOBUTANE = _words("methylpropane", "CC(C)C", [TraceAtom(i, i + 1, "C", ()) for i in range(4)], [])


def test_a_smiles_path_that_keeps_symmetric_parts_loses_nothing():
    nodes = [_n("substituent", [0, 6], [0], label="methyl"), _n("parent", [6, 13], [1, 2, 3], label="propane")]
    assert smiles_path_lost(ISOBUTANE, nodes) == []
    assert "SMILES_PATH_LOST" not in classify(ISOBUTANE, nodes, {})


def test_a_part_the_smiles_path_leaves_unmapped_is_reported(monkeypatch):
    def drop_all(mol, opsin_mol, nodes, name=""):
        return [{**n, "owns": [], "lights": [], "atoms_unmapped": True} for n in nodes]
    monkeypatch.setattr(census, "_remap_nodes", drop_all)
    nodes = [_n("substituent", [0, 6], [0], label="methyl"), _n("parent", [6, 13], [], label="propane")]
    assert smiles_path_lost(ISOBUTANE, nodes) == ["methyl"]
    assert "SMILES_PATH_LOST" in classify(ISOBUTANE, nodes, {})


def test_a_part_the_smiles_path_puts_on_another_element_is_reported(monkeypatch):
    t = _words("ethanol", "CCO", [TraceAtom(0, 1, "C", ()), TraceAtom(1, 2, "C", ()), TraceAtom(2, 3, "O", ())], [])

    def wrong_atom(mol, opsin_mol, nodes, name=""):
        carbon = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C")
        return [{**n, "owns": [carbon] * len(n["owns"]), "atoms_unmapped": False} for n in nodes]
    monkeypatch.setattr(census, "_remap_nodes", wrong_atom)
    assert smiles_path_lost(t, [_n("suffix", [0, 2], [2], label="ol")]) == ["ol"]


TARTARIC = _words("tartaric", "O[C@@H](C(=O)O)[C@@H](C(=O)O)O", [TraceAtom(i, i + 1, "C", ()) for i in range(9)], [])


def _twin_swap(mol, opsin_mol, nodes, name=""):
    # every node through the identity, except that the two centres (atoms 1 and 5) are swapped
    swap = {1: 5, 5: 1}
    return [{**n, "owns": [swap.get(a, a) for a in n["owns"]], "lights": [swap.get(a, a) for a in n["lights"]],
             "atoms_unmapped": False} for n in nodes]


def test_a_stereo_mark_mapped_onto_the_mirror_twin_is_reported(monkeypatch):
    monkeypatch.setattr(census, "SHUFFLES", 1)
    nodes = [_n("stereo", [0, 2], label="2R", lights=[1])]
    monkeypatch.setattr(census, "_typed_in_another_order",
                        lambda smiles, seed: (Chem.MolFromSmiles(smiles), Chem.MolFromSmiles(smiles)))
    monkeypatch.setattr(census, "_remap_nodes", _twin_swap)
    assert smiles_path_lost(TARTARIC, nodes) == ["2R"]


def test_nodes_mapped_through_different_matches_are_reported_by_their_overlap(monkeypatch):
    monkeypatch.setattr(census, "SHUFFLES", 1)
    monkeypatch.setattr(census, "_typed_in_another_order",
                        lambda smiles, seed: (Chem.MolFromSmiles(smiles), Chem.MolFromSmiles(smiles)))

    def split(mol, opsin_mol, nodes, name=""):     # the second node goes through the swapped match
        swap = {2: 3, 3: 2}
        return [nodes[0] | {"atoms_unmapped": False},
                {**nodes[1], "owns": [swap.get(a, a) for a in nodes[1]["owns"]], "atoms_unmapped": False}]
    monkeypatch.setattr(census, "_remap_nodes", split)
    t = _words("ab", "CCCC", [TraceAtom(i, i + 1, "C", ()) for i in range(4)], [])
    nodes = [_n("substituent", [0, 1], [0, 2]), _n("parent", [1, 2], [1, 3])]
    assert set(smiles_path_lost(t, nodes)) == {"ab"}
