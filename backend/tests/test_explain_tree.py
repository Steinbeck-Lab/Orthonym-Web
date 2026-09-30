"""Trace -> nodes, on stored traces (no JVM)."""

import re

import pytest

from app.explain_tree import PART_NODE_KINDS, build_nodes
from app.opsin_trace import Trace, TraceAtom, TracePart
from tests.fixtures.traces import load_traces

TRACES = load_traces()
CAFFEINE = "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione"
IBUPROFEN = "2-[4-(2-methylpropyl)phenyl]propanoic acid"
STEREO_LOCANT = re.compile(r"^(\d+[a-z]?'*)(?:[RSEZrs]\*?|alpha|beta)$")


def _nodes(name):
    t = TRACES[name]
    return t, build_nodes(t)


def _text(t, node):
    return t.text[node["span"][0]:node["span"][1]] if node["span"] else None


def _parts(nodes):
    return [n["label"] for n in nodes if n["kind"] in PART_NODE_KINDS]


def _under(nodes, parent, kind=None):
    return [n for n in nodes if n["parent"] == parent["id"] and (kind is None or n["kind"] == kind)]


@pytest.mark.parametrize("name,labels", [
    ("ethanol", ["ethan", "ol"]),
    (CAFFEINE, ["methyl", "purine", "dione"]),
    (IBUPROFEN, ["methyl", "propyl", "phenyl", "propan", "oic acid"]),
    ("1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane", ["chloro", "chloro", "phenyl", "ethane"]),
    ("1,3,5-triazine-2,4,6-triamine", ["1,3,5-triazine", "triamine"]),
    ("1H-tetrazole", ["tetrazole"]),
    ("dibenzo[b,d]furan", ["dibenzo[b,d]furan"]),
    ("[1,2,4]triazolo[4,3-a]pyridine", ["[1,2,4]triazolo[4,3-a]pyridine"]),
    ("7,8,9,10-tetrahydrobenzo[a]pyren-7-ol", ["benzo[a]pyren", "ol"]),
    ("alpha-D-glucopyranose", ["glucopyranose"]),
    ("propane-1,2,3-triyl trioctadecanoate", ["propane-1,2,3-triyl", "octadecan", "oate"]),
    ("N6-acetyl-L-lysine", ["acetyl", "lysine"]),
    ("(9Z,12Z)-octadeca-9,12-dienoic acid", ["octadeca-9,12-dien", "oic acid"]),
    ("4-tert-butylcyclohexan-1-ol", ["tert-butyl", "cyclohexan", "ol"]),
    ("ethyl acetate", ["ethyl", "acet", "ate"]),
    ("sodium hydrogen carbonate", ["sodium", "hydrogen", "carbonate"]),
    ("1,2,3,4-tetrahydro-1,4-methanonaphthalene", ["methanonaphthalene"]),
    ("6-methoxy-2-[(4-methoxy-3,5-dimethylpyridin-2-yl)methylsulfinyl]-1H-benzimidazole",
     ["methoxy", "methoxy", "methyl", "pyridin-2-yl", "methyl", "sulfinyl", "benzimidazole"]),
])
def test_part_labels(name, labels):
    assert _parts(_nodes(name)[1]) == labels


def test_caffeine_position_locants_each_light_one_methyl():
    t, nodes = _nodes(CAFFEINE)
    (methyl,) = [n for n in nodes if n["label"] == "methyl"]
    kids = _under(nodes, methyl, "locant")
    assert sorted(n["label"] for n in kids) == ["1", "3", "7"]
    lit = [tuple(n["lights"]) for n in kids]
    assert all(len(x) == 1 for x in lit) and {x[0] for x in lit} == set(methyl["owns"])


def test_caffeine_hydro_and_indicated_hydrogen_light_ring_nitrogens():
    t, nodes = _nodes(CAFFEINE)
    (purine,) = [n for n in nodes if n["label"] == "purine"]
    hydro_locants = [n for n in _under(nodes, purine, "locant") if n["span"][0] < t.text.index("hydro")]
    assert sorted(n["label"] for n in hydro_locants) == ["3", "7"]
    for n in hydro_locants:
        (atom,) = n["lights"]
        assert t.atoms[atom].element == "N" and n["label"] in t.atoms[atom].locants
    (one_h,) = _under(nodes, purine, "indicated_h")
    assert _text(t, one_h) == "1H" and t.atoms[one_h["lights"][0]].element == "N"


def test_suffix_locants_light_their_carbonyls():
    t, nodes = _nodes(CAFFEINE)
    (dione,) = [n for n in nodes if n["label"] == "dione"]
    kids = _under(nodes, dione, "locant")
    assert sorted(n["label"] for n in kids) == ["2", "6"]
    for n in kids:
        assert "O" in {t.atoms[i].element for i in n["lights"]}


