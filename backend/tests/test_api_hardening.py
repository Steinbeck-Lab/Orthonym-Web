"""Backend API hardening: per-record caps on molfile/SDF records, CSV
delimiters, the worker parse on /api/translate, bounded parse waits, cached
sorted views, the name cache's outage guard, terminal-status idempotency,
cancel's real answer, partial downloads, the owner-token header, IPv6 peers,
and a name check whose warnings could not be read.

No test here submits a Celery job: every job is built in Redis directly.
"""

import uuid

import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from rdkit import Chem

from app import inputs, jobs_api, main, name_cache, name_check, ratelimit, redis_store, tasks
from app.core.config import get_settings
from app.schemas import BatchRow, JobEnvelope, ResultItem

TOKEN = "owner-token-for-tests"


@pytest.fixture
def client(monkeypatch):
    # The limiters are tested elsewhere; here they would only make these
    # tests depend on what else ran this minute from "testclient".
    for module in (jobs_api, main):
        for name in ("check_fast_allowed", "check_poll_allowed", "check_download_allowed",
                     "check_job_allowed", "require_a_live_jvm"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, lambda *a, **k: None)
    return TestClient(main.app)


def _job_with_rows(job_id: str, statuses: list[str], status: str = "running") -> None:
    redis_store.create_job(job_id, len(statuses), "smiles_list", "203.0.113.9", TOKEN)
    rows = [
        BatchRow(index=i, input=f"in{i}", status=s).model_dump()
        for i, s in enumerate(statuses)
    ]
    redis_store.write_chunk(job_id, 0, rows)
    if status != "running":
        redis_store.set_job_status(job_id, status)


# -- 1. molfile/SDF records get the SMILES path's caps ----------------------


def test_a_molfile_over_the_atom_cap_is_an_error_row_not_a_mol_to_smiles_call(monkeypatch):
    block = Chem.MolToMolBlock(Chem.MolFromSmiles("C" * 2500), forceV3000=True)

    def no_smiles(*_a, **_k):
        raise AssertionError("MolToSmiles ran on an over-cap molecule (it segfaults at ~30k atoms)")

    monkeypatch.setattr(inputs.Chem, "MolToSmiles", no_smiles)
    (row,) = inputs.parse(block.encode(), inputs.sniff(block.encode()), 10)
    assert row.smiles is None
    assert "2500 atoms" in row.error


def test_an_sdf_record_whose_smiles_is_over_the_length_cap_is_an_error_row():
    # 400 atoms, but six characters each in SMILES: under the atom cap,
    # over the length cap.
    block = Chem.MolToMolBlock(Chem.MolFromSmiles("[SiH3]" + "[SiH2]" * 398 + "[SiH3]"))
    data = (block + "$$$$\n").encode()
    (row,) = inputs.parse(data, inputs.InputFormat.SDF, 10)
    assert row.smiles is None
    assert row.error == f"SMILES string exceeds {inputs.MAX_MOLECULE_SMILES_LENGTH} characters"


# -- 13. a tab- or semicolon-separated paste reads as CSV -------------------


@pytest.mark.parametrize("sep", ["\t", ";"])
def test_a_csv_with_a_tab_or_semicolon_delimiter_is_read_with_it(sep):
    data = "\n".join([f"smiles{sep}id"] + [f"C{'C' * i}O{sep}mol{i}" for i in range(11)]).encode()
    fmt = inputs.sniff(data)
    assert fmt is inputs.InputFormat.CSV
    rows = inputs.parse(data, fmt, 100)
    assert len(rows) == 11
    assert (rows[0].smiles, rows[0].input_id) == ("CO", "mol0")
    assert inputs.count_molecules(data, fmt) == 11


# -- 7. a csv.Error in the preview is a 400, not a 500 ----------------------


def test_parse_preview_answers_400_for_a_csv_field_past_the_csv_limit(client):
    text = 'smiles,id\n"' + "C" * 140_000 + '",x\n'
    response = client.post("/api/parse-preview", json={"text": text})
    assert response.status_code == 400, response.text


# -- 1. the blocking wait on a worker's parse is bounded --------------------


class _StartedButSilent:
    state = "STARTED"

    def __init__(self):
        self.revoked = False

    def get(self, timeout=None):
        assert timeout is not None, "an unbounded wait on the worker's parse"
        raise CeleryTimeoutError()

    def revoke(self):
        self.revoked = True

    def forget(self):
        pass


