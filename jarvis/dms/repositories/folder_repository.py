"""DMS Folder Repository — hierarchical folder management."""
from core.base_repository import BaseRepository


class FolderRepository(BaseRepository):

    def get_tree(self, company_id, parent_id=None, include_deleted=False):
        """Get folder tree for a company. If parent_id given, get subtree."""
        conditions = ['f.company_id = %s']
        params = [company_id]

        if not include_deleted:
            conditions.append('f.deleted_at IS NULL')

        if parent_id is not None:
            # Get subtree: all descendants of parent
            conditions.append("f.path LIKE (SELECT path || '%%' FROM dms_folders WHERE id = %s)")
            params.append(parent_id)
        else:
            # Root level only
            conditions.append('f.parent_id IS NULL')

        where = ' AND '.join(conditions)
        return self.query_all(f'''
            SELECT f.*,
                   u.name as created_by_name,
                   (SELECT COUNT(*) FROM dms_documents d
                    WHERE d.folder_id = f.id AND d.deleted_at IS NULL) as document_count,
                   (SELECT COUNT(*) FROM dms_folders sf
                    WHERE sf.parent_id = f.id AND sf.deleted_at IS NULL) as subfolder_count
            FROM dms_folders f
            LEFT JOIN users u ON u.id = f.created_by
            WHERE {where}
            ORDER BY f.sort_order, f.name
        ''', params)

    def get_children(self, folder_id, include_deleted=False):
        """Get direct children of a folder."""
        deleted_filter = '' if include_deleted else 'AND f.deleted_at IS NULL'
        return self.query_all(f'''
            SELECT f.*,
                   u.name as created_by_name,
                   (SELECT COUNT(*) FROM dms_documents d
                    WHERE d.folder_id = f.id AND d.deleted_at IS NULL) as document_count,
                   (SELECT COUNT(*) FROM dms_folders sf
                    WHERE sf.parent_id = f.id AND sf.deleted_at IS NULL) as subfolder_count
            FROM dms_folders f
            LEFT JOIN users u ON u.id = f.created_by
            WHERE f.parent_id = %s {deleted_filter}
            ORDER BY f.sort_order, f.name
        ''', (folder_id,))

    def get_by_id(self, folder_id):
        """Get single folder with stats."""
        return self.query_one('''
            SELECT f.*,
                   u.name as created_by_name,
                   (SELECT COUNT(*) FROM dms_documents d
                    WHERE d.folder_id = f.id AND d.deleted_at IS NULL) as document_count,
                   (SELECT COUNT(*) FROM dms_folders sf
                    WHERE sf.parent_id = f.id AND sf.deleted_at IS NULL) as subfolder_count
            FROM dms_folders f
            LEFT JOIN users u ON u.id = f.created_by
            WHERE f.id = %s
        ''', (folder_id,))

    def get_ancestors(self, folder_id):
        """Get all ancestors from root to parent (breadcrumb)."""
        folder = self.query_one(
            'SELECT path FROM dms_folders WHERE id = %s', (folder_id,))
        if not folder or folder['path'] == '/':
            return []

        # Path format: /1/5/12/ → extract IDs [1, 5, 12]
        ids = [int(x) for x in folder['path'].strip('/').split('/') if x]
        if not ids:
            return []

        placeholders = ','.join(['%s'] * len(ids))
        ancestors = self.query_all(f'''
            SELECT id, name, icon, color, depth
            FROM dms_folders
            WHERE id IN ({placeholders})
            ORDER BY depth
        ''', ids)
        return ancestors

    def get_descendants_ids(self, folder_id):
        """Get all descendant folder IDs (for cascade operations)."""
        folder = self.query_one(
            'SELECT path FROM dms_folders WHERE id = %s', (folder_id,))
        if not folder:
            return []

        path_prefix = folder['path']
        rows = self.query_all('''
            SELECT id FROM dms_folders WHERE path LIKE %s AND id != %s
        ''', (path_prefix + '%', folder_id))
        return [r['id'] for r in rows]

    def create(self, name, company_id, created_by, parent_id=None,
               description=None, icon='bi-folder', color='#6c757d',
               inherit_permissions=True, metadata=None):
        """Create a folder. Auto-computes path and depth."""
        import json as _json

        if parent_id:
            parent = self.query_one(
                'SELECT path, depth FROM dms_folders WHERE id = %s', (parent_id,))
            if not parent:
                raise ValueError('Parent folder not found')
            parent_path = parent['path']
            depth = parent['depth'] + 1
        else:
            parent_path = '/'
            depth = 0

        row = self.execute('''
            INSERT INTO dms_folders
                (name, description, icon, color, parent_id, path, depth,
                 company_id, created_by, inherit_permissions, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (name, description, icon, color, parent_id,
              parent_path,  # temporary — will update below
              depth, company_id, created_by, inherit_permissions,
              _json.dumps(metadata or {})), returning=True)

        # Now set the real path including this folder's ID
        real_path = f"{parent_path.rstrip('/')}/{row['id']}/"
        self.execute(
            'UPDATE dms_folders SET path = %s WHERE id = %s',
            (real_path, row['id']))
        row['path'] = real_path
        return row

    def update(self, folder_id, **fields):
        """Update folder fields. Does NOT handle reparenting (use move())."""
        allowed = {'name', 'description', 'icon', 'color',
                   'inherit_permissions', 'sort_order', 'metadata'}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_by_id(folder_id)

        import json as _json
        set_parts = []
        params = []
        for k, v in updates.items():
            set_parts.append(f'{k} = %s')
            params.append(_json.dumps(v) if k == 'metadata' else v)
        set_parts.append('updated_at = NOW()')
        params.append(folder_id)

        self.execute(
            f"UPDATE dms_folders SET {', '.join(set_parts)} WHERE id = %s",
            params)
        return self.get_by_id(folder_id)

    def move(self, folder_id, new_parent_id):
        """Move a folder to a new parent. Updates path for entire subtree."""
        folder = self.query_one(
            'SELECT * FROM dms_folders WHERE id = %s', (folder_id,))
        if not folder:
            raise ValueError('Folder not found')

        old_path = folder['path']

        if new_parent_id:
            new_parent = self.query_one(
                'SELECT path, depth FROM dms_folders WHERE id = %s', (new_parent_id,))
            if not new_parent:
                raise ValueError('Target parent not found')
            # Prevent moving into own subtree
            if new_parent['path'].startswith(old_path):
                raise ValueError('Cannot move folder into its own subtree')
            new_base_path = f"{new_parent['path'].rstrip('/')}/{folder_id}/"
            new_depth = new_parent['depth'] + 1
        else:
            new_base_path = f"/{folder_id}/"
            new_depth = 0

        depth_delta = new_depth - folder['depth']

        def _do_move(cursor):
            # Update self
            cursor.execute('''
                UPDATE dms_folders
                SET parent_id = %s, path = %s, depth = %s, updated_at = NOW()
                WHERE id = %s
            ''', (new_parent_id, new_base_path, new_depth, folder_id))
            # Update all descendants: replace old path prefix with new
            cursor.execute('''
                UPDATE dms_folders
                SET path = %s || substring(path from %s),
                    depth = depth + %s,
                    updated_at = NOW()
                WHERE path LIKE %s AND id != %s
            ''', (new_base_path, len(old_path) + 1, depth_delta,
                  old_path + '%', folder_id))
        self.execute_many(_do_move)
        return self.get_by_id(folder_id)

    def soft_delete(self, folder_id):
        """Soft-delete a folder (does NOT cascade to children — handle in route)."""
        return self.execute(
            'UPDATE dms_folders SET deleted_at = NOW() WHERE id = %s', (folder_id,))

    def restore(self, folder_id):
        """Restore a soft-deleted folder."""
        return self.execute(
            'UPDATE dms_folders SET deleted_at = NULL WHERE id = %s', (folder_id,))

    def permanent_delete(self, folder_id):
        """Permanently delete a folder (CASCADE removes children + ACL)."""
        return self.execute(
            'DELETE FROM dms_folders WHERE id = %s', (folder_id,))

    def reorder(self, folder_ids):
        """Bulk reorder folders by setting sort_order."""
        def _reorder(cursor):
            for idx, fid in enumerate(folder_ids):
                cursor.execute(
                    'UPDATE dms_folders SET sort_order = %s WHERE id = %s',
                    (idx, fid))
        self.execute_many(_reorder)
