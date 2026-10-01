"""Every hover line says only what is true of the molecule on screen (the 2026-10-01
hover-text audit). The glossary names a bare group "on its own" and adds what the
real atoms carry, measured; hydrogen-locant, anomer, spiro, stereo, isotope and parent
lines say what their mark means. Exact strings: the text is looked up and counted,
never generated, so any change to a line is a change to this file."""

import pytest
from rdkit import Chem

from app.explain_tree import build_nodes
from app.glossary import describe_locant, describe_part, describe_stereo, describe_token, parent_claim_holds
from app.opsin_trace import Trace, TraceAtom, trace
from scripts.explain_census import classify, false_hover_lines


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
    # with no molecule the ring is not known, so it is not called an oxygen ring
    assert describe_locant("position", "beta", anomer=True) == ANOMER.replace("the ring oxygen", "the ring's heteroatom")


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


# -- 4. spiro descriptors, isotope labels and stereo marks -------------------------------

@pytest.mark.parametrize("text,line", [
    ("spiro[4.5]", '"spiro[4.5]" names two rings that share one atom; 4 and 5 count the other atoms in each ring.'),
    ("spiro[4.1.5.3]", '"spiro[4.1.5.3]" names rings joined at single shared atoms (the counting word before it '
                       'says how many); its numbers count the atoms between them, in order along the system.'),
    ("x", '"x" names rings that share single atoms.'),
])
def test_a_spiro_descriptor_says_what_its_numbers_count(text, line):
    assert describe_token("spiro", text) == line


def test_an_isotope_label_names_positions_only_when_it_has_a_locant():
    assert describe_token("isotopeSpecification", "3-2H") == \
        '"3-2H" is an isotope label: it says which isotope sits at the positions it names.'
    assert describe_token("isotopeSpecification", "2H3") == (
        '"2H3" is an isotope label: it says which isotope the part named after it carries in place of the '
        'usual one; the label gives no position number.')


STEREO = [
    ("2S", None, '"2S" fixes the three-dimensional arrangement at the positions it names.'),
    ("NE", None, '"NE" fixes the three-dimensional arrangement at the positions it names.'),
    ("rac", None, '"rac" marks a racemate: an equal mix of the two mirror-image forms.'),
    ("+-", None, '"+-" marks a racemate: an equal mix of the two mirror-image forms.'),
    ("RS", None, '"RS" marks a racemate: an equal mix of the two mirror-image forms.'),
    ("DL", None, '"DL" marks a racemate: an equal mix of the two mirror-image forms.'),
    ("2RS", None, '"2RS" marks a racemate: an equal mix of the two mirror-image forms, R at position 2 in one '
                  'and S in the other.'),
    ("rel", None, '"rel" says the marks of its set give only a relative arrangement; it does not say which of the '
                  'two mirror-image forms is meant.'),
    ("1R*", None, '"1R*" gives the arrangement at the position it names only as a relative arrangement, not '
                  'an absolute one; it does not say which of the two mirror-image forms is meant.'),
    ("1R", "rel", '"1R" gives the arrangement at the position it names only as a relative arrangement, not '
                  'an absolute one; it does not say which of the two mirror-image forms is meant.'),
    ("1R", "rac", '"1R" is part of a racemate mark (rac): the name means an equal mix of this form and '
                  'its mirror image.'),
    ("+", None, '"+" gives the sign of optical rotation: this form turns polarised light to the right. It does '
                'not by itself say how the atoms are arranged.'),
    ("-", None, '"-" gives the sign of optical rotation: this form turns polarised light to the left. It does '
                'not by itself say how the atoms are arranged.'),
    ("D", None, '"D" is a Fischer label: it puts the part named after it in the D series, by comparing one of '
                'its stereocentres with D-glyceraldehyde.'),
    ("L", None, '"L" is a Fischer label: it puts the part named after it in the L series, by comparing one of '
                'its stereocentres with L-glyceraldehyde.'),
    ("cis", None, '"cis" says two groups lie on the same side of the ring or double bond they are on.'),
    ("trans", None, '"trans" says two groups lie on opposite sides of the ring or double bond they are on.'),
    ("R", None, '"R" fixes the three-dimensional arrangement at one stereocentre; the mark itself carries no '
                'position number.'),
    ("E", None, '"E" fixes the arrangement at one double bond: its higher-ranked groups lie on opposite sides. '
                'The mark itself carries no position number.'),
    ("Z", None, '"Z" fixes the arrangement at one double bond: its higher-ranked groups lie on the same side. '
                'The mark itself carries no position number.'),
    ("erythro", None, '"erythro" is a sugar configuration prefix: the stereocentres it covers are arranged as in '
                      'erythrose.'),
    ("endo", None, '"endo" is a stereo descriptor: part of how the name gives the three-dimensional arrangement.'),
]


