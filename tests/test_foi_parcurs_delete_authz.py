"""Authorization guard for the foi_parcurs contract hard-delete route.

Regression cover for the internal-session IDOR fix (JAR-1312): the session
list is group-wide (unscoped reads), so a non-admin must be able to delete
ONLY an internal driving-log session that belongs to their OWN company — never
a client Test Drive, nor a sibling company's internal session. Admins bypass.
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
    # Bypass the @login_required gate — authorization here is driven by the
    # patched current_user, not by an actual authenticated session.
    application.config['LOGIN_DISABLED'] = True
    return application


class _User:
    """Minimal current_user stand-in (real object, not MagicMock, so _is_admin's
    getattr(role_name) reads a plain string)."""
    def __init__(self, role_name, company_id):
        self.role_name = role_name
        self.company_id = company_id
        self.email = 'u@example.ro'


def _call_delete(app, *, contract, role_name, user_company):
    """Invoke api_delete_contract with patched deps.
    Returns (status_code, deleted?) where deleted? is whether the row was removed."""
    from foi_parcurs.routes import contracts
    repo = MagicMock()
    repo.get_contract_by_id.return_value = contract
    with app.test_request_context():
        with patch.object(contracts, '_fp_repo', repo), \
             patch.object(contracts, 'current_user', _User(role_name, user_company)):
            resp = contracts.api_delete_contract(1)
    status = resp[1] if isinstance(resp, tuple) else 200
    return status, repo.delete_contract.called


INTERNAL_C5 = {'id': 1, 'is_internal': True, 'company_id': 5}
INTERNAL_C9 = {'id': 1, 'is_internal': True, 'company_id': 9}
CLIENT_TD_C5 = {'id': 1, 'is_internal': False, 'company_id': 5}


def test_non_admin_deletes_own_company_internal(app):
    status, deleted = _call_delete(app, contract=INTERNAL_C5, role_name='user', user_company=5)
    assert status == 200 and deleted


def test_non_admin_blocked_on_other_company_internal(app):
    status, deleted = _call_delete(app, contract=INTERNAL_C9, role_name='user', user_company=5)
    assert status == 403 and not deleted


def test_non_admin_blocked_on_client_test_drive(app):
    status, deleted = _call_delete(app, contract=CLIENT_TD_C5, role_name='user', user_company=5)
    assert status == 403 and not deleted


def test_non_admin_without_company_blocked(app):
    status, deleted = _call_delete(app, contract=INTERNAL_C5, role_name='user', user_company=None)
    assert status == 403 and not deleted


def test_admin_deletes_any_registration(app):
    status, deleted = _call_delete(app, contract=CLIENT_TD_C5, role_name='admin', user_company=99)
    assert status == 200 and deleted


def test_missing_contract_returns_404(app):
    status, deleted = _call_delete(app, contract=None, role_name='user', user_company=5)
    assert status == 404 and not deleted
