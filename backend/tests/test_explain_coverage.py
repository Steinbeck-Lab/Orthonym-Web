"""Corpus gate (spec §8.3). Every readable FULL + CURATED + golden name must
classify CLEAN under the census's own classifier: every part placed, atoms
partitioned, spans valid and non-crossing, clean labels, no orphan token,
hydro and stereo marks on atoms that carry their locants, and the traced
molecule equal to OPSIN's public parse. Only the two names OPSIN 2.9.0
cannot read may do otherwise, and they must say so."""

import pytest

from scripts.explain_census import run
from tests.conftest import GOLDEN_NAMES
from tests.fixtures.explain_corpus import CURATED, FULL

OPSIN_CANNOT_PARSE = {
    "(1R,2S,3r,4R,5S,6s)-cyclohexane-1,2,3,4,5,6-hexol",
    "dinitrogen tetroxide",
}
NAMES = sorted({name for _, name in CURATED + FULL} | set(GOLDEN_NAMES))


@pytest.mark.parametrize("name", NAMES)
def test_name_is_clean(name):
    (outcomes,) = run([name]).values()
    expected = ["UNREADABLE"] if name in OPSIN_CANNOT_PARSE else ["CLEAN"]
    assert outcomes == expected, (name, outcomes)
