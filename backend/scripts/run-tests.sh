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
# Exit: 0 all passed, 1 tests failed, 2 no summary appeared (real hang).
set -uo pipefail

cd "$(dirname "$0")/.."

LOG=${STITCH_TEST_LOG:-/tmp/stitch-pytest.log}
: > "$LOG"

# .venv-mac, not .venv: the committed .venv is a Linux venv built at
# /home/kohulan/STITCH and cannot run on macOS.
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0} \
PYTHONPATH="$(pwd)" \
  .venv-mac/bin/python -m pytest "$@" > "$LOG" 2>&1 &
PYTEST_PID=$!

# Matches BOTH pytest's banner form ("==== 4 passed in 0.1s ====") and the
# bare form -q prints ("4 passed in 0.1s"). The banner-only pattern made
# `run-tests.sh <file> -q` report "NO PYTEST SUMMARY after 180s" on a suite
# that had already passed -- a false hang, because -q suppresses the ===
# rule the old regex anchored on. Found by a documentation audit that ran
# the script rather than reading it.
SUMMARY='^(=+ .*(passed|failed|error|no tests ran)|[0-9]+ (passed|failed|error)|no tests ran)'
WAIT_SECONDS=${STITCH_TEST_WAIT:-180}

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
grep -E "$SUMMARY" "$LOG" | tail -1

if grep -qE '^=+ .*(failed|error)' "$LOG"; then
    exit 1
fi
exit 0
