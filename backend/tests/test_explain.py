"""explain_name / explain_molecule: the v2 response (JVM + engine)."""

import random

import pytest
from rdkit import Chem

from app import explain as explain_module
from app.explain import _align_spans, explain_molecule, explain_name
from app.explain_tree import PART_NODE_KINDS
from app.opsin_trace import TraceFailure
from app.orthonym_service import get_primary_namer
from tests.conftest import CAFFEINE, GOLDEN_NAMES


def _parts(body):
    return [n for n in body["nodes"] if n["kind"] in PART_NODE_KINDS]


def test_caffeine_by_name():
    body = explain_name(CAFFEINE)
    assert body["error"] is None and body["svg"]
    assert [(n["kind"], n["label"]) for n in _parts(body)] == [
        ("substituent", "methyl"), ("parent", "purine"), ("suffix", "dione")]
    assert sorted(a for n in _parts(body) for a in n["owns"]) == list(range(body["total_atoms"]))


def test_every_golden_name_explains_with_every_part_placed():
    for name in GOLDEN_NAMES:
        body = explain_name(name)
        assert body["error"] is None, name
        assert all(n["span"] for n in _parts(body)), name


def test_unreadable_name_message():
    body = explain_name("zzz not a name")
    assert body["error"] == "OPSIN cannot read this name, so it cannot be explained."
    assert body["nodes"] == []


def test_unavailable_message(monkeypatch):
    monkeypatch.setattr(explain_module, "trace", lambda name: TraceFailure("unavailable"))
    assert explain_name("ethanol")["error"] == \
        "Explain is not available on this server right now. Naming still works."


def test_mismatch_message(monkeypatch):
    monkeypatch.setattr(explain_module, "trace", lambda name: TraceFailure("mismatch"))
    assert explain_name("ethanol")["error"] == "Could not explain this name."


def test_unplaced_message(monkeypatch):
    monkeypatch.setattr(explain_module, "trace", lambda name: TraceFailure("unplaced"))
    assert explain_name("ethanol")["error"] == (
        "OPSIN reads this name in a reordered form (for example a CAS index name), "
        "so its parts cannot be matched to the text. Try the IUPAC form.")


def test_a_cas_index_name_gets_the_reordered_message():
    body = explain_name("acetic acid, ethyl ester")
    assert body["error"] == (
        "OPSIN reads this name in a reordered form (for example a CAS index name), "
        "so its parts cannot be matched to the text. Try the IUPAC form.")
    assert body["nodes"] == []


def test_a_node_building_defect_is_one_message_not_a_crash(monkeypatch):
    def boom(trace):
        raise RuntimeError("defect")
    monkeypatch.setattr(explain_module, "build_nodes", boom)
    body = explain_name("ethanol")
    assert body["error"] == "Could not explain this name." and body["nodes"] == []


def test_smiles_in_maps_atoms_onto_the_users_molecule():
    body = explain_molecule("CCO", namer=get_primary_namer())
    assert body["error"] is None and body["name"] == "ethanol"
    assert sorted(a for n in _parts(body) for a in n["owns"]) == [0, 1, 2]
    assert not any(n["atoms_unmapped"] for n in body["nodes"])


IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"


def _lit(body, label):
    return [n for n in body["nodes"] if n["label"] == label]


def test_symmetric_parts_are_mapped_through_one_match():
    body = explain_molecule(IBUPROFEN, namer=get_primary_namer())
    assert body["error"] is None
    assert body["name"] == "2-[4-(2-methylpropyl)phenyl]propanoic acid"
    assert not [n for n in body["nodes"] if n["atoms_unmapped"]]
    (methyl,), (propyl,) = _lit(body, "methyl"), _lit(body, "propyl")
    assert methyl["owns"] and propyl["owns"]
    assert not set(methyl["owns"]) & set(propyl["owns"])
    assert not set(methyl["lights"]) & set(propyl["lights"])
    user = Chem.MolFromSmiles(IBUPROFEN)
    isobutyl = {0, 1, 2, 3}
    assert set(methyl["owns"]) | set(propyl["owns"]) == isobutyl
    assert all(user.GetAtomWithIdx(a).GetSymbol() == "C" for a in methyl["owns"] + propyl["owns"])


def _node(label, owns, lights=()):
    return {"id": label, "kind": "substituent", "label": label, "span": [0, 1], "owns": list(owns),
            "lights": list(lights), "line": "x", "parent": None, "atoms_unmapped": False}


