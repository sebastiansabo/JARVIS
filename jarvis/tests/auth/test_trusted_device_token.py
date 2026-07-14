"""Tests for stateless trusted-device token helpers used by mobile 2FA.

These helpers mirror the existing create_trusted_device_cookie /
validate_trusted_device_cookie methods (URLSafeTimedSerializer-based), but
bind the token to an explicit, stable device_id supplied by the mobile app
instead of a UA+IP derived device_hash.
"""
import pytest
from itsdangerous import SignatureExpired

from core.auth.services.auth_service import AuthService

SECRET = "test-secret-key"


@pytest.fixture
def auth_service():
    return AuthService()


def test_valid_token_validates_true(auth_service):
    token = auth_service.create_trusted_device_token(1, "dev-abc", SECRET)
    assert auth_service.validate_trusted_device_token(token, 1, "dev-abc", SECRET) is True


def test_different_device_id_fails(auth_service):
    token = auth_service.create_trusted_device_token(1, "dev-abc", SECRET)
    assert auth_service.validate_trusted_device_token(token, 1, "dev-xyz", SECRET) is False


def test_different_user_id_fails(auth_service):
    token = auth_service.create_trusted_device_token(1, "dev-abc", SECRET)
    assert auth_service.validate_trusted_device_token(token, 2, "dev-abc", SECRET) is False


def test_tampered_token_fails(auth_service):
    token = auth_service.create_trusted_device_token(1, "dev-abc", SECRET)
    # Flip a character somewhere in the middle of the token to break the signature.
    mid = len(token) // 2
    flipped_char = "a" if token[mid] != "a" else "b"
    tampered = token[:mid] + flipped_char + token[mid + 1:]
    assert auth_service.validate_trusted_device_token(tampered, 1, "dev-abc", SECRET) is False


def test_expired_token_fails(auth_service, monkeypatch):
    # itsdangerous hardcodes max_age validation inside loads(); the cleanest way to
    # simulate expiry without waiting 30 days is to monkeypatch the serializer's
    # loads() to raise SignatureExpired, exactly as it would for a stale token.
    token = auth_service.create_trusted_device_token(1, "dev-abc", SECRET)

    from itsdangerous import URLSafeTimedSerializer

    def fake_loads(self, *args, **kwargs):
        raise SignatureExpired("token expired")

    monkeypatch.setattr(URLSafeTimedSerializer, "loads", fake_loads)
    assert auth_service.validate_trusted_device_token(token, 1, "dev-abc", SECRET) is False


def test_empty_or_none_token_fails(auth_service):
    assert auth_service.validate_trusted_device_token("", 1, "dev-abc", SECRET) is False
    assert auth_service.validate_trusted_device_token(None, 1, "dev-abc", SECRET) is False
