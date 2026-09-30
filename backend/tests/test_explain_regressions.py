"""Named regressions from the Fable 5.1 review of plan v2 (JVM + engine).
Each class once lit a wrong atom or showed a false line while every gate
stayed green; each test pins the corrected behaviour on a live trace."""

import pytest
from rdkit import Chem

from app.explain_tree import PART_NODE_KINDS, build_nodes, foreign_lights
from app.opsin_trace import Trace, trace
from app.orthonym_service import get_primary_namer
from app.token_owner import assign_owners
from scripts.explain_census import classify


def _nodes(name):
    t = trace(name)
    assert isinstance(t, Trace), (name, t)
    return t, build_nodes(t)


def _one(nodes, **match):
    hits = [n for n in nodes if all(n[k] == v for k, v in match.items())]
    assert len(hits) == 1, (match, hits)
    return hits[0]


def _label_of(nodes, node_id):
    return next(n["label"] for n in nodes if n["id"] == node_id)


# 1. a descriptor the engine writes at the front of a name belongs to the
#    stereocentre it names, wherever that sits
@pytest.mark.parametrize("name,mark,part,locant", [
    ("(2S)-(oxolan-2-yl)methanol", "2S", "oxolan-2-yl", "2"),
    ("(1R)-4-(1-phenylethyl)morpholine", "1R", "ethyl", "1"),
    ("(2R)-(oxolan-2-yl)acetic acid", "2R", "oxolan-2-yl", "2"),
    ("(1R,2S)-2-(methylamino)-1-phenylpropan-1-ol", "2S", "propan", "2"),
])
def test_a_hoisted_descriptor_lights_its_real_stereocentre(name, mark, part, locant):
    t, nodes = _nodes(name)
    node = _one(nodes, kind="stereo", label=mark)
    (atom,) = node["lights"]
    assert locant in t.atoms[atom].locants
    assert _label_of(nodes, node["parent"]) == part


def test_a_lone_descriptor_lights_the_only_stereocentre_of_its_part():
    t, nodes = _nodes("N-[(S)-oxolan-3-yl]methanesulfonamide")
    node = _one(nodes, kind="stereo", label="S")
    assert len(node["lights"]) == 1 and "3" in t.atoms[node["lights"][0]].locants


# 2. hydrogen added inside a suffix locant is an indicated hydrogen
@pytest.mark.parametrize("name,added", [
    ("pyridin-2(1H)-one", ["1H"]),
    ("pyrimidine-2,4(1H,3H)-dione", ["1H", "3H"]),
])
def test_added_hydrogen_in_a_suffix_lights_its_nitrogen(name, added):
    t, nodes = _nodes(name)
    hs = sorted((n for n in nodes if n["kind"] == "indicated_h"), key=lambda n: n["label"])
    assert [n["label"] for n in hs] == added
    for n in hs:
        (atom,) = n["lights"]
        assert t.atoms[atom].element == "N" and n["label"][:-1] in t.atoms[atom].locants
    assert not any(n["kind"] == "locant" and n["label"].endswith("H") for n in nodes)


# 3. a ring-assembly name owns its locants
def test_ring_assembly_locants_belong_to_the_assembly():
    t, nodes = _nodes("1,1'-bi(cyclohexane)")
    (parent,) = [n for n in nodes if n["kind"] == "parent"]
    locants = [n for n in nodes if n["kind"] == "locant"]
    assert {n["label"] for n in locants} == {"1", "1'"}
    for n in locants:
        assert n["parent"] == parent["id"]
        (atom,) = n["lights"]
        assert n["label"] in t.atoms[atom].locants


# 4. a counting word lights what its locants light
def test_a_suffix_counting_word_lights_its_groups_not_the_skeleton():
    t, nodes = _nodes("1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione")
    dione = _one(nodes, kind="suffix", label="dione")
    di = _one(nodes, kind="multiplier", label="di", parent=dione["id"])
    assert {t.atoms[a].element for a in di["lights"]} == {"C", "O"}
    assert sum(t.atoms[a].element == "O" for a in di["lights"]) == 2
    purine = _one(nodes, kind="parent", label="purine")
    hydro_di = _one(nodes, kind="multiplier", label="di", parent=purine["id"])
    assert sorted(t.atoms[a].element for a in hydro_di["lights"]) == ["N", "N"]