@pytest.mark.parametrize("label,within,line", STEREO)
def test_each_kind_of_stereo_mark_says_what_it_means(label, within, line):
    assert describe_stereo(label, within) == line


def test_only_a_mark_with_a_locant_fixes_the_positions_it_names():
    for label, within, line in STEREO:
        assert ("positions it names" in line) == (label in ("2S", "NE") and within is None), label


@pytest.mark.parametrize("name,kind,label,line", [
    ("spiro[4.5]decane", "token", "spiro[4.5]",
     '"spiro[4.5]" names two rings that share one atom; 4 and 5 count the other atoms in each ring.'),
    ("(2H3)methyl benzoate", "token", "2H3",
     '"2H3" is an isotope label: it says which isotope the part named after it carries in place of the usual one; '
     'the label gives no position number.'),
    ("rac-(1R,2S)-2-aminocyclohexan-1-ol", "stereo", "1R",
     '"1R" is part of a racemate mark (rac): the name means an equal mix of this form and its mirror image.'),
    ("rel-(1R,2S)-2-aminocyclohexan-1-ol", "stereo", "2S",
     '"2S" gives the arrangement at the position it names only as a relative arrangement, not an absolute one; it does '
     'not say which of the two mirror-image forms is meant.'),
    ("D-threose", "stereo", "D",
     '"D" is a Fischer label: it puts the part named after it in the D series, by comparing one of its '
     "stereocentres with D-glyceraldehyde."),
    ("(+-)-trans-4-methylcyclohexan-1-ol", "stereo", "+-",
     '"+-" marks a racemate: an equal mix of the two mirror-image forms.'),
])
def test_a_live_mark_line(name, kind, label, line):
    t = trace(name)
    (node,) = [n for n in build_nodes(t) if n["kind"] == kind and n["label"] == label]
    assert node["line"] == line


# -- 5. a parent's prose and its place in the name ----------------------------------------

def _live(name, kind, label):
    """The line of the one node of `kind` and `label` in `name`, after checking that the
    census finds no false line anywhere in the name (every other class is fixed by now)."""
    t, nodes, node = _live_node(name, kind, label)
    assert false_hover_lines(t, nodes) == []
    return node["line"]


def test_a_benzene_ring_prose_needs_aromatic_benzene_rings():
    assert parent_claim_holds("naphthalene", _mol("c1ccc2ccccc2c1"), range(10))
    assert not parent_claim_holds("naphthalene", _mol("C1CCc2ccccc2C1"), range(10))   # tetrahydro
    assert not parent_claim_holds("indol", _mol("O=C1CCCc2[nH]ccc21"), range(10))
    assert parent_claim_holds("pyridin", None, range(6))                              # no ring claim
    assert "two fused benzene rings" not in describe_part("parent", "naphthalene", 10, holds=False)


def test_a_parent_among_several_is_one_of_that_many_cores():
    assert describe_part("parent", "sodium", 1, cores=2) == \
        '"sodium" is one of the two cores this name is built from. It has 1 atom.'
    assert describe_part("parent", "acet", 2, cores=2) == (
        '"acet" is a two-carbon acetyl skeleton. It is one of the two cores this name is built from, and it '
        'holds 2 atoms.')
    assert "built around" in describe_part("parent", "acet", 2)


