"""explain_name / explain_molecule: the v2 response (JVM + engine)."""

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


def test_symmetric_parts_keep_their_text():
    body = explain_molecule("CC(C)Cc1ccc(cc1)C(C)C(=O)O", namer=get_primary_namer())
    assert body["error"] is None
    unmapped = [n for n in body["nodes"] if n["atoms_unmapped"]]
    assert {n["label"] for n in unmapped} >= {"methyl", "propyl"}
    for n in unmapped:
        assert n["owns"] == [] and n["lights"] == [] and n["label"] and n["line"] and n["span"]
    assert any(not n["atoms_unmapped"] and n["owns"] for n in _parts(body))


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
