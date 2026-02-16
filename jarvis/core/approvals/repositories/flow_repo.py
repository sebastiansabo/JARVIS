"""Repository for approval_flows and approval_steps tables."""

import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.approvals.flow_repo')


class FlowRepository:

    # ── Flows ──

    def get_all_flows(self, active_only=True):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            if active_only:
                cursor.execute('''
                    SELECT f.*, u.name as created_by_name
                    FROM approval_flows f
                    LEFT JOIN users u ON u.id = f.created_by
                    WHERE f.is_active = TRUE
                    ORDER BY f.priority DESC, f.name
                ''')
            else:
                cursor.execute('''
                    SELECT f.*, u.name as created_by_name
                    FROM approval_flows f
                    LEFT JOIN users u ON u.id = f.created_by
                    ORDER BY f.priority DESC, f.name
                ''')
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_flow_by_id(self, flow_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT f.*, u.name as created_by_name
                FROM approval_flows f
                LEFT JOIN users u ON u.id = f.created_by
                WHERE f.id = %s
            ''', (flow_id,))
            return dict(cursor.fetchone()) if cursor.rowcount else None
        finally:
            release_db(conn)

    def get_flow_by_slug(self, slug):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('SELECT * FROM approval_flows WHERE slug = %s', (slug,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def get_active_flows_for_entity_type(self, entity_type):
        """Get all active flows for an entity type, ordered by priority DESC."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT * FROM approval_flows
                WHERE entity_type = %s AND is_active = TRUE
                ORDER BY priority DESC
            ''', (entity_type,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def create_flow(self, name, slug, entity_type, created_by, **kwargs):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO approval_flows (name, slug, entity_type, created_by,
                    description, trigger_conditions, priority, allow_parallel_steps,
                    auto_approve_below, auto_reject_after_hours)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
            ''', (
                name, slug, entity_type, created_by,
                kwargs.get('description'),
                _json_or_default(kwargs.get('trigger_conditions'), '{}'),
                kwargs.get('priority', 0),
                kwargs.get('allow_parallel_steps', False),
                kwargs.get('auto_approve_below'),
                kwargs.get('auto_reject_after_hours'),
            ))
            flow_id = cursor.fetchone()['id']
            conn.commit()
            return flow_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def update_flow(self, flow_id, **kwargs):
        allowed = {
            'name', 'slug', 'description', 'entity_type', 'trigger_conditions',
            'is_active', 'priority', 'allow_parallel_steps',
            'auto_approve_below', 'auto_reject_after_hours',
        }
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                if key == 'trigger_conditions':
                    updates.append(f'{key} = %s::jsonb')
                    params.append(_json_or_default(val, '{}'))
                else:
                    updates.append(f'{key} = %s')
                    params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(flow_id)
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                f'UPDATE approval_flows SET {", ".join(updates)} WHERE id = %s',
                params
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def deactivate_flow(self, flow_id):
        return self.update_flow(flow_id, is_active=False)

    # ── Steps ──

    def get_steps_for_flow(self, flow_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT * FROM approval_steps
                WHERE flow_id = %s
                ORDER BY step_order
            ''', (flow_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_step_by_id(self, step_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('SELECT * FROM approval_steps WHERE id = %s', (step_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def create_step(self, flow_id, name, step_order, approver_type, **kwargs):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO approval_steps (flow_id, name, step_order, approver_type,
                    approver_user_id, approver_role_name, requires_all, min_approvals,
                    skip_conditions, timeout_hours, escalation_step_id, escalation_user_id,
                    notify_on_pending, notify_on_decision, reminder_after_hours)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                flow_id, name, step_order, approver_type,
                kwargs.get('approver_user_id'),
                kwargs.get('approver_role_name'),
                kwargs.get('requires_all', False),
                kwargs.get('min_approvals', 1),
                _json_or_default(kwargs.get('skip_conditions'), '{}'),
                kwargs.get('timeout_hours'),
                kwargs.get('escalation_step_id'),
                kwargs.get('escalation_user_id'),
                kwargs.get('notify_on_pending', True),
                kwargs.get('notify_on_decision', True),
                kwargs.get('reminder_after_hours'),
            ))
            step_id = cursor.fetchone()['id']
            conn.commit()
            return step_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def update_step(self, step_id, **kwargs):
        allowed = {
            'name', 'step_order', 'approver_type', 'approver_user_id',
            'approver_role_name', 'requires_all', 'min_approvals',
            'skip_conditions', 'timeout_hours', 'escalation_step_id',
            'escalation_user_id', 'notify_on_pending', 'notify_on_decision',
            'reminder_after_hours',
        }
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                if key == 'skip_conditions':
                    updates.append(f'{key} = %s::jsonb')
                    params.append(_json_or_default(val, '{}'))
                else:
                    updates.append(f'{key} = %s')
                    params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(step_id)
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                f'UPDATE approval_steps SET {", ".join(updates)} WHERE id = %s',
                params
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def delete_step(self, step_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('DELETE FROM approval_steps WHERE id = %s', (step_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def reorder_steps(self, flow_id, step_ids):
        """Reorder steps by setting step_order based on position in step_ids list."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            for idx, step_id in enumerate(step_ids, start=1):
                cursor.execute(
                    'UPDATE approval_steps SET step_order = %s, updated_at = NOW() WHERE id = %s AND flow_id = %s',
                    (idx, step_id, flow_id)
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def get_flow_with_steps(self, flow_id):
        """Get flow dict with embedded steps list."""
        flow = self.get_flow_by_id(flow_id)
        if flow:
            flow['steps'] = self.get_steps_for_flow(flow_id)
        return flow


def _json_or_default(val, default='{}'):
    """Convert value to JSON string for JSONB columns."""
    import json
    if val is None:
        return default
    if isinstance(val, str):
        return val
    return json.dumps(val)