@pytest.mark.parametrize("name,kind,label,line", [
    ("sodium acetate", "parent", "sodium", '"sodium" is one of the two cores this name is built from. It has 1 atom.'),
    ("sodium acetate", "parent", "acet",
     '"acet" is a two-carbon acetyl skeleton. It is one of the two cores this name is built from, and it holds '
     '2 atoms.'),
    ("1,2,3,4-tetrahydronaphthalene", "parent", "naphthalene",
     '"naphthalene" is the core skeleton the rest of the name is built around. It has 10 atoms.'),
    ("copper(II) sulfate pentahydrate", "parent", "copper",
     '"copper" is one of the two cores this name is built from. It has 1 atom.'),
    ("copper(II) sulfate pentahydrate", "parent", "hydrate",
     '"hydrate" is water of crystallisation: water molecules that come with the compound. The name writes it '
     'once for 5 copies.'),
    ("naphthalene", "parent", "naphthalene",
     '"naphthalene" is naphthalene — two fused benzene rings. It is the core the rest of the name is built '
     'around, and it holds 10 atoms.'),
])
def test_a_live_parent_line(name, kind, label, line):
    assert _live(name, kind, label) == line


# -- 6. the gate: a false hover line fails the census -------------------------------------

def test_the_census_classifies_a_false_hover_line():
    old = [_node("substituent", "methyl", owns=[1], lights=[1],
                 line='"methyl" is a CH3 group — one carbon with three hydrogens.')]
    assert "HOVER_LINE_FALSE" in classify(BENZYL_ALCOHOL, old, {})
    true = [_node("substituent", "methyl", owns=[1], lights=[1],
                  line='"methyl" is a one-carbon group (CH3 on its own). Here its carbon carries 2 hydrogens; '
                       'other groups take the rest.')]
    assert "HOVER_LINE_FALSE" not in classify(BENZYL_ALCOHOL, true, {})


@pytest.mark.parametrize("name", [
    "2-(hydroxymethyl)phenol", "N,N-diethylethanamine", "1-methyl-1H-indole", "spiro[4.5]decane",
    "methyl beta-D-galactopyranoside", "DL-alanine", "sodium acetate", "1,2,3,4-tetrahydronaphthalene",
])
def test_a_name_from_every_false_class_is_clean(name):
    t = trace(name)
    assert false_hover_lines(t, build_nodes(t)) == []


# -- 7. whole-plan review: sets written either side, terminal anomer groups, thio sugars, hydrates ----

def _live_node(name, kind, label):
    t = trace(name)
    nodes = build_nodes(t)
    (node,) = [n for n in nodes if n["kind"] == kind and n["label"] == label]
    return t, nodes, node


def _census_flags(name, kind, label, old_line):
    """The census, shown the line this name used to get, must call it false."""
    t, nodes, node = _live_node(name, kind, label)
    old = [dict(n, line=old_line) if n is node else n for n in nodes]
    return false_hover_lines(t, old)


OLD_BARE = ('"{}" fixes the three-dimensional arrangement at one stereocentre; the mark itself carries no '
            'position number.')
OLD_LOCATED = '"{}" fixes the three-dimensional arrangement at the positions it names.'
OLD_REL = ('"rel" says the marks after it give only a relative arrangement; it does not say which of the two '
           'mirror-image forms is meant.')


@pytest.mark.parametrize("label,within,line", [
    ("R", "rel", '"R" gives the arrangement at one stereocentre only as a relative arrangement, not an absolute one; it '
                 'does not say which of the two mirror-image forms is meant.'),
    ("S", "rac", '"S" is part of a racemate mark (rac): the name means an equal mix of this form and its '
                 'mirror image.'),
    ("rel", None, '"rel" says the marks of its set give only a relative arrangement; it does not say which of '
                  'the two mirror-image forms is meant.'),
])
def test_a_bare_mark_in_a_set_and_the_set_word_say_what_they_mean(label, within, line):
    assert describe_stereo(label, within) == line


