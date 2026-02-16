"""Repository for approval_delegations table."""

import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.approvals.delegation_repo')


class DelegationRepository:

    def get_active_for_user(self, user_id):
        """Get delegations where user is delegator or delegate."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
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
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def create(self, delegator_id, delegate_id, starts_at, ends_at,
               reason=None, entity_type=None, flow_id=None):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO approval_delegations
                    (delegator_id, delegate_id, starts_at, ends_at, reason, entity_type, flow_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (delegator_id, delegate_id, starts_at, ends_at, reason, entity_type, flow_id))
            delegation_id = cursor.fetchone()['id']
            conn.commit()
            return delegation_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def deactivate(self, delegation_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                'UPDATE approval_delegations SET is_active = FALSE WHERE id = %s',
                (delegation_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def deactivate_expired(self):
        """Deactivate delegations past their ends_at. Called by scheduler."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                UPDATE approval_delegations
                SET is_active = FALSE
                WHERE is_active = TRUE AND ends_at < NOW()
            ''')
            count = cursor.rowcount
            conn.commit()
            if count > 0:
                logger.info(f"Deactivated {count} expired delegations")
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def get_active_delegates_for_user(self, delegator_id, entity_type=None, flow_id=None):
        """Find who can act on behalf of delegator_id right now."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT delegate_id FROM approval_delegations
                WHERE delegator_id = %s AND is_active = TRUE
                AND NOW() BETWEEN starts_at AND ends_at
                AND (entity_type IS NULL OR entity_type = %s)
                AND (flow_id IS NULL OR flow_id = %s)
            ''', (delegator_id, entity_type, flow_id))
            return [row['delegate_id'] for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def is_delegate_for(self, delegate_id, delegator_id, entity_type=None, flow_id=None):
        """Check if delegate_id can act on behalf of delegator_id."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT id FROM approval_delegations
                WHERE delegator_id = %s AND delegate_id = %s
                AND is_active = TRUE AND NOW() BETWEEN starts_at AND ends_at
                AND (entity_type IS NULL OR entity_type = %s)
                AND (flow_id IS NULL OR flow_id = %s)
                LIMIT 1
            ''', (delegator_id, delegate_id, entity_type, flow_id))
            return cursor.fetchone() is not None
        finally:
            release_db(conn)
