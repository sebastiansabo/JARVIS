"""Final-review FIX 2 (IMPORTANT): `GET /api/users` must not leak `is_ghost`
to callers who aren't ghost-visibility super-admins.

`api_get_users` returns `_user_repo.get_all()` (`SELECT u.*`), which now
includes `is_ghost` for every row since the ghost-users feature landed —
leaking which accounts are flagged to any logged-in user (spec §8: only
super-admins on the `ghost_visible_admin_ids` allowlist may see it). The fix
strips the `is_ghost` key from each row when `can_see_ghosts(current_user.id)`
is False.

DB-free — bypasses `@login_required` the same way tests/auth/test_ghost_endpoint.py
does (call the undecorated view via `__wrapped__`, patch `current_user` on the
routes module) and monkeypatches `_user_repo.get_all` / `ghost.can_see_ghosts`.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

import core.auth.routes as routes
from core.organization import ghost


def _view(view_func):
    """Return the undecorated view (bypass @login_required)."""
    return getattr(view_func, '__wrapped__', view_func)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture(autouse=True)
def _clear_ghost_cache():
    ghost.invalidate_ghost_cache()
    yield
    ghost.invalidate_ghost_cache()


_ROWS = [
    {'id': 1, 'name': 'Regular User', 'email': 'reg@example.com', 'is_ghost': False},
    {'id': 2, 'name': 'Boss', 'email': 'boss@example.com', 'is_ghost': True},
]


def test_is_ghost_redacted_for_non_admin(app, monkeypatch):
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=5))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: False)
    monkeypatch.setattr(routes._user_repo, 'get_all', MagicMock(return_value=[dict(r) for r in _ROWS]))

    with app.test_request_context('/api/users'):
        resp = _view(routes.api_get_users)()

    users = resp.get_json()
    assert len(users) == 2
    for u in users:
        assert 'is_ghost' not in u


def test_is_ghost_present_for_ghost_admin(app, monkeypatch):
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=99))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: uid == 99)
    monkeypatch.setattr(routes._user_repo, 'get_all', MagicMock(return_value=[dict(r) for r in _ROWS]))

    with app.test_request_context('/api/users'):
        resp = _view(routes.api_get_users)()

    users = resp.get_json()
    assert len(users) == 2
    ghost_row = next(u for u in users if u['id'] == 2)
    assert ghost_row['is_ghost'] is True
