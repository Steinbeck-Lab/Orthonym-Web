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


# -- Task 9: hydro locants of a LATER spiro component name OPSIN's primed atoms --------------
SPIRO_HYDRO_B = ("3-(4-fluorophenyl)-1'-[(2-fluorophenyl)methyl]-2',4-dioxospiro"
                 "[1,3-thiazolidine-2,3'-2,3-dihydro-1H-indole]")


def test_hydro_locants_in_the_second_spiro_component_light_the_primed_atoms():
    """"spiro[1,3-thiazolidine-2,3'-2,3-dihydro-1H-indole]": the indole is the second
    component, so its 2,3-dihydro and 1H are positions 2', 3' and 1'. The census gate
    reads that numbering (and stays exact): the first component's 2 and 3 are wrong."""
    t, nodes = _nodes(SPIRO_HYDRO_B)
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]
    h = _one(nodes, kind="indicated_h", label="1H")
    (atom,) = h["lights"]
    assert t.atoms[atom].element == "N" and "1'" in t.atoms[atom].locants
    dihydro = t.text.index("2,3-dihydro")
    two = next(n for n in nodes if n["kind"] == "locant" and n["span"] == [dihydro, dihydro + 1])
    (atom,) = two["lights"]
    assert "2'" in t.atoms[atom].locants
    # the old reading: the thiazolidine carbon that carries a bare 2
    wrong = next(a.index for a in t.atoms if "2" in a.locants)
    two["lights"] = [wrong]
    assert "HYDRO_WRONG" in classify(t, nodes, assign_owners(t.tokens))


def test_the_primes_of_a_spiro_system_restart_at_the_next_spiro_system():
    """Two spiro systems in one name: the first component of the SECOND ("6H,7H-furo...")
    is unprimed again, however many spiro locants were written before it."""
    t, nodes = _nodes("3-hydroxy-7,7-dimethyl-1'-[4'-oxospiro[2,3-dihydro-1H-indene-2,5'-"
                      "4,5-dihydro-1,3-oxazole]-2'-yl]spiro[6H,7H-furo[3,4-b]pyridine-5,4'-piperidine]")
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]
    for label, element in (("6H", "O"), ("7H", "C")):
        h = _one(nodes, kind="indicated_h", label=label)
        (atom,) = h["lights"]
        assert label[:-1] in t.atoms[atom].locants and t.atoms[atom].element == element
    four_five = t.text.index("4,5-dihydro")
    four = next(n for n in nodes if n["kind"] == "locant" and n["span"] == [four_five, four_five + 1])
    (atom,) = four["lights"]
    assert "4'" in t.atoms[atom].locants                      # the first system's second component


# -- Phase C fix round 1 ------------------------------------------------------------------
def _spiro_kids(nodes, label, after):
    return [n for n in nodes if n["kind"] in ("locant", "indicated_h") and n["label"] == label
            and n["span"] and n["span"][0] >= after]


I1_ACID = "(2-oxospiro[indole-3,4'-piperidin]-1(2H)-yl)acetic acid"
I1_IUM = "1-oxidospiro[2,3-dihydro-1-benzothiophene-3,4'-piperidine]-1-ium"


def _chembl_name(fragment):
    from pathlib import Path
    path = Path(__file__).with_name("fixtures") / "explain_chembl_10k.tsv"
    (name,) = [line.split("\t", 1)[1].rstrip("\n") for line in path.open() if fragment in line]
    return name


# I1. a locant written AFTER the spiro bracket is the whole part's own number, never a later
# component's: the -1(2H)-yl of an N-substituted spiro-oxindole is the INDOLE nitrogen
def test_a_locant_after_the_spiro_bracket_is_not_primed():
    t, nodes = _nodes(I1_ACID)
    close = t.text.index("]")
    (one,) = _spiro_kids(nodes, "1", close)
    (atom,) = one["lights"]
    assert t.atoms[atom].element == "N" and "1" in t.atoms[atom].locants and "1'" not in t.atoms[atom].locants
    (h,) = _spiro_kids(nodes, "2H", close)
    (atom,) = h["lights"]
    assert t.atoms[atom].element == "C" and "2" in t.atoms[atom].locants
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


@pytest.mark.parametrize("name", [I1_IUM, "CHEMBL90291"])
def test_a_charge_locant_after_the_spiro_bracket_names_the_charged_sulfur(name):
    if name == "CHEMBL90291":
        name = _chembl_name("CHEMBL90291")
    t, nodes = _nodes(name)
    close = t.text.rindex("]")
    (one,) = _spiro_kids(nodes, "1", close)
    (atom,) = one["lights"]
    assert t.atoms[atom].element == "S" and "1" in t.atoms[atom].locants
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