@pytest.mark.parametrize("name,word", [
    ("rac-(R)-butan-2-ol", "rac"), ("rac-(S)-2-chlorobutane", "rac"), ("rel-(R)-butan-2-ol", "rel"),
])
def test_a_bare_mark_inside_a_racemate_or_relative_set_does_not_fix_the_arrangement(name, word):
    mark = "S" if "(S)" in name else "R"
    t, nodes, node = _live_node(name, "stereo", mark)
    assert "fixes the three-dimensional arrangement" not in node["line"]
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "stereo", mark, OLD_BARE.format(mark))


@pytest.mark.parametrize("name,mark,word", [
    ("(1R,2S)-rel-2-aminocyclohexan-1-ol", "1R", "rel"), ("(1R,2S)-rac-2-aminocyclohexan-1-ol", "1R", "rac"),
    ("(rac)-(2R)-butan-2-ol", "2R", "rac"), ("(rel)-(2R)-butan-2-ol", "2R", "rel"),
    ("(2R)-rel-butan-2-ol", "2R", "rel"), ("(2R)-rac-butan-2-ol", "2R", "rac"),
])
def test_a_set_word_in_any_adjacent_stereo_token_governs_the_marks(name, mark, word):
    t, nodes, node = _live_node(name, "stereo", mark)
    assert ("only as a relative arrangement, not an absolute one" in node["line"]) == (word == "rel")
    assert ("part of a racemate mark" in node["line"]) == (word == "rac")
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "stereo", mark, OLD_LOCATED.format(mark))


@pytest.mark.parametrize("name,word", [
    ("(1R,2S)-rel-2-aminocyclohexan-1-ol", "rel"), ("(1R,2S)-rac-2-aminocyclohexan-1-ol", "rac"),
])
def test_a_set_word_written_after_the_marks_still_governs_them(name, word):
    t, nodes, node = _live_node(name, "stereo", "1R")
    assert "positions it names" not in node["line"] or "only relative" in node["line"]
    assert ("only as a relative arrangement, not an absolute one" in node["line"]) == (word == "rel")
    assert ("part of a racemate mark" in node["line"]) == (word == "rac")
    (setword,) = [n for n in nodes if n["kind"] == "stereo" and n["label"] == word]
    assert "after it" not in setword["line"]
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "stereo", "1R", OLD_LOCATED.format("1R"))
    if word == "rel":
        assert _census_flags(name, "stereo", "rel", OLD_REL)


def test_a_set_word_written_in_front_of_its_marks_still_governs_them():
    t, nodes, node = _live_node("rel-(1R,2S)-2-aminocyclohexan-1-ol", "stereo", "1R")
    assert "only as a relative arrangement, not an absolute one" in node["line"]
    assert false_hover_lines(t, nodes) == []


def _anomer(locant, ring="the ring oxygen"):
    return ANOMER.replace("beta", locant).replace("the ring oxygen", ring)


def test_an_anomeric_group_that_is_one_atom_is_an_atom_not_a_join():
    br = _mol("BrC1OC(CO)C(O)C(O)C1O")
    assert describe_locant("position", "alpha", anomer=True, mol=br, atom=1).endswith(" Here that group is a Br atom.")
    assert describe_locant("position", "alpha", anomer=True, mol=_mol("IC1OC(CO)C(O)C(O)C1O"),
                           atom=1).endswith(" Here that group is an I atom.")
    azide = _mol("[N-]=[N+]=NC1OC(CO)C(O)C(O)C1O")
    assert describe_locant("position", "alpha", anomer=True, mol=azide, atom=3).endswith(
        " Here that group is the N that joins the sugar to the rest of the name.")


