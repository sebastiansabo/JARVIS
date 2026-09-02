"""Mobile first-login bypass fix: the shared `_user_json` serializer must
carry `consents_complete` / `pending_consents_count` on EVERY auth response
body (token / verify-otp / refresh / current-user), because the mobile app
populates its auth store straight from those bodies. Without these keys the
store starts with `consents_complete === undefined`, the gate's `=== false`
check never fires, and the mandatory consent gate is bypassed for the whole
session.

This test drives `_user_json` directly with a monkeypatched
`ConsentService.get_status` so the exact values propagate through — no real DB
needed for the consent counts. `role_id=None` short-circuits the permission
map lookups inside `_user_json`, so no PermissionRepository DB call happens
either. (It lives under jarvis/tests/consents/ so it runs under the plan's
`pytest jarvis/tests/consents/` verify command.)
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import core.mobile.routes._shared as shared_mod
import core.consents.services.consent_service as consent_svc_mod


class _FakeUser:
    def __init__(self, uid=2):
        self.id = uid
        self.name = 'Test User'
        self.email = 'user@example.com'
        self.phone = None
        self.company = None
        self.department = None
        self.role_name = 'Employee'
        self.role_id = None  # skips the permission-map DB lookups in _user_json


def test_user_json_carries_consent_status(monkeypatch):
    monkeypatch.setattr(
        consent_svc_mod.ConsentService, 'get_status',
        lambda self, uid: {'complete': False, 'pending_count': 2},
    )
    result = shared_mod._user_json(_FakeUser())
    assert result['consents_complete'] is False
    assert result['pending_consents_count'] == 2


def test_user_json_consent_status_complete(monkeypatch):
    monkeypatch.setattr(
        consent_svc_mod.ConsentService, 'get_status',
        lambda self, uid: {'complete': True, 'pending_count': 0},
    )
    result = shared_mod._user_json(_FakeUser())
    assert result['consents_complete'] is True
    assert result['pending_consents_count'] == 0


def test_user_json_degrades_to_complete_when_status_raises(monkeypatch):
    """A consents-subsystem hiccup must not break login: the serializer fails
    open to the dormant default (complete=True) rather than throwing."""
    def _boom(self, uid):
        raise RuntimeError('db down')

    monkeypatch.setattr(consent_svc_mod.ConsentService, 'get_status', _boom)
    result = shared_mod._user_json(_FakeUser())
    assert result['consents_complete'] is True
    assert result['pending_consents_count'] == 0