# 5. Fischer D/L describe the residue written right after them
def test_peptide_marks_belong_to_their_own_residue():
    t, nodes = _nodes("L-alanyl-L-valyl-L-leucine")
    parents = [_label_of(nodes, n["parent"]) for n in sorted(
        (n for n in nodes if n["kind"] == "stereo"), key=lambda n: n["span"][0])]
    assert parents == ["alanyl", "valyl", "leucine"]


# 6. multiplicative locants name positions on the multiplied parents
@pytest.mark.parametrize("name", [
    "4,4'-methylenebis(2-chlorophenol)",
    "4,4'-(propane-2,2-diyl)diphenol",
])
def test_multiplicative_locants_light_the_parent_positions(name):
    t, nodes = _nodes(name)
    for label in ("4", "4'"):
        node = next(n for n in nodes if n["kind"] == "locant" and n["label"] == label and n["span"][0] < 4)
        (atom,) = node["lights"]
        assert label in t.atoms[atom].locants and t.atoms[atom].element == "C"


# 7. a steroid stereo token that carries the suffix locants
def test_a_steroid_locant_list_splits_into_locant_and_mark():
    t, nodes = _nodes("estra-1,3,5(10)-triene-3,17beta-diol")
    mark = _one(nodes, kind="stereo", label="17beta")
    (atom,) = mark["lights"]
    assert "17" in t.atoms[atom].locants
    diol = _one(nodes, kind="suffix", label="diol")
    three = _one(nodes, kind="locant", label="3", parent=diol["id"])
    assert "O" in {t.atoms[a].element for a in three["lights"]}


# 8. a carbohydrate root is not split into parent + suffix
def test_a_glycoside_root_keeps_its_oxygens():
    t, nodes = _nodes("methyl alpha-D-glucopyranoside")
    assert not [n for n in nodes if n["kind"] == "suffix"]
    parent = _one(nodes, kind="parent", label="glucopyranoside")
    assert sum(t.atoms[a].element == "O" for a in parent["owns"]) == 6


# 9. the engine's own names for chiral substituents classify CLEAN
ENGINE_SMILES = [
    "OC[C@H]1CCCN1", "OC[C@@H]1CCCCN1", "O=C(N1CCCC1)[C@H]1CCCO1", "CN(C)C[C@H]1CCCO1",
    "c1ccccc1C[C@H]1CCCO1", "O=C(O)C[C@H]1CCCO1", "Fc1ccc(cc1)[C@@H]1CCNC1", "C[C@H](c1ccccc1)N1CCOCC1",
    "C[C@@H]1CCCCN1C(=O)C", "N[C@@H](C)c1ccccc1", "CC(=O)N[C@@H](C)c1ccccc1", "OC(=O)[C@@H]1CCCN1",
    "C[C@H](O)CN1CCOCC1", "C[C@H](O)Cc1ccccc1", "OC[C@H](N)Cc1ccccc1", "C[C@H]1CN(CCO1)c1ccccc1",
    "N#CC[C@H]1CCCO1", "O[C@H]1CCN(C1)C(=O)c1ccccc1", "C[C@@H](CO)NC(=O)c1ccccc1",
    "CC[C@H](C)C(=O)Nc1ccccc1", "C[C@H]1CCC[C@@H](C)N1", "O=C1CC[C@H](N1)C(=O)O", "c1ccc2c(c1)CC[C@H]2N",
    "C[C@@H]1O[C@@H](C)CN1", "CS(=O)(=O)N[C@H]1CCOC1", "Clc1ccc(cc1)[C@H](O)CN", "O=C(Nc1ccccc1)[C@@H]1CCCO1",
    "C[C@H](Nc1ncccn1)c1ccccc1", "OC[C@@H]1CN(CCO1)C", "C[C@@H]1CC(=O)N(C1)c1ccccc1",
]


