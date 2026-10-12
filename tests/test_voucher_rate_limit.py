"""Tests for voucher redeem/lookup rate limiting (brute-force / enumeration).

The code-based endpoints throttle FAILED attempts by IP, by authenticated user
and per voucher code. We verify the guard (`_check_redeem_rate_limit`) blocks /
allows correctly, fails OPEN on error, records attempts upper-cased, and that
the repository builds the expected windowed COUNT. No real DB is used — the
global conftest mocks psycopg2, and we patch the repo / current_user.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import pytest

import accounting.vouchers.routes._shared as shared
from accounting.vouchers.repositories.attempt_repository import VoucherAttemptRepository


class _FakeRepo:
    """Stand-in for VoucherAttemptRepository with configurable counts."""

    def __init__(self, counts=None, raise_on_count=False):
        self.counts = counts or {}
        self.raise_on_count = raise_on_count
        self.recorded = []

    def count_recent(self, *, ip=None, user_id=None, voucher_code=None,
                     window_seconds=600, only_failed=True):
        if self.raise_on_count:
            raise RuntimeError('db down')
        if ip is not None:
            return self.counts.get('ip', 0)
        if user_id is not None:
            return self.counts.get('user', 0)
        if voucher_code is not None:
            return self.counts.get('code', 0)
        return 0

    def record(self, ip, user_id, voucher_code, outcome='fail'):
        self.recorded.append((ip, user_id, voucher_code, outcome))


class _AuthUser:
    is_authenticated = True
    id = 5


# ── App + request-context fixtures ───────────────────────────────────────────

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
    return application


@pytest.fixture
def ctx(app):
    """Anonymous request context with a known client IP."""
    with app.test_request_context('/api/vouchers/lookup/ABC',
                                  headers={'X-Forwarded-For': '9.9.9.9'}):
        yield


# ── Guard behaviour ──────────────────────────────────────────────────────────

def test_allows_when_under_threshold(ctx, monkeypatch):
    monkeypatch.setattr(shared, '_attempt_repo', _FakeRepo(counts={'ip': 0, 'code': 0}))
    assert shared._check_redeem_rate_limit('ABC') is None


def test_blocks_when_ip_over_threshold(ctx, monkeypatch):
    monkeypatch.setattr(shared, '_attempt_repo', _FakeRepo(counts={'ip': shared._RL_IP_MAX}))
    resp = shared._check_redeem_rate_limit('ABC')
    assert resp is not None
    assert resp.status_code == 429
    assert resp.headers.get('Retry-After') == str(shared._RL_IP_WINDOW)


def test_blocks_when_code_over_threshold(ctx, monkeypatch):
    # IP under limit, but this specific code has too many failures.
    monkeypatch.setattr(shared, '_attempt_repo',
                        _FakeRepo(counts={'ip': 0, 'code': shared._RL_CODE_MAX}))
    resp = shared._check_redeem_rate_limit('ABC')
    assert resp is not None
    assert resp.status_code == 429
    assert resp.headers.get('Retry-After') == str(shared._RL_CODE_WINDOW)


def test_blocks_when_user_over_threshold(ctx, monkeypatch):
    monkeypatch.setattr(shared, 'current_user', _AuthUser())
    monkeypatch.setattr(shared, '_attempt_repo',
                        _FakeRepo(counts={'ip': 0, 'user': shared._RL_USER_MAX, 'code': 0}))
    resp = shared._check_redeem_rate_limit('ABC')
    assert resp is not None
    assert resp.status_code == 429
    assert resp.headers.get('Retry-After') == str(shared._RL_USER_WINDOW)


def test_authenticated_caller_not_blocked_by_shared_ip(ctx, monkeypatch):
    # A flooded shared office IP must not lock out an authenticated user who is
    # under their own per-user budget — per-IP is the anonymous backstop only.
    monkeypatch.setattr(shared, 'current_user', _AuthUser())
    monkeypatch.setattr(shared, '_attempt_repo',
                        _FakeRepo(counts={'ip': 9999, 'user': 0, 'code': 0}))
    assert shared._check_redeem_rate_limit('ABC') is None


def test_fails_open_on_repo_error(ctx, monkeypatch):
    monkeypatch.setattr(shared, '_attempt_repo', _FakeRepo(raise_on_count=True))
    # A limiter glitch must never block a legitimate redemption.
    assert shared._check_redeem_rate_limit('ABC') is None


def test_record_attempt_uppercases_code(ctx, monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(shared, '_attempt_repo', fake)
    shared._record_redeem_attempt('abc12', 'fail')
    assert fake.recorded == [('9.9.9.9', None, 'ABC12', 'fail')]


def test_get_client_ip_uses_proxy_appended_last_hop(app):
    # The left-most hop is client-supplied/spoofable; trust only the right-most
    # entry appended by our own proxy.
    with app.test_request_context('/', headers={'X-Forwarded-For': 'spoofed-by-client, 2.2.2.2'}):
        assert shared._get_client_ip() == '2.2.2.2'


# ── Repository SQL shape (no DB) ─────────────────────────────────────────────

def test_count_recent_scopes_window_and_failed_only():
    repo = VoucherAttemptRepository()
    captured = {}

    def fake_query_one(sql, params):
        captured['sql'] = sql
        captured['params'] = params
        return {'cnt': 3}

    repo.query_one = fake_query_one
    n = repo.count_recent(ip='1.2.3.4', window_seconds=600)
    assert n == 3
    assert "created_at > NOW() - INTERVAL '%s seconds'" in captured['sql']
    assert 'ip = %s' in captured['sql']
    assert "outcome = 'fail'" in captured['sql']
    assert captured['params'] == (600, '1.2.3.4')


def test_count_recent_all_outcomes_when_not_only_failed():
    repo = VoucherAttemptRepository()
    captured = {}

    def fake_query_one(sql, params):
        captured['sql'] = sql
        return {'cnt': 0}

    repo.query_one = fake_query_one
    repo.count_recent(voucher_code='X', only_failed=False)
    assert "outcome = 'fail'" not in captured['sql']
    assert 'voucher_code = %s' in captured['sql']