# I2. the hydro gate bounds its primes at the bracket too
def test_the_hydro_gate_accepts_a_bare_locant_after_the_spiro_bracket_and_refuses_a_primed_one():
    name = "spiro[indole-3,4'-piperidin]-2(1H)-one"
    t, nodes = _nodes(name)
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]
    h = _one(nodes, kind="indicated_h", label="1H")
    (atom,) = h["lights"]
    assert t.atoms[atom].element == "N" and "1" in t.atoms[atom].locants
    primed = next(a.index for a in t.atoms if "1'" in a.locants)
    h["lights"] = [primed]
    assert "HYDRO_WRONG" in classify(t, nodes, assign_owners(t.tokens))
    # and the I1 wrong atom (the pre-fix builder output) is no longer waved through
    t, nodes = _nodes(I1_ACID)
    h = _spiro_kids(nodes, "2H", t.text.index("]"))[0]
    h["lights"] = [next(a.index for a in t.atoms if "2'" in a.locants)]
    assert "HYDRO_WRONG" in classify(t, nodes, assign_owners(t.tokens))


# I3. the census class that sees a wrong atom of the right part
def test_locant_wrong_atom_catches_the_round_0_wrong_atoms(monkeypatch):
    """Not vacuous: the I1 charge locant lit on the piperidine N1', and an I4 position lit on
    the ring heteroatom that also carries a 1, are both LOCANT_WRONG_ATOM (and census CLEAN
    before this class existed)."""
    t, nodes = _nodes(I1_IUM)
    (one,) = _spiro_kids(nodes, "1", t.text.rindex("]"))
    one["lights"] = [next(a.index for a in t.atoms if "1'" in a.locants and a.element == "N")]
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    t, nodes = _nodes(I1_ACID)
    one = _spiro_kids(nodes, "1", t.text.index("]"))[0]
    one["lights"] = [next(a.index for a in t.atoms if "1'" in a.locants and a.element == "N")]
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    t, nodes = _nodes("1-oxiranylpropan-2-one")
    p, leading = _leading(nodes, "oxiranyl")
    ring_o = next(a.index for a in t.atoms if a.element == "O" and "1" in a.locants and a.index in p["owns"])
    leading["lights"] = [ring_o]
    leading["line"] = "Position 1."                  # what the round-0 builder said: the part's own number
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    # a primed locant after the bracket is wrong, a bare one inside a later component is wrong
    t, nodes = _nodes("spiro[indole-3,4'-piperidin]-2(1H)-one")
    two = next(n for n in nodes if n["kind"] == "locant" and n["label"] == "2" and n["span"][0] > t.text.index("]"))
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]
    two["lights"] = [a.index for a in t.atoms if "2'" in a.locants]
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))


# I4. OPSIN placed the ring at the written leading number: it is the parent chain's position
@pytest.mark.parametrize("name,part,root", [
    ("1-oxiranylpropan-2-one", "oxiranyl", "propan"),
    ("1-oxiranylethanone", "oxiranyl", "ethan"),
    ("1-thiiranylethanone", "thiiranyl", "ethan"),
    ("1-aziridinylpropan-2-ol", "aziridinyl", "propan"),
])
def test_a_leading_number_opsin_placed_the_ring_at_is_the_parent_chains_position(name, part, root):
    """The 1 is where OPSIN put the ring on the parent chain, like any placed substituent
    ("4-chloro"): it lights what sits at that position, with the "attached at position" line,
    and the label no longer swallows it. Round 0 lit the ring heteroatom ("Position 1.")."""
    t, nodes = _nodes(name)
    p, leading = _leading(nodes, part)                 # the label is "oxiranyl", not "1-oxiranyl"
    assert sorted(leading["lights"]) == sorted(p["owns"])
    assert "attached at position 1" in leading["line"]
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


def test_a_number_before_a_long_alkane_stem_is_a_position_when_opsin_placed_the_part_there():
    t, nodes = _nodes("N-hexadecylnaphthalen-1-amine")
    p, leading = _leading(nodes, "hexadecyl")          # round 0: label "N-hexadecyl", "Position N." lit the whole chain
    assert sorted(leading["lights"]) == sorted(p["owns"]) and "attached at position N" in leading["line"]
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


def test_a_bridge_prefix_belongs_to_the_ring_it_bridges_not_the_substituent_written_after_it():
    t, nodes = _nodes("(5S,9R,13S,14R)-4,5-epoxy-17-methylmorphinane")
    (root,) = [n for n in nodes if n["kind"] == "parent"]
    methyl = _one(nodes, kind="substituent", label="methyl")
    for label in ("4", "5"):
        (n,) = [x for x in nodes if x["kind"] == "locant" and x["label"] == label and x["parent"] == root["id"]]
        (atom,) = n["lights"]
        assert label in t.atoms[atom].locants and atom in root["owns"]
    (seventeen,) = [x for x in nodes if x["kind"] == "locant" and x["label"] == "17"]
    assert seventeen["parent"] == methyl["id"]
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


# -- Phase C fix round 2 ------------------------------------------------------------------
CODEINE = "(5alpha,6alpha)-7,8-didehydro-4,5-epoxy-3-methoxy-17-methylmorphinan-6-ol"