@pytest.mark.parametrize("name,sym", [
    ("2,3,4,6-tetra-O-acetyl-alpha-D-glucopyranosyl bromide", "Br"),
    ("2,3,4,6-tetra-O-acetyl-alpha-D-glucopyranosyl chloride", "Cl"),
])
def test_a_glycosyl_halide_names_the_halogen(name, sym):
    t, nodes, node = _live_node(name, "locant", "alpha")
    assert node["line"] == _anomer("alpha") + f" Here that group is a {sym} atom."
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "locant", "alpha",
                         _anomer("alpha") + f" Here that group is the {sym} that joins the sugar to the rest of the name.")


def test_a_glycosyl_azide_still_joins_the_sugar_to_the_rest():
    t, nodes, node = _live_node("2,3,4,6-tetra-O-acetyl-alpha-D-glucopyranosyl azide", "locant", "alpha")
    assert node["line"].endswith("Here that group is the N that joins the sugar to the rest of the name.")
    assert false_hover_lines(t, nodes) == []


def test_a_thio_sugar_does_not_get_a_ring_oxygen():
    name = "methyl 5-thio-alpha-D-glucopyranoside"
    t, nodes, node = _live_node(name, "locant", "alpha")
    assert node["line"] == _anomer("alpha", "the ring sulfur")
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "locant", "alpha", _anomer("alpha"))
    # what the builder cannot read off the sugar, it does not name
    assert describe_locant("position", "alpha", anomer=True) == _anomer("alpha", "the ring's heteroatom")
    assert describe_locant("position", "beta", anomer=True, mol=_mol("COC1OC(CO)C(O)C(O)C1O"), atom=2,
                           pool=range(11)) == \
        _anomer("beta") + " Here that group is the O that joins the sugar to the rest of the name."


def test_a_hydrate_is_not_counted_among_the_cores():
    name = "copper(II) sulfate pentahydrate"
    t, nodes, node = _live_node(name, "parent", "copper")
    assert node["line"] == '"copper" is one of the two cores this name is built from. It has 1 atom.'
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "parent", "copper",
                         '"copper" is one of the three cores this name is built from. It has 1 atom.')
    (hydrate,) = [n for n in nodes if n["label"] == "hydrate"]
    assert "cores" not in hydrate["line"]


# the relative line is for R and S only; one mark in a set has no "other marks"

@pytest.mark.parametrize("mark", ["2E", "4r", "4s", "2alpha", "3beta", "2Z"])
def test_a_mark_that_a_relative_set_does_not_reverse_keeps_its_absolute_line(mark):
    assert describe_stereo(mark, "rel") == describe_stereo(mark)
    assert "relative" not in describe_stereo(mark, "rel")


def test_a_one_mark_relative_set_does_not_speak_of_other_marks():
    assert "other marks" not in describe_stereo("1R", "rel")
    assert "other marks" not in describe_stereo("1R*")
    t, nodes, node = _live_node("rel-(1R)-1-phenylethan-1-ol", "stereo", "1R")
    assert "other marks" not in node["line"] and "relative arrangement" in node["line"]
    assert false_hover_lines(t, nodes) == []


@pytest.mark.parametrize("name,mark", [
    ("rel-(2E,4R,5S)-5-chlorohept-2-en-4-ol", "2E"),
    ("rel-(1R,2S,4r)-4-chloro-1,2-dimethylcyclohexane", "4r"),
])
def test_an_e_z_or_pseudoasymmetric_mark_in_a_relative_set_stays_absolute(name, mark):
    t, nodes, node = _live_node(name, "stereo", mark)
    assert "relative" not in node["line"]
    assert false_hover_lines(t, nodes) == []
    relative = (f'"{mark}" gives the arrangement at the position it names only as a relative arrangement, not an '
                "absolute one; it does not say which of the two mirror-image forms is meant.")
    assert _census_flags(name, "stereo", mark, relative)


# -- a glycosylamine's NH2 joins nothing; an ylium / ide atom lost its hydrogen to the ending ----

