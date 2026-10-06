"""Repository for mkt_project_webhooks — per-project lead-intake tokens.

Only the SHA-256 hash of a token is stored. Inbound webhook auth hashes the
Bearer token and calls resolve_active() to find its (id, project_id).
"""
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.webhook_repo')


class ProjectWebhookRepository(BaseRepository):

    def create(self, project_id, label, token_hash, token_prefix, created_by):
        """Create a webhook token row. Returns the new id."""
        row = self.execute('''
            INSERT INTO mkt_project_webhooks
                (project_id, label, token_hash, token_prefix, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (project_id, label, token_hash, token_prefix, created_by), returning=True)
        return row['id'] if row else None

    def list_by_project(self, project_id):
        """List tokens for a project (hash never exposed — only prefix)."""
        return self.query_all('''
            SELECT w.id, w.project_id, w.label, w.token_prefix, w.is_active,
                   w.created_at, w.last_used_at, w.revoked_at,
                   u.name AS created_by_name
            FROM mkt_project_webhooks w
            LEFT JOIN users u ON u.id = w.created_by
            WHERE w.project_id = %s
            ORDER BY w.created_at DESC
        ''', (project_id,))

    def resolve_active(self, token_hash):
        """Return {id, project_id} for an active, non-revoked token, else None."""
        return self.query_one('''
            SELECT id, project_id
            FROM mkt_project_webhooks
            WHERE token_hash = %s AND is_active = TRUE AND revoked_at IS NULL
        ''', (token_hash,))

    def touch_last_used(self, webhook_id):
        """Record that a token was just used (best-effort observability)."""
        return self.execute(
            'UPDATE mkt_project_webhooks SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s',
            (webhook_id,),
        )

    def revoke(self, project_id, webhook_id):
        """Revoke a token. Scoped by project_id to prevent cross-project revocation."""
        return self.execute('''
            UPDATE mkt_project_webhooks
            SET is_active = FALSE, revoked_at = CURRENT_TIMESTAMP
            WHERE id = %s AND project_id = %s AND revoked_at IS NULL
        ''', (webhook_id, project_id)) > 0
