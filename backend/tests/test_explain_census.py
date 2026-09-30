"""The census classifier is the yardstick every coverage number is measured
with, so it gets its own tests (synthetic traces, no JVM)."""

from app.opsin_trace import Trace, TraceAtom, TracePart, WrittenToken
from app.token_owner import Owner
from scripts.explain_census import classify

T = Trace(text="ab-1H", smiles="CN", atoms=(TraceAtom(0, 1, "C", ("1",)), TraceAtom(1, 2, "N", ("2",))),
          tokens=(), parts=())


def _n(kind, span, owns=(), label="ab", parent=None, lights=(), line=""):
    return {"id": f"x{kind}{span}", "kind": kind, "span": span, "owns": list(owns), "label": label,
            "parent": parent, "lights": list(lights), "line": line}


def test_clean():
    assert classify(T, [_n("parent", [0, 2], [0, 1])], {}) == ["CLEAN"]


def test_part_unplaced_and_gap():
    out = classify(T, [_n("parent", None, [0])], {})
    assert "PART_UNPLACED" in out and "ATOM_GAP" in out


def test_overlap_crossing_and_bad_span():
    out = classify(T, [_n("parent", [0, 3], [0, 1]), _n("suffix", [2, 5], [1]), _n("token", [4, 9])], {})
    assert {"ATOM_OVERLAP", "CROSSING", "BAD_SPAN"} <= set(out)


def test_orphan_token():
    assert "ORPHAN_TOKEN" in classify(T, [_n("parent", [0, 2], [0, 1])], {0: None, 1: Owner("part", (0, 2))})


def test_hydro_locant_on_the_wrong_atom():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("indicated_h", [3, 5], label="1H", lights=[1])]
    assert "HYDRO_WRONG" in classify(T, nodes, {})


def test_stereo_without_a_parent_or_on_the_wrong_atom():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("stereo", [0, 1], label="2S", lights=[0])]
    out = classify(T, nodes, {})
    assert "STEREO_NO_PARENT" in out and "STEREO_WRONG_ATOM" in out


def test_a_mark_on_an_atom_that_is_not_a_stereocentre_is_wrong():
    t = Trace(text="(2S)-x", smiles="CO", atoms=(TraceAtom(0, 1, "C", ("2",)), TraceAtom(1, 2, "O", ("1",))),
              tokens=(), parts=())
    nodes = [_n("parent", [0, 2], [0, 1]), _n("stereo", [1, 3], label="2S", parent="p", lights=[0])]
    assert "STEREO_WRONG_ATOM" in classify(t, nodes, {})


def test_an_unlit_locant_is_reported():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("locant", [3, 4], label="1", lights=[])]
    assert "LOCANT_UNLIT" in classify(T, nodes, {})


def test_an_unlit_anomer_mark_is_by_design_not_reported():
    nodes = [_n("parent", [0, 2], [0, 1]), _n("locant", [3, 4], label="alpha", lights=[])]
    assert "LOCANT_UNLIT" not in classify(T, nodes, {})


def _lit_case(smiles):
    """atom 0 = root, atom 1 = substituent S (child locant "2" below), atom 2 =
    substituent U; every atom but S carries locant 2."""
    t = Trace(text="a-b-c", smiles=smiles,
              atoms=(TraceAtom(0, 1, "C", ("2",)), TraceAtom(1, 2, "C", ("1",)), TraceAtom(2, 3, "C", ("2",))),
              tokens=(), parts=(TracePart(0, "root", (0, 1), None, (0,)),
                                TracePart(1, "substituent", (2, 3), None, (1,)),
                                TracePart(2, "substituent", (4, 5), None, (2,))))
    parent = _n("substituent", [2, 3], [1], label="b")
    nodes = [_n("parent", [0, 1], [0], label="a"), parent, _n("substituent", [4, 5], [2], label="c")]
    return t, nodes, parent


def test_a_locant_lighting_an_atom_of_an_unrelated_part_is_reported():
    t, nodes, parent = _lit_case("C.C.C")        # S is bonded to nothing
    nodes.append(_n("locant", [2, 3], label="2", parent=parent["id"], lights=[2]))
    assert "LIT_ATOM_FOREIGN" in classify(t, nodes, {})


def test_a_locant_lighting_the_bonded_parent_position_is_clean():
    t, nodes, parent = _lit_case("CC.C")         # S is bonded to the root atom that carries 2
    nodes.append(_n("locant", [2, 3], label="2", parent=parent["id"], lights=[0]))
    assert "LIT_ATOM_FOREIGN" not in classify(t, nodes, {})


def test_a_locant_lighting_its_own_atom_is_clean():
    t, nodes, parent = _lit_case("C.C.C")
    nodes.append(_n("locant", [2, 3], label="1", parent=parent["id"], lights=[1]))
    assert "LIT_ATOM_FOREIGN" not in classify(t, nodes, {})


def _chain_case(lights):
    """"3-x-oxy-root": the leading locant sits in front of substituent P (atom 2,
    carrying the number 3 itself), which is joined to the following substituent
    Q (atom 1), which is bonded to the root atom 0 that carries 3."""
    t = Trace(text="3-x-o-r", smiles="COC",
              atoms=(TraceAtom(0, 1, "C", ("3",)), TraceAtom(1, 2, "O", ("O",)), TraceAtom(2, 3, "C", ("3",))),
              tokens=(WrittenToken(0, "group", "x", (2, 3), (2, 3)),
                      WrittenToken(1, "group", "oxy", (4, 5), (4, 5))),
              parts=(TracePart(0, "root", (6, 7), None, (0,)),
                     TracePart(1, "substituent", (4, 5), None, (1,)),
                     TracePart(2, "substituent", (2, 3), None, (2,))))
    p = _n("substituent", [2, 3], [2], label="x")
    nodes = [_n("parent", [6, 7], [0], label="r"), _n("substituent", [4, 5], [1], label="o"), p,
             _n("locant", [0, 1], label="3", parent=p["id"], lights=lights)]
    return t, nodes


def test_a_chained_substituent_lighting_its_own_attachment_atom_is_reported():
    """The round-1 oseltamivir behaviour: "3-pentan-3-yloxy" lit pentan's own C3."""
    t, nodes = _chain_case([2])
    assert "LIT_ATOM_FOREIGN" in classify(t, nodes, {})


def test_a_chained_substituent_lighting_the_parent_position_is_clean():
    t, nodes = _chain_case([0])
    assert "LIT_ATOM_FOREIGN" not in classify(t, nodes, {})
