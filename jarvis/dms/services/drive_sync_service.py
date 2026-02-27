"""Google Drive sync service for DMS documents.

Uses existing drive_service.py infrastructure to sync document files
to Google Drive with folder structure: Root / DMS / Company / Year / Category / DocTitle /
"""
import logging
import time
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.dms.services.drive_sync')

# Max file size for sync (25 MB, matches document_service.py)
MAX_SYNC_FILE_SIZE = 25 * 1024 * 1024

# Cache drive availability for 5 minutes
_drive_available_cache = {'available': None, 'checked_at': 0}
_DRIVE_CACHE_TTL = 300


class DriveSyncRepository(BaseRepository):
    """Repository for dms_drive_sync table."""

    def get_by_document(self, document_id):
        return self.query_one(
            'SELECT * FROM dms_drive_sync WHERE document_id = %s',
            (document_id,)
        )

    def upsert(self, document_id, drive_folder_id, drive_folder_url=None,
               sync_status='synced'):
        return self.execute('''
            INSERT INTO dms_drive_sync (document_id, drive_folder_id, drive_folder_url,
                                        sync_status, last_synced_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (document_id) DO UPDATE SET
                drive_folder_id = EXCLUDED.drive_folder_id,
                drive_folder_url = EXCLUDED.drive_folder_url,
                sync_status = EXCLUDED.sync_status,
                last_synced_at = CURRENT_TIMESTAMP,
                error_message = NULL
            RETURNING *
        ''', (document_id, drive_folder_id, drive_folder_url, sync_status),
            returning=True)

    def set_error(self, document_id, error_message):
        """Set error status without overwriting existing folder references."""
        return self.execute('''
            INSERT INTO dms_drive_sync (document_id, drive_folder_id, sync_status, error_message)
            VALUES (%s, '', 'error', %s)
            ON CONFLICT (document_id) DO UPDATE SET
                sync_status = 'error',
                error_message = EXCLUDED.error_message
        ''', (document_id, error_message[:500] if error_message else None))

    def delete_by_document(self, document_id):
        return self.execute(
            'DELETE FROM dms_drive_sync WHERE document_id = %s',
            (document_id,)
        )


