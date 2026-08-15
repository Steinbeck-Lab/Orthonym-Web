"""Shared fixtures. GOLDEN_NAMES is the fixed decomposition corpus every
later task asserts against; add to it, never reorder or remove entries.
"""

import pytest

CAFFEINE = "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione"

GOLDEN_NAMES = [
    CAFFEINE,
    "2-[4-(2-methylpropyl)phenyl]propanoic acid",
    "2-acetyloxybenzoic acid",
    "2-amino-3-(1H-indol-3-yl)propanoic acid",
    "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane",
    "ethyl acetate",
    "4-tert-butylcyclohexan-1-ol",
    "2-methyl-1,3,5-trinitrobenzene",
    "benzene",
    "ethanol",
]


@pytest.fixture
def caffeine_name() -> str:
    return CAFFEINE