def test_engine_names_for_chiral_substituents_are_clean():
    namer = get_primary_namer()
    bad = {}
    for smiles in ENGINE_SMILES:
        name = namer.name_with_tree(smiles).name
        t = trace(name)
        if not isinstance(t, Trace):
            bad[name] = t.reason
            continue
        outcomes = classify(t, build_nodes(t), assign_owners(t.tokens))
        if outcomes != ["CLEAN"]:
            bad[name] = outcomes
    assert bad == {}


# -- Phase B fix round 1 ------------------------------------------------------


def _lit(t, nodes, node):
    """[(owning part label, locants)] of the atoms a node lights."""
    owner = {a: n["label"] for n in nodes if n["kind"] in PART_NODE_KINDS for a in n["owns"]}
    return [(owner[a], t.atoms[a].locants) for a in node["lights"]]


def _kid(nodes, parent_label, label, kind="locant"):
    (p,) = [n for n in nodes if n["kind"] in PART_NODE_KINDS and n["label"] == parent_label]
    (k,) = [n for n in nodes if n["parent"] == p["id"] and n["kind"] == kind and n["label"] == label]
    return k


TADALAFIL_NAME = ("(6R,12aR)-6-(1,3-benzodioxol-5-yl)-2-methyl-2,3,6,7,12,12a-hexahydropyrazino"
                  "[1',2':1,6]pyrido[3,4-b]indole-1,4-dione")


# C1. a substituent's own locant lights the substituent's own atom
@pytest.mark.parametrize("name,part,locant,element", [
    ("1-(2-pyrimidinyl)piperazine", "pyrimidinyl", "2", "C"),
    ("N-(2-pyridyl)acetamide", "pyridyl", "2", "C"),
    ("3-methyl-N-(2-pyridyl)butanamide", "pyridyl", "2", "C"),
    ("2-chloro-N-(4-methyl-2-pyridyl)acetamide", "pyridyl", "2", "C"),
    ("3-(2-furyl)propanoic acid", "furyl", "2", "C"),
    ("4-(1-piperidinyl)butan-2-one", "piperidinyl", "1", "N"),
    ("2-(1-naphthyl)acetic acid", "naphthyl", "1", "C"),
    ("1-naphthylacetic acid", "naphthyl", "1", "C"),
    ("N,N-bis(2-chloroethyl)-2-naphthylamine", "naphthyl", "2", "C"),
    ("2-methyl-N-phenyl-1-naphthylamine", "naphthyl", "1", "C"),
    ("2-methyl-3-(1-adamantyl)propanoic acid", "adamantyl", "1", "C"),
    ("1-(1,3-benzodioxol-5-yl)-N-methylpropan-2-amine", "benzodioxol-5-yl", "1", "O"),
    ("1-(1,3-benzodioxol-5-yl)-N-methylpropan-2-amine", "benzodioxol-5-yl", "3", "O"),
    ("5-(1,3-benzodioxol-5-yl)-2-methylpentanoic acid", "benzodioxol-5-yl", "1", "O"),
    ("2-(2,3-dihydro-1-benzofuran-5-yl)propan-1-ol", "benzofuran-5-yl", "1", "O"),
    (TADALAFIL_NAME, "benzodioxol-5-yl", "1", "O"),
    (TADALAFIL_NAME, "benzodioxol-5-yl", "3", "O"),
])
def test_a_substituents_own_locant_lights_its_own_atom(name, part, locant, element):
    t, nodes = _nodes(name)
    node = _kid(nodes, part, locant)
    (lit,) = _lit(t, nodes, node)
    assert lit[0] == part and locant in lit[1]
    assert t.atoms[node["lights"][0]].element == element


