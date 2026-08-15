from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import CAFFEINE

client = TestClient(app)


def test_explain_name_endpoint_decomposes_caffeine():
    response = client.get("/api/explain-name", params={"name": CAFFEINE})
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert {s["kind"] for s in body["segments"]} >= {"substituent", "parent"}


def test_explain_name_endpoint_reports_parse_failure():
    response = client.get("/api/explain-name", params={"name": "zzz not a name"})
    assert response.status_code == 200
    assert response.json()["error"]


def test_existing_smiles_endpoint_still_works():
    response = client.get("/api/explain", params={"smiles": "CCO"})
    assert response.status_code == 200
    body = response.json()
    # A 200 alone proves little: the old code returned 200 with a single
    # undecomposed blob. Assert it actually decomposes and that the response
    # survives the new recursive schema.
    assert body["error"] is None, body["error"]
    assert body["segments"], "SMILES path returned no segments"
    assert all("owns_atoms" in s and "children" in s for s in body["segments"])