def _shuffled(smiles, seed):
    """(the name path's molecule, the user's molecule = the same structure typed in
    another atom order, where) where name-path atom i is user atom where[i]."""
    mol = Chem.MolFromSmiles(smiles)
    order = list(range(mol.GetNumAtoms()))
    random.Random(seed).shuffle(order)
    renumbered = Chem.RenumberAtoms(mol, order)
    typed = Chem.MolToSmiles(renumbered, canonical=False)
    written = [int(i) for i in renumbered.GetProp("_smilesAtomOutputOrder").strip("[],").split(",") if i]
    user = Chem.MolFromSmiles(typed)
    where = {order[old]: new for new, old in enumerate(written)}
    return mol, user, where


# atom indices are the name path's: isobutyl C0 C1 C2 C3; tert-butyl C0..C3 on ring C4;
# the para-substituted ring c4..c10 with O8
@pytest.mark.parametrize("smiles, parts", [
    (IBUPROFEN, {"methyl": [0], "propyl": [1, 2, 3]}),
    ("CC(C)(C)c1ccc(O)cc1", {"methyl": [0], "propan-2-yl": [1, 2, 3]}),
    ("CC(C)Oc1ccccc1", {"methyl": [0], "propan-2-yl": [1, 2, 3]}),
    ("CC(C)(C)c1ccc(O)cc1", {"ortho": [5], "rest": [4, 6, 7, 8, 9, 10]}),
])
@pytest.mark.parametrize("seed", range(6))
def test_remap_gives_every_part_one_symmetry_choice(smiles, parts, seed):
    opsin, user, where = _shuffled(smiles, seed)
    out = explain_module._remap_nodes(user, opsin, [_node(k, v, v) for k, v in parts.items()])
    assert not [n for n in out if n["atoms_unmapped"]]
    owns = [n["owns"] for n in out]
    assert sum(map(len, owns)) == len({a for o in owns for a in o}), "parts stay disjoint"
    assert {a for o in owns for a in o} == {where[i] for v in parts.values() for i in v}
    for n in out:
        assert n["lights"] == n["owns"]
        assert sorted(user.GetAtomWithIdx(a).GetSymbol() for a in n["owns"]) == \
            sorted(opsin.GetAtomWithIdx(i).GetSymbol() for i in parts[n["label"]])


@pytest.mark.parametrize("seed", range(6))
def test_remap_keeps_bonded_parts_bonded(seed):
    # ring atoms c5 (ortho) and c6 (meta) are bonded: whichever side of the ring the
    # two parts land on, they must land on the same side
    opsin, user, _ = _shuffled("CC(C)(C)c1ccc(O)cc1", seed)
    out = explain_module._remap_nodes(user, opsin, [_node("ortho", [5]), _node("meta", [6])])
    assert not [n for n in out if n["atoms_unmapped"]]
    a, b = (n["owns"][0] for n in out)
    assert user.GetBondBetweenAtoms(a, b) is not None


def test_remap_keeps_the_agreement_rule_when_no_match_is_faithful():
    # 4-isopropylimidazole, drawn as the other tautomer: the isopropyl methyls swap
    # between the two matches, and neither match keeps the ring N-H where it was
    opsin, user = Chem.MolFromSmiles("CC(C)c1c[nH]cn1"), Chem.MolFromSmiles("CC(C)c1cnc[nH]1")
    assert len(user.GetSubstructMatches(opsin, uniquify=False)) == 2
    out = {n["label"]: n for n in explain_module._remap_nodes(
        user, opsin, [_node("methyl", [0]), _node("propyl", [1, 2]), _node("ring", [3, 4, 5, 6, 7])])}
    for label in ("methyl", "propyl"):
        assert out[label]["atoms_unmapped"] and out[label]["owns"] == [] == out[label]["lights"]
    assert not out["ring"]["atoms_unmapped"] and out["ring"]["owns"] == [3, 4, 5, 6, 7]


def test_remap_maps_nothing_when_the_atom_counts_differ():
    out = explain_module._remap_nodes(Chem.MolFromSmiles("CCCO"), Chem.MolFromSmiles("CCO"),
                                      [_node("ethanol", [0, 1, 2])])
    assert out[0]["atoms_unmapped"] and out[0]["owns"] == []


def test_remap_uses_a_faithful_match_even_when_the_match_cap_is_hit(monkeypatch):
    monkeypatch.setattr(explain_module, "_MAX_SUBSTRUCT_MATCHES", 2)
    mol = Chem.MolFromSmiles("CC(C)(C)C")        # 24 matches, all faithful
    out = explain_module._remap_nodes(mol, mol, [_node("methyl", [0]), _node("rest", [1, 2, 3, 4])])
    assert not [n for n in out if n["atoms_unmapped"]]
    assert sorted(a for n in out for a in n["owns"]) == [0, 1, 2, 3, 4]