@pytest.mark.parametrize("name", [
    CODEINE,
    "4,5alpha-epoxy-3-methoxy-17-methylmorphinan-6-one",
    "(5S,9R,13S,14R)-4,5-epoxy-17-methylmorphinane",
])
def test_the_parent_label_stays_on_the_stem_and_the_bridge_prefix_is_its_own_child(name):
    """N1: the bridge prefix moved to the root dragged the root's label across the methoxy and
    methyl written between 'epoxy' and the stem ('epoxy-3-methoxy-17-methylmorphinan')."""
    from scripts.explain_census import contained_parts
    t, nodes = _nodes(name)
    (root,) = [n for n in nodes if n["kind"] == "parent"]
    assert root["label"].startswith("morphin") and "epoxy" not in root["label"] and "methyl" not in root["label"]
    epoxy = _one(nodes, kind="token", label="epoxy")
    assert epoxy["parent"] == root["id"] and "bridge" in epoxy["line"]
    assert contained_parts(nodes) == []
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


def test_the_bridge_prefix_lights_the_positions_it_bridges():
    t, nodes = _nodes(CODEINE)
    epoxy = _one(nodes, kind="token", label="epoxy")
    assert sorted(("4" in t.atoms[a].locants, "5" in t.atoms[a].locants) for a in epoxy["lights"]) \
        == [(False, True), (True, False)]
    for label in ("4", "5"):
        node = next(n for n in nodes if n["kind"] == "locant" and n["label"] == label
                    and n["parent"] == epoxy["parent"])
        (atom,) = node["lights"]
        assert label in t.atoms[atom].locants and atom in epoxy["lights"]


def test_part_contains_part_catches_a_label_that_swallows_a_neighbour():
    """Not vacuous: widen the root's span back to the round-1 'epoxy-3-methoxy-17-methylmorphinan'."""
    t, nodes = _nodes(CODEINE)
    (root,) = [n for n in nodes if n["kind"] == "parent"]
    root["span"] = [t.text.index("epoxy"), root["span"][1]]
    root["label"] = t.text[root["span"][0]:root["span"][1]]
    assert "PART_CONTAINS_PART" in classify(t, nodes, assign_owners(t.tokens))


# N2. numbers inside a fusion component's own brackets are the COMPONENT's numbering
def _ring_mates(t, a, b):
    mol = Chem.MolFromSmiles(t.smiles)             # keep the Mol alive while its RingInfo is read
    return any(a in r and b in r for r in mol.GetRingInfo().AtomRings())


def test_a_fusion_components_numbers_light_the_atoms_the_element_and_ring_prove():
    """"[1,3]thiazolo[5,4-b]pyridine": thiazole's 1 is S and its 3 is N. The fused system's own
    N1 / S3 carry the swapped numbers, which is what round 1 lit."""
    t, nodes = _nodes("[1,3]thiazolo[5,4-b]pyridine")
    one = _one(nodes, kind="locant", label="1")
    three = _one(nodes, kind="locant", label="3")
    (s_atom,) = one["lights"]
    (n_atom,) = three["lights"]
    assert t.atoms[s_atom].element == "S" and t.atoms[n_atom].element == "N"
    assert _ring_mates(t, s_atom, n_atom)                  # the thiazole N, not the pyridine N
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


@pytest.mark.parametrize("name", [
    "[1,2,4]triazolo[1,5-a]pyrimidine", "[1,2,4]triazolo[1,5-a]pyridine", "[1,2,4]triazolo[4,3-a]pyridine",
    "6-chloro-[1,2,4]triazolo[1,5-a]pyrimidin-2-amine",
])
def test_a_fusion_number_no_evidence_pins_to_one_atom_lights_nothing_and_is_not_a_failure(name):
    t, nodes = _nodes(name)
    kids = [n for n in nodes if n["kind"] == "locant" and n["span"][1] < t.text.index("triazolo")]
    assert [n["label"] for n in kids if n["span"][0] > t.text.index("[1,2,4]") - 1][:3] == ["1", "2", "4"]
    assert all(n["lights"] == [] for n in kids if n["label"] in ("1", "2", "4") and n["span"][0] < t.text.index("triazolo"))
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]        # not LOCANT_UNLIT


def test_a_fusion_component_number_lights_only_what_is_proven_when_some_are_not():
    t, nodes = _nodes("[1,2,5]oxadiazolo[3,4-b]pyrazine")
    by = {n["label"]: n for n in nodes if n["kind"] == "locant"}
    (o_atom,) = by["1"]["lights"]
    assert t.atoms[o_atom].element == "O"                  # the only oxygen
    assert by["2"]["lights"] == [] and by["5"]["lights"] == []     # two equal nitrogens: not provable


