"""Repository for approval_delegations table."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.approvals.delegation_repo')


class DelegationRepository(BaseRepository):

    def get_active_for_user(self, user_id):
        """Get delegations where user is delegator or delegate."""
        return self.query_all('''
            SELECT d.*,
                   dr.name as delegator_name, dr.email as delegator_email,
                   de.name as delegate_name, de.email as delegate_email,
                   f.name as flow_name
            FROM approval_delegations d
            JOIN users dr ON dr.id = d.delegator_id
            JOIN users de ON de.id = d.delegate_id
            LEFT JOIN approval_flows f ON f.id = d.flow_id
            WHERE (d.delegator_id = %s OR d.delegate_id = %s)
            AND d.is_active = TRUE
            ORDER BY d.starts_at DESC
        ''', (user_id, user_id))

    def create(self, delegator_id, delegate_id, starts_at, ends_at,
               reason=None, entity_type=None, flow_id=None):
        row = self.execute('''
            INSERT INTO approval_delegations
                (delegator_id, delegate_id, starts_at, ends_at, reason, entity_type, flow_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (delegator_id, delegate_id, starts_at, ends_at, reason, entity_type, flow_id),
            returning=True)
        return row['id'] if row else None

    def deactivate(self, delegation_id):
        return self.execute(
            'UPDATE approval_delegations SET is_active = FALSE WHERE id = %s',
            (delegation_id,)
        ) > 0

    def deactivate_expired(self):
        """Deactivate delegations past their ends_at. Called by scheduler."""
        count = self.execute('''
            UPDATE approval_delegations
            SET is_active = FALSE
            WHERE is_active = TRUE AND ends_at < NOW()
        ''')
        if count > 0:
            logger.info(f"Deactivated {count} expired delegations")
        return count

    def get_active_delegates_for_user(self, delegator_id, entity_type=None, flow_id=None):
        """Find who can act on behalf of delegator_id right now."""
        rows = self.query_all('''
            SELECT delegate_id FROM approval_delegations
            WHERE delegator_id = %s AND is_active = TRUE
            AND NOW() BETWEEN starts_at AND ends_at
            AND (entity_type IS NULL OR entity_type = %s)
            AND (flow_id IS NULL OR flow_id = %s)
        ''', (delegator_id, entity_type, flow_id))
        return [row['delegate_id'] for row in rows]

    def is_delegate_for(self, delegate_id, delegator_id, entity_type=None, flow_id=None):
        """Check if delegate_id can act on behalf of delegator_id."""
        return self.query_one('''
            SELECT id FROM approval_delegations
            WHERE delegator_id = %s AND delegate_id = %s
            AND is_active = TRUE AND NOW() BETWEEN starts_at AND ends_at
            AND (entity_type IS NULL OR entity_type = %s)
            AND (flow_id IS NULL OR flow_id = %s)
            LIMIT 1
        ''', (delegator_id, delegate_id, entity_type, flow_id)) is not None
