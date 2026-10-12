"""Regression: `notify_with_push` must fire exactly ONE FCM push.

Before the fix, `notify_with_push` called `notify_users` (which already sent a
push with no data payload) and THEN sent a second push with the data payload —
every call produced two pushes to the same devices. The fix threads a
`send_push=False` flag into `notify_users` so the inner push is suppressed and
only the data-carrying push from `notify_with_push` goes out.

DB-free: `_repo.create_bulk` is mocked, and the lazily-imported
`send_push_to_users` is patched on the push_service module.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

import core.notifications.notify as notify
import core.notifications.push_service as push_service


def _patch(monkeypatch):
    monkeypatch.setattr(notify._repo, 'create_bulk', MagicMock(return_value=[]))
    push_mock = MagicMock()
    # notify.py imports send_push_to_users lazily from this module at call time
    monkeypatch.setattr(push_service, 'send_push_to_users', push_mock)
    return push_mock


def test_notify_with_push_sends_single_push_carrying_data(monkeypatch):
    push_mock = _patch(monkeypatch)

    notify.notify_with_push(
        [1, 2, 3], 'Title', message='Body',
        push_data={'channel_id': '5'}, category='system',
    )

    assert push_mock.call_count == 1, 'notify_with_push must send exactly one push'
    _, kwargs = push_mock.call_args
    assert kwargs.get('data') == {'channel_id': '5'}, 'the single push must carry the data payload'


def test_notify_users_still_pushes_by_default(monkeypatch):
    push_mock = _patch(monkeypatch)
    notify.notify_users([1], 'T', message='B')
    assert push_mock.call_count == 1


def test_notify_users_suppresses_push_when_flag_false(monkeypatch):
    push_mock = _patch(monkeypatch)
    notify.notify_users([1], 'T', message='B', send_push=False)
    assert push_mock.call_count == 0
