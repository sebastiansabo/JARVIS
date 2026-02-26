"""Business logic for DMS documents and file uploads."""
import io
import os
import logging
from dataclasses import dataclass
from typing import Any, Optional

from dms.repositories import DocumentRepository, FileRepository, CategoryRepository

logger = logging.getLogger('jarvis.dms.service')

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'gif'}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

MIME_MAP = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'tiff': 'image/tiff',
    'tif': 'image/tiff',
    'gif': 'image/gif',
}

# Local upload directory (fallback when Drive is not available)
LOCAL_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads', 'dms')


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 200


class DocumentService:
    """Orchestrates DMS business logic."""

    def __init__(self):
        self.doc_repo = DocumentRepository()
        self.file_repo = FileRepository()
        self.cat_repo = CategoryRepository()

    def validate_file(self, filename, file_size):
        """Validate file extension and size."""
        if not filename or '.' not in filename:
            return 'Invalid filename'
        ext = filename.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return f'File type .{ext} not allowed. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
        if file_size > MAX_FILE_SIZE:
            return f'File too large ({file_size // (1024*1024)}MB). Max: {MAX_FILE_SIZE // (1024*1024)}MB'
        return None

    def upload_file(self, document_id, file_bytes, filename, user_id):
        """Upload a file to Google Drive (with local fallback) and create DB record."""
        # Validate
        error = self.validate_file(filename, len(file_bytes))
        if error:
            return ServiceResult(success=False, error=error, status_code=400)

        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            return ServiceResult(success=False, error='Document not found', status_code=404)

        ext = filename.rsplit('.', 1)[-1].lower()
        mime_type = MIME_MAP.get(ext, 'application/octet-stream')

        # Try Google Drive upload
        storage_type, storage_uri, drive_file_id = self._upload_to_drive(
            file_bytes, filename, mime_type, doc
        )

        # Fallback to local
        if storage_type is None:
            storage_type, storage_uri = self._upload_to_local(file_bytes, filename, document_id)

        if not storage_uri:
            return ServiceResult(success=False, error='Failed to store file', status_code=500)

        # Create DB record
        try:
            row = self.file_repo.create(
                document_id, filename, storage_type, storage_uri, user_id,
                file_type=ext,
                mime_type=mime_type,
                file_size=len(file_bytes),
                drive_file_id=drive_file_id,
            )
            file_id = row['id'] if row else None
            return ServiceResult(success=True, data={
                'id': file_id,
                'file_name': filename,
                'file_type': ext,
                'mime_type': mime_type,
                'file_size': len(file_bytes),
                'storage_type': storage_type,
                'storage_uri': storage_uri,
            }, status_code=201)
        except Exception as e:
            logger.exception('Failed to create DMS file record')
            return ServiceResult(success=False, error='Failed to save file record', status_code=500)

    def delete_file(self, file_id):
        """Delete a file from storage and DB."""
        row = self.file_repo.delete(file_id)
        if not row:
            return ServiceResult(success=False, error='File not found', status_code=404)

        # Cleanup storage
        if row['storage_type'] == 'local' and row['storage_uri']:
            base_dir = os.path.realpath(LOCAL_UPLOAD_DIR)
            local_path = os.path.realpath(os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                row['storage_uri'].lstrip('/')
            ))
            if not local_path.startswith(base_dir):
                logger.warning('Path traversal blocked in delete: %s', local_path)
            else:
                try:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                except OSError as e:
                    logger.warning('Failed to delete local file %s: %s', local_path, e)

        return ServiceResult(success=True, data={'deleted': file_id})

    def _upload_to_drive(self, file_bytes, filename, mime_type, doc):
        """Try to upload to Google Drive. Returns (storage_type, uri, drive_file_id) or (None, None, None)."""
        try:
            from core.services.drive_service import get_drive_service, find_or_create_folder, ROOT_FOLDER_ID
            from googleapiclient.http import MediaIoBaseUpload

            service = get_drive_service()

            # Folder: Root / DMS / CompanyName / CategoryName / DocTitle
            dms_folder = find_or_create_folder(service, 'DMS', ROOT_FOLDER_ID)

            company_name = doc.get('company_name') or f"Company-{doc['company_id']}"
            clean_company = ''.join(c for c in company_name if c.isalnum() or c in ' -_').strip() or 'Unknown'
            company_folder = find_or_create_folder(service, clean_company, dms_folder)

            category_name = doc.get('category_name') or 'Uncategorized'
            clean_category = ''.join(c for c in category_name if c.isalnum() or c in ' -_').strip() or 'General'
            category_folder = find_or_create_folder(service, clean_category, company_folder)

            doc_title = doc.get('title', f"Doc-{doc['id']}")
            clean_title = ''.join(c for c in doc_title if c.isalnum() or c in ' -_').strip() or f"Doc-{doc['id']}"
            doc_folder = find_or_create_folder(service, clean_title, category_folder)

            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
            drive_file = service.files().create(
                body={'name': filename, 'parents': [doc_folder]},
                media_body=media,
                fields='id, webViewLink',
                supportsAllDrives=True,
            ).execute()

            drive_link = drive_file.get(
                'webViewLink', f"https://drive.google.com/file/d/{drive_file['id']}/view"
            )
            return 'drive', drive_link, drive_file.get('id')

        except FileNotFoundError:
            logger.info('Google Drive not configured — falling back to local storage')
            return None, None, None
        except Exception as e:
            logger.warning('Google Drive upload failed — falling back to local: %s', e)
            return None, None, None

    def _upload_to_local(self, file_bytes, filename, document_id):
        """Save file to local filesystem."""
        try:
            doc_dir = os.path.join(LOCAL_UPLOAD_DIR, str(document_id))
            os.makedirs(doc_dir, exist_ok=True)

            # Sanitize filename
            safe_name = ''.join(c for c in filename if c.isalnum() or c in '.-_ ').strip()
            if not safe_name:
                safe_name = f'file_{document_id}'

            # Prevent overwrite — append counter
            target = os.path.join(doc_dir, safe_name)
            base, ext = os.path.splitext(target)
            counter = 1
            while os.path.exists(target):
                target = f'{base}_{counter}{ext}'
                counter += 1

            with open(target, 'wb') as f:
                f.write(file_bytes)

            # Return relative URI from jarvis/ root
            rel_path = os.path.relpath(target, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return 'local', '/' + rel_path.replace(os.sep, '/')

        except Exception as e:
            logger.exception('Local file upload failed')
            return None, None
