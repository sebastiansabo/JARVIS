"""Tests for the web trusted-device cookie (30-day 'remember this device').

The cookie must persist regardless of client IP / network changes: it binds to
a signed uid + random nonce, NOT a UA|IP fingerprint. The old fingerprint broke
behind the DigitalOcean proxy (request.remote_addr = proxy, not client) and
forced repeat OTP challenges. Signature + expiry + uid match is the whole check.
"""
import pytest

from core.auth.services.auth_service import AuthService

SECRET = "test-secret-key"


@pytest.fixture
def svc():
    return AuthService()


def test_roundtrip_validates(svc):
    cookie = svc.create_trusted_device_cookie(1, SECRET)
    assert svc.validate_trusted_device_cookie(cookie, 1, SECRET) is True


def test_persists_with_no_ip_or_ua_params(svc):
    # The whole point of the fix: neither create nor validate takes UA/IP, so a
    # network/VPN/IP change cannot invalidate a still-signed, unexpired cookie.
    cookie = svc.create_trusted_device_cookie(42, SECRET)
    assert svc.validate_trusted_device_cookie(cookie, 42, SECRET) is True


def test_wrong_user_rejected(svc):
    cookie = svc.create_trusted_device_cookie(1, SECRET)
    assert svc.validate_trusted_device_cookie(cookie, 2, SECRET) is False


def test_tampered_cookie_rejected(svc):
    cookie = svc.create_trusted_device_cookie(1, SECRET)
    assert svc.validate_trusted_device_cookie(cookie + "x", 1, SECRET) is False


def test_wrong_secret_rejected(svc):
    cookie = svc.create_trusted_device_cookie(1, SECRET)
    assert svc.validate_trusted_device_cookie(cookie, 1, "other-secret") is False


def test_empty_cookie_rejected(svc):
    assert svc.validate_trusted_device_cookie("", 1, SECRET) is False
    assert svc.validate_trusted_device_cookie(None, 1, SECRET) is False


def test_each_cookie_has_unique_nonce(svc):
    # Two cookies for the same user differ (random nonce) — avoids identical
    # tokens and supports future per-device revocation.
    assert svc.create_trusted_device_cookie(1, SECRET) != svc.create_trusted_device_cookie(1, SECRET)


def test_legacy_ua_ip_cookie_still_validates(svc):
    # Migration guarantee: cookies minted by the OLD code carried {uid, dh}.
    # After the fix, validate ignores dh and must still accept them, so nobody
    # is force-logged-out on deploy.
    from itsdangerous import URLSafeTimedSerializer
    legacy = URLSafeTimedSerializer(SECRET).dumps({'uid': 7, 'dh': 'deadbeef' * 8})
    assert svc.validate_trusted_device_cookie(legacy, 7, SECRET) is True
    assert svc.validate_trusted_device_cookie(legacy, 8, SECRET) is False  # uid still enforced


def test_cookie_without_uid_rejected(svc):
    from itsdangerous import URLSafeTimedSerializer
    bad = URLSafeTimedSerializer(SECRET).dumps({'nonce': 'x'})
    assert svc.validate_trusted_device_cookie(bad, 1, SECRET) is False
