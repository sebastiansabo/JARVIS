"""Repository for approval_requests table."""

import json
import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.approvals.request_repo')


class RequestRepository:

    def get_by_id(self, request_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT r.*,
                       f.name as flow_name, f.slug as flow_slug,
                       s.name as current_step_name,
                       u.name as requested_by_name, u.email as requested_by_email
                FROM approval_requests r
                JOIN approval_flows f ON f.id = r.flow_id
                LEFT JOIN approval_steps s ON s.id = r.current_step_id
                JOIN users u ON u.id = r.requested_by
                WHERE r.id = %s
            ''', (request_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def get_by_entity(self, entity_type, entity_id):
        """Get all requests for an entity, newest first."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT r.*,
                       f.name as flow_name,
                       s.name as current_step_name,
                       u.name as requested_by_name, u.email as requested_by_email
                FROM approval_requests r
                JOIN approval_flows f ON f.id = r.flow_id
                LEFT JOIN approval_steps s ON s.id = r.current_step_id
                JOIN users u ON u.id = r.requested_by
                WHERE r.entity_type = %s AND r.entity_id = %s
                ORDER BY r.created_at DESC
            ''', (entity_type, entity_id))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_pending_for_entity(self, entity_type, entity_id):
        """Check if entity already has a pending/in_progress request."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT id FROM approval_requests
                WHERE entity_type = %s AND entity_id = %s
                AND status IN ('pending', 'in_progress')
                LIMIT 1
            ''', (entity_type, entity_id))
            row = cursor.fetchone()
            return row['id'] if row else None
        finally:
            release_db(conn)

    def create(self, entity_type, entity_id, flow_id, requested_by, context_snapshot,
               priority='normal', due_by=None):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO approval_requests
                    (entity_type, entity_id, flow_id, requested_by, context_snapshot, priority, due_by)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id
            ''', (
                entity_type, entity_id, flow_id, requested_by,
                json.dumps(context_snapshot) if isinstance(context_snapshot, dict) else context_snapshot,
                priority, due_by,
            ))
            request_id = cursor.fetchone()['id']
            conn.commit()
            return request_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def update_status(self, request_id, status, **kwargs):
        """Update request status and optional fields."""
        sets = ['status = %s', 'updated_at = NOW()']
        params = [status]
        if 'current_step_id' in kwargs:
            sets.append('current_step_id = %s')
            params.append(kwargs['current_step_id'])
        if 'resolved_at' in kwargs:
            sets.append('resolved_at = %s')
            params.append(kwargs['resolved_at'])
        if 'resolution_note' in kwargs:
            sets.append('resolution_note = %s')
            params.append(kwargs['resolution_note'])
        if 'priority' in kwargs:
            sets.append('priority = %s')
            params.append(kwargs['priority'])
        params.append(request_id)
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                f'UPDATE approval_requests SET {", ".join(sets)} WHERE id = %s',
                params
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def list_requests(self, status=None, entity_type=None, requested_by=None,
                      limit=50, offset=0):
        """List requests with optional filters."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            wheres = []
            params = []
            if status:
                wheres.append('r.status = %s')
                params.append(status)
            if entity_type:
                wheres.append('r.entity_type = %s')
                params.append(entity_type)
            if requested_by:
                wheres.append('r.requested_by = %s')
                params.append(requested_by)
            where_clause = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
            params.extend([limit, offset])
            cursor.execute(f'''
                SELECT r.*,
                       f.name as flow_name,
                       s.name as current_step_name,
                       u.name as requested_by_name, u.email as requested_by_email
                FROM approval_requests r
                JOIN approval_flows f ON f.id = r.flow_id
                LEFT JOIN approval_steps s ON s.id = r.current_step_id
                JOIN users u ON u.id = r.requested_by
                {where_clause}
                ORDER BY r.created_at DESC
                LIMIT %s OFFSET %s
            ''', params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_pending_for_user(self, user_id, entity_type=None):
        """Get requests pending this user's decision.

        Checks:
        - Direct assignment (step.approver_user_id = user)
        - Role match (user's role matches step.approver_role_name)
        - Active delegations
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            params = [user_id, user_id, user_id]
            entity_filter = ''
            if entity_type:
                entity_filter = 'AND r.entity_type = %s'
                params.append(entity_type)
            cursor.execute(f'''
                SELECT DISTINCT r.*,
                       f.name as flow_name,
                       s.name as current_step_name,
                       u.name as requested_by_name, u.email as requested_by_email,
                       EXTRACT(EPOCH FROM (NOW() - r.requested_at)) / 3600.0 as waiting_hours
                FROM approval_requests r
                JOIN approval_flows f ON f.id = r.flow_id
                JOIN approval_steps s ON s.id = r.current_step_id
                JOIN users u ON u.id = r.requested_by
                WHERE r.status IN ('pending', 'in_progress')
                AND (
                    -- Direct user assignment
                    s.approver_user_id = %s
                    -- Role-based assignment
                    OR s.approver_role_name IN (
                        SELECT rl.name FROM roles rl
                        JOIN users usr ON usr.role_id = rl.id
                        WHERE usr.id = %s
                    )
                    -- Active delegation
                    OR s.approver_user_id IN (
                        SELECT d.delegator_id FROM approval_delegations d
                        WHERE d.delegate_id = %s AND d.is_active = TRUE
                        AND NOW() BETWEEN d.starts_at AND d.ends_at
                        AND (d.entity_type IS NULL OR d.entity_type = r.entity_type)
                        AND (d.flow_id IS NULL OR d.flow_id = r.flow_id)
                    )
                )
                -- Exclude requests the user already decided on for this step
                AND NOT EXISTS (
                    SELECT 1 FROM approval_decisions ad
                    WHERE ad.request_id = r.id AND ad.step_id = r.current_step_id
                    AND ad.decided_by = %s
                )
                {entity_filter}
                ORDER BY
                    CASE r.priority
                        WHEN 'urgent' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'normal' THEN 2
                        WHEN 'low' THEN 3
                    END,
                    r.requested_at ASC
            ''', params + [user_id])
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_pending_queue_count(self, user_id):
        """Fast count for badge."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT COUNT(DISTINCT r.id) as cnt
                FROM approval_requests r
                JOIN approval_steps s ON s.id = r.current_step_id
                WHERE r.status IN ('pending', 'in_progress')
                AND (
                    s.approver_user_id = %s
                    OR s.approver_role_name IN (
                        SELECT rl.name FROM roles rl
                        JOIN users usr ON usr.role_id = rl.id
                        WHERE usr.id = %s
                    )
                    OR s.approver_user_id IN (
                        SELECT d.delegator_id FROM approval_delegations d
                        WHERE d.delegate_id = %s AND d.is_active = TRUE
                        AND NOW() BETWEEN d.starts_at AND d.ends_at
                    )
                )
                AND NOT EXISTS (
                    SELECT 1 FROM approval_decisions ad
                    WHERE ad.request_id = r.id AND ad.step_id = r.current_step_id
                    AND ad.decided_by = %s
                )
            ''', (user_id, user_id, user_id, user_id))
            return cursor.fetchone()['cnt']
        finally:
            release_db(conn)

    def get_timed_out_requests(self):
        """Find requests where current step has exceeded timeout_hours."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT r.id as request_id, s.id as step_id,
                       s.timeout_hours, s.escalation_step_id, s.escalation_user_id,
                       r.requested_at, r.status
                FROM approval_requests r
                JOIN approval_steps s ON s.id = r.current_step_id
                WHERE r.status IN ('pending', 'in_progress')
                AND s.timeout_hours IS NOT NULL
                AND r.updated_at < NOW() - (s.timeout_hours || ' hours')::interval
            ''')
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_requests_needing_reminder(self):
        """Find requests where current step has exceeded reminder_after_hours."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT r.id as request_id, s.id as step_id,
                       s.reminder_after_hours
                FROM approval_requests r
                JOIN approval_steps s ON s.id = r.current_step_id
                WHERE r.status IN ('pending', 'in_progress')
                AND s.reminder_after_hours IS NOT NULL
                AND r.updated_at < NOW() - (s.reminder_after_hours || ' hours')::interval
                AND NOT EXISTS (
                    SELECT 1 FROM approval_audit_log al
                    WHERE al.request_id = r.id AND al.action = 'reminder_sent'
                    AND al.created_at > NOW() - (s.reminder_after_hours || ' hours')::interval
                )
            ''')
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_expired_requests(self):
        """Find requests past flow's auto_reject_after_hours."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT r.id as request_id, f.auto_reject_after_hours
                FROM approval_requests r
                JOIN approval_flows f ON f.id = r.flow_id
                WHERE r.status IN ('pending', 'in_progress')
                AND f.auto_reject_after_hours IS NOT NULL
                AND r.requested_at < NOW() - (f.auto_reject_after_hours || ' hours')::interval
            ''')
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)
