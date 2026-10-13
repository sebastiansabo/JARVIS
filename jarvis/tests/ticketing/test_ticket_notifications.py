"""Ticketing notification gaps (cleanup batch):

1. Ticket creation now alerts IT staff (anyone with ticketing/ticket/manage),
   excluding the creator — previously it notified no one and IT had to poll.
2. A status change made by the creator no longer self-notifies them.

Plus a unit check of the PermissionRepository.get_user_ids_with_permission
resolver that powers #1.

DB-free: views are called undecorated (bypassing @login_required) and the
repos / resolver / current_user are stubbed.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

import pytest
from flask import Flask

import ticketing.routes.tickets as routes


def _view(fn):
    return getattr(fn, '__wrapped__', fn)


def _actor(monkeypatch, uid):
    monkeypatch.setattr(routes, 'current_user', MagicMock(id=uid))


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


# ── Gap 1: ticket creation alerts IT staff ──────────────────────────────

def test_create_ticket_notifies_it_staff_excluding_creator(app, monkeypatch):
    monkeypatch.setattr(routes._ticket_repo, 'create', MagicMock(return_value={'id': 42}))
    notify = MagicMock()
    monkeypatch.setattr(routes, 'notify_users', notify)
    perm = MagicMock()
    perm.return_value.get_user_ids_with_permission.return_value = [7, 9, 3]  # 3 == creator
    monkeypatch.setattr('core.roles.repositories.PermissionRepository', perm)
    _actor(monkeypatch, 3)

    with app.test_request_context('/api/tickets', method='POST',
                                  json={'title': 'Printer broken', 'priority': 'high',
                                        'category': 'hardware'}):
        resp = _view(routes.api_create_ticket)()

    assert resp.get_json()['success'] is True
    notify.assert_called_once()
    recipients = notify.call_args.args[0]
    assert set(recipients) == {7, 9}  # creator (3) excluded
    assert notify.call_args.kwargs.get('category') == 'ticketing'
    assert '/app/ticketing/42' == notify.call_args.kwargs.get('link')


def test_create_ticket_no_it_staff_still_creates_and_skips_notify(app, monkeypatch):
    monkeypatch.setattr(routes._ticket_repo, 'create', MagicMock(return_value={'id': 42}))
    notify = MagicMock()
    monkeypatch.setattr(routes, 'notify_users', notify)
    perm = MagicMock()
    perm.return_value.get_user_ids_with_permission.return_value = [3]  # only the creator
    monkeypatch.setattr('core.roles.repositories.PermissionRepository', perm)
    _actor(monkeypatch, 3)

    with app.test_request_context('/api/tickets', method='POST',
                                  json={'title': 'X', 'priority': 'low', 'category': 'other'}):
        resp = _view(routes.api_create_ticket)()

    assert resp.get_json()['success'] is True
    notify.assert_not_called()


# ── Gap 2: status-change self-notify guard ──────────────────────────────

def _status_change(app, monkeypatch, *, creator_id, actor_id):
    ticket = {'id': 5, 'created_by': creator_id, 'assigned_to': None,
              'status': 'open', 'title': 'X'}
    monkeypatch.setattr(routes._ticket_repo, 'get_by_id', MagicMock(return_value=ticket))
    monkeypatch.setattr(routes._ticket_repo, 'update', MagicMock())
    monkeypatch.setattr(routes, '_is_it_staff', lambda: True)
    notify = MagicMock()
    monkeypatch.setattr(routes, 'notify_user', notify)
    _actor(monkeypatch, actor_id)
    with app.test_request_context('/api/tickets/5', method='PUT', json={'status': 'resolved'}):
        _view(routes.api_update_ticket)(5)
    return notify


def test_status_change_by_creator_does_not_self_notify(app, monkeypatch):
    notify = _status_change(app, monkeypatch, creator_id=3, actor_id=3)
    notify.assert_not_called()


def test_status_change_by_other_notifies_creator(app, monkeypatch):
    notify = _status_change(app, monkeypatch, creator_id=3, actor_id=7)
    notify.assert_called_once()
    assert notify.call_args.args[0] == 3  # the creator


# ── resolver powering Gap 1 ──────────────────────────────────────────────

def test_get_user_ids_with_permission_maps_rows(monkeypatch):
    from core.roles.repositories.permission_repository import PermissionRepository
    repo = PermissionRepository()
    monkeypatch.setattr(repo, 'query_all', lambda sql, params: [{'id': 7}, {'id': 9}])
    assert repo.get_user_ids_with_permission('ticketing', 'ticket', 'manage') == [7, 9]
