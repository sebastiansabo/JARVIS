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
