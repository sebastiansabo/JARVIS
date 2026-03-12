"""DMS Folder ACL Repository — per-user/role folder permissions."""
from core.base_repository import BaseRepository


class FolderAclRepository(BaseRepository):

    def get_by_folder(self, folder_id):
        """Get all ACL entries for a folder."""
        return self.query_all('''
            SELECT a.*,
                   u.name as user_name, u.email as user_email,
                   r.name as role_name,
                   gu.name as granted_by_name
            FROM dms_folder_acl a
            LEFT JOIN users u ON u.id = a.user_id
            LEFT JOIN roles r ON r.id = a.role_id
            LEFT JOIN users gu ON gu.id = a.granted_by
            WHERE a.folder_id = %s
            ORDER BY a.role_id IS NULL, u.name, r.name
        ''', (folder_id,))

    def get_entry(self, folder_id, user_id=None, role_id=None):
        """Get a specific ACL entry."""
        if user_id:
            return self.query_one(
                'SELECT * FROM dms_folder_acl WHERE folder_id = %s AND user_id = %s',
                (folder_id, user_id))
        elif role_id:
            return self.query_one(
                'SELECT * FROM dms_folder_acl WHERE folder_id = %s AND role_id = %s',
                (folder_id, role_id))
        return None

    def set_acl(self, folder_id, granted_by, user_id=None, role_id=None,
                can_view=False, can_add=False, can_edit=False,
                can_delete=False, can_manage=False):
        """Set or update an ACL entry (upsert)."""
        if user_id:
            return self.execute('''
                INSERT INTO dms_folder_acl
                    (folder_id, user_id, can_view, can_add, can_edit, can_delete, can_manage, granted_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (folder_id, user_id) WHERE user_id IS NOT NULL
                DO UPDATE SET can_view = EXCLUDED.can_view,
                              can_add = EXCLUDED.can_add,
                              can_edit = EXCLUDED.can_edit,
                              can_delete = EXCLUDED.can_delete,
                              can_manage = EXCLUDED.can_manage,
                              granted_by = EXCLUDED.granted_by
                RETURNING *
            ''', (folder_id, user_id, can_view, can_add, can_edit,
                  can_delete, can_manage, granted_by), returning=True)
        elif role_id:
            return self.execute('''
                INSERT INTO dms_folder_acl
                    (folder_id, role_id, can_view, can_add, can_edit, can_delete, can_manage, granted_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (folder_id, role_id) WHERE role_id IS NOT NULL
                DO UPDATE SET can_view = EXCLUDED.can_view,
                              can_add = EXCLUDED.can_add,
                              can_edit = EXCLUDED.can_edit,
                              can_delete = EXCLUDED.can_delete,
                              can_manage = EXCLUDED.can_manage,
                              granted_by = EXCLUDED.granted_by
                RETURNING *
            ''', (folder_id, role_id, can_view, can_add, can_edit,
                  can_delete, can_manage, granted_by), returning=True)
        raise ValueError('Must specify user_id or role_id')

    def remove_acl(self, acl_id):
        """Remove an ACL entry."""
        return self.execute('DELETE FROM dms_folder_acl WHERE id = %s', (acl_id,))

    def resolve_permissions(self, user_id, role_id, role_name, folder_id):
        """Resolve effective permissions for a user on a folder.

        Walks up the folder tree checking:
        1. Admin/Manager bypass → full access
        2. User-specific ACL (highest priority)
        3. Role-based ACL
        4. Inherit from parent if inherit_permissions=TRUE
        """
        # Admin/Manager bypass
        if role_name in ('Admin', 'Manager'):
            return {
                'can_view': True, 'can_add': True, 'can_edit': True,
                'can_delete': True, 'can_manage': True, 'source': 'role_bypass'
            }

        # Get folder + ancestors path
        folder = self.query_one(
            'SELECT path, inherit_permissions FROM dms_folders WHERE id = %s',
            (folder_id,))
        if not folder:
            return self._no_access()

        # Build ancestor chain from this folder up to root
        path_parts = [int(x) for x in folder['path'].strip('/').split('/') if x]
        # path_parts = [root_id, ..., parent_id, this_folder_id]
        # Check from this folder upwards
        path_parts.reverse()

        for i, fid in enumerate(path_parts):
            # Check user-specific ACL first
            acl = self.query_one('''
                SELECT can_view, can_add, can_edit, can_delete, can_manage
                FROM dms_folder_acl WHERE folder_id = %s AND user_id = %s
            ''', (fid, user_id))
            if acl:
                acl['source'] = 'user_acl'
                acl['source_folder_id'] = fid
                return acl

            # Check role-based ACL
            acl = self.query_one('''
                SELECT can_view, can_add, can_edit, can_delete, can_manage
                FROM dms_folder_acl WHERE folder_id = %s AND role_id = %s
            ''', (fid, role_id))
            if acl:
                acl['source'] = 'role_acl'
                acl['source_folder_id'] = fid
                return acl

            # If this folder does not inherit, stop walking up
            if i == 0 and not folder['inherit_permissions']:
                break
            if i > 0:
                parent_folder = self.query_one(
                    'SELECT inherit_permissions FROM dms_folders WHERE id = %s', (fid,))
                if parent_folder and not parent_folder['inherit_permissions']:
                    break

        return self._no_access()

    def _no_access(self):
        return {
            'can_view': False, 'can_add': False, 'can_edit': False,
            'can_delete': False, 'can_manage': False, 'source': 'default'
        }

    def batch_set_acl(self, folder_id, entries, granted_by):
        """Set multiple ACL entries at once. entries = list of dicts."""
        def _batch(cursor):
            results = []
            for entry in entries:
                uid = entry.get('user_id')
                rid = entry.get('role_id')
                if uid:
                    cursor.execute('''
                        INSERT INTO dms_folder_acl
                            (folder_id, user_id, can_view, can_add, can_edit, can_delete, can_manage, granted_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (folder_id, user_id) WHERE user_id IS NOT NULL
                        DO UPDATE SET can_view = EXCLUDED.can_view,
                                      can_add = EXCLUDED.can_add,
                                      can_edit = EXCLUDED.can_edit,
                                      can_delete = EXCLUDED.can_delete,
                                      can_manage = EXCLUDED.can_manage,
                                      granted_by = EXCLUDED.granted_by
                        RETURNING *
                    ''', (folder_id, uid,
                          entry.get('can_view', False), entry.get('can_add', False),
                          entry.get('can_edit', False), entry.get('can_delete', False),
                          entry.get('can_manage', False), granted_by))
                elif rid:
                    cursor.execute('''
                        INSERT INTO dms_folder_acl
                            (folder_id, role_id, can_view, can_add, can_edit, can_delete, can_manage, granted_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (folder_id, role_id) WHERE role_id IS NOT NULL
                        DO UPDATE SET can_view = EXCLUDED.can_view,
                                      can_add = EXCLUDED.can_add,
                                      can_edit = EXCLUDED.can_edit,
                                      can_delete = EXCLUDED.can_delete,
                                      can_manage = EXCLUDED.can_manage,
                                      granted_by = EXCLUDED.granted_by
                        RETURNING *
                    ''', (folder_id, rid,
                          entry.get('can_view', False), entry.get('can_add', False),
                          entry.get('can_edit', False), entry.get('can_delete', False),
                          entry.get('can_manage', False), granted_by))
                row = cursor.fetchone()
                if row:
                    results.append(dict(row))
            return results
        return self.execute_many(_batch)