# C1. a bridge's locant names the bonded positions of the multiplied root, and
#     only those (not a substituent's atom that happens to carry the number)
@pytest.mark.parametrize("name,bridge,root,locants", [
    ("1,1'-methylenebis(4-methylbenzene)", "methylene", "benzene", ["1", "1'"]),
    ("4,4'-methylenebis(N-butylaniline)", "methylene", "aniline", ["4", "4'"]),
    ("1,1'-(ethane-1,2-diyl)bis(4-methylbenzene)", None, "benzene", ["1", "1'"]),
    ("4,4'-methylenebis(2-chlorophenol)", "methylene", "phenol", ["4", "4'"]),
    ("4,4'-oxydianiline", "oxy", "aniline", ["4", "4'"]),
    ("4,4'-sulfonyldianiline", "sulfonyl", "aniline", ["4", "4'"]),
    ("2,2'-oxydiethanol", "oxy", "ethan", ["2", "2'"]),
    ("4,4'-(propane-2,2-diyl)diphenol", None, "phenol", ["4", "4'"]),
    ("1,1'-methylenebis(4-isocyanatobenzene)", "methylene", "benzene", ["1", "1'"]),
    ("2,2'-methylenebis(6-tert-butyl-4-methylphenol)", "methylene", "phenol", ["2", "2'"]),
    ("2,2'-[ethane-1,2-diylbis(oxy)]diethanol", None, "ethan", ["2", "2'"]),
    ("1,1'-(1,4-phenylene)diethanone", None, "ethan", ["1", "1'"]),
    ("2,2'-[1,4-phenylenebis(oxy)]diacetic acid", None, "acet", ["2", "2'"]),
])
def test_a_bridge_locant_lights_only_the_bonded_root_positions(name, bridge, root, locants):
    t, nodes = _nodes(name)
    for locant in locants:
        if bridge:
            node = _kid(nodes, bridge, locant)
        else:                                  # a bracket's own locant
            (node,) = [n for n in nodes if n["kind"] == "locant" and n["parent"] is None and n["label"] == locant]
        lit = _lit(t, nodes, node)
        assert len(lit) == 1, (name, locant, lit)
        assert lit[0][0] == root and locant in lit[0][1], (name, locant, lit)
    assert foreign_lights(t, nodes) == []


def test_a_phenylene_keeps_its_locants_and_the_ureas_get_theirs():
    t, nodes = _nodes("1,1'-[methylenebis(4,1-phenylene)]bis(3-phenylurea)")
    for label in ("4", "1"):
        node = _kid(nodes, "phenylene", label)
        assert {owner for owner, _ in _lit(t, nodes, node)} == {"phenylene"}
    for label in ("1", "1'"):
        (node,) = [n for n in nodes if n["kind"] == "locant" and n["parent"] is None and n["label"] == label]
        (lit,) = _lit(t, nodes, node)
        assert lit[0] == "urea" and label in lit[1]


# C1. a bracket followed by a ring word is not a multiplicative bridge
@pytest.mark.parametrize("name", [
    "2-(hydroxymethyl)dibenzofuran", "3-(bromomethyl)dibenzothiophene",
    "N-(4-chlorophenyl)diethylamine", "1-(4-chlorophenyl)dimethylsilane",
])
def test_a_bracket_before_a_counting_word_lights_its_own_parts(name):
    t, nodes = _nodes(name)
    (first,) = [n for n in nodes if n["kind"] == "locant" and n["parent"] is None]
    roots = {n["label"] for n in nodes if n["kind"] in ("parent", "suffix")}
    assert first["lights"] and not {owner for owner, _ in _lit(t, nodes, first)} & roots
    assert foreign_lights(t, nodes) == []


def test_a_chain_locant_before_a_root_names_the_root_position():
    for name, part, locant in [("2-acetyloxybenzoic acid", "acetyl", "2"),
                               ("3-methoxycarbonylbenzoic acid", "methoxy", "3")]:
        t, nodes = _nodes(name)
        (lit,) = _lit(t, nodes, _kid(nodes, part, locant))
        assert lit[0].startswith("benz") and locant in lit[1], name