def test_an_anomeric_amine_is_a_lone_atom_too():
    t, nodes, node = _live_node("beta-D-glucopyranosylamine", "locant", "beta")
    assert node["line"] == _anomer("beta") + " Here that group is an N atom."
    assert false_hover_lines(t, nodes) == []
    assert _census_flags("beta-D-glucopyranosylamine", "locant", "beta",
                         _anomer("beta") + " Here that group is the N that joins the sugar to the rest of the name.")


@pytest.mark.parametrize("name", ["4aH-fluoren-4a-ylium", "4aH-fluoren-4a-ide", "3aH-indol-3a-ylium"])
def test_a_charged_atom_lost_its_hydrogen_to_the_ending_not_to_a_group(name):
    t = trace(name)
    nodes = build_nodes(t)
    (node,) = [n for n in nodes if n["kind"] == "indicated_h"]
    assert "takes its place" not in node["line"]
    assert node["line"].endswith("here that atom carries none.")
    assert false_hover_lines(t, nodes) == []
    old = [dict(n, line=n["line"].replace("here that atom carries none.",
                                          "here a group or bond named elsewhere takes its place.")) for n in nodes]
    assert false_hover_lines(t, old)


def test_a_neutral_indicated_hydrogen_keeps_its_line():
    t = trace("4aH-fluorene")
    nodes = build_nodes(t)
    (node,) = [n for n in nodes if n["kind"] == "indicated_h"]
    assert "carries a hydrogen here" in node["line"]
    assert false_hover_lines(t, nodes) == []


# -- fix round 1: a recognised phrase does not excuse an extra claim ---------------------

TETRALIN = _trace("C1CCc2ccccc2C1")
NAPH_TRUE = ('"naphthalene" is naphthalene — two fused benzene rings. It is the core the rest of the name is '
             'built around, and it holds 10 atoms.')


@pytest.mark.parametrize("trace_, node, why", [
    (TETRALIN, _node("parent", "naphthalene", owns=range(10),
                     line='"naphthalene" is two fused aromatic benzene rings. It is the core the rest of the name '
                          'is built around, and it holds 10 atoms.'), "an added benzene claim, the rings are not aromatic"),
    (_trace("[2H]C([2H])([2H])O"), _node("token", "2H3", lights=[0],
                                         line='"2H3" is an isotope label: it says which isotope the part named after it '
                                              'carries in place of the usual one; the label gives no position number. '
                                              'Its carbon carries no hydrogen.'), "an added hydrogen claim"),
    (_trace("C1CCCCC1"), _node("hydro", "hexahydro", lights=range(6),
                               line='"hexahydro" records that hydrogens were added here, which fixes where the double '
                                    'bonds go. Each carbon now carries no hydrogen.'), "an added hydrogen claim"),
])
def test_a_recognised_phrase_does_not_excuse_an_extra_claim(trace_, node, why):
    assert false_hover_lines(trace_, [node]), why


def test_the_recognised_phrase_alone_still_passes():
    assert not false_hover_lines(_trace("c1ccc2ccccc2c1"), [_node("parent", "naphthalene", owns=range(10),
                                                                  line=NAPH_TRUE)])
    assert not false_hover_lines(_trace("[2H]C([2H])([2H])O"), [_node(
        "token", "2H3", lights=[0], line='"2H3" is an isotope label: it says which isotope the part named after it '
        'carries in place of the usual one; the label gives no position number.')])
    assert not false_hover_lines(_trace("C1CCCCC1"), [_node(
        "hydro", "hexahydro", lights=range(6), line='"hexahydro" records that hydrogens were added here, which '
        'fixes where the double bonds go.')])


# -- fix round 1: raised spiro numbers, glycero, acid-addition parts ------------------------

SPIRO_RAISED = ('"spiro[4.2.4^8.2^5]" names rings joined at single shared atoms (the counting word before it says '
                "how many); its plain numbers count the atoms between them, in order along the system, and a raised "
                "number is a position, not a count.")


