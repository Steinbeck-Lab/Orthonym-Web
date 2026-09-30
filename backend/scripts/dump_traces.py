"""Write tests/fixtures/explain_traces.json: one stored OPSIN trace per
readable corpus or golden name, so label/owner/tree tests run without a JVM.

    cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/11 \
      .venv/bin/python scripts/dump_traces.py

Re-run after any change to app/opsin_trace.py; tests/test_trace_fixtures.py
fails when the stored traces drift from a live run.
"""

import json
import os
import sys
from pathlib import Path

from app.opsin_trace import PINNED_OPSIN_VERSION, Trace, trace, trace_to_dict
from tests.conftest import GOLDEN_NAMES
from tests.fixtures.explain_corpus import CURATED, FULL

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "explain_traces.json"


def main() -> None:
    traces, skipped = {}, []
    for name in sorted({n for _, n in CURATED + FULL} | set(GOLDEN_NAMES)):
        result = trace(name)
        if isinstance(result, Trace):
            traces[name] = trace_to_dict(result)
        else:
            skipped.append((name, result.reason))
    OUT.write_text(json.dumps({"opsin": PINNED_OPSIN_VERSION, "traces": traces}, sort_keys=True))
    print(f"wrote {len(traces)} traces to {OUT}")
    for name, reason in skipped:
        print(f"  skipped ({reason}): {name}")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)   # the JVM would otherwise keep the process alive