class DriveSyncService:
    """Syncs DMS document files to Google Drive."""

    def __init__(self):
        self._sync_repo = DriveSyncRepository()

    def get_sync_status(self, document_id):
        """Get current sync status for a document."""
        return self._sync_repo.get_by_document(document_id)

    def sync_document(self, document_id, doc_info, files):
        """Sync all local files for a document to Google Drive.

        Args:
            document_id: DMS document ID
            doc_info: dict with title, company_name, category_name, company_id
            files: list of file rows from dms_files (with storage_type, storage_uri, etc.)

        Returns:
            dict with sync results
        """
        import os
        import io

        try:
            from core.services.drive_service import (
                get_drive_service, find_or_create_folder, ROOT_FOLDER_ID
            )
            from googleapiclient.http import MediaIoBaseUpload
        except ImportError:
            return {'success': False, 'error': 'Google Drive libraries not installed'}

        try:
            service = get_drive_service()
        except Exception:
            logger.warning('Drive auth failed for document %s', document_id)
            self._sync_repo.set_error(document_id, 'Google Drive authentication failed')
            return {'success': False, 'error': 'Google Drive authentication failed'}

        try:
            from datetime import datetime

            # Build folder: Root / DMS / Company / Year / Category / DocTitle
            dms_folder = find_or_create_folder(service, 'DMS', ROOT_FOLDER_ID)

            company_name = doc_info.get('company_name') or f"Company-{doc_info.get('company_id', 0)}"
            clean_company = ''.join(c for c in company_name if c.isalnum() or c in ' -_').strip() or 'Unknown'
            company_folder = find_or_create_folder(service, clean_company, dms_folder)

            # Year from doc_date, fallback to created_at, then current year
            year_str = str(datetime.now().year)
            for date_field in ('doc_date', 'created_at'):
                val = doc_info.get(date_field)
                if val:
                    year_str = str(val)[:4]
                    break
            year_folder = find_or_create_folder(service, year_str, company_folder)

            category_name = doc_info.get('category_name') or 'Uncategorized'
            clean_category = ''.join(c for c in category_name if c.isalnum() or c in ' -_').strip() or 'General'
            category_folder = find_or_create_folder(service, clean_category, year_folder)

            doc_title = doc_info.get('title', f"Doc-{document_id}")
            clean_title = ''.join(c for c in doc_title if c.isalnum() or c in ' -_').strip() or f"Doc-{document_id}"
            doc_folder = find_or_create_folder(service, clean_title, category_folder)

            folder_url = f"https://drive.google.com/drive/folders/{doc_folder}"

            # Upload each local file that isn't already on Drive
            uploaded = []
            skipped = []
            errors = []

            upload_base = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'static', 'uploads', 'dms'
            )

            for f in files:
                # Skip files already on Drive
                if f.get('storage_type') == 'drive' or f.get('drive_file_id'):
                    skipped.append(f['file_name'])
                    continue

                if f.get('storage_type') != 'local' or not f.get('storage_uri'):
                    skipped.append(f['file_name'])
                    continue

                # Resolve local path
                local_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    f['storage_uri'].lstrip('/')
                )
                local_path = os.path.realpath(local_path)

                # Security check
                if not local_path.startswith(os.path.realpath(upload_base)):
                    errors.append({'file': f['file_name'], 'error': 'Invalid path'})
                    continue

                if not os.path.exists(local_path):
                    errors.append({'file': f['file_name'], 'error': 'File not found on disk'})
                    continue

                # File size check
                file_size = os.path.getsize(local_path)
                if file_size > MAX_SYNC_FILE_SIZE:
                    errors.append({'file': f['file_name'], 'error': 'File too large for sync'})
                    continue

                try:
                    with open(local_path, 'rb') as fh:
                        file_bytes = fh.read()

                    mime_type = f.get('mime_type') or 'application/octet-stream'
                    media = MediaIoBaseUpload(
                        io.BytesIO(file_bytes), mimetype=mime_type, resumable=True
                    )
                    drive_file = service.files().create(
                        body={'name': f['file_name'], 'parents': [doc_folder]},
                        media_body=media,
                        fields='id, webViewLink',
                        supportsAllDrives=True,
                    ).execute()

                    drive_link = drive_file.get(
                        'webViewLink',
                        f"https://drive.google.com/file/d/{drive_file['id']}/view"
                    )

                    # Update file record with Drive info
                    from core.database import get_db, get_cursor, release_db
                    conn = get_db()
                    try:
                        cursor = get_cursor(conn)
                        cursor.execute('''
                            UPDATE dms_files SET storage_type = 'drive',
                                storage_uri = %s, drive_file_id = %s
                            WHERE id = %s
                        ''', (drive_link, drive_file.get('id'), f['id']))
                        conn.commit()
                    finally:
                        release_db(conn)

                    uploaded.append(f['file_name'])

                except Exception:
                    logger.warning('Failed to upload %s', f['file_name'])
                    errors.append({'file': f['file_name'], 'error': 'Upload failed'})

            # Save sync record
            self._sync_repo.upsert(
                document_id, doc_folder, folder_url,
                'synced' if not errors else 'partial'
            )

            return {
                'success': True,
                'folder_url': folder_url,
                'uploaded': uploaded,
                'skipped': skipped,
                'errors': errors,
            }

        except Exception:
            logger.exception('Drive sync failed for document %s', document_id)
            self._sync_repo.set_error(document_id, 'Sync failed')
            return {'success': False, 'error': 'Sync failed'}

    def unsync_document(self, document_id):
        """Remove sync record (does NOT delete files from Drive)."""
        self._sync_repo.delete_by_document(document_id)
        return {'success': True}

    def check_drive_available(self):
        """Quick check if Drive API is reachable (cached for 5 minutes)."""
        now = time.time()
        if (_drive_available_cache['available'] is not None
                and now - _drive_available_cache['checked_at'] < _DRIVE_CACHE_TTL):
            return _drive_available_cache['available']

        try:
            from core.services.drive_service import check_drive_auth
            result = check_drive_auth()
        except Exception:
            result = False

        _drive_available_cache['available'] = result
        _drive_available_cache['checked_at'] = now
        return result
