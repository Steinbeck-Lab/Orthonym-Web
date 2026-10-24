"""Name check: does a claimed name describe a structure?"""

from rdkit import Chem

from app.name_check import VERDICT_TEXT, compare_keys


def _key(smiles):
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))


def test_the_same_molecule_is_the_same_structure():
    assert compare_keys(_key("CCO"), _key("OCC")) == "same"


def test_mirror_images_share_a_skeleton_only():
    assert compare_keys(_key("C[C@@H](C(=O)O)N"), _key("C[C@H](C(=O)O)N")) == "stereo"


def test_a_zwitterion_is_the_same_structure_to_inchi():
    # Measured: standard InChI moves the zwitterion's protons back, so
    # L-alanine and its zwitterion share all three key blocks.
    assert compare_keys(_key("C[C@@H](C(=O)O)N"), _key("C[C@@H](C(=O)[O-])[NH3+]")) == "same"


def test_a_charged_form_differs_only_in_protonation():
    # Acetate vs acetic acid: the last block (protonation) differs.
    assert compare_keys(_key("CC(=O)O"), _key("CC(=O)[O-]")) == "protonation"


def test_different_molecules_are_different():
    assert compare_keys(_key("CCO"), _key("CO")) == "different"


def test_a_missing_key_cannot_be_compared():
    assert compare_keys(_key("CCO"), None) == "uncomparable"
    assert compare_keys(None, _key("CCO")) == "uncomparable"


def test_every_verdict_has_its_words():
    assert VERDICT_TEXT == {
        "same": "Same structure",
        "protonation": "Same skeleton; protonation differs",
        "stereo": "Same skeleton; stereo or isotopes differ",
        "different": "Different structure",
        "unreadable": "OPSIN cannot read this name",
        "uncomparable": "Could not compare",
    }


# --- check_pair and the endpoint: OPSIN in-process, Celery eager ---------

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.name_check import check_pair  # noqa: E402

client = TestClient(app)


def test_a_name_for_the_structure_is_the_same_structure():
    result = check_pair("CCO", "ethanol")
    assert result["verdict"] == "same"
    assert result["input_inchikey"] == result["claimed_inchikey"]


def test_a_name_for_another_molecule_is_different():
    result = check_pair("CCO", "methanol")
    assert result["verdict"] == "different"
    assert Chem.MolToSmiles(Chem.MolFromSmiles(result["claimed_smiles"])) == "CO"


def test_a_name_opsin_cannot_read_is_unreadable():
    result = check_pair("CCO", "not a name at all")
    assert result["verdict"] == "unreadable"
    assert result["claimed_smiles"] is None
    assert result["claimed_inchikey"] is None


def test_the_wrong_enantiomer_differs_in_stereo():
    assert check_pair("C[C@@H](C(=O)O)N", "(2R)-2-aminopropanoic acid")["verdict"] == "stereo"


def test_the_endpoint_answers_with_the_verdict_and_the_engines_name(redis_client):
    response = client.post("/api/name-check", json={"smiles": "CCO", "name": "ethanol"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "same"
    assert body["verdict_text"] == "Same structure"
    assert body["engine"]["name"] == "ethanol"
    assert body["engine"]["status"] == "pin"
    assert body["claimed_svg"].startswith("data:image/svg+xml")


def test_a_smiles_rdkit_cannot_read_is_a_400(redis_client):
    response = client.post("/api/name-check", json={"smiles": "C1CC", "name": "ethanol"})
    assert response.status_code == 400
    assert response.json()["detail"]


def test_name_check_spends_the_fast_bucket(redis_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1)
    body = {"smiles": "CCO", "name": "ethanol"}
    assert client.post("/api/name-check", json=body).status_code == 200
    assert client.post("/api/name-check", json=body).status_code == 429


def test_an_empty_field_is_a_422(redis_client):
    assert client.post("/api/name-check", json={"smiles": "CCO", "name": ""}).status_code == 422


def test_a_warning_from_opsin_travels_with_the_verdict(redis_client):
    # OPSIN reads "ethylpyridine" but warns it is ambiguous; the verdict uses
    # what OPSIN returned, and the warning must not be dropped.
    body = client.post(
        "/api/name-check", json={"smiles": "CCc1ccccn1", "name": "ethylpyridine"}
    ).json()
    assert [w["type"] for w in body["warnings"]] == ["APPEARS_AMBIGUOUS"]
    assert body["verdict"] in ("same", "different")


def test_the_answer_is_not_left_in_the_result_backend(redis_client, monkeypatch):
    # Celery's backend keeps every result for 24 h; this one carries the
    # visitor's SMILES and name. /api/translate forgets its result; so must this.
    from app import main

    forgotten = []

    class _Result:
        def get(self, timeout):
            return {
                "verdict": "same", "verdict_text": "Same structure",
                "engine": {"smiles": "CCO", "status": "pin"},
            }

        def forget(self):
            forgotten.append(True)

    monkeypatch.setattr(main.check_name, "apply_async", lambda *a, **k: _Result())
    assert client.post("/api/name-check", json={"smiles": "CCO", "name": "ethanol"}).status_code == 200
    assert forgotten == [True]


def test_both_pictures_come_with_the_answer(redis_client):
    # The page must not fetch "Your structure" with a GET /api/depict?smiles=,
    # which nginx would log; the answer carries it, cached engine row or not.
    from app import name_cache

    first = client.post("/api/name-check", json={"smiles": "CCO", "name": "ethanol"}).json()
    assert first["input_svg"].startswith("data:image/svg+xml")
    assert name_cache.get_cached("CCO", True, True) is not None
    again = client.post("/api/name-check", json={"smiles": "CCO", "name": "ethanol"}).json()
    assert again["input_svg"].startswith("data:image/svg+xml")
    assert again["engine"]["depiction_svg"].startswith("data:image/svg+xml")