def test_bracket_locants_light_their_bracket():
    t, nodes = _nodes(IBUPROFEN)
    top = {n["label"]: n for n in nodes if n["parent"] is None and n["kind"] == "locant"}
    (methyl,) = [n for n in nodes if n["label"] == "methyl"]
    (propyl,) = [n for n in nodes if n["label"] == "propyl"]
    (phenyl,) = [n for n in nodes if n["label"] == "phenyl"]
    assert set(top["4"]["lights"]) == set(methyl["owns"]) | set(propyl["owns"])
    assert set(top["2"]["lights"]) == set(methyl["owns"]) | set(propyl["owns"]) | set(phenyl["owns"])
    assert [n["label"] for n in _under(nodes, methyl, "locant")] == ["2"]


def test_a_locant_written_once_for_several_copies_lights_them_all():
    t, nodes = _nodes("1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane")
    ring_chloro = next(n for n in nodes if n["label"] == "chloro" and n["copies"] == 2)
    (four,) = _under(nodes, ring_chloro, "locant")
    assert four["label"] == "4" and set(four["lights"]) == set(ring_chloro["owns"])


def test_stereo_marks_belong_to_the_word_root():
    for name, marks in [("(1R,2S)-2-(methylamino)-1-phenylpropan-1-ol", {"1R": "1", "2S": "2"}),
                        ("(2S)-2-aminopropanoic acid", {"2S": "2"})]:
        t, nodes = _nodes(name)
        (parent,) = [n for n in nodes if n["kind"] == "parent"]
        stereo = {n["label"]: n for n in nodes if n["kind"] == "stereo"}
        assert set(stereo) == set(marks), name
        for label, locant in marks.items():
            n = stereo[label]
            assert n["parent"] == parent["id"] and _text(t, n) == label
            (atom,) = n["lights"]
            assert locant in t.atoms[atom].locants


def test_a_bracket_stereo_set_belongs_to_the_brackets_main_part():
    name = ("(2S,3S,4S,5R,6S)-6-[(2S,3R,4S,5S,6R)-3,4,5-trihydroxy-6-(hydroxymethyl)"
            "oxan-2-yl]oxy-3,4,5-trihydroxyoxane-2-carboxylic acid")
    t, nodes = _nodes(name)
    by_id = {n["id"]: n for n in nodes}
    inner = [n for n in nodes if n["kind"] == "stereo" and n["span"][0] > name.index("[")]
    outer = [n for n in nodes if n["kind"] == "stereo" and n["span"][0] < name.index("[")]
    assert len(inner) == 5 and len(outer) == 5
    assert {by_id[n["parent"]]["label"] for n in inner} == {"oxan-2-yl"}
    assert {by_id[n["parent"]]["kind"] for n in outer} == {"parent"}


def test_marks_without_a_locant_light_nothing():
    t, nodes = _nodes("(+-)-trans-4-methylcyclohexan-1-ol")
    stereo = [n for n in nodes if n["kind"] == "stereo"]
    assert {n["label"] for n in stereo} == {"+-", "trans"}
    assert all(n["lights"] == [] and n["parent"] for n in stereo)


def test_a_part_without_a_key_is_listed_not_raised():
    t = Trace(text="x", smiles="C", atoms=(TraceAtom(0, 1, "C", ("1",)),), tokens=(),
              parts=(TracePart(0, "substituent", None, None, (0,)),))
    (node,) = build_nodes(t)
    assert node["span"] is None and node["owns"] == [0]


@pytest.mark.parametrize("name", sorted(TRACES))
def test_corpus_invariants(name):
    t, nodes = _nodes(name)
    ids = {n["id"]: n for n in nodes}
    assert all(n["parent"] is None or n["parent"] in ids for n in nodes), name
    parts = [n for n in nodes if n["kind"] in PART_NODE_KINDS]
    assert sorted(a for n in parts for a in n["owns"]) == list(range(len(t.atoms))), name
    assert all(not n["owns"] for n in nodes if n["kind"] not in PART_NODE_KINDS), name
    for n in parts:
        assert n["span"] is not None and n["label"], (name, n)
        label = n["label"]
        assert label[0] not in "-,')]}" and label[-1] not in "-,([{", (name, label)
        assert all(label.count(o) == label.count(c) for o, c in ("()", "[]", "{}")), (name, label)
    spans = [tuple(n["span"]) for n in nodes if n["span"]]
    assert all(0 <= a < b <= len(t.text) for a, b in spans), name
    for a in spans:
        for b in spans:
            assert not (a[0] < b[0] < a[1] < b[1]), (name, a, b)
    for n in nodes:
        if n["kind"] == "indicated_h" or (n["kind"] == "locant" and "hydrogen" in n["line"]):
            loc = n["label"][:-1] if n["kind"] == "indicated_h" else n["label"]
            assert n["lights"] and all(loc in t.atoms[a].locants for a in n["lights"]), (name, n)
        if n["kind"] == "stereo":
            assert n["span"] and n["parent"], (name, n)
            m = STEREO_LOCANT.match(n["label"])
            if m:
                assert n["lights"] and all(m.group(1) in t.atoms[a].locants for a in n["lights"]), (name, n)
