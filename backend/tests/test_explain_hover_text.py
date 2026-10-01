"""Every hover line says only what is true of the molecule on screen (the 2026-10-01
hover-text audit). The glossary names a bare group "on its own" and adds what the
real atoms carry, measured; hydrogen-locant, anomer, spiro, stereo, isotope and parent
lines say what their mark means. Exact strings: the text is looked up and counted,
never generated, so any change to a line is a change to this file."""

import pytest
from rdkit import Chem

from app.opsin_trace import Trace, TraceAtom
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


