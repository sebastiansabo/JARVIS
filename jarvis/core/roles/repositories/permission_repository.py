"""Permission repository.

Handles all database operations for permission management (v1 and v2).
"""

import logging
import time
from typing import Optional

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.roles.permission_repository')

_perm_cache = {}
_PERM_CACHE_TTL = 300  # 5 minutes


def _cache_get(key):
    cached = _perm_cache.get(key)
    if cached and (time.time() - cached[1]) < _PERM_CACHE_TTL:
        return cached[0]
    return None


def _cache_set(key, value):
    _perm_cache[key] = (value, time.time())


def _cache_clear():
    _perm_cache.clear()


class PermissionRepository(BaseRepository):

    # ---- Permissions v1 ----

    def get_all(self) -> list[dict]:
        """Get all permissions grouped by module."""
        permissions = self.query_all('''
            SELECT id, module_key, permission_key, label, description, icon, sort_order, parent_id
            FROM permissions
            ORDER BY module_key, sort_order, id
        ''')

        modules = {}
        for perm in permissions:
            module_key = perm['module_key']
            if module_key not in modules:
                modules[module_key] = {
                    'key': module_key,
                    'label': module_key.replace('_', ' ').title(),
                    'permissions': []
                }
            modules[module_key]['permissions'].append(perm)

        module_labels = {
            'system': 'System',
            'invoices': 'Invoices',
            'accounting': 'Accounting',
            'hr': 'HR Module'
        }
        for key, label in module_labels.items():
            if key in modules:
                modules[key]['label'] = label

        return list(modules.values())

    def get_flat(self) -> list[dict]:
        """Get all permissions as flat list."""
        return self.query_all('''
            SELECT id, module_key, permission_key, label, description, icon, sort_order, parent_id
            FROM permissions
            ORDER BY module_key, sort_order, id
        ''')

    def get_role_permissions(self, role_id: int) -> dict:
        """Get permissions for a role as dict: {module_key: {permission_key: bool}}."""
        cache_key = f'role_perms_{role_id}'
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        def _work(cursor):
            cursor.execute('''
                SELECT p.module_key, p.permission_key, rp.granted
                FROM role_permissions rp
                JOIN permissions p ON p.id = rp.permission_id
                WHERE rp.role_id = %s AND rp.granted = TRUE
            ''', (role_id,))
            result = {}
            for row in cursor.fetchall():
                module = row['module_key']
                perm = row['permission_key']
                if module not in result:
                    result[module] = {}
                result[module][perm] = True
            return result

        result = self.execute_many(_work)
        _cache_set(cache_key, result)
        return result

    def get_role_permissions_list(self, role_id: int) -> list[dict]:
        """Get permissions for a role as list of 'module.permission' strings."""
        cache_key = f'role_perms_list_{role_id}'
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        def _work(cursor):
            cursor.execute('''
                SELECT p.module_key, p.permission_key, p.label
                FROM role_permissions rp
                JOIN permissions p ON p.id = rp.permission_id
                WHERE rp.role_id = %s AND rp.granted = TRUE
                ORDER BY p.module_key, p.sort_order
            ''', (role_id,))
            result = []
            for row in cursor.fetchall():
                result.append({
                    'key': f"{row['module_key']}.{row['permission_key']}",
                    'module': row['module_key'],
                    'permission': row['permission_key'],
                    'label': row['label']
                })
            return result

        result = self.execute_many(_work)
        _cache_set(cache_key, result)
        return result

    def set_role_permissions(self, role_id: int, permissions: list[str]) -> bool:
        """Set permissions for a role. Also syncs to old boolean columns."""
        def _work(cursor):
            cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))
            for perm_str in permissions:
                parts = perm_str.split('.')
                if len(parts) != 2:
                    continue
                module_key, perm_key = parts
                cursor.execute('''
                    INSERT INTO role_permissions (role_id, permission_id, granted)
                    SELECT %s, id, TRUE FROM permissions
                    WHERE module_key = %s AND permission_key = %s
                    ON CONFLICT (role_id, permission_id) DO UPDATE SET granted = TRUE
                ''', (role_id, module_key, perm_key))
            self._sync_permissions_to_role_booleans(cursor, role_id, permissions)

        self.execute_many(_work)
        _cache_clear()
        return True

    def _sync_permissions_to_role_booleans(self, cursor, role_id: int, permissions: list[str]):
        """Sync new permission format to old boolean columns."""
        perm_set = set(permissions)
        bool_updates = {
            'can_access_settings': 'system.settings' in perm_set,
            'can_view_invoices': 'invoices.view' in perm_set,
            'can_add_invoices': 'invoices.add' in perm_set,
            'can_edit_invoices': 'invoices.edit' in perm_set,
            'can_delete_invoices': 'invoices.delete' in perm_set,
            'can_access_accounting': 'accounting.dashboard' in perm_set,
            'can_access_templates': 'accounting.templates' in perm_set,
            'can_access_connectors': 'accounting.connectors' in perm_set,
            'can_access_hr': 'hr.access' in perm_set,
            'is_hr_manager': 'hr.manager' in perm_set,
        }
        updates = ', '.join([f"{col} = %s" for col in bool_updates.keys()])
        values = list(bool_updates.values()) + [role_id]
        cursor.execute(f'UPDATE roles SET {updates} WHERE id = %s', values)

    def sync_role_from_booleans(self, role_id: int) -> bool:
        """Sync old boolean columns to new permissions table (for migration)."""
        def _work(cursor):
            cursor.execute('SELECT * FROM roles WHERE id = %s', (role_id,))
            role = cursor.fetchone()
            if not role:
                return False
            permission_map = {
                ('system', 'settings'): role.get('can_access_settings', False),
                ('invoices', 'view'): role.get('can_view_invoices', False),
                ('invoices', 'add'): role.get('can_add_invoices', False),
                ('invoices', 'edit'): role.get('can_edit_invoices', False),
                ('invoices', 'delete'): role.get('can_delete_invoices', False),
                ('accounting', 'dashboard'): role.get('can_access_accounting', False),
                ('accounting', 'templates'): role.get('can_access_templates', False),
                ('accounting', 'connectors'): role.get('can_access_connectors', False),
                ('hr', 'access'): role.get('can_access_hr', False),
                ('hr', 'manager'): role.get('is_hr_manager', False),
            }
            cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))
            for (module_key, perm_key), granted in permission_map.items():
                if granted:
                    cursor.execute('''
                        INSERT INTO role_permissions (role_id, permission_id, granted)
                        SELECT %s, id, TRUE FROM permissions
                        WHERE module_key = %s AND permission_key = %s
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role_id, module_key, perm_key))
            return True

        return self.execute_many(_work)

    # ---- Permissions v2 ----

    def get_matrix(self) -> dict:
        """Get all permissions organized for matrix display."""
        def _work(cursor):
            cursor.execute('''
                SELECT id, module_key, module_label, module_icon, entity_key, entity_label,
                       action_key, action_label, description, is_scope_based, sort_order
                FROM permissions_v2
                ORDER BY module_key, entity_key, sort_order
            ''')
            perms = cursor.fetchall()
            cursor.execute('SELECT id, name, description FROM roles ORDER BY id')
            roles = [dict(row) for row in cursor.fetchall()]
            return perms, roles

        perms, roles = self.execute_many(_work)

        modules = {}
        for p in perms:
            mod_key = p['module_key']
            ent_key = p['entity_key']
            if mod_key not in modules:
                modules[mod_key] = {
                    'key': mod_key,
                    'label': p['module_label'],
                    'icon': p['module_icon'],
                    'entities': {}
                }
            if ent_key not in modules[mod_key]['entities']:
                modules[mod_key]['entities'][ent_key] = {
                    'key': ent_key,
                    'label': p['entity_label'],
                    'actions': []
                }
            modules[mod_key]['entities'][ent_key]['actions'].append({
                'id': p['id'],
                'key': p['action_key'],
                'label': p['action_label'],
                'description': p['description'],
                'is_scope_based': p['is_scope_based']
            })

        modules_list = []
        for mod in modules.values():
            mod['entities'] = list(mod['entities'].values())
            modules_list.append(mod)

        return {
            'modules': modules_list,
            'roles': roles
        }

    def get_role_permissions_v2(self, role_id: int) -> dict:
        """Get all v2 permissions for a role."""
        def _work(cursor):
            cursor.execute('''
                SELECT permission_id, scope, granted
                FROM role_permissions_v2
                WHERE role_id = %s
            ''', (role_id,))
            result = {}
            for row in cursor.fetchall():
                result[row['permission_id']] = {
                    'scope': row['scope'],
                    'granted': row['granted']
                }
            return result

        return self.execute_many(_work)

    def get_all_role_permissions_v2(self) -> dict:
        """Get v2 permissions for all roles."""
        def _work(cursor):
            cursor.execute('''
                SELECT role_id, permission_id, scope, granted
                FROM role_permissions_v2
            ''')
            result = {}
            for row in cursor.fetchall():
                role_id = row['role_id']
                if role_id not in result:
                    result[role_id] = {}
                result[role_id][row['permission_id']] = {
                    'scope': row['scope'],
                    'granted': row['granted']
                }
            return result

        return self.execute_many(_work)

    def set_role_permission_v2(self, role_id: int, permission_id: int,
                               scope: str = None, granted: bool = None) -> bool:
        """Set a single v2 permission for a role."""
        def _work(cursor):
            cursor.execute('SELECT is_scope_based FROM permissions_v2 WHERE id = %s', (permission_id,))
            perm = cursor.fetchone()
            if not perm:
                return False
            is_scope_based = perm['is_scope_based']
            if is_scope_based:
                actual_scope = scope if scope else 'deny'
                actual_granted = actual_scope != 'deny'
            else:
                actual_granted = granted if granted is not None else False
                actual_scope = 'all' if actual_granted else 'deny'
            cursor.execute('''
                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (role_id, permission_id)
                DO UPDATE SET scope = %s, granted = %s, updated_at = CURRENT_TIMESTAMP
            ''', (role_id, permission_id, actual_scope, actual_granted, actual_scope, actual_granted))
            return True

        result = self.execute_many(_work)
        _cache_clear()
        return result

    def set_role_permissions_v2_bulk(self, role_id: int, permissions: dict) -> bool:
        """Set multiple v2 permissions for a role at once."""
        def _work(cursor):
            for perm_id, values in permissions.items():
                perm_id = int(perm_id)
                cursor.execute('SELECT is_scope_based FROM permissions_v2 WHERE id = %s', (perm_id,))
                perm = cursor.fetchone()
                if not perm:
                    continue
                is_scope_based = perm['is_scope_based']
                if is_scope_based:
                    s = values.get('scope', 'deny')
                    g = s != 'deny'
                else:
                    g = values.get('granted', False)
                    s = 'all' if g else 'deny'
                cursor.execute('''
                    INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (role_id, permission_id)
                    DO UPDATE SET scope = %s, granted = %s, updated_at = CURRENT_TIMESTAMP
                ''', (role_id, perm_id, s, g, s, g))
            self._sync_v2_permissions_to_booleans(cursor, role_id)

        self.execute_many(_work)
        _cache_clear()
        return True

    def _sync_v2_permissions_to_booleans(self, cursor, role_id: int):
        """Sync v2 permissions to old boolean columns for backward compatibility."""
        cursor.execute('''
            SELECT p.module_key, p.entity_key, p.action_key, rp.scope, rp.granted
            FROM role_permissions_v2 rp
            JOIN permissions_v2 p ON p.id = rp.permission_id
            WHERE rp.role_id = %s
        ''', (role_id,))
        perms = {}
        for row in cursor.fetchall():
            key = f"{row['module_key']}.{row['entity_key']}.{row['action_key']}"
            perms[key] = row['scope'] != 'deny' or row['granted']
        bool_updates = {
            'can_access_settings': perms.get('system.settings.access', False) or perms.get('system.settings.edit', False),
            'can_view_invoices': perms.get('invoices.records.view', False),
            'can_add_invoices': perms.get('invoices.records.add', False),
            'can_edit_invoices': perms.get('invoices.records.edit', False),
            'can_delete_invoices': perms.get('invoices.records.delete', False),
            'can_access_accounting': perms.get('accounting.dashboard.access', False),
            'can_access_templates': perms.get('invoices.templates.edit', False),
            'can_access_connectors': perms.get('accounting.connectors.access', False),
            'can_access_hr': perms.get('hr.module.access', False) or perms.get('hr.bonuses.view', False),
            'is_hr_manager': perms.get('hr.bonuses.view_amounts', False),
            'can_access_crm': perms.get('sales.module.access', False),
            'can_edit_crm': perms.get('sales.clients.edit', False) or perms.get('sales.deals.edit', False),
            'can_delete_crm': perms.get('sales.clients.delete', False) or perms.get('sales.deals.delete', False),
            'can_export_crm': perms.get('sales.clients.export', False) or perms.get('sales.deals.export', False),
        }
        updates = ', '.join([f"{col} = %s" for col in bool_updates.keys()])
        values = list(bool_updates.values()) + [role_id]
        cursor.execute(f'UPDATE roles SET {updates} WHERE id = %s', values)

    def check_permission_v2(self, role_id: int, module: str, entity: str, action: str) -> dict:
        """Check if a role has a specific v2 permission."""
        row = self.query_one('''
            SELECT rp.scope, rp.granted
            FROM role_permissions_v2 rp
            JOIN permissions_v2 p ON p.id = rp.permission_id
            WHERE rp.role_id = %s
              AND p.module_key = %s
              AND p.entity_key = %s
              AND p.action_key = %s
        ''', (role_id, module, entity, action))
        if row:
            has_perm = row['scope'] != 'deny' or row['granted']
            return {'has_permission': has_perm, 'scope': row['scope']}
        return {'has_permission': False, 'scope': 'deny'}
