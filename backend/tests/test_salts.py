"""Opt-in salt stripping: name the largest organic fragment, say what went."""

from rdkit import Chem

from app.salts import strip


def strip_salts(smiles):
    """(kept, removed) from the production `strip`, for readable asserts."""
    kept, notes = strip(smiles)
    return kept, notes.get("removed")


def test_one_fragment_is_unchanged():
    assert strip_salts("CCO") == ("CCO", None)


def test_the_typed_text_of_the_kept_fragment_is_named():
    assert strip_salts("CC(=O)Oc1ccccc1C(=O)O.Cl") == ("CC(=O)Oc1ccccc1C(=O)O", "Cl")


def test_the_typed_order_is_kept():
    assert strip_salts("Cl.OCC") == ("OCC", "Cl")


def test_every_removed_fragment_is_listed():
    assert strip_salts("CCO.Cl.Cl") == ("CCO", "Cl.Cl")


def test_an_all_inorganic_salt_keeps_one_fragment():
    kept, removed = strip_salts("[Na+].[Cl-]")
    assert kept and removed
    assert {kept, removed} == {"[Na+]", "[Cl-]"}


def test_one_molecule_written_across_a_dot_is_not_split():
    # A ring-closure digit joins the two pieces: RDKit sees one fragment.
    assert strip_salts("C1.C1") == ("C1.C1", None)


def test_pieces_that_do_not_parse_alone_fall_back_to_canonical():
    # Ethane written across a dot, plus HCl: two fragments, but "C1" alone
    # is not a SMILES, so the kept text is RDKit's canonical form.
    kept, removed = strip_salts("C1.C1.Cl")
    assert (kept, removed) == ("CC", "Cl")
    assert Chem.MolFromSmiles(kept) is not None


# --- in the naming paths ----------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app import name_cache, tasks  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_the_fast_path_names_the_kept_fragment(redis_client):
    body = client.post("/api/translate", json={"smiles": ["CCO.Cl"], "strip_salts": True}).json()
    (row,) = body["results"]
    assert row["smiles"] == "CCO"
    assert row["stripped_from"] == "CCO.Cl"
    assert row["removed"] == "Cl"
    assert row["name"] == "ethanol"


def test_the_switch_is_off_by_default(redis_client):
    (row,) = client.post("/api/translate", json={"smiles": ["CCO.Cl"]}).json()["results"]
    assert row["smiles"] == "CCO.Cl"
    assert row["stripped_from"] is None


def test_a_stripped_row_does_not_reach_the_cache(redis_client):
    client.post("/api/translate", json={"smiles": ["CCO.Cl"], "strip_salts": True})
    (row,) = client.post("/api/translate", json={"smiles": ["CCO"]}).json()["results"]
    assert row["stripped_from"] is None
    cached = name_cache.get_cached("CCO", True, True)
    assert cached is not None and cached.stripped_from is None


def test_a_batch_row_says_what_was_removed(redis_client):
    item = {"index": 0, "raw_input": "CCO.Cl", "input_id": None, "smiles": "CCO.Cl",
            "error": None, "strip_salts": True}
    (row,), failed = tasks._name_prepared([item], True, True)
    assert (row["smiles"], row["stripped_from"], row["removed"]) == ("CCO", "CCO.Cl", "Cl")
    assert row["name"] == "ethanol" and failed == 0


def test_a_job_strips_when_asked(redis_client):
    job = client.post("/api/jobs", json={"text": "CCO.Cl\nCCN\n", "strip_salts": True}).json()
    rows = client.get(f"/api/jobs/{job['job_id']}/results").json()["rows"]
    assert [(r["smiles"], r["removed"]) for r in rows] == [("CCO", "Cl"), ("CCN", None)]


def test_a_job_echoes_the_strip_switch(redis_client):
    job = client.post("/api/jobs", json={"text": "CCO\n", "strip_salts": True}).json()
    assert client.get(f"/api/jobs/{job['job_id']}").json()["strip_salts"] is True
    job = client.post("/api/jobs", json={"text": "CCO\n"}).json()
    assert client.get(f"/api/jobs/{job['job_id']}").json()["strip_salts"] is False


def test_an_old_job_has_no_strip_switch():
    from app.redis_store import job_switches

    assert job_switches({"best_effort": "1", "verify": "1"})["strip_salts"] is None


