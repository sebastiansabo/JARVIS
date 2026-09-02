"""Final-review FIX 1 (CRITICAL): the generic `POST /api/notification-settings`
endpoint (`@login_required` only, no key whitelist) must never be able to
write the `ghost_visible_admin_ids` security control.

Before the fix, `api_save_notification_settings` forwarded the raw request
payload straight to `NotificationRepository.save_settings_bulk`, so any
authenticated user could `POST {"ghost_visible_admin_ids": "<own id>"}` and
grant themselves ghost-visibility. The fix strips that one key from the
incoming dict before it reaches `save_settings_bulk`; all other keys must
keep working exactly as before. Internal seeding (`save_notification_setting`
/ `save_setting` called directly, not via this route) is untouched.

DB-free: bypasses `@login_required` the same way tests/auth/test_ghost_endpoint.py
does (call the undecorated view via `__wrapped__`) and monkeypatches
`_notif_repo.save_settings_bulk` to capture exactly what was forwarded.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

import pytest
from flask import Flask

import core.notifications.routes as routes


def _view(view_func):
    """Return the undecorated view (bypass @login_required)."""
    return getattr(view_func, '__wrapped__', view_func)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


def test_ghost_admin_ids_key_stripped_before_save(app, monkeypatch):
    """Malicious/naive payload containing the ghost key: the ghost key must
    never reach save_settings_bulk, but a benign key in the same payload
    still gets through untouched."""
    save_mock = MagicMock(return_value=True)
    monkeypatch.setattr(routes._notif_repo, 'save_settings_bulk', save_mock)

    payload = {
        'ghost_visible_admin_ids': '2',
        'pontaje_digest_enabled': 'true',
    }
    with app.test_request_context('/api/notification-settings', method='POST', json=payload):
        resp = _view(routes.api_save_notification_settings)()

    assert resp.get_json() == {'success': True}
    save_mock.assert_called_once()
    forwarded = save_mock.call_args[0][0]
    assert 'ghost_visible_admin_ids' not in forwarded
    assert forwarded == {'pontaje_digest_enabled': 'true'}


def test_payload_without_ghost_key_is_unaffected(app, monkeypatch):
    """No ghost key in the payload at all -> nothing changes, everything
    forwards as-is (regression guard: the strip must be a no-op otherwise)."""
    save_mock = MagicMock(return_value=True)
    monkeypatch.setattr(routes._notif_repo, 'save_settings_bulk', save_mock)

    payload = {'pontaje_digest_enabled': 'true', 'commit_digest_daily_enabled': 'false'}
    with app.test_request_context('/api/notification-settings', method='POST', json=payload):
        resp = _view(routes.api_save_notification_settings)()

    assert resp.get_json() == {'success': True}
    save_mock.assert_called_once_with(payload)


def test_ghost_admin_ids_alone_in_payload_saves_nothing(app, monkeypatch):
    """Payload consisting ONLY of the ghost key: save_settings_bulk is still
    called (existing behavior for empty dict), but with an empty dict — the
    ghost value is silently dropped, not stored anywhere."""
    save_mock = MagicMock(return_value=True)
    monkeypatch.setattr(routes._notif_repo, 'save_settings_bulk', save_mock)

    payload = {'ghost_visible_admin_ids': '2,3,4'}
    with app.test_request_context('/api/notification-settings', method='POST', json=payload):
        resp = _view(routes.api_save_notification_settings)()

    assert resp.get_json() == {'success': True}
    save_mock.assert_called_once_with({})
