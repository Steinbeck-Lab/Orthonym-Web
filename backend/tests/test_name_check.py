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
        "stereo_protonation": "Same skeleton; stereo or isotopes and protonation differ",
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


# --- review fixes -----------------------------------------------------------

import pytest  # noqa: E402
from celery.exceptions import SoftTimeLimitExceeded  # noqa: E402

from app import name_check, tasks  # noqa: E402


def _pair(i, smiles, name):
    return {"index": i, "raw_input": smiles, "input_id": None, "smiles": smiles,
            "error": None, "claimed_name": name}


def test_a_time_limit_in_the_check_keeps_the_rows_already_checked(monkeypatch):
    real = name_check.check_pair
    calls = []

    def slow(smiles, name):
        calls.append(name)
        if len(calls) == 2:
            raise SoftTimeLimitExceeded()
        return real(smiles, name)

    monkeypatch.setattr(name_check, "check_pair", slow)
    with pytest.raises(tasks._ChunkTimedOut) as caught:
        tasks._name_prepared([_pair(0, "CCO", "ethanol"), _pair(1, "CO", "methanol")], True, True)
    timeout = caught.value
    # The row whose check ran out of time is still named and kept, without a
    # verdict; nothing after it was touched.
    assert [r["verdict"] for r in timeout.rows] == ["same", None]
    assert [r["name"] for r in timeout.rows] == ["ethanol", "methanol"]
    assert timeout.remaining == []
    rows, _ = tasks._timed_out_rows(timeout)
    assert [r["claimed_name"] for r in rows] == ["ethanol", "methanol"]


def test_a_timed_out_row_keeps_its_claimed_name():
    timeout = tasks._ChunkTimedOut([], 0, [_pair(0, "CCO", "ethanol"), _pair(1, None, "x") | {"raw_input": "C1CC", "error": "bad"}])
    rows, _ = tasks._timed_out_rows(timeout)
    assert [r["claimed_name"] for r in rows] == ["ethanol", "x"]


def test_the_single_check_survives_an_engine_crash(redis_client, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("namer exploded")

    monkeypatch.setattr(tasks, "translate_one", boom)
    response = client.post("/api/name-check", json={"smiles": "CCCCO", "name": "butan-1-ol"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "same"
    assert body["engine"]["status"] == "error"
    assert body["input_svg"]


@pytest.mark.parametrize("smiles", ["CCO\nCO", "   ", "CCO CO"])
def test_more_or_less_than_one_smiles_is_a_400(redis_client, smiles):
    response = client.post("/api/name-check", json={"smiles": smiles, "name": "ethanol"})
    assert response.status_code == 400, response.text


def test_a_name_on_two_lines_is_refused(redis_client):
    response = client.post("/api/name-check", json={"smiles": "CCO", "name": "ethanol\nmethanol"})
    assert response.status_code == 400
    assert "one line" in response.json()["detail"]


def test_a_batch_row_keeps_opsins_warning(redis_client):
    (row,), _ = tasks._name_prepared([_pair(0, "CCc1cccnc1", "ethylpyridine")], True, True)
    assert "APPEARS_AMBIGUOUS" in row["opsin_warnings"]


# --- small things -------------------------------------------------------------


def test_stereo_and_protonation_both_differing_say_both():
    # D-alanine against L-alaninium: block 2 and block 3 both differ.
    assert compare_keys(_key("C[C@@H](C(=O)O)N"), _key("C[C@H](C(=O)O)[NH3+]")) == "stereo_protonation"
    assert VERDICT_TEXT["stereo_protonation"] == "Same skeleton; stereo or isotopes and protonation differ"


def test_a_check_row_carries_the_verdict_words(redis_client):
    (row,), _ = tasks._name_prepared([_pair(0, "C[C@@H](C(=O)O)N", "(2R)-2-aminopropanoic acid")], True, True)
    assert row["verdict"] == "stereo"
    assert row["verdict_text"] == "Same skeleton; stereo or isotopes differ"


def test_the_csv_and_sdf_carry_the_verdict_words():
    from app.jobs_api import CSV_COLUMNS
    from app.sdf_export import SDF_TAGS

    assert CSV_COLUMNS[CSV_COLUMNS.index("verdict") + 1] == "verdict_text"
    assert ("VERDICT_TEXT", "verdict_text") in SDF_TAGS


def _forgotten_after(monkeypatch, task, method, url, **kw):
    from app import main

    forgotten = []
    reply = kw.pop("reply")

    class _Result:
        def get(self, timeout):
            return reply

        def forget(self):
            forgotten.append(True)

    monkeypatch.setattr(getattr(main, task), "apply_async", lambda *a, **k: _Result())
    response = getattr(client, method)(url, **kw)
    assert response.status_code == 200, response.text
    return forgotten


def test_explain_and_from_name_forget_their_results(redis_client, monkeypatch):
    explain_reply = {"smiles": "CCO", "name": "ethanol", "nodes": []}
    assert _forgotten_after(monkeypatch, "explain_smiles", "get", "/api/explain", params={"smiles": "CCO"}, reply=dict(explain_reply)) == [True]
    assert _forgotten_after(monkeypatch, "explain_iupac_name", "get", "/api/explain-name", params={"name": "ethanol"}, reply=dict(explain_reply)) == [True]
    n2s = {"smiles": "CCO", "canonical_smiles": "CCO", "inchi": None, "inchikey": None,
           "molblock": None, "depiction_svg": None, "warnings": [], "error": None}
    assert _forgotten_after(monkeypatch, "name_to_smiles", "get", "/api/iupac-to-smiles", params={"name": "ethanol"}, reply=n2s) == [True]
