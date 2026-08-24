"""Permission-gate tests for the Happy admin routes (spec §12 DoD).

Every admin endpoint must reject unauthenticated (401) and unprivileged (403)
callers via @v2_permission_required, and let a privileged caller through.
Runs under the psycopg2 mock in jarvis/conftest.py.
"""
import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from happy.routes import happy_bp


class FakeUser(UserMixin):
    def __init__(self, uid, role_id=None, is_admin=False, can_access_settings=False):
        self.id = uid
        self.role_id = role_id
        self.is_admin = is_admin
        self.can_access_settings = can_access_settings


UNPRIV = FakeUser(1)                       # authenticated, no role, no bypass -> 403
ADMIN = FakeUser(2, is_admin=True)          # admin bypass in the decorator


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = "test"
    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def _load(uid):                         # noqa: ANN001
        return None

    @lm.request_loader
    def _load_req(req):                      # noqa: ANN001
        kind = req.headers.get("X-Test-User")
        return {"admin": ADMIN, "unpriv": UNPRIV}.get(kind)

    app.register_blueprint(happy_bp, url_prefix="/api/happy")
    return app.test_client()


ADMIN_ENDPOINTS = [
    ("GET", "/api/happy/admin/campaigns"),
    ("POST", "/api/happy/admin/campaigns"),
    ("GET", "/api/happy/admin/campaigns/1"),
    ("PUT", "/api/happy/admin/campaigns/1"),
    ("POST", "/api/happy/admin/campaigns/1/preview-audience"),
    ("POST", "/api/happy/admin/campaigns/1/publish"),
    ("POST", "/api/happy/admin/campaigns/1/pause"),
]


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_requires_authentication(client, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_denied_without_permission(client, method, path):
    resp = client.open(path, method=method, json={}, headers={"X-Test-User": "unpriv"})
    assert resp.status_code == 403


def test_admin_allows_privileged_user(client, monkeypatch):
    # Admin bypass lets the view run; stub the repo so no DB is needed.
    from happy.repositories import CampaignRepository
    monkeypatch.setattr(CampaignRepository, "list", lambda self, status=None: [])
    resp = client.get("/api/happy/admin/campaigns", headers={"X-Test-User": "admin"})
    assert resp.status_code == 200
    assert resp.get_json() == {"campaigns": []}


def test_employee_surface_requires_authentication(client):
    assert client.get("/api/happy/surface?placement=interstitial&route=/app/hub").status_code == 401
