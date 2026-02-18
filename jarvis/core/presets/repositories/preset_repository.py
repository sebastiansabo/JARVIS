"""User filter presets repository.

Handles all database operations for user filter presets.
"""

import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.presets.repository')


class PresetRepository(BaseRepository):

    def get_presets(self, user_id: int, page_key: str) -> list:
        """Get all filter presets for a user on a specific page."""
        return self.query_all('''
            SELECT id, user_id, page_key, name, is_default, preset_data,
                   created_at, updated_at
            FROM user_filter_presets
            WHERE user_id = %s AND page_key = %s
            ORDER BY is_default DESC, name ASC
        ''', (user_id, page_key))

    def get_default(self, user_id: int, page_key: str) -> dict | None:
        """Get the default preset for a user on a specific page."""
        return self.query_one('''
            SELECT id, user_id, page_key, name, is_default, preset_data,
                   created_at, updated_at
            FROM user_filter_presets
            WHERE user_id = %s AND page_key = %s AND is_default = TRUE
            LIMIT 1
        ''', (user_id, page_key))

    def save(self, user_id: int, page_key: str, name: str, preset_data: dict, is_default: bool = False) -> int:
        """Create a new filter preset. Returns preset id."""
        def _work(cursor):
            if is_default:
                cursor.execute('''
                    UPDATE user_filter_presets SET is_default = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND page_key = %s AND is_default = TRUE
                ''', (user_id, page_key))

            cursor.execute('''
                INSERT INTO user_filter_presets (user_id, page_key, name, preset_data, is_default)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                RETURNING id
            ''', (user_id, page_key, name, json.dumps(preset_data), is_default))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update(self, preset_id: int, user_id: int, name: str = None,
               preset_data: dict = None, is_default: bool = None) -> bool:
        """Update an existing preset. Returns True if found and updated."""
        def _work(cursor):
            cursor.execute('SELECT page_key FROM user_filter_presets WHERE id = %s AND user_id = %s', (preset_id, user_id))
            row = cursor.fetchone()
            if not row:
                return False

            page_key = row['page_key']

            if is_default:
                cursor.execute('''
                    UPDATE user_filter_presets SET is_default = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND page_key = %s AND is_default = TRUE AND id != %s
                ''', (user_id, page_key, preset_id))

            updates = ['updated_at = CURRENT_TIMESTAMP']
            params = []
            if name is not None:
                updates.append('name = %s')
                params.append(name)
            if preset_data is not None:
                updates.append('preset_data = %s::jsonb')
                params.append(json.dumps(preset_data))
            if is_default is not None:
                updates.append('is_default = %s')
                params.append(is_default)

            params.extend([preset_id, user_id])
            cursor.execute(f'''
                UPDATE user_filter_presets SET {', '.join(updates)}
                WHERE id = %s AND user_id = %s
            ''', params)
            return True
        return self.execute_many(_work)

    def delete(self, preset_id: int, user_id: int) -> bool:
        """Delete a preset. Returns True if found and deleted."""
        rowcount = self.execute(
            'DELETE FROM user_filter_presets WHERE id = %s AND user_id = %s',
            (preset_id, user_id)
        )
        return rowcount > 0