def test_parse_or_400_answers_504_when_the_worker_never_answers(monkeypatch):
    pending = _StartedButSilent()
    monkeypatch.setattr(jobs_api.parse_input, "apply_async", lambda *a, **k: pending)
    with pytest.raises(HTTPException) as caught:
        jobs_api._parse_or_400(b"CCO", 10)
    assert caught.value.status_code == 504
    assert pending.revoked


# -- 2. /api/translate's job branch parses in a worker ----------------------


def test_translate_over_the_fast_limit_parses_in_a_worker_not_here(client, monkeypatch):
    def no_web_parse(*_a, **_k):
        raise AssertionError("the job branch parsed in the web process")

    seen = {}

    def worker_parse(data, max_molecules, kind="name", fmt=None):
        seen.update(data=data, fmt=fmt)
        return fmt, inputs.parse(data, fmt, max_molecules)

    monkeypatch.setattr(main, "_canonicalize", no_web_parse)
    monkeypatch.setattr(main, "_parse_or_400", worker_parse)
    monkeypatch.setattr(
        main, "admit_and_dispatch",
        lambda ip, molecules, fmt, options: JobEnvelope(
            job_id="x", molecule_count=len(molecules), status="queued", owner_token="t"
        ),
    )
    n = get_settings().FAST_PATH_MAX_MOLECULES + 1
    response = client.post("/api/translate", json={"smiles": ["CCO"] * n})
    assert response.status_code == 200, response.text
    assert response.json()["molecule_count"] == n
    assert seen["fmt"] is inputs.InputFormat.SMILES_LIST


def test_parse_input_reads_a_given_format_instead_of_sniffing():
    # "smiles" on the first line sniffs as a CSV header; a SMILES list it is.
    outcome = tasks.parse_input.run(b"smiles\nCCO", 10, "name", "smiles_list")
    assert outcome["fmt"] == "smiles_list"
    assert len(outcome["molecules"]) == 2


# -- 5. /api/iupac-to-smiles refuses a multi-line or over-long name ---------


def test_iupac_to_smiles_refuses_a_name_with_a_line_break(client, monkeypatch):
    monkeypatch.setattr(main, "_fast_result", lambda *a, **k: pytest.fail("OPSIN was asked"))
    response = client.get("/api/iupac-to-smiles", params={"name": "benzene\nethanol"})
    assert response.status_code == 400


def test_iupac_to_smiles_refuses_a_name_past_the_length_cap(client, monkeypatch):
    monkeypatch.setattr(main, "_fast_result", lambda *a, **k: pytest.fail("OPSIN was asked"))
    response = client.get(
        "/api/iupac-to-smiles", params={"name": "a" * (name_check.MAX_CLAIMED_NAME_LENGTH + 1)}
    )
    assert response.status_code == 422


# -- 3. a sorted or filtered view is computed once, then served cached ------


