"""The stored traces must match a live OPSIN run, or every JVM-free test
built on them tests a world that no longer exists."""

import pytest

from app.opsin_trace import trace
from tests.conftest import GOLDEN_NAMES
from tests.fixtures.explain_corpus import CURATED, FULL
from tests.fixtures.traces import load_traces

SAMPLE = [
    "ethanol",
    "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione",
    "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane",
    "alpha-D-glucopyranose",
    "(1R,2S)-2-(methylamino)-1-phenylpropan-1-ol",
    "2-[4-(2-methylpropyl)phenyl]propanoic acid",
]
OPSIN_CANNOT_PARSE = {"(1R,2S,3r,4R,5S,6s)-cyclohexane-1,2,3,4,5,6-hexol", "dinitrogen tetroxide"}


def test_fixture_covers_every_readable_corpus_and_golden_name():
    expected = ({n for _, n in CURATED + FULL} | set(GOLDEN_NAMES)) - OPSIN_CANNOT_PARSE
    assert set(load_traces()) == expected


@pytest.mark.parametrize("name", SAMPLE)
def test_stored_trace_matches_a_live_run(name):
    assert load_traces()[name] == trace(name)
