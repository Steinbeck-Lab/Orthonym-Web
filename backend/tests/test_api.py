from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import CAFFEINE

client = TestClient(app)


def test_explain_name_endpoint_decomposes_caffeine():
    response = client.get("/api/explain-name", params={"name": CAFFEINE})
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert {n["kind"] for n in body["nodes"]} >= {"substituent", "parent", "suffix", "hydro", "locant"}
    # Token nodes (the "3,7-dihydro" hydro word, locants) own no atoms; the
    # part nodes own all 14, once each.
    parts = [n for n in body["nodes"] if n["kind"] in ("substituent", "parent", "suffix")]
    assert all(n["owns"] == [] for n in body["nodes"] if n not in parts)
    assert sorted(a for n in parts for a in n["owns"]) == list(range(14))
    assert body["total_atoms"] == 14 and body["svg"]


def test_explain_name_endpoint_reports_parse_failure():
    response = client.get("/api/explain-name", params={"name": "zzz not a name"})
    assert response.status_code == 200
    assert response.json()["error"]


def test_existing_smiles_endpoint_still_works():
    response = client.get("/api/explain", params={"smiles": "CCO"})
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None, body["error"]
    parts = [n for n in body["nodes"] if n["kind"] in ("substituent", "parent", "suffix")]
    assert [n["label"] for n in parts] == ["ethan", "ol"]
    assert sorted(a for n in parts for a in n["owns"]) == [0, 1, 2]
    assert all(set(n) >= {"id", "parent", "span", "owns", "lights", "line"} for n in body["nodes"])
    assert body["total_atoms"] == 3 and body["svg"]
