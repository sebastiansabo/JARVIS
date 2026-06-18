"""Data access layer for BAB uploads, entries, and EUR rates."""
from core.base_repository import BaseRepository


class BabRepository(BaseRepository):

    # ── Uploads ──

    def get_upload(self, upload_id):
        return self.query_one(
            'SELECT * FROM bab_uploads WHERE id = %s', (upload_id,))

    def get_upload_by_period(self, company_id, year, month):
        return self.query_one(
            'SELECT * FROM bab_uploads WHERE company_id = %s AND period_year = %s AND period_month = %s',
            (company_id, year, month))

    def get_periods(self, company_id):
        """Return all uploads for a company — caller builds 12-month grid."""
        return self.query_all(
            'SELECT * FROM bab_uploads WHERE company_id = %s ORDER BY period_year DESC, period_month DESC',
            (company_id,))

    def list_uploads(self, company_id):
        return self.query_all(
            'SELECT * FROM bab_uploads WHERE company_id = %s ORDER BY uploaded_at DESC',
            (company_id,))

    def create_upload(self, company_id, year, month, filename, uploaded_by, row_count, status='ready'):
        return self.execute(
            '''INSERT INTO bab_uploads (company_id, period_year, period_month, filename, uploaded_by, row_count, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING *''',
            (company_id, year, month, filename, uploaded_by, row_count, status),
            returning=True)

    def update_upload_status(self, upload_id, status, error_msg=None):
        return self.execute(
            'UPDATE bab_uploads SET status = %s, error_msg = %s WHERE id = %s',
            (status, error_msg, upload_id))

    def reimport_upload(self, upload_id, filename, uploaded_by, row_count):
        return self.execute(
            '''UPDATE bab_uploads
               SET filename = %s, uploaded_by = %s, uploaded_at = NOW(),
                   row_count = %s, status = 'ready', error_msg = NULL,
                   import_count = import_count + 1
               WHERE id = %s
               RETURNING *''',
            (filename, uploaded_by, row_count, upload_id),
            returning=True)

    def delete_upload(self, upload_id):
        return self.execute(
            'DELETE FROM bab_uploads WHERE id = %s', (upload_id,))

    def lock_upload(self, upload_id, user_id):
        return self.execute(
            '''UPDATE bab_uploads SET locked_at = NOW(), locked_by = %s
               WHERE id = %s RETURNING *''',
            (user_id, upload_id), returning=True)

    def unlock_upload(self, upload_id, user_id):
        return self.execute(
            '''UPDATE bab_uploads
               SET locked_at = NULL, locked_by = NULL,
                   unlocked_at = NOW(), unlocked_by = %s
               WHERE id = %s RETURNING *''',
            (user_id, upload_id), returning=True)

    # ── Entries ──

    def insert_entries(self, upload_id, company_id, entries):
        """Bulk insert parsed BAB entries. Returns row count."""
        if not entries:
            return 0

        def _bulk(cursor):
            for e in entries:
                cursor.execute(
                    '''INSERT INTO bab_entries (upload_id, company_id, konto, konto_bez, saldo1, kostenstelle, kst_bez1)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                    (upload_id, company_id, e['konto'], e.get('konto_bez'),
                     e['saldo1'], e['kostenstelle'], e.get('kst_bez1')))
            return len(entries)

        return self.execute_many(_bulk)

    def delete_entries(self, upload_id):
        return self.execute(
            'DELETE FROM bab_entries WHERE upload_id = %s', (upload_id,))

    def get_entries(self, upload_id):
        return self.query_all(
            'SELECT * FROM bab_entries WHERE upload_id = %s', (upload_id,))

    # ── EUR Rates ──

    def get_eur_rate(self, company_id, year, month):
        return self.query_one(
            'SELECT * FROM bab_eur_rates WHERE company_id = %s AND period_year = %s AND period_month = %s',
            (company_id, year, month))

    def set_eur_rate(self, company_id, year, month, rate, user_id):
        return self.execute(
            '''INSERT INTO bab_eur_rates (company_id, period_year, period_month, eur_rate, set_by)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (company_id, period_year, period_month)
               DO UPDATE SET eur_rate = EXCLUDED.eur_rate, set_by = EXCLUDED.set_by, set_at = NOW()
               RETURNING *''',
            (company_id, year, month, rate, user_id),
            returning=True)
