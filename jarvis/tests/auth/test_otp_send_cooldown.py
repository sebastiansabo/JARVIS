"""Service-level tests for the OTP send cooldown (dedup).

generate_and_send_otp() must reuse a still-valid, unused code sent within
OTP_RESEND_COOLDOWN_SECONDS instead of creating a new one and emailing again.
This collapses rapid re-login bursts (one email per attempt) across both the
web and mobile login paths. Explicit "resend" (resend_otp) is unaffected.
"""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

from core.auth.services.auth_service import AuthService

SECRET = 'test-secret'


class FakeRepo:
    """Minimal stand-in for UserRepository's OTP methods."""

    def __init__(self, active_otp=None):
        self._active_otp = active_otp
        self.created = []  # list of (user_id, code_hash, expires_at)
        self.invalidated = []  # otp_ids passed to mark_otp_used
        self._next_id = 100

    def get_active_otp_for_user(self, user_id):
        return self._active_otp

    def create_otp(self, user_id, code, expires_at):
        self._next_id += 1
        self.created.append((user_id, code, expires_at))
        return self._next_id

    def mark_otp_used(self, otp_id):
        self.invalidated.append(otp_id)
        return True


@pytest.fixture
def svc(monkeypatch):
    s = AuthService()
    s.user_repo = FakeRepo()
    # Count emails without touching SMTP.
    sent = []
    monkeypatch.setattr(
        s, '_send_otp_email',
        lambda name, email, code: (sent.append((email, code)) or (True, None)),
    )
    s._sent = sent
    return s


def _otp_row(otp_id=55, age_seconds=10):
    created = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        'id': otp_id,
        'user_id': 1,
        'code': 'hashed',
        'expires_at': datetime.now(timezone.utc) + timedelta(minutes=4),
        'attempts': 0,
        'send_count': 1,
        'used_at': None,
        'created_at': created,
    }


def test_no_active_otp_creates_and_sends(svc):
    otp_id, ok, err = svc.generate_and_send_otp(1, 'u@x.ro', 'U', SECRET)
    assert ok and err is None
    assert len(svc.user_repo.created) == 1
    assert len(svc._sent) == 1
    assert otp_id == 101  # new id returned by FakeRepo.create_otp


def test_recent_active_otp_is_reused_no_email(svc):
    svc.user_repo._active_otp = _otp_row(otp_id=55, age_seconds=20)
    otp_id, ok, err = svc.generate_and_send_otp(1, 'u@x.ro', 'U', SECRET)
    assert ok and err is None
    assert otp_id == 55            # reuse existing challenge
    assert svc.user_repo.created == []  # no new row
    assert svc._sent == []              # no email


def test_active_otp_past_cooldown_sends_new(svc):
    svc.user_repo._active_otp = _otp_row(
        otp_id=55, age_seconds=AuthService.OTP_RESEND_COOLDOWN_SECONDS + 10)
    otp_id, ok, err = svc.generate_and_send_otp(1, 'u@x.ro', 'U', SECRET)
    assert ok and err is None
    assert len(svc.user_repo.created) == 1  # fresh code
    assert len(svc._sent) == 1              # fresh email
    assert otp_id != 55


def test_failed_send_invalidates_otp_so_cooldown_wont_reuse(svc, monkeypatch):
    # First send fails -> the freshly created code must be invalidated so a
    # later login attempt within the cooldown isn't falsely suppressed.
    monkeypatch.setattr(
        svc, '_send_otp_email',
        lambda name, email, code: (False, 'SMTP down'),
    )
    otp_id, ok, err = svc.generate_and_send_otp(1, 'u@x.ro', 'U', SECRET)
    assert ok is False and err == 'SMTP down'
    assert len(svc.user_repo.created) == 1
    assert svc.user_repo.invalidated == [otp_id]  # row invalidated on failure


def test_cooldown_boundary_tz_naive_created_at(svc):
    # DB may return a tz-naive created_at; it must be treated as UTC.
    row = _otp_row(otp_id=77, age_seconds=5)
    row['created_at'] = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None)
    svc.user_repo._active_otp = row
    otp_id, ok, err = svc.generate_and_send_otp(1, 'u@x.ro', 'U', SECRET)
    assert otp_id == 77
    assert svc._sent == []
