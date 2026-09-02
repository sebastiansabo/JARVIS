"""Deleting a client's contact person is blocked while that contact is the
driver on an active (PLANNED/FILLED) session — Piece 3 of the Corectează work.

A contact who is nobody's active driver deletes normally; a cross-client
contact_id still 404s (existing anti-IDOR ownership check).
"""
import sys, os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


CONTACT = {'id': 10, 'client_id': 21382, 'full_name': 'Calin Gonta'}


def _call_delete(app, *, existing=CONTACT, active_count=0):
    from crm.routes import clients
    repo = MagicMock()
    repo.get.return_value = existing
    repo.active_session_count.return_value = active_count
    with app.test_request_context():
        with patch.object(clients, '_contact_repo', repo):
            resp = clients.api_delete_client_contact(21382, 10)
    status = resp[1] if isinstance(resp, tuple) else 200
    return status, repo.delete.called


def test_deletes_when_not_an_active_driver(app):
    status, deleted = _call_delete(app, active_count=0)
    assert status == 200 and deleted


def test_blocked_when_driver_on_active_session(app):
    status, deleted = _call_delete(app, active_count=1)
    assert status == 409 and not deleted


def test_missing_contact_returns_404(app):
    status, deleted = _call_delete(app, existing=None)
    assert status == 404 and not deleted


def test_cross_client_contact_returns_404(app):
    status, deleted = _call_delete(app, existing={'id': 10, 'client_id': 999})
    assert status == 404 and not deleted
