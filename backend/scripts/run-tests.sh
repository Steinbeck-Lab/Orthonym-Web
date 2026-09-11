#!/usr/bin/env bash
#
# Run pytest and report the real result, without waiting on the JVM.
#
# Why this exists: JPype starts a JVM for OPSIN, and the JVM refuses to let
# the process exit afterwards. The suite finishes in ~3 seconds and then the
# process sits there for minutes before dying with exit 144 -- *after* pytest
# has already printed a correct summary. So a plain `pytest` invocation looks
# like a 10-minute hang followed by a failure, and neither is true.
#
# This waits for pytest's own summary line to appear in the log, then kills
# the corpse and reports the summary. The summary line is the result; the
# exit code and wall-clock are noise.
#
# Usage:
#   backend/scripts/run-tests.sh                        # whole suite
#   backend/scripts/run-tests.sh tests/test_inputs.py -v
#
# Exit: 0 all passed, 1 tests failed, 2 no summary appeared (real hang),
# 3 no interpreter found (see the venv resolution below).
set -uo pipefail

cd "$(dirname "$0")/.."

LOG=${ORTHONYM_TEST_LOG:-/tmp/orthonym-pytest.log}
: > "$LOG"

# .venv-mac and .venv are not interchangeable: a venv is tied to the OS
# and interpreter it was built with, and orthonym pulls in compiled
# native deps (rdkit, JPype's JVM bridge), so a Linux .venv cannot run on
# macOS and vice versa. Prefer .venv-mac when it exists so the
# maintainer's macOS workflow stays byte-identical to before this
# detection was added; otherwise fall back to .venv, the Linux venv
# CLAUDE.md/INSTALL.md have every other command run through. Fail loudly
# and by name rather than silently running the wrong interpreter (or
# failing deep inside pytest with an obscure import error) when neither
# is present.
if [ -x .venv-mac/bin/python ]; then
    PYTHON=.venv-mac/bin/python
elif [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
else
    echo "error: no interpreter at .venv-mac/bin/python or .venv/bin/python." >&2
    echo "Build one (from backend/): python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt" >&2
    exit 3
fi

REDIS_URL=${REDIS_URL:-redis://localhost:6379/0} \
PYTHONPATH="$(pwd)" \
  "$PYTHON" -m pytest "$@" > "$LOG" 2>&1 &
PYTEST_PID=$!

# Matches BOTH pytest's banner form ("==== 4 passed in 0.1s ====") and the
# bare form -q prints ("4 passed in 0.1s"). The banner-only pattern made
# `run-tests.sh <file> -q` report "NO PYTEST SUMMARY after 180s" on a suite
# that had already passed -- a false hang, because -q suppresses the ===
# rule the old regex anchored on. Found by a documentation audit that ran
# the script rather than reading it.
#
# The outcome list must be COMPLETE, not just the common three: a -q run whose
# summary is "1 xfailed in 0.01s" or "1 skipped in 0.00s" matched neither
# alternative, so the waiter below burned the full ORTHONYM_TEST_WAIT and then
# reported a hang on a suite that had finished in milliseconds. Third bug from
# this one regex; add any outcome word pytest can print, never a subset.
_OUTCOMES='passed|failed|error|errors|skipped|xfailed|xpassed|deselected|warning|warnings'
SUMMARY="^(=+ .*($_OUTCOMES|no tests ran)|[0-9]+ ($_OUTCOMES)|no tests ran)"
WAIT_SECONDS=${ORTHONYM_TEST_WAIT:-180}

for _ in $(seq 1 "$WAIT_SECONDS"); do
    grep -qE "$SUMMARY" "$LOG" && break
    # If pytest died without a summary (import crash), stop waiting.
    kill -0 "$PYTEST_PID" 2>/dev/null || break
    sleep 1
done

kill -9 "$PYTEST_PID" 2>/dev/null
wait "$PYTEST_PID" 2>/dev/null

if ! grep -qE "$SUMMARY" "$LOG"; then
    echo "NO PYTEST SUMMARY after ${WAIT_SECONDS}s. Full log: $LOG" >&2
    tail -40 "$LOG" >&2
    exit 2
fi

grep -E '^(FAILED|ERROR)' "$LOG" || true
FINAL=$(grep -E "$SUMMARY" "$LOG" | tail -1)
echo "$FINAL"

# Decide from the summary LINE, not the whole log, and without anchoring on
# the "===" banner: under -q pytest prints a bare "1 failed, 1 passed in
# 0.09s" with no === rule, so the old banner-anchored regex exited 0 on a
# failing run -- a green light on red tests, and the same regex-anchoring
# mistake as the false hang above, pointing the other way.
#
# "[0-9]+ " prefix is load-bearing: a plain *failed* match would also fire
# on "1 xfailed", failing a suite whose expected-failures all behaved.
if printf '%s\n' "$FINAL" | grep -qE '[0-9]+ (failed|error)'; then
    exit 1
fi
exit 0
