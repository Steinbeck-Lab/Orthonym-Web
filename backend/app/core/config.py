"""Central settings for the STITCH backend.

Precedence is environment variable > deployment profile > code default, and
it is implemented explicitly below because pydantic-settings' own ordering
is the opposite: init kwargs beat env vars. An operator who sets
MAX_BATCH_SIZE in the environment must win over a profile file they did not
write, so profile values are only applied to keys absent from os.environ.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> the backend root, which is
# WORKDIR /code in the image. Profiles must live under backend/ because the
# Docker build context is ./backend; a repo-root config/ is unreachable.
PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAXMEMORY: str = "2gb"

    CELERY_WORKERS_FAST: int = 2
    CELERY_WORKERS_BATCH: int = 2

    FAST_PATH_MAX_MOLECULES: int = 10
    FAST_PATH_TIMEOUT: int = 30

    BATCH_CHUNK_SIZE: int = 25
    MAX_BATCH_SIZE: int = 10000
    MAX_FILE_SIZE_MB: int = 50

    JOB_RESULT_TTL_SECONDS: int = 86400
    NAME_CACHE_TTL_SECONDS: int = 604800

    RATE_LIMIT_MAX_CONCURRENT_JOBS: int = 2
    RATE_LIMIT_JOBS_PER_HOUR: int = 20
    RATE_LIMIT_FAST_PER_MINUTE: int = 60
    # /api/depict is called once per visible row in a batch results table --
    # a legitimate 1,000-row view is 1,000 calls well within a minute, which
    # RATE_LIMIT_FAST_PER_MINUTE (sized for a single OPSIN lookup) would
    # wrongly treat as abuse. Same mechanism, a much larger budget: it is
    # pure RDKit with no JVM/worker/queue behind it, so the cost per call is
    # far lower anyway.
    RATE_LIMIT_DEPICT_PER_MINUTE: int = 1200
    # GET /api/jobs/{id} and .../results are polled repeatedly by design --
    # a progress bar checking every 1-2 s is 30-60 req/min for ONE job, and
    # a caller can have several open at once. check_fast_allowed's budget
    # (60/minute, sized for a single OPSIN lookup) would throttle ordinary
    # polling, so this is its own, larger budget (round 3 review, finding
    # 4) -- still bounded, unlike having no limiter at all.
    RATE_LIMIT_POLL_PER_MINUTE: int = 300

    CHUNK_SOFT_TIME_LIMIT: int = 600
    CHUNK_HARD_TIME_LIMIT: int = 900

    # X-Forwarded-For is attacker-controlled unless a reverse proxy is
    # known to overwrite it. Trusting it unconditionally would make every
    # per-IP cap bypassable with one header, so it is opt-in.
    TRUST_PROXY_HEADERS: bool = False

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


def load_profile(name: str) -> dict[str, Any]:
    """Read one deployment profile. Raises ValueError on an unknown name --
    a typo in DEPLOYMENT_PROFILE must not silently fall back to defaults.
    """
    path = PROFILE_DIR / f"{name}.yml"
    if not path.is_file():
        available = sorted(p.stem for p in PROFILE_DIR.glob("*.yml"))
        raise ValueError(
            f"Unknown DEPLOYMENT_PROFILE {name!r}. Available: {available}"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    profile = os.environ.get("DEPLOYMENT_PROFILE", "").strip()
    overrides: dict[str, Any] = {}
    if profile:
        for key, value in load_profile(profile).items():
            if key not in os.environ:
                overrides[key] = value
    return Settings(**overrides)
