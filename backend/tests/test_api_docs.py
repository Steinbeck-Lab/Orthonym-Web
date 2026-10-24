"""About's API section (frontend/src/lib/apiEndpoints.json) against the
real routes, both ways, so the page can neither invent nor miss one."""

import json
from pathlib import Path

from app.main import app

DOCS = Path(__file__).resolve().parents[2] / "frontend/src/lib/apiEndpoints.json"

# Public routes the section leaves out, each for a reason.
UNDOCUMENTED = {
    # Need the owner token a job's creator gets; a page of curl examples
    # cannot show a working call.
    ("POST", "/api/jobs/{job_id}/cancel"),
    ("DELETE", "/api/jobs/{job_id}"),
}


def _routes() -> set[tuple[str, str]]:
    # The OpenAPI paths, not app.routes: an included router is one opaque
    # entry in app.routes on this FastAPI, and the schema lists every path.
    return {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        for method in ops
    }


def _documented() -> set[tuple[str, str]]:
    return {(e["method"], e["path"]) for e in json.loads(DOCS.read_text())}


def test_every_documented_endpoint_exists():
    assert _documented() - _routes() == set()


def test_every_public_route_is_documented():
    assert _routes() - UNDOCUMENTED - _documented() == set()


def test_every_entry_has_a_working_example_shape():
    for entry in json.loads(DOCS.read_text()):
        assert entry["summary"], entry
        assert entry["curl"].startswith("curl "), entry
