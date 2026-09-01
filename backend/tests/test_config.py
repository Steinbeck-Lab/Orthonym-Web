import pytest

from app.core.config import Settings, get_settings, load_profile


def test_defaults_are_sized_for_the_documented_host():
    """Constructed with _env_file=None so this reads the CODE defaults.

    Settings() honours model_config's env_file=".env", so on a developer
    machine that has one -- which is the documented local-dev setup -- this
    test read their values and failed with no hint that their own environment
    caused it (audit item NB-4). It asserts what the code ships, so it must
    not depend on what any particular host happens to have lying next to it.
    """
    settings = Settings(_env_file=None)
    assert settings.CELERY_WORKERS_FAST == 2
    assert settings.CELERY_WORKERS_BATCH == 2
    assert settings.BATCH_CHUNK_SIZE == 25
    assert settings.MAX_BATCH_SIZE == 10000
    assert settings.FAST_PATH_MAX_MOLECULES == 10
    assert settings.JOB_RESULT_TTL_SECONDS == 86400
    assert settings.TRUST_PROXY_HEADERS is False


def test_profile_overrides_default(monkeypatch):
    monkeypatch.delenv("MAX_BATCH_SIZE", raising=False)
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "small")
    get_settings.cache_clear()
    assert get_settings().MAX_BATCH_SIZE == load_profile("small")["MAX_BATCH_SIZE"]
    get_settings.cache_clear()


def test_env_beats_profile(monkeypatch):
    # pydantic-settings gives init kwargs precedence over env by default,
    # which is backwards for us: an operator's explicit env var must win
    # over a profile file they did not write.
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "small")
    monkeypatch.setenv("MAX_BATCH_SIZE", "77")
    get_settings.cache_clear()
    assert get_settings().MAX_BATCH_SIZE == 77
    get_settings.cache_clear()


def test_unknown_profile_fails_loudly(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "enormous")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="enormous"):
        get_settings()
    get_settings.cache_clear()
