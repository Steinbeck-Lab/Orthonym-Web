"""Every hover line says only what is true of the molecule on screen (the 2026-10-01
hover-text audit). The glossary names a bare group "on its own" and adds what the
real atoms carry, measured; hydrogen-locant, anomer, spiro, stereo, isotope and parent
lines say what their mark means. Exact strings: the text is looked up and counted,
never generated, so any change to a line is a change to this file."""

import pytest
from rdkit import Chem

from app.explain_tree import build_nodes
from app.glossary import describe_locant, describe_part
from app.opsin_trace import Trace, TraceAtom, trace
from scripts.explain_census import false_hover_lines


def _mol(smiles):
    return Chem.MolFromSmiles(smiles)


def _trace(smiles):
    mol = _mol(smiles)
    return Trace(text="x" * 40, smiles=smiles, tokens=(), parts=(),
                 atoms=tuple(TraceAtom(a.GetIdx(), a.GetIdx() + 1, a.GetSymbol(), ()) for a in mol.GetAtoms()))


def _node(kind, label, owns=(), lights=(), line="", copies=1):
    return {"id": f"{kind}-{label}", "kind": kind, "span": None, "owns": list(owns), "label": label,
            "parent": None, "lights": list(lights), "line": line, "copies": copies}


# -- 1. the census check: it reads each claim and measures it, by its own rules ----------

BENZYL_ALCOHOL = _trace("OCc1ccccc1")


@pytest.mark.parametrize("line,false", [
    ('"methyl" is a CH3 group — one carbon with three hydrogens.', True),          # the old line
    ('"methyl" is a one-carbon group (CH3 on its own).', True),                    # the clause is missing
    ('"methyl" is a one-carbon group (CH3 on its own). Here its carbon carries 3 hydrogens; '
     'other groups take the rest.', True),                                         # the wrong count
    ('"methyl" is a one-carbon group (CH3 on its own). Here its carbon carries 2 hydrogens; '
     'other groups take the rest.', False),
    ("reworded", False),                                                          # claims nothing
    ('"methyl" carries hydrogens, somehow.', True),                               # a claim it cannot read
])
def test_the_census_reads_a_group_line_and_counts_the_atoms(line, false):
    nodes = [_node("substituent", "methyl", owns=[1], lights=[1], line=line)]
    assert bool(false_hover_lines(BENZYL_ALCOHOL, nodes)) == false


def test_the_census_checks_a_hydrogen_locant_against_its_lit_atom():
    t = _trace("Cn1ccc2ccccc21")                                   # 1-methyl-1H-indole: N1 is atom 1
    said = [_node("indicated_h", "1H", lights=[1], line="Position 1 — the N1 atom carries a hydrogen here.")]
    assert false_hover_lines(t, said)
    taken = "Position 1 — the name puts a hydrogen on the N1 atom; here a group or bond named elsewhere takes its place."
    assert not false_hover_lines(t, [_node("indicated_h", "1H", lights=[1], line=taken)])


def test_the_census_checks_what_a_mark_means():
    t = _trace("CC(N)C(=O)O")
    fixes = '"{}" fixes the three-dimensional arrangement at the positions it names.'
    for label in ("D", "DL", "rac", "+-", "+", "E", "R", "cis", "erythro"):
        assert false_hover_lines(t, [_node("stereo", label, line=fixes.format(label))]), label
    assert not false_hover_lines(t, [_node("stereo", "2S", line=fixes.format("2S"))])
    assert false_hover_lines(t, [_node("stereo", "2S", line='"2S" marks a racemate: an equal mix of the two '
                                                              'mirror-image forms.')])


def test_the_census_checks_a_spiro_line_against_the_rings_it_lights():
    t = _trace("C1CCCC12CCCCC2")
    old = _node("token", "spiro[4.5]", lights=range(10), line='"spiro[4.5]" marks one atom shared between two rings.')
    new = _node("token", "spiro[4.5]", lights=range(10),
                line='"spiro[4.5]" names two rings that share one atom; 4 and 5 count the other atoms in each ring.')
    wrong = _node("token", "spiro[4.5]", lights=range(10),
                  line='"spiro[4.5]" names two rings that share one atom; 5 and 4 count the other atoms in each ring.')
    assert false_hover_lines(t, [old]) and false_hover_lines(t, [wrong]) and not false_hover_lines(t, [new])


def test_the_census_checks_an_anomer_against_the_group_on_its_carbon():
    t = _trace("COC1OC(CO)C(O)C(O)C1O")                            # a methyl glycoside: C2 is anomeric
    old = '"beta" names the anomer: which way the OH on the ring carbon next to the ring oxygen points.'
    assert false_hover_lines(t, [_node("locant", "beta", lights=[2], line=old)])
    oh = ('"beta" names the anomer: which way the group on the ring carbon next to the ring oxygen points, '
          "relative to the sugar's reference stereocentre. Here that group is an OH.")
    assert false_hover_lines(t, [_node("locant", "beta", lights=[2], line=oh)])