def test_locant_wrong_atom_catches_the_round_1_fusion_component_atoms():
    """Not vacuous: round 1 lit the fused system's atom with the same NUMBER."""
    t, nodes = _nodes("[1,3]thiazolo[5,4-b]pyridine")
    one = _one(nodes, kind="locant", label="1")
    three = _one(nodes, kind="locant", label="3")
    good1, good3 = list(one["lights"]), list(three["lights"])
    one["lights"] = [next(a.index for a in t.atoms if "1" in a.locants)]          # fused N1
    assert t.atoms[one["lights"][0]].element == "N"
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    one["lights"] = good1
    three["lights"] = [next(a.index for a in t.atoms if a.element == "N" and a.index != good3[0])]   # pyridine N
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    three["lights"] = good3
    t, nodes = _nodes("[1,2,4]triazolo[1,5-a]pyrimidine")
    two = _one(nodes, kind="locant", label="2")
    two["lights"] = [next(a.index for a in t.atoms if "2" in a.locants)]           # fused C2, a carbon
    assert t.atoms[two["lights"][0]].element == "C"
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))


# -- Phase C fix round 3 ------------------------------------------------------------------
# R2-1. the BASE component's bracketed numbers, written after the fusion descriptor
def test_a_fusion_base_components_numbers_light_the_atoms_the_element_and_ring_prove():
    """"imidazo[2,1-b][1,3]thiazole": thiazole's 3 is a nitrogen; round 2 lit fused C3."""
    t, nodes = _nodes("imidazo[2,1-b][1,3]thiazole")
    one = _one(nodes, kind="locant", label="1")
    three = _one(nodes, kind="locant", label="3")
    (s_atom,) = one["lights"]
    (n_atom,) = three["lights"]
    assert t.atoms[s_atom].element == "S" and t.atoms[n_atom].element == "N" and _ring_mates(t, s_atom, n_atom)
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


def test_a_benzo_led_component_and_a_base_after_a_prefix_use_the_same_rule():
    t, nodes = _nodes("pyrimido[2,1-b][1,3]benzothiazole")
    one, three = _one(nodes, kind="locant", label="1"), _one(nodes, kind="locant", label="3")
    assert [t.atoms[a].element for a in one["lights"] + three["lights"]] == ["S", "N"]
    t, nodes = _nodes("[1,3]benzodioxolo[5,6-g]quinoline")           # two equal oxygens: not provable
    assert [n["lights"] for n in nodes if n["kind"] == "locant" and n["label"] in ("1", "3")
            and n["span"][0] < 6] == [[], []]
    t, nodes = _nodes("pyrrolo[2,1-f][1,2,4]triazine")
    assert [n["lights"] for n in nodes if n["kind"] == "locant" and n["label"] in ("1", "2", "4")] == [[], [], []]
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


@pytest.mark.parametrize("name", [
    "imidazo[2,1-b][1,3]thiazole", "6-phenyl-2,3,5,6-tetrahydroimidazo[2,1-b][1,3]thiazole",
    "pyrrolo[2,1-f][1,2,4]triazine", "pyrimido[2,1-b][1,3]benzothiazole",
])
def test_locant_wrong_atom_catches_the_round_2_base_component_atoms(name):
    """Not vacuous: round 2 lit the fused system's atom carrying the same number."""
    t, nodes = _nodes(name)
    node = [n for n in nodes if n["kind"] == "locant" and n["label"] in ("1", "2", "3", "4")
            and n["span"][0] > t.text.index("][")][-1]                  # the last: its fused atom differs
    node["lights"] = [next(a.index for a in t.atoms if node["label"] in a.locants)]      # the fused atom
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))


def test_a_bare_replacement_locant_keeps_its_fused_lookup():
    """Minor (b): "4-azabenzo[a]pyrene" is in the fused system's own numbering, not bracketed."""
    t, nodes = _nodes("4-azabenzo[a]pyrene")
    four = _one(nodes, kind="locant", label="4")
    (atom,) = four["lights"]
    assert t.atoms[atom].element == "N" and "4" in t.atoms[atom].locants


# Minor (a). the LOCANT_UNLIT exemption covers only numbers the evidence cannot pin
def test_a_provable_fusion_number_that_lights_nothing_is_a_failure():
    t, nodes = _nodes("[1,3]thiazolo[5,4-b]pyridine")
    _one(nodes, kind="locant", label="1")["lights"] = []
    assert "LOCANT_UNLIT" in classify(t, nodes, assign_owners(t.tokens)) or \
        "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    t, nodes = _nodes("[1,2,4]triazolo[1,5-a]pyrimidine")            # unprovable: nothing is right
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


# R2-2. a bare number split out of a stereo token belongs to the suffix only if it is the suffix's
@pytest.mark.parametrize("name", [
    "4,5alpha-epoxy-3-methoxy-17-methylmorphinan-6-one",
    "4,5alpha-epoxy-14-hydroxy-3-methoxy-17-methylmorphinan-6-one",
])
def test_the_four_of_four_five_alpha_epoxy_belongs_to_the_bridge_not_the_ketone(name):
    t, nodes = _nodes(name)
    epoxy = _one(nodes, kind="token", label="epoxy")
    four = next(n for n in nodes if n["kind"] == "locant" and n["label"] == "4" and n["span"][0] == 0)
    assert four["parent"] == epoxy["id"] and "attached at position" not in four["line"]
    (atom,) = four["lights"]
    assert "4" in t.atoms[atom].locants and atom in epoxy["lights"]
    assert sorted(epoxy["lights"]) == sorted(a.index for a in t.atoms if {"4", "5"} & set(a.locants)
                                             and a.element == "C" and a.index in four["lights"] + epoxy["lights"])
    suffix = _one(nodes, kind="suffix", label="one")
    assert [n["label"] for n in nodes if n["kind"] == "locant" and n["parent"] == suffix["id"]] == ["6"]
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


