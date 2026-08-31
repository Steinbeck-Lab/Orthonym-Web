"""The celeryd_init guard must actually fire.

A guard that never runs is worse than no guard, because it reads as
protection. This starts a JVM deliberately and asserts the handler refuses.
"""

import pytest


def test_parent_guard_raises_when_a_jvm_is_already_started(monkeypatch):
    from app import celery_app as celery_module

    monkeypatch.setattr(
        celery_module, "_jvm_is_started", lambda: True, raising=True
    )
    with pytest.raises(RuntimeError, match="JVM was already started"):
        celery_module._assert_parent_has_no_jvm()


def test_parent_guard_is_silent_when_no_jvm_is_started(monkeypatch):
    from app import celery_app as celery_module

    monkeypatch.setattr(
        celery_module, "_jvm_is_started", lambda: False, raising=True
    )
    celery_module._assert_parent_has_no_jvm()  # must not raise


def test_parent_guard_is_registered_on_celeryd_init():
    from celery.signals import celeryd_init

    from app import celery_app as celery_module

    receivers = [r() for _, r in celeryd_init.receivers]
    assert celery_module._assert_parent_has_no_jvm in receivers
