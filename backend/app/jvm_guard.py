"""The one gate between a naming request and OPSIN's SELF-01 verification.

A separate module rather than living in app.ratelimit (which every other
per-endpoint check lives in) because this check is not per-IP -- every
caller is refused identically, regardless of who they are. It is its own
module rather than living in app.main so that app.jobs_api can call it too
without a main-imports-jobs_api-imports-main cycle (main.py already
imports app.jobs_api at module scope).
"""

from __future__ import annotations

from fastapi import HTTPException

from app import redis_store


def require_a_live_jvm() -> None:
    """The Orthonym engine's SELF-01 gate fails OPEN without a JVM, shipping a
    fallback labelled as a verified PIN. Serving a name -- or, for
    POST /api/jobs, DISPATCHING a batch that will go on to name molecules
    with nobody verifying the tier -- in that state would break PRODUCT.md
    principle 3, so every such path refuses instead (round 2 review,
    Also-fix: POST /api/jobs is a naming endpoint too, and was missing this
    gate entirely).
    """
    if not redis_store.any_worker_has_opsin():
        raise HTTPException(
            status_code=503,
            detail=(
                "No worker currently has a live JVM, so OPSIN cannot verify "
                "any name. Refusing rather than serving names with an "
                "unverified confidence tier. See /api/health."
            ),
        )
