"""Tag repository.

Handles all database operations for tags, tag groups, and entity tags.
"""

import logging
from typing import Optional

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.tags.repository')


class TagRepository(BaseRepository):

    # ---- Tag Groups ----

    def get_groups(self, active_only: bool = True) -> list:
        """Get all tag groups, optionally filtered by active status."""
        if active_only:
            return self.query_all('SELECT * FROM tag_groups WHERE is_active = TRUE ORDER BY sort_order, name')
        return self.query_all('SELECT * FROM tag_groups ORDER BY sort_order, name')

    def save_group(self, name: str, description: str = None, color: str = '#6c757d', sort_order: int = 0) -> int:
        """Create a new tag group. Returns the group ID."""
        result = self.execute('''
            INSERT INTO tag_groups (name, description, color, sort_order)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (name.strip(), description, color, sort_order), returning=True)
        return result['id']

    def update_group(self, group_id: int, **kwargs) -> bool:
        """Update a tag group. Returns True if updated."""
        allowed = {'name', 'description', 'color', 'sort_order', 'is_active'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                if key == 'name':
                    val = val.strip()
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(group_id)
        return self.execute(f'UPDATE tag_groups SET {", ".join(updates)} WHERE id = %s', params) > 0

    def delete_group(self, group_id: int) -> bool:
        """Soft-delete a tag group (set is_active=FALSE)."""
        return self.update_group(group_id, is_active=False)

    # ---- Tags ----

    def get_tags(self, user_id: int, group_id: int = None, active_only: bool = True) -> list:
        """Get tags visible to a user (global + user's private), joined with group info."""
        conditions = ['(t.is_global = TRUE OR t.created_by = %s)']
        params = [user_id]
        if active_only:
            conditions.append('t.is_active = TRUE')
        if group_id is not None:
            conditions.append('t.group_id = %s')
            params.append(group_id)
        where = ' AND '.join(conditions)
        return self.query_all(f'''
            SELECT t.*, g.name as group_name, g.color as group_color
            FROM tags t
            LEFT JOIN tag_groups g ON g.id = t.group_id AND g.is_active = TRUE
            WHERE {where}
            ORDER BY g.sort_order NULLS LAST, g.name NULLS LAST, t.sort_order, t.name
        ''', params)

    def get_tag(self, tag_id: int) -> Optional[dict]:
        """Get a single tag by ID with group info."""
        return self.query_one('''
            SELECT t.*, g.name as group_name, g.color as group_color
            FROM tags t
            LEFT JOIN tag_groups g ON g.id = t.group_id
            WHERE t.id = %s
        ''', (tag_id,))

    def save_tag(self, name: str, is_global: bool, created_by: int,
                 group_id: int = None, color: str = '#0d6efd',
                 icon: str = None, sort_order: int = 0) -> int:
        """Create a new tag. Returns the tag ID."""
        result = self.execute('''
            INSERT INTO tags (name, group_id, color, icon, is_global, created_by, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (name.strip(), group_id, color, icon, is_global, created_by, sort_order),
            returning=True)
        return result['id']

    def update_tag(self, tag_id: int, **kwargs) -> bool:
        """Update a tag. Returns True if updated."""
        allowed = {'name', 'group_id', 'color', 'icon', 'sort_order', 'is_active'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                if key == 'name' and val is not None:
                    val = val.strip()
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(tag_id)
        return self.execute(f'UPDATE tags SET {", ".join(updates)} WHERE id = %s', params) > 0

    def delete_tag(self, tag_id: int) -> bool:
        """Soft-delete a tag (set is_active=FALSE)."""
        return self.update_tag(tag_id, is_active=False)

    # ---- Entity Tags ----

    def get_entity_tags(self, entity_type: str, entity_id: int, user_id: int) -> list:
        """Get all tags for an entity visible to the user."""
        return self.query_all('''
            SELECT t.id, t.name, t.color, t.icon, t.is_global, t.group_id,
                   g.name as group_name, g.color as group_color,
                   et.tagged_by, et.created_at as tagged_at
            FROM entity_tags et
            JOIN tags t ON t.id = et.tag_id AND t.is_active = TRUE
            LEFT JOIN tag_groups g ON g.id = t.group_id AND g.is_active = TRUE
            WHERE et.entity_type = %s AND et.entity_id = %s
            AND (t.is_global = TRUE OR t.created_by = %s)
            ORDER BY g.sort_order NULLS LAST, t.sort_order, t.name
        ''', (entity_type, entity_id, user_id))

    def get_entities_tags_bulk(self, entity_type: str, entity_ids: list, user_id: int) -> dict:
        """Bulk fetch tags for multiple entities. Returns dict {entity_id: [tags]}."""
        if not entity_ids:
            return {}

        def _work(cursor):
            cursor.execute('''
                SELECT et.entity_id, t.id, t.name, t.color, t.icon, t.is_global, t.group_id,
                       g.name as group_name, g.color as group_color
                FROM entity_tags et
                JOIN tags t ON t.id = et.tag_id AND t.is_active = TRUE
                LEFT JOIN tag_groups g ON g.id = t.group_id AND g.is_active = TRUE
                WHERE et.entity_type = %s AND et.entity_id = ANY(%s)
                AND (t.is_global = TRUE OR t.created_by = %s)
                ORDER BY et.entity_id, g.sort_order NULLS LAST, t.sort_order, t.name
            ''', (entity_type, entity_ids, user_id))
            result = {}
            for row in cursor.fetchall():
                row_dict = dict(row)
                eid = row_dict.pop('entity_id')
                if eid not in result:
                    result[eid] = []
                result[eid].append(row_dict)
            return result

        return self.execute_many(_work)

    def add_entity_tag(self, tag_id: int, entity_type: str, entity_id: int, tagged_by: int) -> bool:
        """Tag an entity. Returns True if added, False if already exists."""
        result = self.execute('''
            INSERT INTO entity_tags (tag_id, entity_type, entity_id, tagged_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tag_id, entity_type, entity_id) DO NOTHING
            RETURNING id
        ''', (tag_id, entity_type, entity_id, tagged_by), returning=True)
        return result is not None

    def remove_entity_tag(self, tag_id: int, entity_type: str, entity_id: int) -> bool:
        """Remove a tag from an entity."""
        return self.execute('''
            DELETE FROM entity_tags
            WHERE tag_id = %s AND entity_type = %s AND entity_id = %s
        ''', (tag_id, entity_type, entity_id)) > 0

    def bulk_add_entity_tags(self, tag_id: int, entity_type: str, entity_ids: list, tagged_by: int) -> int:
        """Tag multiple entities at once. Returns count of newly tagged entities."""
        if not entity_ids:
            return 0

        def _work(cursor):
            values = [(tag_id, entity_type, eid, tagged_by) for eid in entity_ids]
            from psycopg2.extras import execute_values
            execute_values(cursor, '''
                INSERT INTO entity_tags (tag_id, entity_type, entity_id, tagged_by)
                VALUES %s
                ON CONFLICT (tag_id, entity_type, entity_id) DO NOTHING
            ''', values)
            return cursor.rowcount

        return self.execute_many(_work)

    def bulk_remove_entity_tags(self, tag_id: int, entity_type: str, entity_ids: list) -> int:
        """Remove a tag from multiple entities at once."""
        if not entity_ids:
            return 0
        return self.execute('''
            DELETE FROM entity_tags
            WHERE tag_id = %s AND entity_type = %s AND entity_id = ANY(%s)
        ''', (tag_id, entity_type, entity_ids))