def test_a_raised_number_in_a_polyspiro_descriptor_is_a_position_not_a_count():
    assert describe_token("spiro", "spiro[4.2.4^8.2^5]") == SPIRO_RAISED
    assert "raised" not in describe_token("spiro", "spiro[4.1.5.3]")
    t, nodes, node = _live_node("dispiro[4.2.4^8.2^5]tetradecane", "token", "spiro[4.2.4^8.2^5]")
    assert node["line"] == SPIRO_RAISED
    assert false_hover_lines(t, nodes) == []
    assert _census_flags("dispiro[4.2.4^8.2^5]tetradecane", "token", "spiro[4.2.4^8.2^5]",
                         SPIRO_RAISED.replace("its plain numbers count the atoms between them, in order along the "
                                              "system, and a raised number is a position, not a count",
                                              "its numbers count the atoms between them, in order along the system"))


def test_glycero_covers_one_stereocentre():
    assert describe_stereo("glycero") == ('"glycero" is a sugar configuration prefix: the stereocentre it covers is '
                                          "arranged as in glyceraldehyde.")
    assert "stereocentres it covers" in describe_stereo("erythro")
    t, nodes, node = _live_node("D-glycero-D-gluco-heptose", "stereo", "glycero")
    assert "the stereocentre it covers" in node["line"]
    assert false_hover_lines(t, nodes) == []
    assert _census_flags("D-glycero-D-gluco-heptose", "stereo", "glycero",
                         describe_stereo("erythro").replace("erythro", "glycero"))


@pytest.mark.parametrize("name,label,line", [
    ("propan-2-amine hydrochloride", "hydrochloride",
     '"hydrochloride" is hydrochloric acid (HCl) that comes with the compound as a salt.'),
    ("propan-2-amine hydrobromide", "hydrobromide",
     '"hydrobromide" is hydrobromic acid (HBr) that comes with the compound as a salt.'),
    ("propan-2-amine dihydrochloride", "hydrochloride",
     '"hydrochloride" is hydrochloric acid (HCl) that comes with the compound as a salt. The name writes it once '
     "for 2 copies."),
])
def test_an_acid_addition_part_is_not_a_core(name, label, line):
    t, nodes, node = _live_node(name, "parent", label)
    assert node["line"] == line
    (amine,) = [n for n in nodes if n["kind"] == "parent" and n["label"] == "propan"]
    assert "the core the rest of the name is built around" in amine["line"]
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "parent", "propan",
                         amine["line"].replace("the core the rest of the name is built around",
                                               "one of the two cores this name is built from"))


# -- fix round 1: multiplied hydrates, a set word's reach over the whole name ------------------

HYDRATE_LINE = ('"monohydrate" is water of crystallisation: water molecules that come with the compound.')


def test_a_multiplied_hydrate_is_not_a_core():
    t, nodes, node = _live_node("caffeine monohydrate", "parent", "monohydrate")
    assert node["line"] == HYDRATE_LINE
    (caffeine,) = [n for n in nodes if n["label"] == "caffeine"]
    assert "is the core skeleton the rest of the name is built around" in caffeine["line"]
    assert false_hover_lines(t, nodes) == []
    assert _census_flags("caffeine monohydrate", "parent", "caffeine",
                         caffeine["line"].replace("is the core skeleton the rest of the name is built around",
                                                  "is one of the two cores this name is built from"))


@pytest.mark.parametrize("name,mark,word", [
    ("rel-(R)-2-[(S)-1-hydroxyethyl]butan-1-ol", "S", "rel"),
    ("rac-(R)-2-[(S)-1-hydroxyethyl]butan-1-ol", "S", "rac"),
])
def test_a_set_word_reaches_every_mark_of_its_word(name, mark, word):
    t, nodes, node = _live_node(name, "stereo", mark)
    assert ("relative arrangement" in node["line"]) == (word == "rel")
    assert ("part of a racemate mark" in node["line"]) == (word == "rac")
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "stereo", mark, OLD_BARE.format(mark))


