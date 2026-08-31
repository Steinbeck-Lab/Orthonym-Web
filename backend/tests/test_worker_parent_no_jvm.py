"""The celeryd_init guard must actually STOP the worker.

A guard that raises and is ignored is worse than no guard, because it reads
as protection. Celery's Signal.send wraps every receiver in `except
Exception`, logs the traceback, and returns the exception as a response which
celery/apps/worker.py discards -- so a RuntimeError here is swallowed and the
worker boots and forks anyway. SystemExit derives from BaseException and
escapes that handler, which is why the guard uses it.

The third test is the one that matters: it sends the real signal rather than
calling the handler, so it fails if the exception type is ever softened back
to something Celery swallows.
"""

import pytest
from celery.signals import celeryd_init

from app import celery_app as celery_module


def test_parent_guard_exits_when_a_jvm_is_already_started(monkeypatch):
    monkeypatch.setattr(celery_module, "_jvm_is_started", lambda: True)
    with pytest.raises(SystemExit):
        celery_module._assert_parent_has_no_jvm()


def test_parent_guard_is_silent_when_no_jvm_is_started(monkeypatch):
    monkeypatch.setattr(celery_module, "_jvm_is_started", lambda: False)
    celery_module._assert_parent_has_no_jvm()  # must not raise


def test_the_guard_actually_escapes_celerys_signal_dispatch(monkeypatch):
    # Celery swallows Exception in Signal.send. If the guard is ever changed
    # back to a plain exception, this is the test that catches it: send()
    # would return normally and the worker would keep booting.
    monkeypatch.setattr(celery_module, "_jvm_is_started", lambda: True)
    with pytest.raises(SystemExit):
        celeryd_init.send(sender="test")


def test_parent_guard_is_registered_on_celeryd_init():
    receivers = [r() if callable(r) else r for _, r in celeryd_init.receivers]
    assert celery_module._assert_parent_has_no_jvm in receivers
