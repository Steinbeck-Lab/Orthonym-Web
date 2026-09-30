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
    # Caffeine's name carries a referential "3,7-dihydro-1H-" part: it must
    # keep owns_atoms false and own no atoms, and the structure must render.
    referential = [s for s in body["segments"] if not s["owns_atoms"]]
    assert referential and all(s["atom_indices"] == [] for s in referential)
    assert body["total_atoms"] == 14 and body["svg"]


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
    # The key check above is satisfied by the response model's defaults, so
    # assert values: owning segments hold atoms, referential ones hold none.
    for s in body["segments"]:
        if s["owns_atoms"]:
            assert s["atom_indices"], s["label"]
        else:
            assert s["atom_indices"] == [], s["label"]
    assert any(s["owns_atoms"] for s in body["segments"])
    assert body["total_atoms"] == 3 and body["svg"]