def test_the_census_checks_a_parent_against_the_name_and_its_rings():
    salt = _trace("CC(=O)[O-].[Na+]")
    one = '"sodium" is the core skeleton the rest of the name is built around. It has 1 atom.'
    nodes = [_node("parent", "sodium", owns=[4], line=one), _node("parent", "acet", owns=[0, 1], line="x")]
    assert false_hover_lines(salt, nodes)
    tetralin = _trace("C1CCc2ccccc2C1")
    naph = ('"naphthalene" is naphthalene — two fused benzene rings. It is the core the rest of the name is '
            'built around, and it holds 10 atoms.')
    assert false_hover_lines(tetralin, [_node("parent", "naphthalene", owns=range(10), line=naph)])


def test_the_census_checks_an_isotope_label_for_a_locant():
    t = _trace("[2H]C([2H])([2H])O")
    old = '"2H3" is an isotope label: it says which isotope sits at the positions it names.'
    assert false_hover_lines(t, [_node("token", "2H3", lights=[0, 2, 3], line=old)])
    assert not false_hover_lines(t, [_node("token", "3-2H", line=old.replace("2H3", "3-2H"))])


# -- 2. a group with a bare formula: the base line, plus the hydrogens its atoms carry -----

def test_a_group_on_its_own_gets_the_base_line_only():
    assert describe_part("substituent", "methyl", 1, mol=_mol("Cc1ccccc1"), atoms=[0]) == \
        '"methyl" is a one-carbon group (CH3 on its own).'
    assert describe_part("substituent", "methyl", 1) == '"methyl" is a one-carbon group (CH3 on its own).'


def test_a_group_whose_atoms_carry_fewer_hydrogens_says_how_many():
    assert describe_part("substituent", "methyl", 1, mol=_mol("OCc1ccccc1"), atoms=[1]) == (
        '"methyl" is a one-carbon group (CH3 on its own). Here its carbon carries 2 hydrogens; '
        'other groups take the rest.')
    assert "Here its carbon carries no hydrogen; other groups take the rest." in \
        describe_part("substituent", "methyl", 1, mol=_mol("FC(F)(F)c1ccccc1"), atoms=[1])


def test_a_nitrogen_group_says_what_its_nitrogen_carries():
    assert describe_part("substituent", "amino", 1, mol=_mol("CN(C)c1ccccc1"), atoms=[1]) == \
        '"amino" is a nitrogen group (-NH2 on its own). Here the nitrogen carries no hydrogen.'
    assert describe_part("suffix", "amine", 1, mol=_mol("CCN(CC)CC"), atoms=[2]) == \
        'The "amine" ending means a nitrogen group (-NH2 on its own). Here the nitrogen carries no hydrogen.'
    assert describe_part("suffix", "diamine", 2, mol=_mol("NCCN"), atoms=[0, 3]) == \
        'The "diamine" ending means a nitrogen group (-NH2 on its own).'


def test_two_carbon_groups_count_every_carbon():
    assert describe_part("substituent", "ethyl", 2, mol=_mol("OCCN"), atoms=[1, 2]) == (
        '"ethyl" is a two-carbon group (CH3-CH2- on its own). Here each of its carbons carries 2 hydrogens; '
        'other groups take the rest.')
    assert describe_part("substituent", "acetyl", 3, mol=_mol("c1ccccc1CC(=O)Cl"), atoms=[6, 7, 8]) == (
        '"acetyl" is a two-carbon group with a C=O (CH3-C(=O)- on its own). Here its end carbon carries '
        '2 hydrogens; other groups take the rest.')


def test_an_isotopic_hydrogen_is_a_hydrogen():
    cd3 = _mol("[2H]C([2H])([2H])Oc1ccccc1")
    assert "Here" not in describe_part("substituent", "methyl", 4, mol=cd3, atoms=[0, 1, 2, 3])


def test_a_label_that_only_ends_in_a_group_does_not_get_its_carbon_count():
    assert "two-carbon" not in describe_part("substituent", "methylethyl", 3)


@pytest.mark.parametrize("name,kind,label,line", [
    ("2-(hydroxymethyl)phenol", "substituent", "methyl",
     '"methyl" is a one-carbon group (CH3 on its own). Here its carbon carries 2 hydrogens; other groups take the rest.'),
    ("(methylamino)acetic acid", "substituent", "amino",
     '"amino" is a nitrogen group (-NH2 on its own). Here the nitrogen carries 1 hydrogen.'),
    ("N,N-diethylethanamine", "suffix", "amine",
     'The "amine" ending means a nitrogen group (-NH2 on its own). Here the nitrogen carries no hydrogen.'),
    ("(2H3)methyl benzoate", "substituent", "methyl", '"methyl" is a one-carbon group (CH3 on its own).'),
])
def test_a_live_group_line(name, kind, label, line):
    t = trace(name)
    (node,) = [n for n in build_nodes(t) if n["kind"] == kind and n["label"] == label]
    assert node["line"] == line