# gate: the names the review probed carry no foreign lit atom
@pytest.mark.parametrize("name", [
    "(2S)-2-[(2S)-2-aminopropanamido]propanoic acid", "ethyl (2R)-2-hydroxypropanoate",
    "1,3-bis(1H-1,2,4-triazol-1-yl)propan-2-ol", "N-(1,3-thiazol-2-yl)acetamide",
    "2-(1,3-dioxolan-2-yl)ethan-1-amine", "4-(1,3-oxazol-2-yl)butan-1-ol",
    "bis(2-ethylhexyl) benzene-1,2-dicarboxylate", "tris(2-chloroethyl) phosphate",
    "2-[(4-chlorophenyl)methyl]-1H-benzimidazole", "N-[4-(dimethylamino)phenyl]acetamide",
    "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane", "5alpha-androstane-3beta,17beta-diol",
    "11beta,17,21-trihydroxypregn-4-ene-3,20-dione", "alpha-D-glucopyranose", "beta-D-fructofuranose",
    "methyl beta-D-ribofuranoside", "2,2'-bipyridine", "[1,1'-biphenyl]-4-carboxylic acid",
])
def test_probed_names_light_no_foreign_atom(name):
    t, nodes = _nodes(name)
    assert foreign_lights(t, nodes) == [], name


# I1. a locant in a stereo list in front of a prefix is the prefix's
def test_a_locant_listed_with_a_mark_before_a_prefix_belongs_to_the_prefix():
    t, nodes = _nodes("11beta,17,21-trihydroxypregn-4-ene-3,20-dione")
    hydroxy = [n for n in nodes if n["kind"] == "substituent" and n["label"] == "hydroxy"]
    assert len(hydroxy) == 1 and hydroxy[0]["copies"] == 3
    for label in ("17", "21"):
        node = _kid(nodes, "hydroxy", label)
        (atom,) = node["lights"]
        assert atom in hydroxy[0]["owns"] and t.atoms[atom].element == "O"
        # the hydroxyl sits on the carbon that carries that locant
        assert any(label in t.atoms[x].locants and x not in hydroxy[0]["owns"] for x in _neighbours(t, atom))
    dione = _one(nodes, kind="suffix", label="dione")
    assert sorted(n["label"] for n in nodes if n["parent"] == dione["id"] and n["kind"] == "locant") == ["20", "3"]
    # the stereo mark of the same token still lights its stereocentre
    (atom,) = _one(nodes, kind="stereo", label="11beta")["lights"]
    assert "11" in t.atoms[atom].locants


def _neighbours(t, atom):
    return {n.GetIdx() for n in Chem.MolFromSmiles(t.smiles).GetAtomWithIdx(atom).GetNeighbors()}


# I2. glossary lines on live names
def test_a_greek_position_is_not_an_anomer():
    for name in ("alpha,alpha,alpha-trifluorotoluene", "alpha-methylbenzyl alcohol"):
        t, nodes = _nodes(name)
        assert not [n for n in nodes if "anomer" in n["line"]], name


def test_a_sugar_anomer_line_survives_on_a_sugar():
    t, nodes = _nodes("alpha-D-glucopyranose")
    assert [n for n in nodes if n["label"] == "alpha" and "anomer" in n["line"]]


@pytest.mark.parametrize("name,wrong", [
    ("ethanethiol", "-OH"),
    ("benzenesulfonic acid", "C(=O)OH"),
    ("methyl methanesulfonate", "ester"),
    ("4-methylbenzenesulfonamide", "C(=O)N"),
    ("pyridine-2(1H)-thione", "C=O"),
    ("phenoxyacetic acid", "-O- linkage"),
])
def test_no_part_line_states_a_wrong_group(name, wrong):
    t, nodes = _nodes(name)
    for n in nodes:
        if n["kind"] in PART_NODE_KINDS:
            assert wrong not in n["line"], (name, n["label"], n["line"])


# N1. an unbracketed compound substituent: the locant in front is the parent's
@pytest.mark.parametrize("name,part,locant,root", [
    ("2-propan-2-yloxyethanol", "propan-2-yl", "2", "ethan"),
    ("2-butan-2-yloxypyridine", "butan-2-yl", "2", "pyridine"),
    ("1-acetyloxy-2-methylbenzene", "acetyl", "1", "benzene"),
])
def test_a_compound_substituents_leading_locant_lights_the_parent_atom(name, part, locant, root):
    t, nodes = _nodes(name)
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == part]
    leading = min((n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"
                   and n["label"] == locant), key=lambda n: n["span"][0])
    (lit,) = _lit(t, nodes, leading)
    assert lit[0] == root and locant in lit[1], (name, lit)
    assert foreign_lights(t, nodes) == []


