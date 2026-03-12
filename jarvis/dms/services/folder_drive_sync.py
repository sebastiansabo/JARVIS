"""Google Drive folder sync — mirrors DMS folder tree to Google Drive.

For each dms_folder, creates a matching Google Drive folder and stores
the drive_folder_id + drive_folder_url on the row.

Structure in Drive mirrors JARVIS:
    Root (ROOT_FOLDER_ID) / DMS / Company / Year / Category / ...
"""
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.dms.services.folder_drive_sync')


class FolderDriveSyncService:
    """Syncs DMS folder hierarchy to Google Drive."""

    def __init__(self):
        self._repo = BaseRepository()

    def sync_folder_to_drive(self, folder_id: int) -> dict:
        """Sync a single folder (and its ancestors) to Google Drive.

        Walks up to root ensuring every ancestor has a Drive folder,
        then creates/finds the target folder.

        Returns dict with drive_folder_id, drive_folder_url.
        """
        try:
            service, root_folder_id = self._get_drive()
        except Exception as e:
            return {'success': False, 'error': str(e)}

        folder = self._repo.query_one(
            'SELECT * FROM dms_folders WHERE id = %s', (folder_id,))
        if not folder:
            return {'success': False, 'error': 'Folder not found'}

        # Already synced?
        if folder.get('drive_folder_id'):
            return {
                'success': True,
                'drive_folder_id': folder['drive_folder_id'],
                'drive_folder_url': folder['drive_folder_url'],
                'already_synced': True,
            }

        try:
            # Build ancestor chain (root → ... → parent → self)
            chain = self._get_ancestor_chain(folder_id)

            # DMS root in Drive
            from core.services.drive_service import find_or_create_folder
            dms_root = find_or_create_folder(service, 'DMS', root_folder_id)

            # Walk down chain, creating Drive folders as needed
            current_drive_parent = dms_root
            for node in chain:
                if node.get('drive_folder_id'):
                    current_drive_parent = node['drive_folder_id']
                    continue

                clean_name = self._clean_name(node['name'])
                drive_id = find_or_create_folder(
                    service, clean_name, current_drive_parent)
                drive_url = f"https://drive.google.com/drive/folders/{drive_id}"

                # Save to DB
                self._repo.execute('''
                    UPDATE dms_folders
                    SET drive_folder_id = %s, drive_folder_url = %s,
                        drive_synced_at = NOW()
                    WHERE id = %s
                ''', (drive_id, drive_url, node['id']))

                current_drive_parent = drive_id

            # Reload target folder
            updated = self._repo.query_one(
                'SELECT drive_folder_id, drive_folder_url FROM dms_folders WHERE id = %s',
                (folder_id,))

            return {
                'success': True,
                'drive_folder_id': updated['drive_folder_id'],
                'drive_folder_url': updated['drive_folder_url'],
            }

        except Exception:
            logger.exception('Drive sync failed for folder %d', folder_id)
            return {'success': False, 'error': 'Drive sync failed'}

    def sync_tree_to_drive(self, company_id: int | None = None) -> dict:
        """Sync entire folder tree (or one company's tree) to Drive.

        Returns summary with counts.
        """
        try:
            service, root_folder_id = self._get_drive()
        except Exception as e:
            return {'success': False, 'error': str(e)}

        from core.services.drive_service import find_or_create_folder

        conditions = ['f.deleted_at IS NULL']
        params: list = []
        if company_id:
            conditions.append('f.company_id = %s')
            params.append(company_id)

        folders = self._repo.query_all(f'''
            SELECT f.id, f.name, f.parent_id, f.depth, f.drive_folder_id
            FROM dms_folders f
            WHERE {" AND ".join(conditions)}
            ORDER BY f.depth, f.sort_order, f.name
        ''', params or None)

        # DMS root in Drive
        dms_root = find_or_create_folder(service, 'DMS', root_folder_id)

        # Map folder_id → drive_folder_id
        drive_map: dict[int, str] = {}
        synced = 0
        skipped = 0
        errors = 0

        for f in folders:
            if f.get('drive_folder_id'):
                drive_map[f['id']] = f['drive_folder_id']
                skipped += 1
                continue

            # Determine Drive parent
            if f['parent_id'] and f['parent_id'] in drive_map:
                drive_parent = drive_map[f['parent_id']]
            elif f['depth'] == 0:
                drive_parent = dms_root
            else:
                # Parent not synced yet — skip, will be caught in next pass
                errors += 1
                continue

            try:
                clean_name = self._clean_name(f['name'])
                drive_id = find_or_create_folder(service, clean_name, drive_parent)
                drive_url = f"https://drive.google.com/drive/folders/{drive_id}"

                self._repo.execute('''
                    UPDATE dms_folders
                    SET drive_folder_id = %s, drive_folder_url = %s,
                        drive_synced_at = NOW()
                    WHERE id = %s
                ''', (drive_id, drive_url, f['id']))

                drive_map[f['id']] = drive_id
                synced += 1
            except Exception:
                logger.warning('Failed to sync folder %d to Drive', f['id'])
                errors += 1

        return {
            'success': True,
            'total': len(folders),
            'synced': synced,
            'skipped': skipped,
            'errors': errors,
        }

    def get_or_create_drive_folder(self, folder_id: int) -> str | None:
        """Get Drive folder ID for a JARVIS folder, creating if needed.

        Used by document upload to place files in the right Drive folder.
        Returns drive_folder_id or None if Drive unavailable.
        """
        folder = self._repo.query_one(
            'SELECT drive_folder_id FROM dms_folders WHERE id = %s',
            (folder_id,))
        if not folder:
            return None
        if folder.get('drive_folder_id'):
            return folder['drive_folder_id']

        result = self.sync_folder_to_drive(folder_id)
        return result.get('drive_folder_id')

    # ── Helpers ──

    def _get_drive(self):
        """Get Drive service + root folder ID."""
        from core.services.drive_service import get_drive_service, ROOT_FOLDER_ID
        service = get_drive_service()
        return service, ROOT_FOLDER_ID

    def _get_ancestor_chain(self, folder_id: int) -> list[dict]:
        """Get ordered list from root → target folder."""
        folder = self._repo.query_one(
            'SELECT id, path FROM dms_folders WHERE id = %s', (folder_id,))
        if not folder:
            return []

        path = folder['path'].strip('/')
        if not path:
            return [folder]

        ids = [int(x) for x in path.split('/') if x]
        if not ids:
            return [folder]

        placeholders = ','.join(['%s'] * len(ids))
        rows = self._repo.query_all(f'''
            SELECT id, name, depth, drive_folder_id
            FROM dms_folders
            WHERE id IN ({placeholders})
            ORDER BY depth
        ''', ids)
        return rows

    @staticmethod
    def _clean_name(name: str) -> str:
        """Clean folder name for Google Drive (remove problematic chars)."""
        clean = ''.join(c for c in name if c.isalnum() or c in ' -_.()').strip()
        return clean or 'Unnamed'
