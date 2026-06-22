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

    # ── Report Config ──

    def get_config(self, company_id):
        rows = self.query_all(
            'SELECT * FROM bab_report_config WHERE company_id = %s ORDER BY sort_order',
            (company_id,))
        for row in rows:
            if row.get('row_type') == 'subtotal':
                row['indicator_ids'] = self.get_subtotal_refs(row['id'])
            else:
                row['indicator_ids'] = []
        return rows

    def save_config_row(self, company_id, sort_order, kst, group_name, item_label, konto_list, row_type='sum', subtotal_of=None, is_main_total=False):
        return self.execute(
            '''INSERT INTO bab_report_config (company_id, sort_order, kst, group_name, item_label, konto_list, row_type, subtotal_of, is_main_total)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *''',
            (company_id, sort_order, kst, group_name, item_label, konto_list, row_type, subtotal_of, is_main_total),
            returning=True)

    def update_config_row(self, row_id, sort_order, kst, group_name, item_label, konto_list, row_type='sum', subtotal_of=None, is_main_total=False):
        return self.execute(
            '''UPDATE bab_report_config
               SET sort_order = %s, kst = %s, group_name = %s, item_label = %s,
                   konto_list = %s, row_type = %s, subtotal_of = %s, is_main_total = %s, updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (sort_order, kst, group_name, item_label, konto_list, row_type, subtotal_of, is_main_total, row_id),
            returning=True)

    def delete_config_row(self, row_id):
        return self.execute('DELETE FROM bab_report_config WHERE id = %s', (row_id,))

    def get_subtotal_refs(self, subtotal_row_id):
        """Get indicator IDs referenced by a subtotal row."""
        return [r['indicator_row_id'] for r in self.query_all(
            'SELECT indicator_row_id FROM bab_subtotal_refs WHERE subtotal_row_id = %s',
            (subtotal_row_id,))]

    def set_subtotal_refs(self, subtotal_row_id, indicator_ids):
        """Replace all indicator refs for a subtotal row (transactional)."""
        def _work(cursor):
            cursor.execute('DELETE FROM bab_subtotal_refs WHERE subtotal_row_id = %s', (subtotal_row_id,))
            for ind_id in indicator_ids:
                cursor.execute(
                    'INSERT INTO bab_subtotal_refs (subtotal_row_id, indicator_row_id) VALUES (%s, %s) ON CONFLICT DO NOTHING',
                    (subtotal_row_id, ind_id))
            return len(indicator_ids)
        return self.execute_many(_work)

    def replace_config(self, company_id, rows):
        """Replace all config rows for a company in one transaction."""
        def _work(cursor):
            cursor.execute('DELETE FROM bab_report_config WHERE company_id = %s', (company_id,))
            for r in rows:
                cursor.execute(
                    '''INSERT INTO bab_report_config (company_id, sort_order, kst, group_name, item_label, konto_list, row_type, subtotal_of)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                    (company_id, r['sort_order'], r['kst'], r['group_name'], r['item_label'],
                     r['konto_list'], r.get('row_type', 'sum'), r.get('subtotal_of')))
            return len(rows)
        return self.execute_many(_work)
