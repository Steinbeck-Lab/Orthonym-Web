"""Which Orthonym engine this process names with.

Read once at import: an installed engine cannot change without a restart.
Every result and /api/health report these, so a name can always be traced to
the engine that wrote it -- the engine tracks main, and two builds can share a
version, so the commit is what tells them apart.
"""

import importlib.metadata
import json
from pathlib import Path

import orthonym

from .core.config import get_settings


def _engine_commit() -> str | None:
    """The engine commit, or None when nothing recorded one.

    pip records it for a git-URL install (a local venv, CI). The Docker image
    installs from a checked-out directory, so the Dockerfile writes it to
    ORTHONYM_COMMIT_FILE instead.
    """
    path = get_settings().ORTHONYM_COMMIT_FILE
    if path:
        try:
            return Path(path).read_text().strip() or None
        except OSError:
            return None
    try:
        info = json.loads(importlib.metadata.distribution("orthonym").read_text("direct_url.json") or "{}")
    except (importlib.metadata.PackageNotFoundError, ValueError):
        return None
    return info.get("vcs_info", {}).get("commit_id")


ENGINE_VERSION: str = orthonym.__version__
ENGINE_COMMIT: str | None = _engine_commit()