def test_a_locant_under_a_suffix_must_be_one_the_suffix_is_bonded_to():
    """Not vacuous: the pre-fix tree, with the 4 under the ketone."""
    t, nodes = _nodes("4,5alpha-epoxy-3-methoxy-17-methylmorphinan-6-one")
    suffix = _one(nodes, kind="suffix", label="one")
    four = next(n for n in nodes if n["kind"] == "locant" and n["label"] == "4" and n["span"][0] == 0)
    four["parent"] = suffix["id"]
    assert "LOCANT_WRONG_ATOM" in classify(t, nodes, assign_owners(t.tokens))
    # "3,17beta-diol": the numbers the diol is bonded to stay fine
    t, nodes = _nodes("estra-1,3,5(10)-triene-3,17beta-diol")
    assert classify(t, nodes, assign_owners(t.tokens)) == ["CLEAN"]


# Minor (c). the exemptions read tokens and parts, not the glossary's words
@pytest.mark.parametrize("name", [
    "4,5alpha-epoxy-3-methoxy-17-methylmorphinan-6-one", "3-(α-D-mannopyranosyloxy)benzoic acid",
    "1-oxiranylpropan-2-one", "6-phenyl-2,3,5,6-tetrahydroimidazo[2,1-b][1,3]thiazole",
    "3α,21-dihydroxy-5α-pregnan-20-one", "N-hexadecylnaphthalen-1-amine",
    "2-(2-pyridylmethyl)benzoic acid", "(2R,3S)-2-(3,4-dihydroxyphenyl)-5,7-dihydroxy-3-(β-D-xylopyranosyloxy)-2,3-dihydro-4H-1-benzopyran-4-one",
])
def test_the_gate_does_not_depend_on_the_wording_of_a_line(name):
    t, nodes = _nodes(name)
    before = classify(t, nodes, assign_owners(t.tokens))
    for n in nodes:
        n["line"] = "reworded"
    assert classify(t, nodes, assign_owners(t.tokens)) == before == ["CLEAN"]


# ======================================================================================
# Final whole-branch review (Fable 5.1): I1, I2, I3, I5, M1, M4, M5, M8
# ======================================================================================

def _owner(nodes, atom):
    return next(n for n in nodes if n["kind"] in PART_NODE_KINDS and atom in n["owns"])


def _clean(t, nodes):
    return classify(t, nodes, assign_owners(t.tokens))


# I1. "n-O-": the O names the PARENT's oxygen, the number the parent carbon it hangs on
@pytest.mark.parametrize("name,sub,parent,number", [
    ("4-O-beta-D-galactopyranosyl-D-glucopyranose", "galactopyranosyl", "glucopyranose", "4"),
    ("4-O-alpha-D-glucopyranosyl-D-glucopyranose", "glucopyranosyl", "glucopyranose", "4"),
    ("6-O-acetyl-D-glucopyranose", "acetyl", "glucopyranose", "6"),
    ("3-O-methyl-D-glucose", "methyl", "glucose", "3"),
    ("2-O-methyl-D-ribose", "methyl", "ribose", "2"),
])
def test_an_n_o_pair_lights_the_parents_oxygen_and_carbon_never_the_substituents_own(name, sub, parent, number):
    t, nodes = _nodes(name)
    child = _one(nodes, kind="substituent", label=sub)
    num = next(n for n in nodes if n["kind"] == "locant" and n["parent"] == child["id"] and n["label"] == number)
    oxy = next(n for n in nodes if n["kind"] == "locant" and n["parent"] == child["id"] and n["label"] == "O")
    (carbon,) = num["lights"]
    (oxygen,) = oxy["lights"]
    own = set(child["owns"])
    assert carbon not in own and oxygen not in own
    assert _owner(nodes, carbon)["label"] == parent and _owner(nodes, oxygen)["label"] == parent
    assert t.atoms[carbon].element == "C" and number in t.atoms[carbon].locants
    assert t.atoms[oxygen].element == "O"
    mol = Chem.MolFromSmiles(t.smiles)
    assert mol.GetBondBetweenAtoms(carbon, oxygen) is not None
    assert any(n.GetIdx() in own for n in mol.GetAtomWithIdx(oxygen).GetNeighbors())
    assert _clean(t, nodes) == ["CLEAN"]


