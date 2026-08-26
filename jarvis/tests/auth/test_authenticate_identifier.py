"""UserRepository.authenticate_identifier routes to email vs phone lookup
and enforces the same active + password checks as authenticate()."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from werkzeug.security import generate_password_hash
from core.auth.repositories.user_repository import UserRepository


@pytest.fixture
def repo():
    return UserRepository()


def _user(**over):
    d = {'id': 1, 'email': 'v@example.com', 'is_active': True,
         'password_hash': generate_password_hash('secretpass1'),
         'role_name': 'Viewer'}
    d.update(over)
    return d


def test_email_identifier_uses_email_lookup(repo, monkeypatch):
    called = {}

    def fake_get_by_email(e):
        called['email'] = e
        return _user()

    monkeypatch.setattr(repo, 'get_by_email', fake_get_by_email)
    monkeypatch.setattr(repo, 'get_by_phone', lambda p: pytest.fail('should not call phone'))
    out = repo.authenticate_identifier('v@example.com', 'secretpass1')
    assert out['id'] == 1
    assert called['email'] == 'v@example.com'


def test_phone_identifier_uses_phone_lookup(repo, monkeypatch):
    called = {}

    def fake_get_by_phone(p):
        called['phone'] = p
        return _user()

    monkeypatch.setattr(repo, 'get_by_phone', fake_get_by_phone)
    monkeypatch.setattr(repo, 'get_by_email', lambda e: pytest.fail('should not call email'))
    out = repo.authenticate_identifier('0723574040', 'secretpass1')
    assert out['id'] == 1
    assert called['phone'] == '0723574040'


def test_wrong_password_returns_none(repo, monkeypatch):
    monkeypatch.setattr(repo, 'get_by_phone', lambda p: _user())
    assert repo.authenticate_identifier('0723574040', 'WRONG') is None


def test_inactive_user_returns_none(repo, monkeypatch):
    monkeypatch.setattr(repo, 'get_by_email', lambda e: _user(is_active=False))
    assert repo.authenticate_identifier('v@example.com', 'secretpass1') is None
