"""run-tests.sh must report the right exit code under BOTH pytest output forms.

This script has now shipped two bugs from the same root cause: a regex
anchored on pytest's "====" banner, which `-q` does not print. The first
made a passing suite look like a 180 s hang. The second made a FAILING suite
exit 0 -- a green light on red tests, which is worse, and which survived
because nothing here ever ran the script against a failure.

The inner pytest deliberately targets a file outside the repo so the real
conftest.py (which requires Redis) never loads: these cases are about the
shell script's exit code, not about Orthonym.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run-tests.sh"

PASSING = "def test_p():\n    assert True\n"
FAILING = "def test_p():\n    assert True\n\n\ndef test_f():\n    assert False\n"
XFAILING = (
    "import pytest\n\n\n"
    "@pytest.mark.xfail(reason='expected')\n"
    "def test_x():\n    assert False\n"
)
SKIPPED = (
    "import pytest\n\n\n"
    "@pytest.mark.skip(reason='skipped')\n"
    "def test_s():\n    assert True\n"
)


def run(tmp_path, body, extra_args):
    probe = tmp_path / "test_probe.py"
    probe.write_text(body, encoding="utf-8")
    return subprocess.run(
        [str(SCRIPT), str(probe), "-p", "no:cacheprovider", *extra_args],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(tmp_path),
            # Isolated log: the default /tmp/orthonym-pytest.log is shared, and
            # a concurrent run would otherwise read the other one's summary.
            "ORTHONYM_TEST_LOG": str(tmp_path / "probe.log"),
            "ORTHONYM_TEST_WAIT": "60",
        },
    ).returncode


# -q is the case both bugs hid in; the default form is here so a "fix" that
# only ever looks at the bare summary cannot pass either.
FORMS = pytest.mark.parametrize("extra", [[], ["-q"]], ids=["banner", "quiet"])


@FORMS
def test_a_failing_run_exits_1(tmp_path, extra):
    assert run(tmp_path, FAILING, extra) == 1


@FORMS
def test_a_passing_run_exits_0(tmp_path, extra):
    assert run(tmp_path, PASSING, extra) == 0


@FORMS
def test_an_expected_failure_is_not_a_failure(tmp_path, extra):
    """"1 xfailed" contains the substring "failed". A naive *failed* match
    fails a suite whose expected-failures all behaved exactly as declared.
    """
    assert run(tmp_path, XFAILING, extra) == 0


@FORMS
def test_a_skip_only_run_is_not_a_hang(tmp_path, extra):
    """"1 skipped in 0.00s" is a real, complete summary. Missing it from the
    outcome list made the waiter sit out its whole timeout and then report
    "NO PYTEST SUMMARY" (exit 2) on a run that finished in milliseconds.
    """
    assert run(tmp_path, SKIPPED, extra) == 0


ERRORING = "import no_such_module_for_the_probe\n\n\ndef test_e():\n    pass\n"
# Dies at collection without ever printing a summary.
NO_SUMMARY = "import os\nos._exit(0)\n"


@FORMS
def test_a_run_that_only_errors_exits_1(tmp_path, extra):
    """"1 error in 0.02s" is a red run with no "failed" in it; a check that
    only looks for "failed" reports a collection error as green.
    """
    assert run(tmp_path, ERRORING, extra) == 1


def test_a_run_with_no_summary_exits_2(tmp_path):
    """A pytest that dies without a summary is a hang or a crash, never a pass."""
    assert run(tmp_path, NO_SUMMARY, ["-q"]) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="bash script")
def test_the_script_is_executable():
    assert SCRIPT.is_file() and SCRIPT.stat().st_mode & 0o111
