from app.schemas import ExplainNode, ExplainResponse


def test_a_part_node_owns_its_atoms():
    node = ExplainNode(id="n0", kind="substituent", label="methyl", span=[9, 15], copies=3,
                       owns=[0, 11, 12], lights=[0, 11, 12], line="three CH3 groups")
    assert node.owns == [0, 11, 12] and node.copies == 3 and node.parent is None


def test_a_token_node_owns_nothing_and_lights_its_atoms():
    node = ExplainNode(id="n1", parent="n0", kind="locant", label="7", span=[4, 5],
                       lights=[11], line="Position 7")
    assert node.owns == [] and node.lights == [11] and node.parent == "n0"


def test_an_unplaced_node_has_no_span():
    node = ExplainNode(id="n2", kind="stereo", label="2S", line="x")
    assert node.span is None and node.atoms_unmapped is False


def test_the_response_carries_nodes():
    body = ExplainResponse(smiles="CCO", name="ethanol", nodes=[
        ExplainNode(id="n0", kind="parent", label="ethan", span=[0, 5], owns=[0, 1], line="x")])
    assert body.model_dump()["nodes"][0]["label"] == "ethan"
