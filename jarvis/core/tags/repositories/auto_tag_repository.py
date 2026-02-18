"""Auto-tag rules repository.

CRUD operations for auto_tag_rules table.
"""
import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.tags.auto_tag_repository')


class AutoTagRepository(BaseRepository):

    def get_rules(self, entity_type: str = None, active_only: bool = True) -> list:
        """Get auto-tag rules, optionally filtered by entity_type."""
        conditions = []
        params = []
        if active_only:
            conditions.append('r.is_active = TRUE')
        if entity_type:
            conditions.append('r.entity_type = %s')
            params.append(entity_type)
        where = f'WHERE {" AND ".join(conditions)}' if conditions else ''
        return self.query_all(f'''
            SELECT r.*, t.name as tag_name, t.color as tag_color,
                   u.name as created_by_name
            FROM auto_tag_rules r
            JOIN tags t ON t.id = r.tag_id
            LEFT JOIN users u ON u.id = r.created_by
            {where}
            ORDER BY r.created_at DESC
        ''', params)

    def get_rule(self, rule_id: int) -> dict | None:
        """Get a single rule by ID."""
        return self.query_one('''
            SELECT r.*, t.name as tag_name, t.color as tag_color
            FROM auto_tag_rules r
            JOIN tags t ON t.id = r.tag_id
            WHERE r.id = %s
        ''', (rule_id,))

    def create_rule(self, name: str, entity_type: str, tag_id: int,
                    conditions: list, match_mode: str = 'all',
                    run_on_create: bool = True,
                    created_by: int = None) -> int:
        """Create a new auto-tag rule. Returns rule ID."""
        result = self.execute('''
            INSERT INTO auto_tag_rules (name, entity_type, tag_id, conditions, match_mode, run_on_create, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name.strip(), entity_type, tag_id,
              json.dumps(conditions), match_mode, run_on_create, created_by),
            returning=True)
        return result['id']

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
        return self.execute(
            f'UPDATE auto_tag_rules SET {", ".join(updates)} WHERE id = %s',
            params,
        ) > 0

    def delete_rule(self, rule_id: int) -> bool:
        """Hard-delete a rule."""
        return self.execute('DELETE FROM auto_tag_rules WHERE id = %s', (rule_id,)) > 0
