from tests.conftest import GOLDEN_NAMES


def test_golden_corpus_is_populated():
    assert len(GOLDEN_NAMES) == 10
    assert all(isinstance(n, str) and n for n in GOLDEN_NAMES)


def test_app_imports():
    from app import explain  # noqa: F401