def test_a_counted_n_o_pair_lights_each_parent_oxygen():
    t, nodes = _nodes("2,3,4-tri-O-acetyl-D-glucose")
    acetyl = _one(nodes, kind="substituent", label="acetyl")
    numbers = {n["label"]: n for n in nodes if n["kind"] == "locant" and n["parent"] == acetyl["id"]
               and n["label"] in ("2", "3", "4")}
    oxy = next(n for n in nodes if n["kind"] == "locant" and n["parent"] == acetyl["id"] and n["label"] == "O")
    assert sorted(len(n["lights"]) for n in numbers.values()) == [1, 1, 1] and len(oxy["lights"]) == 3
    for label, n in numbers.items():
        assert label in t.atoms[n["lights"][0]].locants and n["lights"][0] not in acetyl["owns"]
    # the counting word counts the acetyl groups, not the glucose carbons
    assert set(_one(nodes, kind="multiplier", label="tri")["lights"]) == set(acetyl["owns"])


@pytest.mark.parametrize("name", [
    "4-O-beta-D-galactopyranosyl-D-glucopyranose", "6-O-acetyl-D-glucopyranose", "3-O-methyl-D-glucose",
    "2,3,4-tri-O-acetyl-D-glucose",
])
def test_the_gate_refuses_a_pair_that_lights_the_substituents_own_atom(name):
    """Not vacuous: the review's old reading (the number and the O lighting the
    substituent's own atoms) is reported by both lit-atom checks."""
    t, nodes = _nodes(name)
    child = next(n for n in nodes if n["kind"] == "substituent")
    kids = [n for n in nodes if n["kind"] == "locant" and n["parent"] == child["id"] and n["lights"]
            and (n["label"] == "O" or n["label"].isdigit())]
    assert kids and _clean(t, nodes) == ["CLEAN"]
    for k in kids:
        k["lights"] = [child["owns"][0]]
    out = _clean(t, nodes)
    assert "LIT_ATOM_FOREIGN" in out and "LOCANT_WRONG_ATOM" in out
    assert foreign_lights(t, nodes)


def test_an_element_symbol_without_a_number_is_not_a_pair():
    """"N-methylacetamide": a lone element locant is the substituent's own position."""
    t, nodes = _nodes("N-methylacetamide")
    methyl = _one(nodes, kind="substituent", label="methyl")
    n = next(n for n in nodes if n["kind"] == "locant" and n["label"] == "N")
    assert "oxygen" not in n["line"] and "joined through" not in n["line"]
    assert n["lights"] and _clean(t, nodes) == ["CLEAN"]


# I2. a functional-class word owns its own atoms
@pytest.mark.parametrize("name,word,elements", [
    ("methyl ethyl ketone", "ketone", ["C", "O"]),
    ("ethyl methyl ketone", "ketone", ["C", "O"]),
    ("methyl isobutyl ketone", "ketone", ["C", "O"]),
    ("methyl vinyl ketone", "ketone", ["C", "O"]),
    ("methyl phenyl ketone", "ketone", ["C", "O"]),
    ("methyl tert-butyl ether", "ether", ["O"]),
    ("ethyl vinyl ether", "ether", ["O"]),
    ("ethyl phenyl ether", "ether", ["O"]),
    ("benzyl methyl ether", "ether", ["O"]),
    ("methyl phenyl sulfide", "sulfide", ["S"]),
    ("diethyl ether", "ether", ["O"]),
    ("dimethyl sulfoxide", "sulfoxide", ["O", "S"]),
    ("acetyl chloride", "chloride", ["Cl"]),
    ("benzyl alcohol", "alcohol", ["O"]),
    ("acetic anhydride", "anhydride", ["O"]),
    ("ethylene glycol", "glycol", ["O", "O"]),
])
def test_a_functional_word_owns_the_atoms_it_adds_and_the_alkyls_only_their_own(name, word, elements):
    t, nodes = _nodes(name)
    node = _one(nodes, label=word)
    assert node["kind"] == "suffix" and node["span"] is not None
    assert sorted(t.atoms[a].element for a in node["owns"]) == elements
    assert sorted(node["lights"]) == sorted(node["owns"])
    for n in nodes:
        if n["kind"] == "substituent" and n["label"] in ("methyl", "ethyl", "isobutyl", "vinyl", "phenyl",
                                                         "tert-butyl", "benzyl"):
            assert all(t.atoms[a].element == "C" for a in n["owns"]), (name, n["label"])
    assert t.text[node["span"][0]:node["span"][1]] == word
    assert _clean(t, nodes) == ["CLEAN"]


def test_the_ester_word_owns_no_atom_and_lights_nothing_else():
    """"L-alanine methyl ester hydrochloride": the word 'ester' used to light the chloride."""
    t, nodes = _nodes("L-alanine methyl ester hydrochloride")
    ester = _one(nodes, label="ester")
    assert ester["owns"] == [] and ester["lights"] == [] and ester["span"] is not None
    chloride = _one(nodes, label="hydrochloride")
    assert not set(chloride["lights"]) & set(ester["lights"])
    assert [n for n in nodes if n["kind"] != "stereo" and n["parent"] == chloride["id"]] == []
    assert _clean(t, nodes) == ["CLEAN"]


