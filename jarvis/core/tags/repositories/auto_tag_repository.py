"""Auto-tag rules repository.

CRUD operations for auto_tag_rules table.
"""
import json
import logging

from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.tags.auto_tag_repository')


class AutoTagRepository:

    def get_rules(self, entity_type: str = None, active_only: bool = True) -> list:
        """Get auto-tag rules, optionally filtered by entity_type."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            conditions = []
            params = []
            if active_only:
                conditions.append('r.is_active = TRUE')
            if entity_type:
                conditions.append('r.entity_type = %s')
                params.append(entity_type)
            # Guard: conditions are code-controlled literals, never user input
            if conditions:
                assert all(isinstance(c, str) and ('%s' in c or c == 'r.is_active = TRUE') for c in conditions), \
                    "SQL conditions must be parameterized strings"
            where = f'WHERE {" AND ".join(conditions)}' if conditions else ''
            cursor.execute(f'''
                SELECT r.*, t.name as tag_name, t.color as tag_color,
                       u.name as created_by_name
                FROM auto_tag_rules r
                JOIN tags t ON t.id = r.tag_id
                LEFT JOIN users u ON u.id = r.created_by
                {where}
                ORDER BY r.created_at DESC
            ''', params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_rule(self, rule_id: int) -> dict | None:
        """Get a single rule by ID."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT r.*, t.name as tag_name, t.color as tag_color
                FROM auto_tag_rules r
                JOIN tags t ON t.id = r.tag_id
                WHERE r.id = %s
            ''', (rule_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def create_rule(self, name: str, entity_type: str, tag_id: int,
                    conditions: list, match_mode: str = 'all',
                    run_on_create: bool = True,
                    created_by: int = None) -> int:
        """Create a new auto-tag rule. Returns rule ID."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO auto_tag_rules (name, entity_type, tag_id, conditions, match_mode, run_on_create, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (name.strip(), entity_type, tag_id,
                  json.dumps(conditions), match_mode, run_on_create, created_by))
            rule_id = cursor.fetchone()['id']
            conn.commit()
            return rule_id
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def update_rule(self, rule_id: int, **kwargs) -> bool:
        """Update a rule. Returns True if updated."""
        allowed = {'name', 'entity_type', 'tag_id', 'conditions', 'match_mode', 'is_active', 'run_on_create'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                if key == 'name' and val is not None:
                    val = val.strip()
                if key == 'conditions':
                    val = json.dumps(val)
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(rule_id)
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                f'UPDATE auto_tag_rules SET {", ".join(updates)} WHERE id = %s',
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def delete_rule(self, rule_id: int) -> bool:
        """Hard-delete a rule."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('DELETE FROM auto_tag_rules WHERE id = %s', (rule_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)
