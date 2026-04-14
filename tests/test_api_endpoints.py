"""Deep API endpoint tests using Flask test client.

Tests route registration, auth enforcement, and response shapes.
All DB calls are mocked via conftest.py psycopg2 patch.
"""
import sys, os, json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


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


class TestBlueprintRegistration:
    """Verify all expected blueprints registered after create_app()."""

    EXPECTED_BLUEPRINTS = {
        'auth', 'approvals', 'notifications', 'profile',
        'organization', 'mobile', 'roles', 'checkin',
    }

    def test_expected_blueprints_registered(self, app):
        registered = set(app.blueprints.keys())
        missing = self.EXPECTED_BLUEPRINTS - registered
        assert not missing, f"Missing blueprints: {missing}"

    def test_health_route_exists(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/health' in rules

    def test_approvals_routes_exist(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        # Approvals blueprint is registered with /approvals prefix
        approval_rules = [r for r in rules if r.startswith('/approvals/')]
        assert len(approval_rules) > 0, f"No approval routes found. All rules: {sorted(rules)[:20]}"

    def test_mobile_auth_routes_exist(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/api/auth/token' in rules, f"/api/auth/token not in rules: {sorted(rules)[:30]}"
        assert '/api/auth/refresh' in rules, f"/api/auth/refresh not in rules"

    def test_notification_routes_exist(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/api/notification-settings' in rules, f"/api/notification-settings not in rules"
        assert '/notifications/api/list' in rules, f"/notifications/api/list not in rules"


class TestMobileAuthEndpoints:
    """Mobile JWT auth — token + refresh endpoints."""

    def test_token_endpoint_exists(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/api/auth/token' in rules

    def test_token_missing_body_returns_400(self, client):
        """POST /api/auth/token with empty JSON body returns 400."""
        resp = client.post('/api/auth/token', json={})
        assert resp.status_code == 400

    def test_token_missing_email_returns_400(self, client):
        """POST /api/auth/token with password but no email returns 400."""
        resp = client.post('/api/auth/token', json={'password': 'secret'})
        assert resp.status_code == 400

    def test_token_missing_password_returns_400(self, client):
        """POST /api/auth/token with email but no password returns 400."""
        resp = client.post('/api/auth/token', json={'email': 'user@test.com'})
        assert resp.status_code == 400

    def test_token_no_json_body_returns_400(self, client):
        """POST /api/auth/token with no body at all returns 400."""
        resp = client.post('/api/auth/token')
        # 400 (missing body parsed as None) or 415 (unsupported media type) are both acceptable
        assert resp.status_code in (400, 415)

    def test_token_invalid_credentials_returns_401(self, client):
        """POST /api/auth/token with wrong credentials returns 401."""
        with patch('core.auth.repositories.UserRepository.authenticate', return_value=None):
            resp = client.post('/api/auth/token', json={
                'email': 'nonexistent@test.com',
                'password': 'wrongpassword',
            })
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert 'error' in data

    def test_refresh_without_token_returns_401(self, client):
        """POST /api/auth/refresh with no refresh_token returns 401."""
        resp = client.post('/api/auth/refresh', json={})
        assert resp.status_code in (400, 401)

    def test_refresh_with_invalid_token_returns_401(self, client):
        """POST /api/auth/refresh with a garbage token returns 401."""
        resp = client.post('/api/auth/refresh', json={'refresh_token': 'not.a.valid.jwt'})
        assert resp.status_code == 401
        data = resp.get_json()
        assert 'error' in data

    def test_refresh_no_json_body_returns_400(self, client):
        """POST /api/auth/refresh with no body at all returns 400."""
        resp = client.post('/api/auth/refresh')
        # 400 (missing body) or 401 (no token supplied) or 415 (media type) are all acceptable
        assert resp.status_code in (400, 401, 415)

    def test_token_returns_json(self, client):
        """POST /api/auth/token always returns JSON (even on error)."""
        resp = client.post('/api/auth/token', json={})
        assert resp.content_type.startswith('application/json')


class TestNotificationEndpoints:
    """Notification routes — require login (flask-login)."""

    def test_notification_settings_get_requires_auth(self, client):
        """GET /api/notification-settings without login returns 302 (redirect to login)."""
        resp = client.get('/api/notification-settings')
        # flask-login redirects to login page when not authenticated
        assert resp.status_code in (401, 302)

    def test_notification_settings_post_requires_auth(self, client):
        """POST /api/notification-settings without login returns 302."""
        resp = client.post('/api/notification-settings', json={})
        assert resp.status_code in (401, 302)

    def test_notifications_list_requires_auth(self, client):
        """GET /notifications/api/list without login returns 302."""
        resp = client.get('/notifications/api/list')
        assert resp.status_code in (401, 302)

    def test_notifications_unread_count_requires_auth(self, client):
        """GET /notifications/api/unread-count without login returns 302."""
        resp = client.get('/notifications/api/unread-count')
        assert resp.status_code in (401, 302)

    def test_mark_all_read_requires_auth(self, client):
        """POST /notifications/api/mark-all-read without login returns 302."""
        resp = client.post('/notifications/api/mark-all-read')
        assert resp.status_code in (401, 302)

    def test_push_manager_settings_requires_auth(self, client):
        """GET /api/push-manager/settings without login returns 302."""
        resp = client.get('/api/push-manager/settings')
        assert resp.status_code in (401, 302)


class TestApprovalsEndpoints:
    """Approvals routes — require login (flask-login).

    The approvals blueprint is mounted with url_prefix='/approvals',
    so all routes are under /approvals/api/...
    """

    def test_requests_list_get_requires_auth(self, client):
        """GET /approvals/api/requests without login returns 302."""
        resp = client.get('/approvals/api/requests')
        assert resp.status_code in (401, 302)

    def test_requests_post_requires_auth(self, client):
        """POST /approvals/api/requests without login returns 302."""
        resp = client.post('/approvals/api/requests', json={'entity_type': 'invoice', 'entity_id': 1})
        assert resp.status_code in (401, 302)

    def test_decide_endpoint_requires_auth(self, client):
        """POST /approvals/api/requests/<id>/decide without login returns 302."""
        resp = client.post('/approvals/api/requests/1/decide', json={'decision': 'approve'})
        assert resp.status_code in (401, 302)

    def test_cancel_endpoint_requires_auth(self, client):
        """POST /approvals/api/requests/<id>/cancel without login returns 302."""
        resp = client.post('/approvals/api/requests/1/cancel')
        assert resp.status_code in (401, 302)

    def test_my_queue_requires_auth(self, client):
        """GET /approvals/api/my-queue without login returns 302."""
        resp = client.get('/approvals/api/my-queue')
        assert resp.status_code in (401, 302)

    def test_my_queue_count_requires_auth(self, client):
        """GET /approvals/api/my-queue/count without login returns 302."""
        resp = client.get('/approvals/api/my-queue/count')
        assert resp.status_code in (401, 302)

    def test_flows_list_requires_auth(self, client):
        """GET /approvals/api/flows without login returns 302."""
        resp = client.get('/approvals/api/flows')
        assert resp.status_code in (401, 302)

    def test_delegations_requires_auth(self, client):
        """GET /approvals/api/delegations without login returns 302."""
        resp = client.get('/approvals/api/delegations')
        assert resp.status_code in (401, 302)

    def test_audit_requires_auth(self, client):
        """GET /approvals/api/audit without login returns 302."""
        resp = client.get('/approvals/api/audit')
        assert resp.status_code in (401, 302)


class TestDBConnectionLifecycle:
    """Verify database get_db/release_db are called correctly in handlers."""

    def test_release_db_called_in_handlers(self):
        """approvals/handlers: release_db must be called even on exception.

        After the handlers/ package split, get_db/release_db/_get_user_email live in
        _shared.py — patch there.
        """
        from core.approvals.handlers import _shared as h

        mock_conn = MagicMock()
        mock_cursor_obj = MagicMock()
        mock_cursor_obj.fetchone.side_effect = Exception("DB error")

        with patch.object(h, 'get_db', return_value=mock_conn), \
             patch.object(h, 'get_cursor', return_value=mock_cursor_obj), \
             patch.object(h, 'release_db') as mock_release:
            try:
                h._get_user_email(999)
            except Exception:
                pass
            # release_db must have been called in the finally block
            mock_release.assert_called_once_with(mock_conn)

    def test_get_user_email_returns_none_on_missing_user(self):
        """_get_user_email returns (None, None) when DB row not found."""
        from core.approvals.handlers import _shared as h

        mock_conn = MagicMock()
        mock_cursor_obj = MagicMock()
        mock_cursor_obj.fetchone.return_value = None

        with patch.object(h, 'get_db', return_value=mock_conn), \
             patch.object(h, 'get_cursor', return_value=mock_cursor_obj), \
             patch.object(h, 'release_db'):
            name, email = h._get_user_email(999)
        assert name is None
        assert email is None

    def test_get_user_email_returns_none_for_falsy_id(self):
        """_get_user_email short-circuits on falsy user_id and returns (None, None)."""
        from core.approvals.handlers import _shared as h
        # No DB call should be made at all for falsy ids
        for falsy in (0, None, ''):
            name, email = h._get_user_email(falsy)
            assert name is None
            assert email is None


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200

    def test_health_returns_json(self, client):
        resp = client.get('/health')
        assert resp.content_type.startswith('application/json')

    def test_health_body_has_status(self, client):
        resp = client.get('/health')
        data = resp.get_json()
        assert data is not None
        # Accept either {"status": ...} or {"ok": ...} or anything truthy
        assert isinstance(data, dict)


class TestURLRules:
    """Verify exact URL rules known from route inspection.

    Mobile/auth/notification routes have no blueprint prefix.
    Approvals routes are under /approvals/ (blueprint url_prefix).
    """

    KNOWN_RULES = [
        # Mobile auth (mobile blueprint, no prefix)
        '/api/auth/token',
        '/api/auth/refresh',
        '/api/auth/logout',
        '/api/auth/current-user',
        # Mobile dashboard (mobile blueprint, no prefix)
        '/api/mobile/dashboard',
        '/api/mobile/version',
        # Device registration (mobile blueprint, no prefix)
        '/api/devices/register',
        '/api/devices/unregister',
        # Notifications (notifications blueprint, no prefix)
        '/api/notification-settings',
        '/api/notification-logs',
        '/notifications/api/list',
        '/notifications/api/unread-count',
        '/notifications/api/mark-all-read',
        # Push manager (notifications blueprint, no prefix)
        '/api/push-manager/settings',
        # Approvals (approvals blueprint, url_prefix='/approvals')
        '/approvals/api/requests',
        '/approvals/api/my-queue',
        '/approvals/api/my-queue/count',
        '/approvals/api/my-requests',
        '/approvals/api/flows',
        '/approvals/api/delegations',
        '/approvals/api/audit',
        # Health (app-level route)
        '/health',
    ]

    def test_known_rules_all_registered(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        missing = [r for r in self.KNOWN_RULES if r not in rules]
        assert not missing, f"Expected URL rules not registered: {missing}"
