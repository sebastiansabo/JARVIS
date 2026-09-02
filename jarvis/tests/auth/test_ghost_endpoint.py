"""Tests for Task 12: admin-gated endpoint to toggle a user's ghost mode.

The existing auth test suite (tests/auth/*.py) has no shared
`client_logged_in_regular` / `client_logged_in_ghost_admin` fixtures — only
ad-hoc, per-file local `app`/Flask-test-client fixtures with session-based
login (see test_carpark_finance_flag.py). Per task-12 brief's documented
fallback, these tests instead call the view functions directly:

  - `@login_required`'s wrapper is bypassed via `.__wrapped__` (flask_login
    uses functools.wraps, so the raw view is reachable), since the wrapper
    checks flask_login's own real `current_user` LocalProxy, which needs a
    fully wired LoginManager/session to satisfy outside of a real request.
  - `current_user` is patched directly on the `core.auth.routes` module
    (the view functions read it from their own module globals at call
    time, so this affects them exactly like a real login would).
  - `can_see_ghosts` / `invalidate_ghost_cache` are patched on
    `core.organization.ghost` — the views import them lazily
    (`from core.organization.ghost import ...`) *inside* the function body,
    so the lazy import picks up whatever is bound on the module at call
    time, same as a real login-based test would exercise.
  - A genuine `app.test_request_context(...)` is still used so `request`
    (also a Flask context-local) works for `request.get_json()`.

This exercises the real, undecorated production route bodies end-to-end
(permission guard, repo call, cache invalidation, response shape) without
requiring a real DB (root conftest.py already mocks psycopg2 for the whole
suite) or inventing fixtures the repo doesn't have.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

import core.auth.routes as routes
from core.auth.repositories.user_repository import UserRepository
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


# ---- GET /api/users/can-manage-ghosts ------------------------------------

def test_can_manage_ghosts_true_for_admin(app, monkeypatch):
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=99))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: uid == 99)

    with app.test_request_context('/api/users/can-manage-ghosts'):
        resp = _view(routes.api_can_manage_ghosts)()

    assert resp.get_json() == {'can_manage_ghosts': True}


def test_can_manage_ghosts_false_for_regular_user(app, monkeypatch):
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=2))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: False)

    with app.test_request_context('/api/users/can-manage-ghosts'):
        resp = _view(routes.api_can_manage_ghosts)()

    assert resp.get_json() == {'can_manage_ghosts': False}


# ---- PUT /api/users/<id>/ghost -------------------------------------------

def test_put_ghost_forbidden_for_non_admin(app, monkeypatch):
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=2))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: False)
    set_ghost_mock = MagicMock()
    monkeypatch.setattr(routes._user_repo, 'set_ghost', set_ghost_mock)
    invalidate_mock = MagicMock()
    monkeypatch.setattr(ghost, 'invalidate_ghost_cache', invalidate_mock)

    with app.test_request_context('/api/users/5/ghost', method='PUT', json={'is_ghost': True}):
        result = _view(routes.api_set_user_ghost)(5)

    resp, status = result
    assert status == 403
    set_ghost_mock.assert_not_called()
    invalidate_mock.assert_not_called()


def test_put_ghost_allowed_for_admin(app, monkeypatch):
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=99))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: True)
    set_ghost_mock = MagicMock(return_value=True)
    monkeypatch.setattr(routes._user_repo, 'set_ghost', set_ghost_mock)
    invalidate_mock = MagicMock()
    monkeypatch.setattr(ghost, 'invalidate_ghost_cache', invalidate_mock)

    with app.test_request_context('/api/users/5/ghost', method='PUT', json={'is_ghost': True}):
        resp = _view(routes.api_set_user_ghost)(5)

    assert resp.get_json() == {'success': True, 'is_ghost': True}
    set_ghost_mock.assert_called_once_with(5, True)
    invalidate_mock.assert_called_once()


def test_put_ghost_false_payload_round_trips(app, monkeypatch):
    """`is_ghost: false` must clear the flag, not just be treated as absent."""
    monkeypatch.setattr(routes, 'current_user', SimpleNamespace(id=99))
    monkeypatch.setattr(ghost, 'can_see_ghosts', lambda uid: True)
    set_ghost_mock = MagicMock(return_value=True)
    monkeypatch.setattr(routes._user_repo, 'set_ghost', set_ghost_mock)
    monkeypatch.setattr(ghost, 'invalidate_ghost_cache', MagicMock())

    with app.test_request_context('/api/users/5/ghost', method='PUT', json={'is_ghost': False}):
        resp = _view(routes.api_set_user_ghost)(5)

    assert resp.get_json() == {'success': True, 'is_ghost': False}
    set_ghost_mock.assert_called_once_with(5, False)


# ---- UserRepository.set_ghost ---------------------------------------------

def test_set_ghost_issues_expected_update(monkeypatch):
    repo = UserRepository()
    captured = {}

    def fake_execute(self, sql, params=None, returning=False):
        captured['sql'] = sql
        captured['params'] = params
        return 1

    monkeypatch.setattr(UserRepository, 'execute', fake_execute)

    result = repo.set_ghost(5, True)

    assert result is True
    assert 'UPDATE users' in captured['sql']
    assert 'is_ghost' in captured['sql']
    assert 'WHERE id' in captured['sql']
    assert captured['params'] == (True, 5)


def test_set_ghost_coerces_truthy_value_to_bool(monkeypatch):
    repo = UserRepository()
    captured = {}

    def fake_execute(self, sql, params=None, returning=False):
        captured['params'] = params
        return 1

    monkeypatch.setattr(UserRepository, 'execute', fake_execute)

    repo.set_ghost(5, 1)

    assert captured['params'] == (True, 5)
