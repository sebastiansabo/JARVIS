"""Repository for approval_decisions table."""

import json
import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.approvals.decision_repo')


class DecisionRepository:

    def create(self, request_id, step_id, decided_by, decision, comment=None,
               conditions=None, delegated_to=None, delegation_reason=None):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO approval_decisions
                    (request_id, step_id, decided_by, decision, comment,
                     conditions, delegated_to, delegation_reason)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id
            ''', (
                request_id, step_id, decided_by, decision, comment,
                json.dumps(conditions) if conditions else None,
                delegated_to, delegation_reason,
            ))
            decision_id = cursor.fetchone()['id']
            conn.commit()
            return decision_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def get_decisions_for_request(self, request_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT d.*,
                       u.name as decided_by_name, u.email as decided_by_email,
                       s.name as step_name,
                       du.name as delegated_to_name
                FROM approval_decisions d
                JOIN users u ON u.id = d.decided_by
                JOIN approval_steps s ON s.id = d.step_id
                LEFT JOIN users du ON du.id = d.delegated_to
                WHERE d.request_id = %s
                ORDER BY d.decided_at
            ''', (request_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_decisions_for_step(self, request_id, step_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT d.*, u.name as decided_by_name
                FROM approval_decisions d
                JOIN users u ON u.id = d.decided_by
                WHERE d.request_id = %s AND d.step_id = %s
                ORDER BY d.decided_at
            ''', (request_id, step_id))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def has_user_decided_on_step(self, request_id, step_id, user_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT id FROM approval_decisions
                WHERE request_id = %s AND step_id = %s AND decided_by = %s
                LIMIT 1
            ''', (request_id, step_id, user_id))
            return cursor.fetchone() is not None
        finally:
            release_db(conn)

    def count_decisions_for_step(self, request_id, step_id):
        """Count approved/rejected/total decisions for a step."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE decision = 'approved') as approved,
                    COUNT(*) FILTER (WHERE decision = 'rejected') as rejected,
                    COUNT(*) FILTER (WHERE decision = 'returned') as returned,
                    COUNT(*) FILTER (WHERE decision = 'abstained') as abstained
                FROM approval_decisions
                WHERE request_id = %s AND step_id = %s
            ''', (request_id, step_id))
            return dict(cursor.fetchone())
        finally:
            release_db(conn)
