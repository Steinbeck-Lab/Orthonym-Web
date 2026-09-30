"""GET /api/iupac-to-smiles returns the identifier set the EBI OPSIN page
offers, plus a molblock for the SDF download.

The endpoint's four new fields are OPTIONAL by design: RDKit's InChI writer
declines some inputs outright, and 2D coordinate generation can fail. A row
that loses one identifier must still deliver the others -- these tests are
what make that degradation real rather than aspirational.
"""

from fastapi.testclient import TestClient
from rdkit import Chem

from app.main import app

client = TestClient(app)

# Aspirin. Chosen because its OPSIN output is NOT RDKit-canonical, which is
# what makes `canonical_smiles` distinguishable from `smiles` below.
ASPIRIN = "2-acetyloxybenzoic acid"
ASPIRIN_INCHIKEY = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"


def _convert(name):
    response = client.get("/api/iupac-to-smiles", params={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_parsed_name_carries_every_identifier(redis_client):
    body = _convert(ASPIRIN)
    assert body["error"] is None
    assert body["smiles"]
    assert body["canonical_smiles"]
    assert body["molblock"]
    assert body["inchi"].startswith("InChI=1S/C9H8O4/")
    # A LITERAL key, not just "is a string": an InChI writer that silently
    # started emitting the wrong standard key would pass every shape check.
    assert body["inchikey"] == ASPIRIN_INCHIKEY


def test_canonical_smiles_is_not_just_a_copy_of_opsins_output(redis_client):
    """The two fields exist to be compared. OPSIN writes aspirin as
    C(C)(=O)OC1=C(C(=O)O)C=CC=C1 and RDKit canonicalises it to
    CC(=O)Oc1ccccc1C(=O)O -- if these ever match for this molecule, one of
    the two fields has stopped being computed and is echoing the other.
    """
    body = _convert(ASPIRIN)
    assert body["smiles"] != body["canonical_smiles"]
    assert Chem.MolToSmiles(Chem.MolFromSmiles(body["smiles"])) == body["canonical_smiles"]


def test_the_molblock_round_trips_to_the_same_molecule(redis_client):
    """The SDF download is only worth shipping if a viewer can read it back.
    Parsing the molblock and comparing InChIKeys is the strongest cheap
    check: it catches a molblock written without coordinates, with the wrong
    atom count, or from the wrong molecule.
    """
    body = _convert(ASPIRIN)
    parsed = Chem.MolFromMolBlock(body["molblock"])
    assert parsed is not None
    assert Chem.MolToInchiKey(parsed) == ASPIRIN_INCHIKEY
    # Same InChIKey says nothing about coordinates: a molblock written from a
    # molecule with no 2D layout has every atom at the origin and a viewer
    # draws one dot.
    positions = {
        (round(float(x), 3), round(float(y), 3))
        for x, y, _ in parsed.GetConformer().GetPositions()
    }
    assert len(positions) == parsed.GetNumAtoms()


def test_a_name_opsin_cannot_parse_returns_an_error_row(redis_client):
    body = _convert("not a chemical name at all zzzz")
    assert body["error"]
    assert body["smiles"] is None
    # Every new field is present and null -- absent keys would make the
    # frontend's optional chaining silently render an empty row instead.
    assert body["canonical_smiles"] is None
    assert body["inchi"] is None
    assert body["inchikey"] is None
    assert body["molblock"] is None


def test_an_inchi_failure_degrades_instead_of_failing_the_row(
    redis_client, monkeypatch
):
    """RDKit's InChI writer is not total: it declines several organometallics
    and unusual valences, logging rather than raising a typed error. Losing
    the InChI must cost only the InChI.

    This test is what earns the try/except in name_to_smiles. Without it the
    guard is untested and a later simplification removing it passes green.
    """

    def boom(*args, **kwargs):
        raise RuntimeError("InChI writer declined this molecule")

    monkeypatch.setattr("rdkit.Chem.MolToInchi", boom)
    monkeypatch.setattr("rdkit.Chem.MolToInchiKey", boom)

    body = _convert(ASPIRIN)
    assert body["error"] is None
    assert body["inchi"] is None
    assert body["inchikey"] is None
    # The identifiers that did not depend on InChI survive.
    assert body["smiles"]
    assert body["canonical_smiles"]
    assert body["molblock"]
    assert body["depiction_svg"]


def test_an_empty_inchi_is_reported_as_missing_not_as_an_empty_string(
    redis_client, monkeypatch
):
    """RDKit's InChI writer can also decline by returning "" and logging. An
    empty string is not an identifier; the row must carry null for it, like
    the raising case above, and must not derive a key from it.
    """
    monkeypatch.setattr("rdkit.Chem.MolToInchi", lambda *a, **k: "")

    body = _convert(ASPIRIN)
    assert body["error"] is None
    assert body["inchi"] is None
    assert body["inchikey"] is None
    assert body["molblock"]
