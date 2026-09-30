from app.explain import explain_molecule, explain_name
from app.orthonym_service import get_primary_namer
from tests.conftest import CAFFEINE

# Must match _EXPLAIN_WIDTH / _EXPLAIN_HEIGHT in explain.py.
WIDTH, HEIGHT = 340, 260


def test_caffeine_has_one_point_per_heavy_atom():
    result = explain_name(CAFFEINE)
    assert result["total_atoms"] == 14
    assert len(result["atom_points"]) == 14


def test_every_point_is_inside_the_drawing():
    result = explain_name(CAFFEINE)
    for index, (x, y) in enumerate(result["atom_points"]):
        assert 0 <= x <= WIDTH, f"atom {index} x={x} outside 0..{WIDTH}"
        assert 0 <= y <= HEIGHT, f"atom {index} y={y} outside 0..{HEIGHT}"


def test_methyl_carbons_get_points_even_though_rdkit_draws_no_symbol():
    # This is the whole point of the task. RDKit emits a standalone atom-N
    # element only for atoms it draws a symbol for, so caffeine's methyl
    # carbons have none and cannot be highlighted today.
    result = explain_name(CAFFEINE)
    methyl = next(s for s in result["segments"] if s["kind"] == "substituent")
    # kind == "substituent" only: the methyl segment's children now also
    # include TOKEN siblings ("tri", the "1,3,7-" locant token), which own no
    # atoms at all (atom_indices == []) by design.
    for child in methyl["children"]:
        if child["kind"] != "substituent":
            continue
        index = child["atom_indices"][0]
        x, y = result["atom_points"][index]
        assert (x, y) != (0.0, 0.0), f"atom {index} has no real coordinate"


def test_structure_in_path_also_carries_points():
    result = explain_molecule("CCO", namer=get_primary_namer())
    assert len(result["atom_points"]) == result["total_atoms"]


def test_error_responses_carry_an_empty_list_not_a_missing_key():
    result = explain_name("definitely not a chemical name")
    assert result["error"]
    assert result["atom_points"] == []


def test_every_atom_gets_its_own_distinct_point():
    # The existing tests only prove no point is (0,0). A stub returning ONE
    # constant for every atom would pass all of them, and the glow would
    # then draw every circle on top of the same spot.
    result = explain_name(CAFFEINE)
    points = [tuple(p) for p in result["atom_points"]]
    assert len(set(points)) == len(points), (
        f"{len(points) - len(set(points))} atoms share a coordinate"
    )


def test_each_point_belongs_to_its_own_atom():
    # Distinct and in-bounds still pass for points shuffled between atoms,
    # which would light the wrong atom. RDKit draws every bond at one length,
    # so a point list in the wrong order or invented rather than read from
    # the drawer makes bonded atoms land far apart or at uneven distances.
    import math

    from rdkit import Chem

    result = explain_name(CAFFEINE)
    mol = Chem.MolFromSmiles(result["smiles"])
    points = result["atom_points"]
    lengths = [
        math.dist(points[b.GetBeginAtomIdx()], points[b.GetEndAtomIdx()])
        for b in mol.GetBonds()
    ]
    assert len(lengths) == 15
    assert max(lengths) - min(lengths) < 0.1 * max(lengths), lengths
