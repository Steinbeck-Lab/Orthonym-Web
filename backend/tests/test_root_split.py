from app.opsin_decompose import decompose
from app.root_split import split_root
from tests.conftest import CAFFEINE


def _root(result):
    return next(p for p in result.parts if p.kind == "root")


def test_caffeine_root_splits_into_nine_ring_atoms_and_two_oxygens():
    result = decompose(CAFFEINE)
    split = split_root(result, _root(result))
    assert len(split.parent_atoms) == 9
    assert len(split.suffix_atoms) == 2
    assert not set(split.parent_atoms) & set(split.suffix_atoms)


def test_caffeine_suffix_oxygens_are_oxygens():
    result = decompose(CAFFEINE)
    split = split_root(result, _root(result))
    by_index = {a.rdkit_index: a for a in result.atoms}
    assert {by_index[i].element for i in split.suffix_atoms} == {"O"}


def test_caffeine_suffix_oxygens_hang_off_c2_and_c6():
    result = decompose(CAFFEINE)
    split = split_root(result, _root(result))
    assert sorted(split.suffix_locants.values()) == ["2", "6"]


def test_benzene_has_no_suffix_atoms():
    result = decompose("benzene")
    split = split_root(result, _root(result))
    assert split.suffix_atoms == ()
    assert len(split.parent_atoms) == 6


from app.opsin_decompose import DecomposedAtom, Decomposition, NamePart


def _fake(atoms, part_ids, smiles="CCO"):
    return Decomposition(
        smiles=smiles,
        atoms=tuple(atoms),
        parts=(NamePart("root", "x", None, tuple(part_ids), ()),),
    )


def test_degrades_to_all_parent_when_no_atom_has_a_numeric_locant():
    # Every locant is element-symbol style, so the numeric rule finds no
    # parent. It must hand back everything as parent, not call it all suffix.
    result = _fake(
        [DecomposedAtom(0, 1, "C", ("C",)), DecomposedAtom(1, 2, "O", ("O",))],
        [1, 2],
    )
    split = split_root(result, result.parts[0])
    assert split.parent_atoms == (0, 1)
    assert split.suffix_atoms == ()
    assert split.suffix_locants == {}


def test_degrades_to_all_parent_when_smiles_cannot_be_parsed():
    result = _fake(
        [DecomposedAtom(0, 1, "C", ("1",)), DecomposedAtom(1, 2, "O", ("O",))],
        [1, 2],
        smiles="this is not a smiles",
    )
    split = split_root(result, result.parts[0])
    assert split.parent_atoms == (0, 1)
    assert split.suffix_atoms == ()
