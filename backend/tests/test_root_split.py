from app.opsin_trace import trace
from app.root_split import split_root
from tests.conftest import CAFFEINE


def _root(t):
    return next(p for p in t.parts if p.kind == "root")


def test_caffeine_root_splits_into_nine_ring_atoms_and_two_oxygens():
    t = trace(CAFFEINE)
    split = split_root(t, _root(t).atoms)
    assert len(split.parent_atoms) == 9
    assert len(split.suffix_atoms) == 2
    assert not set(split.parent_atoms) & set(split.suffix_atoms)


def test_caffeine_suffix_oxygens_are_oxygens():
    t = trace(CAFFEINE)
    split = split_root(t, _root(t).atoms)
    by_index = {a.index: a for a in t.atoms}
    assert {by_index[i].element for i in split.suffix_atoms} == {"O"}


def test_caffeine_suffix_oxygens_hang_off_c2_and_c6():
    t = trace(CAFFEINE)
    split = split_root(t, _root(t).atoms)
    assert sorted(split.suffix_locants.values()) == ["2", "6"]


def test_benzene_has_no_suffix_atoms():
    t = trace("benzene")
    split = split_root(t, _root(t).atoms)
    assert split.suffix_atoms == ()
    assert len(split.parent_atoms) == 6