def test_a_nested_naphthyl_keeps_its_own_attachment_locant():
    t, nodes = _nodes("4-(2-naphthyl)phenol")
    (lit,) = _lit(t, nodes, _kid(nodes, "naphthyl", "2"))
    assert lit[0] == "naphthyl" and "2" in lit[1]


# OOS-1. a bracketed compound substituent: the number is on the parent, not acetyl's CH3
@pytest.mark.parametrize("name,part,locant,root", [
    ("4-(2-acetyloxyethyl)phenol", "acetyl", "2", "ethyl"),
    ("4-(2-benzoyloxyethyl)phenol", "benzoyl", "2", "ethyl"),
    ("4-(3-acetyloxypropyl)phenol", "acetyl", "3", "propyl"),
])
def test_a_bracketed_chain_locant_names_the_position_on_the_substituent_it_hangs_on(name, part, locant, root):
    t, nodes = _nodes(name)
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == part]
    leading = min((n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"
                   and n["label"] == locant), key=lambda n: n["span"][0])
    (lit,) = _lit(t, nodes, leading)
    assert lit[0] == root and locant in lit[1], (name, lit)
    assert foreign_lights(t, nodes) == []
    # the gate sees the old behaviour: a carbon of acetyl itself (its CH3 also carries a 2)
    own = next(a for a in p["owns"] if t.atoms[a].element == "C")
    leading["lights"] = [own]
    assert foreign_lights(t, nodes) == [(locant, [own])]