def test_a_set_word_reaches_a_mark_in_another_word_of_the_name():
    # rel / rac say the whole compound's arrangement is relative / a mix (IUPAC P-93.1.3)
    t, nodes, node = _live_node("rel-(R)-butan-2-yl (S)-2-methylbutanoate", "stereo", "S")
    assert "relative arrangement" in node["line"]
    assert false_hover_lines(t, nodes) == []


# -- final wave: a chain line is measured; a bracket scopes its own set word; "part of" a racemate mark ----

def _chain_line(name, label):
    t, nodes, node = _live_node(name, "substituent", label)
    return t, nodes, node["line"]


@pytest.mark.parametrize("name,label", [("4-tert-butylcyclohexan-1-ol", "tert-butyl"),
                                        ("4-isobutylcyclohexan-1-ol", "isobutyl")])
def test_a_branched_butyl_is_not_a_four_carbon_chain(name, label):
    t, nodes, line = _chain_line(name, label)
    assert "chain" not in line
    assert line == f'"{label}" covers 4 atoms of this structure.'
    assert false_hover_lines(t, nodes) == []
    assert _census_flags(name, "substituent", label, f'"{label}" is a four-carbon chain.')


@pytest.mark.parametrize("name,label,line", [
    ("4-butylcyclohexan-1-ol", "butyl", '"butyl" is a four-carbon chain.'),
    ("4-sec-butylcyclohexan-1-ol", "sec-butyl", '"sec-butyl" is a four-carbon chain.'),
    ("1-propylcyclohexane", "propyl", '"propyl" is a three-carbon chain.'),
])
def test_a_chain_line_that_the_atoms_bear_out_is_kept(name, label, line):
    t, nodes, said = _chain_line(name, label)
    assert said == line
    assert false_hover_lines(t, nodes) == []


def test_the_census_measures_a_chain():
    t = _trace("CC(C)(C)C1CCCCC1")
    four = '"tert-butyl" is a four-carbon chain.'
    assert false_hover_lines(t, [_node("substituent", "tert-butyl", owns=[0, 1, 2, 3], line=four)])
    t2 = _trace("CCCCC1CCCCC1")
    assert not false_hover_lines(t2, [_node("substituent", "butyl", owns=[0, 1, 2, 3], line='"butyl" is a four-carbon chain.')])


def test_a_set_word_inside_a_bracket_keeps_to_that_bracket():
    name = "(1R,2S)-2-[rel-(1R)-1-hydroxyethyl]cyclohexan-1-ol"
    t = trace(name)
    nodes = build_nodes(t)
    marks = [n for n in nodes if n["kind"] == "stereo"]
    outer1, outer2, inner = [n for n in marks if n["label"] in ("1R", "2S")][0], \
        [n for n in marks if n["label"] == "2S"][0], [n for n in marks if n["label"] == "1R"][1]
    assert "fixes the three-dimensional arrangement" in outer1["line"]
    assert "fixes the three-dimensional arrangement" in outer2["line"]
    assert "relative arrangement" in inner["line"]
    assert false_hover_lines(t, nodes) == []
    old = [dict(n, line=n["line"]) for n in nodes]
    for n in old:
        if n["id"] == outer1["id"]:
            n["line"] = inner["line"]
    assert false_hover_lines(t, old)


def test_a_racemate_mark_is_part_of_it_on_whichever_side_it_is_written():
    assert describe_stereo("1R", "rac") == ('"1R" is part of a racemate mark (rac): the name means an equal mix '
                                            "of this form and its mirror image.")
    t, nodes, node = _live_node("(S)-rac-butan-2-ol", "stereo", "S")
    assert "written inside" not in node["line"] and "is part of a racemate mark (rac)" in node["line"]
    assert false_hover_lines(t, nodes) == []
