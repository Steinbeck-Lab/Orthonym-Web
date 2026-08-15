from app.schemas import ExplainSegment


def test_segment_nests_children():
    child = ExplainSegment(
        label="7", kind="substituent", owns_atoms=True, locant="7",
        explanation="Position 7", atom_indices=[11], highlight_atoms=[11],
    )
    parent = ExplainSegment(
        label="1,3,7-trimethyl", kind="substituent", owns_atoms=True,
        explanation="three CH3 groups", atom_indices=[0, 11, 12],
        highlight_atoms=[0, 11, 12], children=[child],
    )
    assert parent.children[0].locant == "7"


def test_referential_segment_owns_nothing():
    segment = ExplainSegment(
        label="3,7-dihydro-1H-", kind="modifier", owns_atoms=False,
        explanation="records where hydrogens sit",
        atom_indices=[], highlight_atoms=[1, 3, 7],
    )
    assert segment.atom_indices == []
    assert segment.highlight_atoms == [1, 3, 7]