# NB5. a ring substituent's own attachment number, followed by a linker ("2-pyridylmethyl"):
# the inner number is the ring's, even when the parent has a position with the same number
@pytest.mark.parametrize("name,part", [
    ("2-(2-pyridylmethyl)benzoic acid", "pyridyl"),
    ("2-(2-pyridylmethoxy)benzaldehyde", "pyridyl"),
    ("3-(3-pyridylmethyl)benzoic acid", "pyridyl"),
    ("2-(2-thienylmethyl)pyridine", "thienyl"),
    ("2-(2-furylmethylsulfanyl)pyridine", "furyl"),
    ("2-(2-naphthyloxy)propanoic acid", "naphthyl"),
    ("N-(2-pyridylmethyl)acetamide", "pyridyl"),       # different numbers: was always right
])
def test_a_ring_substituents_own_attachment_locant_lights_its_own_atom(name, part):
    t, nodes = _nodes(name)
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == part]
    leading = min((n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"),
                  key=lambda n: n["span"][0])
    (atom,) = leading["lights"]
    mol = Chem.MolFromSmiles(t.smiles)
    assert atom in p["owns"] and leading["label"] in t.atoms[atom].locants, (name, leading)
    assert mol.GetAtomWithIdx(atom).IsInRing()
    assert any(n not in p["owns"] for n in _neighbours(t, atom))          # the atom the linker hangs on
    assert foreign_lights(t, nodes) == [], name
    # the gate sees the old behaviour: the parent's position carrying the same number
    if name.startswith("N-"):
        return
    root = next(n for n in nodes if n["kind"] == "parent")
    foreign = next(a for a in root["owns"] if leading["label"] in t.atoms[a].locants)
    leading["lights"] = [foreign]
    assert foreign_lights(t, nodes) == [(leading["label"], [foreign])], name


def _owner_label(nodes, atom):
    return next(n["label"] for n in nodes if n["kind"] in PART_NODE_KINDS and atom in n["owns"])


# NB6 + NB7 (controller ruling, IUPAC P-16.5.1). A leading locant written directly before an
# UNBRACKETED chained substituent names the PARENT position the whole chain hangs on -- always.
# A ring's own attachment number is only one written inside it ("pyridin-2-yl"), read from the
# written text (OPSIN drops that token). Bracketed chains keep their own reading.
@pytest.mark.parametrize("name,part,root", [
    # NB6: the ring writes its own attachment; the number in front is still the parent's
    ("2-pyridin-2-yloxybenzoic acid", "pyridin-2-yl", "benz"),
    ("2-naphthalen-2-yloxyacetic acid", "naphthalen-2-yl", "acet"),
    ("3-pyridin-3-yloxypropan-1-ol", "pyridin-3-yl", "propan"),
    ("4-pyridin-4-ylmethylpyridine", "pyridin-4-yl", "pyridine"),
    ("2-thiophen-2-ylmethylpyridine", "thiophen-2-yl", "pyridine"),
    # NB7: phenyl / cyclohexyl never write an attachment, and the linker's own "1" is not a position
    ("1-phenylmethoxynaphthalene", "phenyl", "naphthalene"),
    ("1-phenylmethoxy-4-nitrobenzene", "phenyl", "benzene"),
    ("1-cyclohexyloxy-4-nitrobenzene", "cyclohexyl", "benzene"),
    ("1-phenylsulfanyl-2-nitrobenzene", "phenyl", "benzene"),
    ("1-cyclohexylmethoxybenzene", "cyclohexyl", "benzene"),
    ("1-phenylmethylpiperazine", "phenyl", "piperazine"),
    ("1-naphthalen-1-ylmethylnaphthalene", "naphthalen-1-yl", "naphthalene"),
    # the round-4 reading of these two (the ring's own number) is reversed: unbracketed -> parent
    ("2-pyridyloxybenzoic acid", "pyridyl", "benz"),
    ("2-naphthyloxyacetic acid", "naphthyl", "acet"),
])
def test_a_leading_locant_before_an_unbracketed_chain_names_the_parent_position(name, part, root):
    t, nodes = _nodes(name)
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == part]
    leading = min((n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"),
                  key=lambda n: n["span"][0])
    (atom,) = leading["lights"]
    assert atom not in p["owns"] and leading["label"] in t.atoms[atom].locants, (name, leading)
    assert _owner_label(nodes, atom).startswith(root), (name, _owner_label(nodes, atom))
    assert foreign_lights(t, nodes) == [], name
    # the gate sees the old behaviour: an atom of the substituent (or its linker) for that number
    chain = [a for n in nodes if n["kind"] == "substituent" for a in n["owns"]
             if leading["label"] in t.atoms[a].locants]
    assert chain, name
    leading["lights"] = [chain[0]]
    assert foreign_lights(t, nodes) == [(leading["label"], [chain[0]])], name


@pytest.mark.parametrize("name,part", [
    ("2-(2-pyridylmethyl)benzoic acid", "pyridyl"),
    ("2-(2-naphthyloxy)propanoic acid", "naphthyl"),
])
def test_a_bracketed_chain_keeps_the_rings_own_attachment_locant(name, part):
    t, nodes = _nodes(name)
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == part]
    inner = min((n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"),
                key=lambda n: n["span"][0])
    (atom,) = inner["lights"]
    assert atom in p["owns"], (name, inner)
    assert foreign_lights(t, nodes) == [], name


def test_a_linkers_own_number_is_not_a_position_the_bracketed_chain_hangs_on():
    """NB7, chain_edge: "(1-phenylmethoxyethyl)": methoxy's CH2 carries 1/C, but the 1 is ethyl's."""
    t, nodes = _nodes("4-(1-phenylmethoxyethyl)phenol")
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == "phenyl"]
    (leading,) = [n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"]
    (atom,) = leading["lights"]
    assert _owner_label(nodes, atom) == "ethyl" and "1" in t.atoms[atom].locants
    assert foreign_lights(t, nodes) == []


# -- Task 9 (ChEMBL census): a leading locant before a chain of substituents ---------------
def _leading(nodes, part):
    (p,) = [n for n in nodes if n["kind"] == "substituent" and n["label"] == part]
    return p, min((n for n in nodes if n["parent"] == p["id"] and n["kind"] == "locant"),
                  key=lambda n: n["span"][0])


# "cyclo" / "tert-" are part of the substituent's own name, so the number written before
# them still leads a BRACKETED chain: it names the position on the chain member it hangs on
@pytest.mark.parametrize("name,part,root,element", [
    ("3-(4-cyclopropylmethoxybenzamido)benzoic acid", "cyclopropyl", "benzamido", "C"),
    ("4-(2-cyclopropylmethylaminopyridin-4-yl)pyridine", "cyclopropyl", "pyridin-4-yl", "C"),
])
def test_a_locant_before_a_cyclo_substituent_in_a_bracket_names_the_position_it_hangs_on(
        name, part, root, element):
    t, nodes = _nodes(name)
    p, leading = _leading(nodes, part)
    (atom,) = leading["lights"]
    assert atom not in p["owns"] and leading["label"] in t.atoms[atom].locants
    assert t.atoms[atom].element == element and _owner_label(nodes, atom) == root
    assert foreign_lights(t, nodes) == []
    leading["lights"] = [next(a for a in p["owns"] if t.atoms[a].element == "C")]       # the ring's own carbon
    assert foreign_lights(t, nodes) == [(leading["label"], leading["lights"])]


# an element-symbol number ("N-ethylcarbamoyl") names the atom of the chain member it hangs on,
# never the same-lettered atom of the first member nor the linker
@pytest.mark.parametrize("name,part,owner", [
    ("N-ethylcarbamoyl-2-methoxy-4-[(methylamino)methyl]-1-(methylsulfanyl)benzene", "ethyl", "carbamoyl"),
    ("4-(N-diaminomethylidenecarbamimidoyl)piperazine", "amino", "carbamimidoyl"),
])
def test_an_element_symbol_locant_before_a_chain_names_that_atom_of_a_later_member(name, part, owner):
    t, nodes = _nodes(name)
    p, leading = _leading(nodes, part)
    assert leading["label"] == "N"
    (atom,) = leading["lights"]
    assert t.atoms[atom].element == "N" and "N" in t.atoms[atom].locants
    assert atom not in p["owns"] and _owner_label(nodes, atom) == owner
    assert foreign_lights(t, nodes) == []
    leading["lights"] = [next(a for a in p["owns"] if "N" in t.atoms[a].locants or t.atoms[a].element == "C")]
    assert foreign_lights(t, nodes) == [(leading["label"], leading["lights"])]


# a locant before a heteroatom token is a replacement locant only when a heteroatom sits there
def test_a_locant_before_oxiranyl_is_the_position_the_chain_hangs_on_not_a_replacement_locant():
    t, nodes = _nodes("3-oxiranylmethoxybenzoic acid")
    p, leading = _leading(nodes, "oxiranyl")              # the label no longer swallows the "3-"
    (atom,) = leading["lights"]
    assert atom not in p["owns"] and _owner_label(nodes, atom).startswith("benz")
    assert "3" in t.atoms[atom].locants and foreign_lights(t, nodes) == []
    # a real replacement locant keeps being part of the name
    t, nodes = _nodes("5-(1,3-dioxolan-2-yl)pentan-2-one")
    (ring,) = [n for n in nodes if n["kind"] == "substituent"]
    assert ring["label"].startswith("1,3-dioxolan")
    assert [t.atoms[a].element for n in nodes if n["kind"] == "locant" and n["label"] in ("1", "3")
            and n["parent"] == ring["id"] for a in n["lights"]] == ["O", "O"]


# N-5a: the gate called correct builder output foreign on unbracketed ester alcohol chains, where
# the number names a position INSIDE the chain (the builder falls back to the chain edge)
@pytest.mark.parametrize("name,part,locant,owner", [
    ("2-acetyloxyethyl acetate", "acetyl", "2", "ethyl"),
    ("2-benzoyloxyethyl benzoate", "benzoyl", "2", "ethyl"),
    ("3-acetyloxypropyl acetate", "acetyl", "3", "propyl"),
])
def test_the_gate_accepts_a_number_naming_a_later_member_of_an_unbracketed_chain(name, part, locant, owner):
    t, nodes = _nodes(name)
    p, leading = _leading(nodes, part)
    assert leading["label"] == locant
    (atom,) = leading["lights"]
    assert _owner_label(nodes, atom) == owner and locant in t.atoms[atom].locants
    assert foreign_lights(t, nodes) == []
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]
    # ...and is still strict: the chain's own carbon for that number is foreign
    own = next(a for a in p["owns"] if t.atoms[a].element == "C")
    leading["lights"] = [own]
    assert foreign_lights(t, nodes) == [(locant, [own])]
