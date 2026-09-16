"""Env gate for the background scheduler (tasks.cleanup.start_scheduler).

The scheduler runs autonomous jobs that email / push REAL users (overdue-return
alerts, doc-expiry warnings, digests). It must be possible to switch it off on
an environment whose DB is stale — the staging service was re-emailing real
advisors from months-old FILLED sessions. Gate: ENABLE_SCHEDULER=false disables
it; the flag defaults ON so prod and local dev are unchanged when it is unset.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import tasks.cleanup as cleanup


@pytest.mark.parametrize('value,expected', [
    (None, True),      # unset → default ON (prod / local unchanged)
    ('true', True),
    ('TRUE', True),
    ('1', True),
    ('false', False),  # the value set on the staging service
    ('FALSE', False),
    ('0', False),
    ('no', False),
    ('off', False),
    (' false ', False),  # tolerate stray whitespace in the DO env value
])
def test_scheduler_enabled_reads_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('ENABLE_SCHEDULER', raising=False)
    else:
        monkeypatch.setenv('ENABLE_SCHEDULER', value)
    assert cleanup._scheduler_enabled() is expected


def test_start_scheduler_is_noop_when_disabled(monkeypatch):
    """Disabled env → the scheduler never starts, yet is_scheduler_ok() stays
    True so the /health check does not flip to unhealthy."""
    monkeypatch.setenv('ENABLE_SCHEDULER', 'false')
    cleanup._scheduler_disabled = False  # reset any state from a prior test

    cleanup.start_scheduler()

    assert cleanup.scheduler.running is False
    assert cleanup._scheduler_disabled is True
    assert cleanup.is_scheduler_ok() is True
