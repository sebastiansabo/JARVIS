"""Regression: Field-Sales 'visit planned' in-app + push must fire even when
SMTP is unconfigured.

Before the fix, notify_visit_planned early-returned if SMTP wasn't configured,
silently dropping the manager's in-app/push notification along with the email.
Now the email arm is gated on SMTP while the in-app/push arm always fires.

DB-free: the module's collaborators are stubbed.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

import field_sales.notifications as fsn


def _patch(monkeypatch, smtp_ok):
    monkeypatch.setattr(fsn, 'is_smtp_configured', lambda: smtp_ok)
    monkeypatch.setattr(fsn, '_get_manager_emails_for_user', lambda uid: (['mgr@x.ro'], [11]))
    monkeypatch.setattr(fsn, '_get_user_name', lambda uid: 'KAM Ana')
    send = MagicMock()
    notify = MagicMock()
    monkeypatch.setattr(fsn, 'send_email', send)
    monkeypatch.setattr(fsn, 'notify_users', notify)
    return send, notify


_VISIT = {'kam_id': 1, 'client_name': 'ACME', 'planned_date': '2026-10-20', 'id': 99}


def test_inapp_fires_when_smtp_unconfigured(monkeypatch):
    send, notify = _patch(monkeypatch, smtp_ok=False)
    fsn.notify_visit_planned(_VISIT)
    send.assert_not_called()       # email suppressed when SMTP is down
    notify.assert_called_once()    # ...but the in-app/push STILL fires (the fix)
    assert notify.call_args.args[0] == [11]
    assert notify.call_args.kwargs.get('category') == 'field_sales'


def test_both_fire_when_smtp_configured(monkeypatch):
    send, notify = _patch(monkeypatch, smtp_ok=True)
    fsn.notify_visit_planned(_VISIT)
    send.assert_called_once()
    notify.assert_called_once()
