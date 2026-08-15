from app.opsin_decompose import decompose, heavy_atom_indices
from tests.conftest import CAFFEINE


def test_caffeine_yields_three_separately_locanted_methyls():
    result = decompose(CAFFEINE)
    assert result is not None, "reflection unavailable — check OPSIN jar"

    subs = [p for p in result.parts if p.kind == "substituent"]
    assert [p.locant for p in subs] == ["1", "3", "7"]
    # Each methyl is one carbon plus three hydrogens in OPSIN's id space.
    assert [len(p.opsin_atom_ids) for p in subs] == [4, 4, 4]
    # The three methyls are disjoint.
    assert len(set().union(*(set(p.opsin_atom_ids) for p in subs))) == 12


def test_caffeine_root_is_a_single_part():
    result = decompose(CAFFEINE)
    roots = [p for p in result.parts if p.kind == "root"]
    assert len(roots) == 1


def test_root_records_its_suffix_token_names():
    # Caffeine's "-2,6-dione" reaches OPSIN as two "one" suffix tokens.
    # Task 7 needs these so an "-ol" is never described as a C=O.
    root = next(p for p in decompose(CAFFEINE).parts if p.kind == "root")
    assert root.suffix_texts == ("one", "one")


def test_alcohol_root_records_ol_not_one():
    root = next(
        p for p in decompose("4-tert-butylcyclohexan-1-ol").parts if p.kind == "root"
    )
    assert "ol" in root.suffix_texts


def test_caffeine_atoms_carry_ring_locants():
    result = decompose(CAFFEINE)
    by_index = {a.rdkit_index: a for a in result.atoms}
    assert len(by_index) == 14, "caffeine has 14 heavy atoms"
    # OPSIN numbers the purine ring; N1 and C2 must be labelled.
    assert by_index[1].element == "N" and "1" in by_index[1].locants
    assert by_index[2].element == "C" and "2" in by_index[2].locants


def test_unparseable_name_returns_none():
    assert decompose("not a chemical name at all") is None


def test_heavy_atom_indices_drops_hydrogens():
    result = decompose(CAFFEINE)
    subs = [p for p in result.parts if p.kind == "substituent"]
    # Each methyl is 4 OPSIN atoms (C + 3H) but only 1 heavy atom.
    for part in subs:
        assert len(heavy_atom_indices(result, part.opsin_atom_ids)) == 1


def test_owning_parts_partition_all_heavy_atoms():
    result = decompose(CAFFEINE)
    covered = set()
    for part in result.parts:
        indices = set(heavy_atom_indices(result, part.opsin_atom_ids))
        assert not (indices & covered), f"{part.text} overlaps an earlier part"
        covered |= indices
    assert covered == set(range(14))
