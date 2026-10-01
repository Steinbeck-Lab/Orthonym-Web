"""Write tests/fixtures/explain_traces.json: one stored OPSIN trace per
readable corpus or golden name, so label/owner/tree tests run without a JVM.

    cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/11 \
      .venv/bin/python scripts/dump_traces.py

Re-run after any change to app/opsin_trace.py; tests/test_trace_fixtures.py
fails when the stored traces drift from a live run, or when the stored
opsin_trace_sha256 is not the hash of the current app/opsin_trace.py.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

from app.opsin_trace import Trace, running_opsin_version, trace, trace_to_dict
from tests.conftest import GOLDEN_NAMES
from tests.fixtures.explain_corpus import CURATED, FULL

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "tests" / "fixtures" / "explain_traces.json"
MODULE = BACKEND / "app" / "opsin_trace.py"


def main() -> None:
    version = running_opsin_version()
    if version is None:
        raise SystemExit("OPSIN tracing is unavailable (no JVM or jar?); nothing written")
    traces, skipped = {}, []
    for name in sorted({n for _, n in CURATED + FULL} | set(GOLDEN_NAMES)):
        result = trace(name)
        if isinstance(result, Trace):
            traces[name] = trace_to_dict(result)
        else:
            skipped.append((name, result.reason))
    header = {
        "opsin": version,
        "opsin_trace_sha256": hashlib.sha256(MODULE.read_bytes()).hexdigest(),
        "traces": traces,
    }
    OUT.write_text(json.dumps(header, sort_keys=True))
    print(f"wrote {len(traces)} traces to {OUT}")
    for name, reason in skipped:
        print(f"  skipped ({reason}): {name}")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)   # the JVM would otherwise keep the process alive