def test_remap_maps_nothing_when_the_cap_is_hit_and_no_match_is_faithful(monkeypatch):
    monkeypatch.setattr(explain_module, "_MAX_SUBSTRUCT_MATCHES", 2)
    opsin, user = Chem.MolFromSmiles("CC(C)c1c[nH]cn1"), Chem.MolFromSmiles("CC(C)c1cnc[nH]1")
    out = explain_module._remap_nodes(user, opsin, [_node("ring", [3, 4, 5, 6, 7])])
    assert out[0]["atoms_unmapped"] and out[0]["owns"] == []


@pytest.mark.parametrize("smiles", ["CC(C)(C)c1ccc(O)cc1", "CC(C)Oc1ccccc1"])
def test_symmetric_molecules_map_every_part(smiles):
    body = explain_molecule(smiles, namer=get_primary_namer())
    assert body["error"] is None
    assert not [n for n in body["nodes"] if n["atoms_unmapped"]]
    owned = sorted(a for n in _parts(body) for a in n["owns"])
    assert owned == list(range(body["total_atoms"]))


def test_bad_smiles():
    body = explain_molecule("not smiles((", namer=get_primary_namer())
    assert body["error"] == "Could not parse this SMILES string"


def test_align_spans_identity_is_a_no_op():
    nodes = [{"span": [0, 3]}]
    assert _align_spans(nodes, "eth", "eth") is nodes


def test_align_spans_maps_a_replaced_block_to_the_whole_original():
    read, shown = "alpha-D-glucose", "α-D-glucose"
    out = _align_spans([{"span": [0, 5]}, {"span": [8, 15]}, {"span": [2, 4]}], read, shown)
    assert out[0]["span"] == [0, 1]
    assert shown[out[1]["span"][0]:out[1]["span"][1]] == "glucose"
    assert out[2]["span"] == [0, 1]


def test_align_spans_drops_a_span_that_maps_to_nothing():
    assert _align_spans([{"span": [0, 3]}], "xyzabc", "abc")[0]["span"] is None


# -- Phase C fix round 1 (M6): no exception becomes a 500 ----------------------------------
import pytest
from celery.exceptions import SoftTimeLimitExceeded

NOT_NAMED = "Orthonym could not confidently name this molecule, so there is nothing to explain."


class _Namer:
    """A namer whose name_with_tree misbehaves."""
    def __init__(self, exc):
        self.exc = exc

    def name_with_tree(self, smiles):
        raise self.exc


def test_an_engine_that_raises_gets_the_engine_failure_message_not_a_500():
    body = explain_molecule("CCO", namer=_Namer(RuntimeError("engine defect")))
    assert body["error"] == NOT_NAMED                      # section 7: no name from the engine
    assert body["name"] is None and body["nodes"] == [] and body["svg"] is None and body["total_atoms"] == 3


def test_a_drawing_defect_is_one_message_not_a_crash(monkeypatch):
    def boom(mol):
        raise RuntimeError("drawer defect")
    monkeypatch.setattr(explain_module, "_inline_svg", boom)
    body = explain_molecule("CCO", namer=get_primary_namer())
    assert body["error"] == "Could not explain this name." and body["name"] == "ethanol" and body["nodes"] == []
    body = explain_name("ethanol")
    assert body["error"] == "Could not explain this name." and body["nodes"] == [] and body["svg"] is None


def test_a_soft_time_limit_is_never_swallowed_by_the_new_guards(monkeypatch):
    with pytest.raises(SoftTimeLimitExceeded):
        explain_molecule("CCO", namer=_Namer(SoftTimeLimitExceeded()))

    def slow(mol):
        raise SoftTimeLimitExceeded()
    monkeypatch.setattr(explain_module, "_inline_svg", slow)
    with pytest.raises(SoftTimeLimitExceeded):
        explain_molecule("CCO", namer=get_primary_namer())
    with pytest.raises(SoftTimeLimitExceeded):
        explain_name("ethanol")


def test_a_soft_time_limit_inside_build_nodes_is_never_swallowed(monkeypatch):
    # The node-building guard is `except Exception`, and SoftTimeLimitExceeded is an
    # Exception: without its own re-raise a soft limit that fires here became "Could
    # not explain this name." and the task ran on into the hard limit (final review I4).
    def boom(trace):
        raise SoftTimeLimitExceeded()
    monkeypatch.setattr(explain_module, "build_nodes", boom)
    with pytest.raises(SoftTimeLimitExceeded):
        explain_name("ethanol")
    with pytest.raises(SoftTimeLimitExceeded):
        explain_molecule("CCO", namer=get_primary_namer())
