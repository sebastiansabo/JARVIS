"""Module menu repository.

Handles all database operations for module menu management.
"""

import time
import logging
from typing import Optional

from core.base_repository import BaseRepository
from core.cache import _cache_lock

logger = logging.getLogger('jarvis.core.settings.menus.repository')

# In-memory cache for module menu items
_module_menu_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 minutes TTL
}


def clear_module_menu_cache():
    """Clear the module menu cache. Call this after menu updates."""
    global _module_menu_cache
    with _cache_lock:
        _module_menu_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Module menu cache cleared')


class MenuRepository(BaseRepository):

    def _row_to_dict(self, row, include_timestamps=False) -> dict:
        """Convert a menu row to a dictionary."""
        item = {
            'id': row['id'],
            'parent_id': row['parent_id'],
            'module_key': row['module_key'],
            'name': row['name'],
            'description': row['description'],
            'icon': row['icon'],
            'url': row['url'],
            'color': row['color'],
            'status': row['status'],
            'sort_order': row['sort_order'],
        }
        if include_timestamps:
            item['created_at'] = row.get('created_at')
            item['updated_at'] = row.get('updated_at')
        return item

    def get_items(self, include_hidden: bool = False) -> list:
        """Get all module menu items organized hierarchically.

        Returns a list of parent modules with their children nested.
        """
        global _module_menu_cache

        # Check cache first (only for non-admin requests)
        if not include_hidden:
            with _cache_lock:
                if _module_menu_cache['data'] is not None and \
                   (time.time() - _module_menu_cache['timestamp']) < _module_menu_cache['ttl']:
                    return _module_menu_cache['data']

        if include_hidden:
            status_filter = ""
        else:
            status_filter = "WHERE status IN ('active', 'coming_soon')"

        rows = self.query_all(f'''
            SELECT id, parent_id, module_key, name, description, icon, url, color, status, sort_order
            FROM module_menu_items
            {status_filter}
            ORDER BY sort_order, name
        ''')

        # Build hierarchical structure
        items_by_id = {}
        parent_items = []

        for row in rows:
            item = self._row_to_dict(row)
            item['children'] = []
            items_by_id[row['id']] = item

            if row['parent_id'] is None:
                parent_items.append(item)

        # Attach children to parents
        for row in rows:
            if row['parent_id'] is not None and row['parent_id'] in items_by_id:
                items_by_id[row['parent_id']]['children'].append(items_by_id[row['id']])

        # Sort children by sort_order
        for item in parent_items:
            item['children'].sort(key=lambda x: (x['sort_order'], x['name']))

        # Cache the result (only for non-admin requests)
        if not include_hidden:
            with _cache_lock:
                _module_menu_cache['data'] = parent_items
                _module_menu_cache['timestamp'] = time.time()

        return parent_items

    def get_all_flat(self) -> list:
        """Get all module menu items as a flat list (for admin UI)."""
        rows = self.query_all('''
            SELECT id, parent_id, module_key, name, description, icon, url, color, status, sort_order,
                   created_at, updated_at
            FROM module_menu_items
            ORDER BY parent_id NULLS FIRST, sort_order, name
        ''')
        return [self._row_to_dict(row, include_timestamps=True) for row in rows]

    def get_by_id(self, item_id: int) -> Optional[dict]:
        """Get a single module menu item by ID."""
        row = self.query_one('''
            SELECT id, parent_id, module_key, name, description, icon, url, color, status, sort_order,
                   created_at, updated_at
            FROM module_menu_items
            WHERE id = %s
        ''', (item_id,))
        return self._row_to_dict(row, include_timestamps=True) if row else None

    def save(self, item_id: Optional[int], data: dict) -> Optional[dict]:
        """Create or update a module menu item."""
        def _work(cursor):
            if item_id:
                cursor.execute('''
                    UPDATE module_menu_items
                    SET parent_id = %s, module_key = %s, name = %s, description = %s,
                        icon = %s, url = %s, color = %s, status = %s, sort_order = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id
                ''', (
                    data.get('parent_id'),
                    data.get('module_key'),
                    data.get('name'),
                    data.get('description'),
                    data.get('icon', 'bi-grid'),
                    data.get('url'),
                    data.get('color', '#6c757d'),
                    data.get('status', 'active'),
                    data.get('sort_order', 0),
                    item_id
                ))
            else:
                cursor.execute('''
                    INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    data.get('parent_id'),
                    data.get('module_key'),
                    data.get('name'),
                    data.get('description'),
                    data.get('icon', 'bi-grid'),
                    data.get('url'),
                    data.get('color', '#6c757d'),
                    data.get('status', 'active'),
                    data.get('sort_order', 0)
                ))
            return cursor.fetchone()

        result = self.execute_many(_work)
        clear_module_menu_cache()
        return self.get_by_id(result['id']) if result else None

    def delete(self, item_id: int) -> bool:
        """Delete a module menu item and all its children (cascades)."""
        deleted = self.execute('DELETE FROM module_menu_items WHERE id = %s', (item_id,)) > 0
        if deleted:
            clear_module_menu_cache()
        return deleted

    def update_order(self, items: list) -> bool:
        """Update the sort order of multiple menu items at once.

        Args:
            items: List of dicts with 'id' and 'sort_order' keys
        """
        def _work(cursor):
            for item in items:
                cursor.execute('''
                    UPDATE module_menu_items
                    SET sort_order = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (item['sort_order'], item['id']))
        self.execute_many(_work)
        clear_module_menu_cache()
        return True