def test_two_parts_with_one_label_are_counted_apart():
    t = trace("1,3,5-tris(bromomethyl)-2,4,6-trimethylbenzene")
    assert sorted(n["line"] for n in build_nodes(t) if n["label"] == "methyl") == [
        '"methyl" is a one-carbon group (CH3 on its own). Here each of its carbons carries 2 hydrogens; other '
        'groups take the rest. The name writes it once for 3 copies.',
        '"methyl" is a one-carbon group (CH3 on its own). The name writes it once for 3 copies.',
    ]


def test_the_structure_path_shows_the_lines_of_its_name():
    """explain_molecule keeps the line of every node of the name it traced, mapped or not:
    the line is measured on OPSIN's molecule, which is the user's (same atom count)."""
    from app.explain import explain_molecule
    from app.orthonym_service import get_primary_namer
    for smiles in ("OCc1ccccc1O", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"):
        r = explain_molecule(smiles, get_primary_namer())
        named = {n["id"]: n["line"] for n in build_nodes(trace(r["name"]))}
        assert [n["line"] for n in r["nodes"]] == [named[n["id"]] for n in r["nodes"]], smiles
    r = explain_molecule("OCc1ccccc1O", get_primary_namer())
    assert any("Here its carbon carries 2 hydrogens" in n["line"] for n in r["nodes"] if n["label"] == "methyl")


# -- 3. a hydro / indicated / added hydrogen locant, and a sugar's anomer ----------------

def test_a_hydrogen_locant_on_an_atom_with_a_hydrogen_keeps_its_line():
    assert describe_locant("modifier", "1", "N", mol=_mol("c1ccc2[nH]ccc2c1"), atom=4) == \
        "Position 1 — the N1 atom carries a hydrogen here."


def test_a_hydrogen_locant_whose_hydrogen_was_replaced_says_so():
    assert describe_locant("modifier", "1", "N", mol=_mol("Cn1ccc2ccccc21"), atom=1) == (
        "Position 1 — the name puts a hydrogen on the N1 atom; here a group or bond named elsewhere "
        "takes its place.")
    assert "takes its place" in describe_locant("modifier", "4", "C", mol=_mol("O=C1C=COC=C1"), atom=1)


def test_a_hydrogen_locant_on_an_atom_that_cannot_carry_one_claims_no_replacement():
    assert describe_locant("modifier", "6", "O", mol=_mol("C1COCC1"), atom=2) == \
        "Position 6 — the name puts a hydrogen on the O6 atom; here that atom carries none."


def test_a_hydrogen_locant_with_no_one_atom_claims_nothing_about_it():
    assert describe_locant("modifier", "2", None) == "Position 2 — the name puts a hydrogen at this position."
    assert describe_locant("modifier", "2", "C") == "Position 2 — the name puts a hydrogen on the C2 atom."


ANOMER = ('"beta" names the anomer: which way the group on the ring carbon next to the ring oxygen points, '
          "relative to the sugar's reference stereocentre.")


def test_an_anomer_line_says_what_the_anomeric_carbon_holds():
    glycoside = _mol("COC1OC(CO)C(O)C(O)C1O")
    assert describe_locant("position", "beta", anomer=True, mol=glycoside, atom=2) == \
        ANOMER + " Here that group is the O that joins the sugar to the rest of the name."
    assert describe_locant("position", "beta", anomer=True, mol=_mol("OC1OC(CO)C(O)C(O)C1O"), atom=1) == \
        ANOMER + " Here that group is an OH."
    assert describe_locant("position", "beta", anomer=True) == ANOMER


@pytest.mark.parametrize("name,kind,label,line", [
    ("1-methyl-1H-indole", "indicated_h", "1H",
     "Position 1 — the name puts a hydrogen on the N1 atom; here a group or bond named elsewhere takes its place."),
    ("1,2,3,4-tetrahydronaphthalene", "locant", "1", "Position 1 — the C1 atom carries a hydrogen here."),
    ("methyl beta-D-galactopyranoside", "locant", "beta",
     ANOMER + " Here that group is the O that joins the sugar to the rest of the name."),
    ("beta-D-glucopyranose", "locant", "beta", ANOMER + " Here that group is an OH."),
    ("1-(beta-D-ribofuranosyl)pyrimidine-2,4(1H,3H)-dione", "locant", "beta",
     ANOMER + " Here that group is the N that joins the sugar to the rest of the name."),
])
def test_a_live_locant_line(name, kind, label, line):
    t = trace(name)
    (node,) = [n for n in build_nodes(t) if n["kind"] == kind and n["label"] == label]
    assert node["line"] == line


def test_a_hydro_locant_on_the_spiro_atom_gives_way_to_the_spiro_bond():
    t = trace("spiro[2,3-dihydro-1-benzofuran-3,4'-piperidine]")
    hydro = [n["line"] for n in build_nodes(t) if n["kind"] == "locant" and "hydrogen" in n["line"]]
    assert hydro == ["Position 2 — the C2 atom carries a hydrogen here.",
                     "Position 3 — the name puts a hydrogen on the C3 atom; here a group or bond named elsewhere "
                     "takes its place."]


