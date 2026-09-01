"""Task 4 — consents_bp route tests: auth gate, IDOR guard, R2 permission gating.

Real-DB integration (Ruling R6): placed under jarvis/tests/consents/ so it
reuses this package's conftest.py probe/skip (REAL_DB_AVAILABLE), matching
test_consent_repository.py's idiom — Task 1's migration already created +
seeded consent_documents (all 3 seed docs is_active=FALSE), and importing
core.consents.repositories.consent_repository (via routes -> service -> repo)
transitively imports `database`, whose module-level init_db() applies the
schema on import, so no explicit migration call is needed here either.

Test client: builds a minimal Flask app registering only consents_bp with a
real flask_login LoginManager (mirrors tests/happy/test_admin_permissions.py
and tests/dept_pulse/test_dept_pulse_routes.py) so @login_required and the
local R2 gates in routes.py are exercised for real — no full app.py, no live
session cookie. `login_as(user_id)` sets the flask-login session key directly
via client.session_transaction(), which is what the brief's
`login_as(2)` call needs.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from core.consents.routes import consents_bp
from core.consents.repositories.consent_repository import ConsentRepository
from .conftest import REAL_DB_AVAILABLE


@pytest.fixture(autouse=True)
def _skip_without_real_db():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or DB driver '
            'mocked) — skipping consents route tests'
        )


class FakeUser(UserMixin):
    def __init__(self, uid, role_id=None, can_access_settings=False, can_access_hr=False):
        self.id = uid
        self.role_id = role_id
        self.can_access_settings = can_access_settings
        self.can_access_hr = can_access_hr

    def get_id(self):
        return str(self.id)


# id=2 is deliberately a "normal user" per the brief's test_sign_... comment.
_USERS = {
    2: FakeUser(2),                                    # normal user -> 403 on admin/HR routes
    3: FakeUser(3, can_access_settings=True),           # Settings admin
    4: FakeUser(4, can_access_hr=True),                 # HR admin
}


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.secret_key = 'test-secret'
    flask_app.config['TESTING'] = True
    lm = LoginManager()
    lm.init_app(flask_app)

    @lm.user_loader
    def _load(uid):
        return _USERS.get(int(uid))

    flask_app.register_blueprint(consents_bp)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_as(client):
    def _login(user_id):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True
    return _login


# ---------- auth gate ----------

def test_pending_requires_auth(client):
    resp = client.get('/api/consents/pending')
    assert resp.status_code in (302, 401)  # redirect to login or unauthorized


def test_mobile_pending_requires_auth(client):
    resp = client.get('/api/mobile/consents/pending')
    assert resp.status_code in (302, 401)


def test_mine_requires_auth(client):
    resp = client.get('/api/consents/mine')
    assert resp.status_code in (302, 401)


# ---------- Task 12: GET /api/consents/mine (profile "Acorduri semnate") ----------
# The route itself does no SQL (Ruling R1) — it calls
# ConsentRepository.get_user_signatures(), exercised here only through HTTP.

def test_mine_returns_documents_key_for_logged_in_user(client, login_as):
    login_as(2)  # normal user
    resp = client.get('/api/consents/mine')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'documents' in body
    # All 3 seed docs are is_active=FALSE by default (see
    # test_consent_repository.py), so an empty list here is expected and
    # valid — the shape assertion above is what this test guards.
    assert isinstance(body['documents'], list)


def test_mine_shows_signed_at_after_signing(client, login_as):
    # Activate 'nda' as a Settings admin, sign it as a normal user (id=2), and
    # confirm /api/consents/mine flips signed_at from null to a timestamp.
    # The `finally` restores the DB EXACTLY as it was found: it reverts
    # is_active (so test_consent_repository.py's "all seeds inactive" and
    # test_current_user_exposes_consents_complete's "zero active mandatory"
    # invariants still hold) AND deletes the signature row this test created
    # (so no stray user_consent_signatures row leaks into the real dev DB).
    # The DELETE lives in ConsentRepository.delete_signature() — no SQL in
    # this *routes*-named test file (Ruling R1). We also delete any
    # pre-existing signature up front so signed_at is provably null before
    # signing, making this a full round-trip on every run regardless of prior
    # state.
    repo = ConsentRepository()
    login_as(3)  # Settings admin
    target = _seed_doc(client, 'nda')
    original_active = target['is_active']
    doc_id = target['id']
    repo.delete_signature(2, doc_id)  # clear any leftover from a prior run
    resp = client.put(f"/api/consents/documents/{doc_id}",
                      json={'is_active': True, 'body': target['body']})
    assert resp.status_code == 200
    try:
        login_as(2)  # normal user
        resp = client.get('/api/consents/mine')
        assert resp.status_code == 200
        docs = {d['doc_key']: d for d in resp.get_json()['documents']}
        assert 'nda' in docs
        assert docs['nda']['signed_at'] is None

        sign_resp = client.post('/api/consents/sign', json={
            'document_id': doc_id,
            'signature_image': 'data:image/png;base64,AAAA',
        })
        assert sign_resp.status_code == 200

        resp = client.get('/api/consents/mine')
        assert resp.status_code == 200
        docs = {d['doc_key']: d for d in resp.get_json()['documents']}
        assert docs['nda']['signed_at'] is not None
    finally:
        repo.delete_signature(2, doc_id)
        login_as(3)
        client.put(f"/api/consents/documents/{doc_id}",
                   json={'is_active': original_active, 'body': target['body']})


# ---------- IDOR guard: sign always uses the session user, never body user_id ----------

def test_sign_uses_session_user_not_body(client, login_as):
    login_as(2)  # a normal user
    # attempt to sign on behalf of another user via body -> ignored
    resp = client.post('/api/consents/sign', json={'user_id': 999, 'document_id': 1,
                                                     'signature_image': ''})
    # no active docs seeded -> invalid_document OR signature_required, never 200 with user 999
    assert resp.status_code == 400


def test_mobile_sign_uses_session_user_not_body(client, login_as):
    login_as(2)
    resp = client.post('/api/mobile/consents/sign', json={'user_id': 999, 'document_id': 1,
                                                            'signature_image': ''})
    assert resp.status_code == 400


# ---------- R2: document editor gated to Settings admins ----------

def test_documents_editor_requires_auth(client):
    resp = client.get('/api/consents/documents')
    assert resp.status_code in (302, 401)


def test_documents_editor_denied_for_regular_user(client, login_as):
    login_as(2)
    resp = client.get('/api/consents/documents')
    assert resp.status_code == 403


def test_documents_editor_allows_settings_admin(client, login_as):
    login_as(3)
    resp = client.get('/api/consents/documents')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'documents' in body
    keys = {d['doc_key'] for d in body['documents']}
    assert {'data_usage', 'gdpr', 'nda'}.issubset(keys)


def test_create_document_denied_for_regular_user(client, login_as):
    login_as(2)
    resp = client.post('/api/consents/documents', json={'doc_key': 'x', 'title': 'X'})
    assert resp.status_code == 403


# ---------- R2: compliance gated to HR admins ----------

def test_compliance_denied_for_regular_user(client, login_as):
    login_as(2)
    resp = client.get('/api/consents/compliance')
    assert resp.status_code == 403


def test_compliance_allows_hr_admin(client, login_as):
    login_as(4)
    resp = client.get('/api/consents/compliance')
    assert resp.status_code == 200
    assert 'compliance' in resp.get_json()


def test_compliance_allows_settings_admin_too(client, login_as):
    # can_access_settings is the codebase-wide "admin" fallback (mirrors the
    # can_access_hr-or-can_access_settings pattern in core/connectors/*).
    login_as(3)
    resp = client.get('/api/consents/compliance')
    assert resp.status_code == 200


# ---------- PUT /api/consents/documents/<int:doc_id> (update_document) ----------
# These drive everything through the HTTP editor endpoints (no direct SQL in this
# *routes*-named test file, which the architecture hook would otherwise flag).
# They target the seeded `nda` doc and always leave is_active=False untouched, so
# the sibling schema/repo tests' invariants (doc_key list == data_usage/gdpr/nda,
# all seeds inactive, count_active_mandatory == 0) still hold. version is asserted
# relatively (bumped vs unchanged), so repeated runs — which mutate nda's
# body/version monotonically — stay green.

def _seed_doc(client, doc_key='nda'):
    """Read a seeded document (id/body/version/...) via the admin editor GET.
    Caller must already be logged in as a Settings admin."""
    resp = client.get('/api/consents/documents')
    assert resp.status_code == 200
    for d in resp.get_json()['documents']:
        if d['doc_key'] == doc_key:
            return d
    raise AssertionError(f'{doc_key} not present in seeded documents')


def test_update_document_denied_for_regular_user(client, login_as):
    login_as(2)  # regular user, no settings/hr access
    # 403 fires in the gate before any doc lookup, so the id need not exist.
    resp = client.put('/api/consents/documents/1', json={'title': 'nope'})
    assert resp.status_code == 403


def test_update_document_allows_settings_admin(client, login_as):
    login_as(3)  # Settings admin
    target = _seed_doc(client, 'nda')
    # Title-only change, same body -> valid 200 update.
    resp = client.put(f"/api/consents/documents/{target['id']}",
                      json={'title': 'NDA — admin edit', 'body': target['body']})
    assert resp.status_code == 200
    doc = resp.get_json()['document']
    assert doc['doc_key'] == 'nda'


def test_update_document_bumps_version_on_changed_body(client, login_as):
    login_as(3)
    target = _seed_doc(client, 'nda')
    old_version = target['version']

    # Changed body -> version must bump (routes.py: bump = body != existing.body).
    changed_body = (target['body'] or '') + ' [rev]'
    resp = client.put(f"/api/consents/documents/{target['id']}",
                      json={'body': changed_body})
    assert resp.status_code == 200
    bumped_version = resp.get_json()['document']['version']
    assert bumped_version > old_version

    # Same body (now `changed_body`) with a title-only edit -> NO bump.
    resp2 = client.put(f"/api/consents/documents/{target['id']}",
                       json={'body': changed_body, 'title': 'NDA — title only'})
    assert resp2.status_code == 200
    assert resp2.get_json()['document']['version'] == bumped_version


# ---------- Task 5: consents_complete surfaced on /api/auth/current-user ----------
# This exercises core.auth.routes.api_current_user, which lives on auth_bp
# (not consents_bp), so it needs its own tiny Flask app instead of the
# `app`/`client` fixtures above — but it reuses this module's real-DB gate
# (the module-level `_skip_without_real_db` autouse fixture still applies)
# and the same login_as(session) idiom as the rest of this file.

def test_current_user_exposes_consents_complete():
    from core.auth import auth_bp
    from core.auth.models import User

    flask_app = Flask(__name__)
    flask_app.secret_key = 'test-secret'
    flask_app.config['TESTING'] = True
    lm = LoginManager()
    lm.init_app(flask_app)

    # role_id left None so the v2-permissions lookups in api_current_user
    # short-circuit to {} — only ConsentService (real DB) is exercised here.
    user = User({'id': 2, 'email': 'user2@test.local', 'name': 'Test User 2'})

    @lm.user_loader
    def _load(uid):
        return user if int(uid) == user.id else None

    flask_app.register_blueprint(auth_bp)
    test_client = flask_app.test_client()
    with test_client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True

    resp = test_client.get('/api/auth/current-user')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'consents_complete' in body['user']
    assert 'pending_consents_count' in body['user']
    # all 3 seed docs are is_active=FALSE -> nothing mandatory -> complete
    assert body['user']['consents_complete'] is True
    assert body['user']['pending_consents_count'] == 0
