"""Dropdown options and VAT rates repository.

Handles all database operations for dropdown options and VAT rate management.
"""

import logging
from typing import Optional

from core.base_repository import BaseRepository
from core.cache import create_cache, get_cache_lock, _is_cache_valid

logger = logging.getLogger('jarvis.core.settings.dropdowns.repository')

# Cache all dropdown options per type (near-static data, 5 min TTL)
_options_cache: dict[str, dict] = {}  # key: dropdown_type → cache entry
_options_all_cache = create_cache(ttl=300)  # cache for get_options(type=None)


class DropdownRepository(BaseRepository):

    # ---- VAT Rates ----

    def get_vat_rates(self, active_only: bool = False) -> list[dict]:
        """Get all VAT rates, optionally filtering for active only."""
        if active_only:
            return self.query_all('''
                SELECT id, name, rate, is_default, is_active, created_at
                FROM vat_rates WHERE is_active = TRUE ORDER BY rate DESC
            ''')
        return self.query_all('''
            SELECT id, name, rate, is_default, is_active, created_at
            FROM vat_rates ORDER BY rate DESC
        ''')

    def add_vat_rate(self, name: str, rate: float, is_default: bool = False, is_active: bool = True) -> int:
        """Add a new VAT rate. Returns the new rate ID."""
        def _work(cursor):
            if is_default:
                cursor.execute('UPDATE vat_rates SET is_default = FALSE WHERE is_default = TRUE')
            cursor.execute('''
                INSERT INTO vat_rates (name, rate, is_default, is_active)
                VALUES (%s, %s, %s, %s) RETURNING id
            ''', (name, rate, is_default, is_active))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update_vat_rate(self, rate_id: int, name: str = None, rate: float = None,
                        is_default: bool = None, is_active: bool = None) -> bool:
        """Update a VAT rate."""
        updates = []
        params = []
        if name is not None:
            updates.append('name = %s')
            params.append(name)
        if rate is not None:
            updates.append('rate = %s')
            params.append(rate)
        if is_default is not None:
            updates.append('is_default = %s')
            params.append(is_default)
        if is_active is not None:
            updates.append('is_active = %s')
            params.append(is_active)
        if not updates:
            return False
        params.append(rate_id)

        def _work(cursor):
            if is_default:
                cursor.execute('UPDATE vat_rates SET is_default = FALSE WHERE is_default = TRUE')
            cursor.execute(f'UPDATE vat_rates SET {", ".join(updates)} WHERE id = %s', params)
            return cursor.rowcount > 0
        return self.execute_many(_work)

    def delete_vat_rate(self, rate_id: int) -> bool:
        """Delete a VAT rate."""
        return self.execute('DELETE FROM vat_rates WHERE id = %s', (rate_id,)) > 0

    # ---- Dropdown Options ----

    def get_options(self, dropdown_type: str = None, active_only: bool = False) -> list[dict]:
        """Get dropdown options, optionally filtered by type and active status."""
        # Cache only non-filtered reads (most common call pattern)
        if not active_only:
            lock = get_cache_lock()
            if dropdown_type:
                with lock:
                    entry = _options_cache.get(dropdown_type)
                    if entry and _is_cache_valid(entry):
                        return entry['data']
            else:
                with lock:
                    if _is_cache_valid(_options_all_cache):
                        return _options_all_cache['data']

        query = 'SELECT * FROM dropdown_options WHERE 1=1'
        params = []
        if dropdown_type:
            query += ' AND dropdown_type = %s'
            params.append(dropdown_type)
        if active_only:
            query += ' AND is_active = TRUE'
        query += ' ORDER BY dropdown_type, sort_order, label'
        result = self.query_all(query, tuple(params) if params else None)

        if not active_only:
            lock = get_cache_lock()
            if dropdown_type:
                with lock:
                    _options_cache[dropdown_type] = {'data': result, 'timestamp': __import__('time').time(), 'ttl': 300}
            else:
                with lock:
                    _options_all_cache['data'] = result
                    _options_all_cache['timestamp'] = __import__('time').time()
        return result

    def _invalidate_options_cache(self, dropdown_type: str = None):
        """Clear cached options — call after any write operation."""
        lock = get_cache_lock()
        with lock:
            if dropdown_type and dropdown_type in _options_cache:
                del _options_cache[dropdown_type]
            _options_all_cache['data'] = None  # invalidate the all-types cache

    def get_option(self, option_id: int) -> Optional[dict]:
        """Get a specific dropdown option by ID."""
        return self.query_one('SELECT * FROM dropdown_options WHERE id = %s', (option_id,))

    def add_option(self, dropdown_type: str, value: str, label: str,
                   color: str = None, opacity: float = 0.7, sort_order: int = 0,
                   is_active: bool = True, notify_on_status: bool = False) -> int:
        """Add a new dropdown option. Returns the new option ID."""
        result = self.execute('''
            INSERT INTO dropdown_options (dropdown_type, value, label, color, opacity, sort_order, is_active, notify_on_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (dropdown_type, value, label, color, opacity, sort_order, is_active, notify_on_status), returning=True)
        self._invalidate_options_cache(dropdown_type)
        return result['id']

    def update_option(self, option_id: int, value: str = None, label: str = None,
                      color: str = None, opacity: float = None, sort_order: int = None,
                      is_active: bool = None, notify_on_status: bool = None) -> bool:
        """Update a dropdown option. Returns True if updated."""
        updates = []
        params = []
        if value is not None:
            updates.append('value = %s')
            params.append(value)
        if label is not None:
            updates.append('label = %s')
            params.append(label)
        if color is not None:
            updates.append('color = %s')
            params.append(color)
        if opacity is not None:
            updates.append('opacity = %s')
            params.append(opacity)
        if sort_order is not None:
            updates.append('sort_order = %s')
            params.append(sort_order)
        if is_active is not None:
            updates.append('is_active = %s')
            params.append(is_active)
        if notify_on_status is not None:
            updates.append('notify_on_status = %s')
            params.append(notify_on_status)
        if not updates:
            return False
        params.append(option_id)
        updated = self.execute(f"UPDATE dropdown_options SET {', '.join(updates)} WHERE id = %s", tuple(params)) > 0
        if updated:
            self._invalidate_options_cache()
        return updated

    def delete_option(self, option_id: int) -> bool:
        """Delete a dropdown option."""
        deleted = self.execute('DELETE FROM dropdown_options WHERE id = %s', (option_id,)) > 0
        if deleted:
            self._invalidate_options_cache()
        return deleted

    def should_notify_on_status(self, status_value: str, dropdown_type: str = 'invoice_status') -> bool:
        """Check if a status value should trigger notifications."""
        result = self.query_one('''
            SELECT notify_on_status FROM dropdown_options
            WHERE dropdown_type = %s AND value = %s AND is_active = TRUE
        ''', (dropdown_type, status_value))
        return result['notify_on_status'] if result and result['notify_on_status'] else False