def test_two_functional_words_written_together_are_one_node_over_their_atoms():
    t, nodes = _nodes("ethyl methyl ketone oxime")
    word = _one(nodes, label="ketone oxime")
    assert sorted(t.atoms[a].element for a in word["owns"]) == ["C", "N", "O"]
    assert _clean(t, nodes) == ["CLEAN"]


def _swallow(t, nodes, word):
    """The pre-fix tree: the functional word's node removed, its atoms handed to the
    node written right before it, whose label now runs over the word."""
    fn = next(n for n in nodes if n["label"] == word)
    nodes.remove(fn)
    holder = max((n for n in nodes if n["kind"] in PART_NODE_KINDS and n["span"] and n["span"][1] <= fn["span"][0]),
                 key=lambda n: n["span"][1])
    holder["owns"] = sorted(set(holder["owns"]) | set(fn["owns"]))
    holder["span"] = [holder["span"][0], fn["span"][1]]
    holder["label"] = t.text[holder["span"][0]:holder["span"][1]]
    return holder


@pytest.mark.parametrize("name,word", [
    ("methyl ethyl ketone", "ketone"), ("diethyl ether", "ether"), ("acetic anhydride", "anhydride"),
    ("benzyl alcohol", "alcohol"),
])
def test_the_gate_sees_a_swallowed_functional_word(name, word):
    t, nodes = _nodes(name)
    _swallow(t, nodes, word)
    out = _clean(t, nodes)
    assert "FUNCTION_SWALLOWED" in out, out


def test_the_gate_sees_an_alkyl_that_owns_the_functional_groups_atoms():
    """The review's picture: "methyl" owning (and lighting) the C=O of methyl ethyl ketone."""
    t, nodes = _nodes("methyl ethyl ketone")
    ketone = _one(nodes, label="ketone")
    methyl = _one(nodes, label="methyl")
    methyl["owns"] = sorted(set(methyl["owns"]) | set(ketone["owns"]))
    ketone["owns"] = []
    assert "ALKYL_HETERO" in _clean(t, nodes)


# I3. lines that state chemistry are used only when the atoms bear them out
@pytest.mark.parametrize("name,label", [
    ("sodium acetate", "ate"), ("sodium benzoate", "oate"), ("calcium acetate", "ate"),
    ("lithium 2-hydroxypropanoate", "oate"), ("potassium 2-hydroxybenzoate", "oate"),
    ("2-(trimethylazaniumyl)acetate", "ate"),
])
def test_the_ate_line_is_true_of_a_carboxylate_salt(name, label):
    t, nodes = _nodes(name)
    line = _one(nodes, kind="suffix", label=label)["line"]
    assert "carboxylate salt" in line and "ester linkage" in line      # says both, claims neither alone
    assert _clean(t, nodes) == ["CLEAN"]


@pytest.mark.parametrize("name,label", [
    ("benzoic acid hydrazide", "oic acid"), ("isonicotinic acid hydrazide", "ic acid"),
    ("benzoic acid methyl ester", "oic acid"), ("acetic acid ethyl ester", "ic acid"),
])
def test_an_acid_ending_on_a_hydrazide_or_ester_does_not_claim_a_carboxylic_acid(name, label):
    t, nodes = _nodes(name)
    line = _one(nodes, kind="suffix", label=label)["line"]
    assert "C(=O)OH" not in line and "covers" in line
    assert _clean(t, nodes) == ["CLEAN"]


def test_the_one_ending_of_an_oxime_or_semicarbazone_does_not_claim_a_carbonyl():
    for name in ("cyclohexanone oxime", "cyclohexanone semicarbazone"):
        t, nodes = _nodes(name)
        assert not [n for n in nodes if n["kind"] == "suffix" and "a C=O group (a carbonyl)" in n["line"]], name
        assert _clean(t, nodes) == ["CLEAN"], name


def test_a_real_acid_and_a_real_ketone_keep_their_lines():
    t, nodes = _nodes("benzoic acid")
    assert "C(=O)OH" in _one(nodes, kind="suffix")["line"]
    t, nodes = _nodes("butan-2-one")
    assert "C=O" in _one(nodes, kind="suffix", label="one")["line"]


def test_the_gate_sees_a_false_suffix_claim(monkeypatch):
    from app import glossary
    t, nodes = _nodes("benzoic acid methyl ester")
    suffix = _one(nodes, kind="suffix", label="oic acid")
    suffix["line"] = glossary.describe_part("suffix", "oic acid", None, len(suffix["owns"]))   # the claim, asserted
    assert "LINE_CLAIM_FALSE" in _clean(t, nodes)
    # the review's salt: an ester claim on the -C(=O)O- of a carboxylate
    t, nodes = _nodes("sodium acetate")
    monkeypatch.setitem(glossary._SUFFIX_CLAIMS, "ate", "ester")
    assert "LINE_CLAIM_FALSE" in _clean(t, nodes)
    monkeypatch.undo()
    t, nodes = _nodes("ethyl acetate")
    monkeypatch.setitem(glossary._SUFFIX_CLAIMS, "ate", "ester")
    assert "LINE_CLAIM_FALSE" not in _clean(t, nodes)       # a real ester bears the claim out


