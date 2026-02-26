"""Repository for dms_files table."""
from core.base_repository import BaseRepository


class FileRepository(BaseRepository):

    def get_by_document(self, document_id):
        return self.query_all('''
            SELECT f.*, u.name AS uploaded_by_name
            FROM dms_files f
            JOIN users u ON u.id = f.uploaded_by
            WHERE f.document_id = %s
            ORDER BY f.created_at DESC
        ''', (document_id,))

    def get_by_id(self, file_id):
        return self.query_one(
            'SELECT * FROM dms_files WHERE id = %s', (file_id,)
        )

    def create(self, document_id, file_name, storage_type, storage_uri, uploaded_by, **kwargs):
        return self.execute('''
            INSERT INTO dms_files (document_id, file_name, file_type, mime_type, file_size,
                                   storage_type, storage_uri, drive_file_id, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            document_id, file_name,
            kwargs.get('file_type'),
            kwargs.get('mime_type'),
            kwargs.get('file_size'),
            storage_type, storage_uri,
            kwargs.get('drive_file_id'),
            uploaded_by,
        ), returning=True)

    def delete(self, file_id):
        """Delete file record and return it (for storage cleanup)."""
        row = self.query_one('SELECT * FROM dms_files WHERE id = %s', (file_id,))
        if row:
            self.execute('DELETE FROM dms_files WHERE id = %s', (file_id,))
        return row