def test_the_csv_has_the_strip_columns(redis_client):
    job = client.post("/api/jobs", json={"text": "CCO.Cl\nCCN\n", "strip_salts": True}).json()
    lines = client.get(f"/api/jobs/{job['job_id']}/results.csv").text.splitlines()
    cols = lines[0].split(",")
    assert cols[-2:] == ["engine_version", "engine_commit"]
    at = cols.index("stripped_from")
    assert cols[at + 1] == "removed"
    first = lines[1].split(",")
    assert (first[at], first[at + 1]) == ("CCO.Cl", "Cl")


def test_the_sdf_has_the_strip_tags():
    from app.sdf_export import sdf_record

    record = sdf_record({"smiles": "CCO", "status": "pin", "stripped_from": "CCO.Cl", "removed": "Cl"})
    assert "> <STRIPPED_FROM>\nCCO.Cl\n" in record
    assert "> <REMOVED>\nCl\n" in record
    assert "> <STRIPPED_FROM>\n\n" in sdf_record({"smiles": "CCO", "status": "pin"})


# --- review fixes: error and timeout paths, cache, check jobs ----------------

import pytest  # noqa: E402
from celery.exceptions import SoftTimeLimitExceeded  # noqa: E402

_SALT = {"index": 0, "raw_input": "CCO.Cl", "input_id": None, "smiles": "CCO.Cl",
         "error": None, "strip_salts": True}


def _boom(*args, **kwargs):
    raise RuntimeError("engine down")


def test_a_batch_engine_error_names_the_fragment_it_ran_on(redis_client, monkeypatch):
    monkeypatch.setattr(tasks, "name_one", _boom)
    (row,), _ = tasks._name_prepared([dict(_SALT)], True, True)
    assert (row["status"], row["smiles"], row["stripped_from"], row["removed"]) == (
        "error", "CCO", "CCO.Cl", "Cl")


def test_a_fast_engine_error_keeps_the_note(redis_client, monkeypatch):
    monkeypatch.setattr(tasks, "translate_one", _boom)
    monkeypatch.setattr(tasks.name_cache, "get_cached", lambda *a, **k: None)
    (row,) = client.post("/api/translate", json={"smiles": ["CCCO.Cl"], "strip_salts": True}).json()["results"]
    assert (row["status"], row["smiles"], row["stripped_from"]) == ("error", "CCCO", "CCCO.Cl")


def test_a_timed_out_row_names_the_fragment_it_ran_on():
    # The loop hands over what the engine was given (test_name_check covers
    # that path end to end); the handler only labels it.
    timeout = tasks._ChunkTimedOut(
        [], 0, [dict(_SALT)], named_as=("CCO", {"stripped_from": "CCO.Cl", "removed": "Cl"})
    )
    (row,), _ = tasks._timed_out_rows(timeout)
    assert (row["smiles"], row["stripped_from"], row["removed"]) == ("CCO", "CCO.Cl", "Cl")


def test_the_batch_path_does_not_poison_the_cache(redis_client):
    tasks._name_prepared([dict(_SALT)], True, True)
    cached = name_cache.get_cached("CCO", True, True)
    assert cached is not None and cached.stripped_from is None


def test_a_check_job_never_strips(redis_client):
    job = client.post(
        "/api/jobs", json={"text": "smiles,name\nCCO.Cl,ethanol\n", "kind": "check", "strip_salts": True}
    ).json()
    status = client.get(f"/api/jobs/{job['job_id']}").json()
    assert status["strip_salts"] is False
    (row,) = client.get(f"/api/jobs/{job['job_id']}/results").json()["rows"]
    assert row["stripped_from"] is None and row["smiles"] == "CCO.Cl"


def test_a_structure_rdkit_cannot_read_says_it_was_not_stripped(redis_client, monkeypatch):
    # CDK rescues some inputs RDKit refuses; those are never stripped, and
    # the row must say the switch did nothing rather than stay silent.
    item = dict(_SALT, smiles="C[N](C)(C)(C)C.Cl", raw_input="C[N](C)(C)(C)C.Cl")
    (row,), _ = tasks._name_prepared([item], True, True)
    assert row["strip_skipped"] is True
    assert row["stripped_from"] is None
    assert strip_salts("C[N](C)(C)(C)C.Cl") == ("C[N](C)(C)(C)C.Cl", None)


def test_an_ordinary_row_is_not_marked_skipped(redis_client):
    (row,), _ = tasks._name_prepared([dict(_SALT)], True, True)
    assert row["strip_skipped"] is False
