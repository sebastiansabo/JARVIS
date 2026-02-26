"""CRM Import Batch Repository — tracks import history."""

from core.base_repository import BaseRepository


class ImportRepository(BaseRepository):

    def create(self, source_type, filename, uploaded_by):
        return self.execute(
            '''INSERT INTO crm_import_batches (source_type, filename, uploaded_by)
               VALUES (%s, %s, %s) RETURNING id''',
            (source_type, filename, uploaded_by), returning=True
        )

    def update_stats(self, batch_id, total_rows=0, new_rows=0, updated_rows=0,
                     skipped_rows=0, new_clients=0, matched_clients=0,
                     status='completed', error_log=None):
        import json
        self.execute(
            '''UPDATE crm_import_batches
               SET total_rows = %s, new_rows = %s, updated_rows = %s,
                   skipped_rows = %s, new_clients = %s, matched_clients = %s,
                   status = %s, error_log = %s
               WHERE id = %s''',
            (total_rows, new_rows, updated_rows, skipped_rows,
             new_clients, matched_clients, status,
             json.dumps(error_log or []), batch_id)
        )

    def list_batches(self, source_type=None, limit=20, offset=0):
        if source_type:
            return self.query_all(
                '''SELECT b.*, u.name as uploaded_by_name
                   FROM crm_import_batches b
                   LEFT JOIN users u ON u.id = b.uploaded_by
                   WHERE b.source_type = %s
                   ORDER BY b.created_at DESC LIMIT %s OFFSET %s''',
                (source_type, limit, offset)
            )
        return self.query_all(
            '''SELECT b.*, u.name as uploaded_by_name
               FROM crm_import_batches b
               LEFT JOIN users u ON u.id = b.uploaded_by
               ORDER BY b.created_at DESC LIMIT %s OFFSET %s''',
            (limit, offset)
        )

    def get_last_import(self, source_type):
        return self.query_one(
            '''SELECT * FROM crm_import_batches
               WHERE source_type = %s AND status = 'completed'
               ORDER BY created_at DESC LIMIT 1''',
            (source_type,)
        )
