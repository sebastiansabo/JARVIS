"""Tests for the project-leads webhook feature (Phase 1).

Covers:
- marketing.services.webhook_token  — token generation + hashing (pure)
- marketing.services.lead_intake     — webhook payload normalization (pure)
- marketing.repositories.webhook_repo.ProjectWebhookRepository (mocked DB)
- marketing.repositories.lead_repo.ProjectLeadRepository (mocked DB)
- marketing.routes.leads_webhook     — public intake endpoint (minimal Flask app)
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_B = 'core.base_repository'


def _mock_db():
    return MagicMock(), MagicMock()


# ═══════════════════════════════════════════════
# webhook_token  (pure helpers)
# ═══════════════════════════════════════════════

class TestWebhookToken:

    def test_generate_token_shape(self):
        from marketing.services import webhook_token
        plaintext, token_hash, prefix = webhook_token.generate_token()
        assert plaintext.startswith('whk_')
        assert len(token_hash) == 64            # sha256 hex
        assert all(c in '0123456789abcdef' for c in token_hash)
        assert prefix and plaintext.startswith(prefix)

    def test_hash_token_matches_generated(self):
        from marketing.services import webhook_token
        plaintext, token_hash, _ = webhook_token.generate_token()
        assert webhook_token.hash_token(plaintext) == token_hash

    def test_hash_token_is_deterministic_and_distinct(self):
        from marketing.services import webhook_token
        assert webhook_token.hash_token('whk_abc') == webhook_token.hash_token('whk_abc')
        assert webhook_token.hash_token('whk_abc') != webhook_token.hash_token('whk_xyz')

    def test_hash_token_ignores_surrounding_whitespace(self):
        from marketing.services import webhook_token
        assert webhook_token.hash_token('  whk_abc  ') == webhook_token.hash_token('whk_abc')

    def test_generated_tokens_are_unique(self):
        from marketing.services import webhook_token
        a, _, _ = webhook_token.generate_token()
        b, _, _ = webhook_token.generate_token()
        assert a != b


# ═══════════════════════════════════════════════
# lead_intake.normalize_lead_payload  (pure)
# ═══════════════════════════════════════════════

class TestLeadIntake:

    def test_full_payload_normalized(self):
        from marketing.services.lead_intake import normalize_lead_payload
        data = {
            'contact_name': ' Ion Popescu ', 'phone': '+40722000000',
            'email': 'ion@example.com', 'company_name': 'ACME SRL', 'cui': 'RO123',
            'source': 'facebook_lead_ads', 'utm_source': 'facebook',
            'utm_campaign': 'summer', 'message': 'Interested', 'model_of_interest': 'XC60',
        }
        out = normalize_lead_payload(data)
        assert out['contact_name'] == 'Ion Popescu'          # trimmed
        assert out['email'] == 'ion@example.com'
        assert out['utm_source'] == 'facebook'
        assert out['raw_payload'] == data                    # original preserved

    def test_phone_only_is_valid(self):
        from marketing.services.lead_intake import normalize_lead_payload
        out = normalize_lead_payload({'phone': '0722000000'})
        assert out['phone'] == '0722000000'

    def test_email_only_is_valid(self):
        from marketing.services.lead_intake import normalize_lead_payload
        assert normalize_lead_payload({'email': 'a@b.ro'})['email'] == 'a@b.ro'

    def test_name_only_is_valid(self):
        from marketing.services.lead_intake import normalize_lead_payload
        assert normalize_lead_payload({'contact_name': 'Jane'})['contact_name'] == 'Jane'

    def test_empty_payload_rejected(self):
        from marketing.services.lead_intake import normalize_lead_payload
        with pytest.raises(ValueError):
            normalize_lead_payload({})

    def test_whitespace_only_identity_rejected(self):
        from marketing.services.lead_intake import normalize_lead_payload
        with pytest.raises(ValueError):
            normalize_lead_payload({'contact_name': '   ', 'phone': '', 'email': None})

    def test_non_dict_rejected(self):
        from marketing.services.lead_intake import normalize_lead_payload
        with pytest.raises(ValueError):
            normalize_lead_payload(['not', 'a', 'dict'])

    def test_unknown_keys_only_in_raw_payload(self):
        from marketing.services.lead_intake import normalize_lead_payload
        out = normalize_lead_payload({'phone': '0722', 'weird_key': 'keepme'})
        assert 'weird_key' not in out
        assert out['raw_payload']['weird_key'] == 'keepme'

    def test_long_value_truncated(self):
        from marketing.services.lead_intake import normalize_lead_payload
        out = normalize_lead_payload({'contact_name': 'x' * 5000})
        assert len(out['contact_name']) == 2000


# ═══════════════════════════════════════════════
# ProjectWebhookRepository  (mocked DB)
# ═══════════════════════════════════════════════

class TestProjectWebhookRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_returns_id(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = {'id': 7}

        from marketing.repositories.webhook_repo import ProjectWebhookRepository
        repo = ProjectWebhookRepository()
        result = repo.create(project_id=1, label='Zapier', token_hash='h', token_prefix='whk_abc', created_by=5)
        assert result == 7
        conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_resolve_active_returns_row(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = {'id': 7, 'project_id': 1}

        from marketing.repositories.webhook_repo import ProjectWebhookRepository
        row = ProjectWebhookRepository().resolve_active('somehash')
        assert row == {'id': 7, 'project_id': 1}

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_resolve_active_none_when_missing(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = None

        from marketing.repositories.webhook_repo import ProjectWebhookRepository
        assert ProjectWebhookRepository().resolve_active('nope') is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_revoke_true_when_updated(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.rowcount = 1

        from marketing.repositories.webhook_repo import ProjectWebhookRepository
        assert ProjectWebhookRepository().revoke(project_id=1, webhook_id=7) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_revoke_false_when_absent(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.rowcount = 0

        from marketing.repositories.webhook_repo import ProjectWebhookRepository
        assert ProjectWebhookRepository().revoke(project_id=1, webhook_id=999) is False


# ═══════════════════════════════════════════════
# ProjectLeadRepository  (mocked DB)
# ═══════════════════════════════════════════════

class TestProjectLeadRepository:

    def _normalized(self):
        from marketing.services.lead_intake import normalize_lead_payload
        return normalize_lead_payload({'contact_name': 'Jane', 'phone': '0722', 'x': 1})

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_returns_id(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = {'id': 42}

        from marketing.repositories.lead_repo import ProjectLeadRepository
        result = ProjectLeadRepository().create(
            project_id=1, payload=self._normalized(), received_via='webhook', webhook_id=7)
        assert result == 42
        conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_status_true(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.rowcount = 1

        from marketing.repositories.lead_repo import ProjectLeadRepository
        assert ProjectLeadRepository().update(project_id=1, lead_id=42, status='contacted') is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_no_fields_false(self, mock_get_db, mock_get_cursor, mock_release):
        from marketing.repositories.lead_repo import ProjectLeadRepository
        assert ProjectLeadRepository().update(project_id=1, lead_id=42) is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_true_when_removed(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.rowcount = 1

        from marketing.repositories.lead_repo import ProjectLeadRepository
        assert ProjectLeadRepository().delete(project_id=1, lead_id=42) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_status_counts_maps_rows(self, mock_get_db, mock_get_cursor, mock_release):
        conn, cursor = _mock_db()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchall.return_value = [{'status': 'new', 'cnt': 3}, {'status': 'contacted', 'cnt': 1}]

        from marketing.repositories.lead_repo import ProjectLeadRepository
        assert ProjectLeadRepository().status_counts(project_id=1) == {'new': 3, 'contacted': 1}


# ═══════════════════════════════════════════════
# Public webhook intake route (minimal Flask app)
# ═══════════════════════════════════════════════

class TestLeadsWebhookRoute:

    URL = '/marketing/api/webhooks/leads'

    def _app(self):
        from flask import Flask
        from marketing.routes import leads_webhook as mod
        app = Flask(__name__)
        app.register_blueprint(mod.leads_webhook_bp, url_prefix='/marketing/api/webhooks')
        # Patch the module-level singletons so no real DB/rate state is touched.
        mod._webhook_repo = MagicMock()
        mod._lead_repo = MagicMock()
        mod._activity_repo = MagicMock()
        mod._rate_limiter = MagicMock()
        mod._rate_limiter.is_allowed.return_value = (True, 0)
        mod._ip_rate_limiter = MagicMock()
        mod._ip_rate_limiter.is_allowed.return_value = (True, 0)
        return app, mod

    def test_missing_token_401(self):
        app, mod = self._app()
        r = app.test_client().post(self.URL, json={'phone': '0722'})
        assert r.status_code == 401
        mod._lead_repo.create.assert_not_called()

    def test_invalid_token_401(self):
        app, mod = self._app()
        mod._webhook_repo.resolve_active.return_value = None
        r = app.test_client().post(self.URL, json={'phone': '0722'},
                                   headers={'Authorization': 'Bearer whk_bad'})
        assert r.status_code == 401
        mod._lead_repo.create.assert_not_called()

    def test_valid_token_creates_lead_for_token_project(self):
        app, mod = self._app()
        mod._webhook_repo.resolve_active.return_value = {'id': 7, 'project_id': 3}
        mod._lead_repo.create.return_value = 42
        r = app.test_client().post(
            self.URL,
            json={'contact_name': 'Jane', 'phone': '0722', 'source': 'fb', 'project_id': 999},
            headers={'Authorization': 'Bearer whk_good'})
        assert r.status_code == 201
        body = r.get_json()
        assert body['success'] is True and body['lead_id'] == 42
        # project comes from the TOKEN (3), never from the body (999)
        args, kwargs = mod._lead_repo.create.call_args
        assert (args and args[0] == 3) or kwargs.get('project_id') == 3
        mod._webhook_repo.touch_last_used.assert_called_once_with(7)

    def test_empty_lead_rejected_400(self):
        app, mod = self._app()
        mod._webhook_repo.resolve_active.return_value = {'id': 7, 'project_id': 3}
        r = app.test_client().post(self.URL, json={'message': 'no identity here'},
                                   headers={'Authorization': 'Bearer whk_good'})
        assert r.status_code == 400
        mod._lead_repo.create.assert_not_called()

    def test_rate_limited_429(self):
        app, mod = self._app()
        mod._webhook_repo.resolve_active.return_value = {'id': 7, 'project_id': 3}
        mod._rate_limiter.is_allowed.return_value = (False, 30)
        r = app.test_client().post(self.URL, json={'phone': '0722'},
                                   headers={'Authorization': 'Bearer whk_good'})
        assert r.status_code == 429
        mod._lead_repo.create.assert_not_called()

    def test_ip_throttle_blocks_before_token_lookup(self):
        """A per-IP flood is rejected 429 without ever hitting the token DB lookup."""
        app, mod = self._app()
        mod._webhook_repo.resolve_active.return_value = {'id': 7, 'project_id': 3}
        mod._lead_repo.create.return_value = 42
        mod._ip_rate_limiter.is_allowed.return_value = (False, 30)
        r = app.test_client().post(self.URL, json={'phone': '0722'},
                                   headers={'Authorization': 'Bearer whk_whatever'})
        assert r.status_code == 429
        mod._webhook_repo.resolve_active.assert_not_called()
        mod._lead_repo.create.assert_not_called()
