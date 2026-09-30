from tests.conftest import GOLDEN_NAMES


def test_golden_corpus_is_populated():
    # Entries may be added (never removed), so a floor, not an exact count.
    assert len(GOLDEN_NAMES) >= 10
    assert len(set(GOLDEN_NAMES)) == len(GOLDEN_NAMES)
    assert all(isinstance(n, str) and n for n in GOLDEN_NAMES)


def test_app_imports():
    from app import explain  # noqa: F401
