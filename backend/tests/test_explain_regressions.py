"""Named regressions from the Fable 5.1 review of plan v2 (JVM + engine).
Each class once lit a wrong atom or showed a false line while every gate
stayed green; each test pins the corrected behaviour on a live trace."""

import pytest

from app.explain_tree import PART_NODE_KINDS, build_nodes
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