def test_a_sorted_view_is_cached_so_later_pages_do_not_decode_every_row(
    client, monkeypatch, job_id
):
    _job_with_rows(job_id, ["error", "pin", "abstain", "pin"])
    tasks._close_job(job_id, 1)
    first = client.get(f"/api/jobs/{job_id}/results", params={"sort": "tier", "limit": 2})
    assert first.status_code == 200, first.text
    assert [r["index"] for r in first.json()["rows"]] == [1, 3]

    def no_full_read(*_a, **_k):
        raise AssertionError("the whole row list was decoded again")

    monkeypatch.setattr(jobs_api.redis_store, "iter_all_rows", no_full_read)
    second = client.get(
        f"/api/jobs/{job_id}/results", params={"sort": "tier", "offset": 2, "limit": 2}
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert [r["index"] for r in body["rows"]] == [2, 0]
    assert body["matched"] == 4


def test_a_filtered_view_is_its_own_cached_order(client, job_id):
    _job_with_rows(job_id, ["error", "pin", "abstain", "pin"])
    tasks._close_job(job_id, 1)
    client.get(f"/api/jobs/{job_id}/results", params={"sort": "tier"})
    filtered = client.get(
        f"/api/jobs/{job_id}/results", params={"sort": "tier", "status": "pin"}
    ).json()
    assert [r["index"] for r in filtered["rows"]] == [1, 3]
    assert filtered["matched"] == 2


# -- 4. a row demoted for a missing round trip is never cached --------------


@pytest.mark.parametrize(
    "status, limit_code", [("best_effort", None), ("abstain", "withheld_unchecked")]
)
def test_a_row_demoted_for_a_missing_round_trip_is_not_cached(status, limit_code):
    smiles = f"C{uuid.uuid4().hex}"
    item = ResultItem(
        smiles=smiles, status=status, tier="systematic_verified",
        name=None if status == "abstain" else "x", limit_code=limit_code,
    )
    try:
        name_cache.put_cached(item, best_effort=True, verify=True)
        assert name_cache.get_cached(smiles, True, True) is None
        # With verify off there is never a round trip, by request: cached.
        name_cache.put_cached(item, best_effort=True, verify=False)
        assert name_cache.get_cached(smiles, True, False) is not None
    finally:
        client = redis_store.get_redis()
        for verify in (True, False):
            client.delete(name_cache.cache_key(smiles, True, verify))


# -- 6. a redelivered close never wipes a terminal job's rows ---------------


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_a_redelivered_close_keeps_a_terminal_jobs_partial_rows(job_id, terminal):
    _job_with_rows(job_id, ["pin", "pin"])
    redis_store.get_redis().hset(redis_store.job_meta_key(job_id), "total", 5)
    if terminal == "cancelled":
        redis_store.set_job_status(job_id, "cancelled")
    # The first close assembles the two rows (and marks a short job failed).
    assert tasks._close_job(job_id, 1) == 2
    assert redis_store.rows_length(job_id) == 2
    assert redis_store.read_job_meta(job_id)["status"] == terminal
    # The redelivery: the chunk keys are gone now.
    tasks._close_job(job_id, 1)
    assert redis_store.rows_length(job_id) == 2


# -- 8. cancel answers the status the job really has ------------------------


def test_cancel_reports_the_real_status_when_the_job_finished_first(
    client, monkeypatch, job_id
):
    _job_with_rows(job_id, ["pin"])

    def lost_the_race(jid, status):
        # The job closed between cancel's read and its compare-and-set.
        redis_store.get_redis().hset(redis_store.job_meta_key(jid), "status", "failed")
        return False

    monkeypatch.setattr(jobs_api.redis_store, "set_job_status", lost_the_race)
    response = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-Owner-Token": TOKEN})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"


# -- 11. the owner token travels in a header (the query still works) --------


def test_the_owner_token_is_read_from_the_header_and_still_from_the_query(client, job_id):
    _job_with_rows(job_id, ["pin"])
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 403
    assert client.post(
        f"/api/jobs/{job_id}/cancel", headers={"X-Owner-Token": "wrong"}
    ).status_code == 403
    by_header = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-Owner-Token": TOKEN})
    assert by_header.json()["status"] == "cancelled"
    by_query = client.delete(f"/api/jobs/{job_id}", params={"owner_token": TOKEN})
    assert by_query.status_code == 200, by_query.text


# -- 9. a cancelled job's rows can be downloaded, as a partial file ---------


@pytest.mark.parametrize("ext", ["csv", "sdf"])
def test_a_cancelled_jobs_rows_download_as_a_partial_file(client, job_id, ext):
    _job_with_rows(job_id, ["pin", "pin"], status="cancelled")
    tasks._close_job(job_id, 1)
    response = client.get(f"/api/jobs/{job_id}/results.{ext}")
    assert response.status_code == 200, response.text
    assert response.headers["X-Orthonym-Job-Status"] == "cancelled"
    assert f"-partial.{ext}" in response.headers["Content-Disposition"]


# -- 10. a direct IPv6 peer is bucketed by /64 ------------------------------


def test_a_direct_ipv6_peer_is_bucketed_by_its_64(monkeypatch):
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", False)

    def peer(host):
        return Request({"type": "http", "headers": [], "client": (host, 1)})

    assert ratelimit.client_ip(peer("2001:db8::1")) == ratelimit.client_ip(peer("2001:db8::ffff"))
    assert ratelimit.client_ip(peer("2001:db8::1")) == "2001:db8::"
    assert ratelimit.client_ip(peer("testclient")) == "testclient"


# -- 12. a name check keeps its verdict when the warnings cannot be read ----


def test_a_verdict_survives_warnings_that_cannot_be_read(monkeypatch):
    import orthonym.validation.opsin_roundtrip as roundtrip

    def no_jvm(_name):
        raise RuntimeError("OPSIN warnings need the in-process JVM")

    monkeypatch.setattr(roundtrip, "opsin_parse", lambda name: "CCO")
    monkeypatch.setattr(name_check, "opsin_warnings", no_jvm)
    result = name_check.check_pair("CCO", "ethanol")
    assert result["verdict"] == "same"
    assert result["warnings"] is None

    row = {}
    tasks._check_row({"smiles": "CCO", "claimed_name": "ethanol"}, row)
    assert row["verdict"] == "same"
    assert row["opsin_warnings"] == name_check.WARNINGS_UNAVAILABLE
