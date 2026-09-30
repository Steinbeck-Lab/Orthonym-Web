import pytest

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


# -- amino-acid and peptide roots: the group owns only its own atoms ------------
def _split(name):
    t = trace(name)
    root = next(p for p in t.parts if p.kind == "root")
    split = split_root(t, root.atoms)
    by_index = {a.index: a for a in t.atoms}
    return t, by_index, split


def _suffix_elements(name):
    t, by_index, split = _split(name)
    return sorted(by_index[i].element for i in split.suffix_atoms)


@pytest.mark.parametrize("name,suffix", [
    ("glycinamide", ["N", "O"]),                     # the alpha nitrogen is glycine's, not the amide's
    ("L-alaninamide", ["N", "O"]),
    ("L-alanyl-L-alaninamide", ["N", "O"]),
    ("L-prolyl-L-leucylglycinamide", ["N", "O"]),
    ("methyl L-alaninate", ["O", "O"]),              # the amino nitrogen is alanine's, not the ester's
    ("L-phenylalaninamide", ["C", "N", "O"]),        # C(=O)N; the alpha/beta carbons stay in the parent
    ("L-(+)-lactic acid", ["O", "O"]),               # the 2-hydroxyl oxygen stays in the parent
    # side-chain heteroatoms carry element locants too, but sit on Cbeta, not on the group's carbon
    ("L-serinamide", ["N", "O"]),
    ("methyl L-serinate", ["O", "O"]),
    ("L-threoninamide", ["N", "O"]),
    ("L-tyrosinamide", ["C", "N", "O"]),
    ("L-cysteinamide", ["N", "O"]),
    ("methyl L-methioninate", ["O", "O"]),
    ("N-methyl-D-aspartic acid", ["O", "O", "O", "O"]),   # two acids; the N-methylamino nitrogen is the stem's
])
def test_an_amino_acid_group_owns_only_its_own_atoms(name, suffix):
    assert _suffix_elements(name) == suffix


@pytest.mark.parametrize("name,element", [
    ("L-serinamide", "O"), ("methyl L-serinate", "O"), ("L-threoninamide", "O"),
    ("L-tyrosinamide", "O"), ("L-cysteinamide", "S"), ("methyl L-methioninate", "S"),
])
def test_a_side_chain_heteroatom_stays_in_the_parent(name, element):
    t, by_index, split = _split(name)
    side = [i for i in split.parent_atoms if by_index[i].element == element]
    assert side, name
    assert not any(by_index[i].element == element for i in split.suffix_atoms if element == "S")


def test_phenylalaninamide_keeps_alpha_and_beta_in_the_parent():
    t, by_index, split = _split("L-phenylalaninamide")
    greek = {i for i, a in by_index.items() if set(a.locants) & {"alpha", "beta"}}
    assert len(greek) == 2 and greek <= set(split.parent_atoms)


@pytest.mark.parametrize("name,suffix", [
    ("benzoic acid", ["C", "O", "O"]),               # the group's own carbon has only a Greek locant
    ("benzonitrile", ["C", "N"]),
    ("acetamide", ["N", "O"]),
    ("butanamide", ["N", "O"]),
    ("trans-cinnamic acid", ["C", "O", "O"]),
    ("benzeneacetic acid", ["C", "O", "O"]),
    ("benzaldehyde", ["C", "O"]),
    ("benzamide", ["C", "N", "O"]),
    ("salicylic acid", ["C", "O", "O"]),             # the phenolic oxygen stays in the parent
    ("mandelic acid", ["C", "O", "O"]),             # the alpha-hydroxyl and its carbon stay in the parent
    ("hexanedioic acid", ["O", "O", "O", "O"]),      # a counted group sits on both ends
    ("pentanedial", ["O", "O"]),
    ("naphthalene-2-sulfonate", ["O", "O", "O", "S"]),
    ("estra-1,3,5(10)-triene-3,17beta-diol", ["O", "O"]),
    # two root copies; the bridging oxygen has no locant but sits on a group carbon
    ("acetic anhydride", ["O", "O", "O"]),
])
def test_acids_nitriles_and_amides_keep_their_group_carbon(name, suffix):
    t = trace(name)
    by_index = {a.index: a for a in t.atoms}
    got = sorted(by_index[i].element for p in t.parts if p.kind == "root"
                 for i in split_root(t, p.atoms).suffix_atoms)
    assert got == suffix


def test_known_limitation_a_conjunctive_name_hands_its_chain_carbon_to_the_suffix():
    """KNOWN LIMITATION, pinned (not xfail): "cyclohexaneethanol" writes a ring
    and a chain into one root, and OPSIN gives the chain carbon next to the
    oxygen an element locant (alpha/C'), so the suffix 'ol' owns that CH2 as
    well as the oxygen. The right split is suffix = the O only. When this is
    fixed, this test should FLIP: change the expected suffix to ['O']."""
    assert _suffix_elements("cyclohexaneethanol") == ["C", "O"]