# I5. an isotopic hydrogen belongs to the skeleton, not the characteristic group
def test_a_deuterium_is_the_skeletons_not_the_suffixs():
    t, nodes = _nodes("(2H3)methanol")
    ol = _one(nodes, kind="suffix", label="ol")
    assert [t.atoms[a].element for a in ol["owns"]] == ["O"]
    parent = _one(nodes, kind="parent", label="methan")
    assert sorted(t.atoms[a].element for a in parent["owns"]) == ["C", "H", "H", "H"]
    iso = _one(nodes, kind="token", label="2H3")
    assert sorted(iso["lights"]) == sorted(a for a in parent["owns"] if t.atoms[a].element == "H")
    assert "isotope" in iso["line"] and "written" not in iso["line"]
    assert _clean(t, nodes) == ["CLEAN"]


def test_the_gate_sees_a_hydrogen_in_a_suffix():
    t, nodes = _nodes("(2H3)methanol")
    ol = _one(nodes, kind="suffix", label="ol")
    parent = _one(nodes, kind="parent", label="methan")
    h = next(a for a in parent["owns"] if t.atoms[a].element == "H")
    parent["owns"].remove(h)
    ol["owns"].append(h)
    assert "SUFFIX_OWNS_H" in _clean(t, nodes)


# M1. one atom is not "1 atoms"
@pytest.mark.parametrize("name", ["sodium", "triethylamine", "hydroxylamine hydrochloride", "methane"])
def test_a_single_atom_parent_says_atom_not_atoms(name):
    t, nodes = _nodes(name)
    for n in nodes:
        assert "1 atoms" not in n["line"], (name, n["line"])
    assert any("1 atom." in n["line"] for n in nodes if n["kind"] == "parent")


# M4. an oxidation number belongs to the metal written before it
def test_an_oxidation_number_lights_its_metal_not_the_anion():
    t, nodes = _nodes("copper(II) sulfate pentahydrate")
    roman = _one(nodes, label="(II)")
    copper = _one(nodes, kind="parent", label="copper")
    assert roman["parent"] == copper["id"] and roman["lights"] == copper["owns"]
    assert "oxidation number" in roman["line"]
    assert _clean(t, nodes) == ["CLEAN"]
    sulfate = _one(nodes, kind="parent", label="sulfate")
    roman["lights"] = list(sulfate["owns"])
    assert "OXIDATION_WRONG" in _clean(t, nodes)


def test_water_of_crystallisation_is_not_called_the_core_skeleton():
    t, nodes = _nodes("magnesium sulfate heptahydrate")
    line = _one(nodes, kind="parent", label="hydrate")["line"]
    assert "water of crystallisation" in line and "core" not in line and "7 copies" in line


# M5. the prose of a parent stem is used only when the atom count fits it
@pytest.mark.parametrize("name,parent", [("acetophenone", "acet"), ("benzophenone", "benz")])
def test_a_parent_stem_whose_node_holds_more_than_the_stem_gets_the_neutral_line(name, parent):
    t, nodes = _nodes(name)
    node = _one(nodes, kind="parent", label=parent)
    assert "is the core skeleton" in node["line"] and "acetyl" not in node["line"] and "benzene ring" not in node["line"]
    assert _clean(t, nodes) == ["CLEAN"]
    # the gate: the prose asserted over atoms it does not fit
    from app import glossary
    prose, _ = glossary.parent_claim(parent)
    node["line"] = f'"{parent}" is {prose}. It holds {len(node["owns"])} atoms.'
    assert "LINE_CLAIM_FALSE" in _clean(t, nodes)


def test_a_parent_stem_that_fits_keeps_its_prose():
    t, nodes = _nodes("benzoic acid")
    assert "a benzene ring" in _one(nodes, kind="parent", label="benz")["line"]
    t, nodes = _nodes("ethanol")
    assert "two-carbon" in _one(nodes, kind="parent", label="ethan")["line"]


# M8. "bi" in "bicyclo[...]" counts rings, not copies
def test_a_von_baeyer_multiplier_counts_rings_and_dicyclohexyl_counts_copies():
    t, nodes = _nodes("bicyclo[2.2.2]octane")
    assert "rings of the cage" in _one(nodes, kind="multiplier", label="bi")["line"]
    t, nodes = _nodes("tricyclo[3.3.1.1^{3,7}]decane")
    assert "three" in _one(nodes, kind="multiplier", label="tri")["line"]
    t, nodes = _nodes("dicyclohexyl ether")
    assert "how many of the next group" in _one(nodes, kind="multiplier", label="di")["line"]
