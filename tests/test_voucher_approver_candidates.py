"""Tests for the voucher approver-candidates query + route.

The "Send for Approval to" picker (web + mobile) must offer only *management*
of the issuer's company: responsables of any structure node (levels L1-L5) in
the company, plus the company's L0 responsables. We assert the SQL scopes to
the company and restricts to responsables (without a DB), and that the route is
auth-protected.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.vouchers.repositories.voucher_repository import VoucherRepository


def _capture(repo):
    """Replace query_all so we can inspect the SQL/params without a DB."""
    calls = {}

    def fake_query_all(sql, params):
        calls['sql'] = sql
        calls['params'] = params
        return []

    repo.query_all = fake_query_all
    return calls


def test_approver_candidates_scopes_to_company_and_management():
    repo = VoucherRepository()
    calls = _capture(repo)
    repo.get_approver_candidates(16)
    sql = calls['sql']
    # Level responsables (structure_node_members) + L0 (company_responsables),
    # both scoped to the issuer's company.
    assert "snm.role = 'responsable'" in sql
    assert 'sn.company_id = %s' in sql
    assert 'company_responsables' in sql
    assert 'cr.company_id = %s' in sql
    # Excludes inactive / ghost users.
    assert 'is_active' in sql
    assert 'is_ghost' in sql
    # company_id is bound once per subquery.
    assert calls['params'] == (16, 16)


# ── Route auth protection ────────────────────────────────────────────────────

import pytest


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
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


def test_approver_candidates_route_auth_protected(client):
    resp = client.get('/api/vouchers/approver-candidates')
    assert resp.status_code != 404, 'route should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
