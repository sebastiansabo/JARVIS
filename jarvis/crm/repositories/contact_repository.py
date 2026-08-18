"""CRM Contact Repository — CRUD for company contact persons (crm_client_contacts)."""

from core.base_repository import BaseRepository

_COLS = ('full_name', 'email', 'phone', 'driver_license_serie',
         'driver_license_number', 'driver_license_photo', 'driver_license_expiry')


class ContactRepository(BaseRepository):

    def list_by_client(self, client_id):
        return self.query_all(
            'SELECT * FROM crm_client_contacts WHERE client_id = %s '
            'ORDER BY is_primary DESC, full_name', (client_id,))

    def get(self, contact_id):
        return self.query_one('SELECT * FROM crm_client_contacts WHERE id = %s', (contact_id,))

    def create(self, client_id, data):
        first = not self.query_one(
            'SELECT 1 FROM crm_client_contacts WHERE client_id = %s LIMIT 1', (client_id,))
        # Insert as primary only when it's safely true (first contact for the
        # client — no existing TRUE row to collide with the partial unique
        # index). An explicit is_primary request on a later contact is applied
        # afterward via set_primary(), which atomically flips the old/new rows
        # in one statement instead of racing the index with a direct INSERT.
        wants_primary = bool(data.get('is_primary'))
        cols = ['client_id', 'is_primary'] + list(_COLS)
        vals = [client_id, first] + [data.get(c) for c in _COLS]
        placeholders = ', '.join(['%s'] * len(cols))
        row = self.execute(
            f"INSERT INTO crm_client_contacts ({', '.join(cols)}) "
            f"VALUES ({placeholders}) RETURNING *", tuple(vals), returning=True)
        if row and wants_primary and not first:
            self.set_primary(client_id, row['id'])
            row = self.get(row['id'])
        return row

    def update(self, contact_id, data):
        # is_primary is intentionally excluded from the generic column loop for
        # the TRUE case: setting it directly to TRUE here would collide with the
        # partial unique index whenever another contact for the same client is
        # still primary, so promotion routes through set_primary() below. An
        # explicit is_primary=False demote IS safe inline (it only ever removes
        # an index entry, never adds a colliding one), so it's folded into the
        # generic SET so a demote-only payload actually writes.
        demote = 'is_primary' in data and not data['is_primary']
        sets, params = [], []
        for col in _COLS:
            if col in data:
                sets.append(f'{col} = %s')
                params.append(data[col])
        if demote:
            sets.append('is_primary = FALSE')
        if not sets and 'is_primary' not in data:
            return None
        if sets:
            sets.append('updated_at = NOW()')
            params.append(contact_id)
            row = self.execute(
                f"UPDATE crm_client_contacts SET {', '.join(sets)} WHERE id = %s RETURNING *",
                tuple(params), returning=True)
        else:
            row = self.get(contact_id)
        if not row:
            return None
        if data.get('is_primary'):
            self.set_primary(row['client_id'], contact_id)
            row = self.get(contact_id)
        return row

    def set_primary(self, client_id, contact_id):
        # Two statements in one transaction, not a single
        # `SET is_primary = (id = %s) WHERE client_id = %s`: Postgres does not
        # guarantee a multi-row UPDATE checks a unique index only after all
        # rows are touched, so setting the new row TRUE before the old TRUE
        # row is cleared can spuriously violate idx_crm_client_contacts_primary
        # depending on physical row order (verified against the partial
        # unique index locally). Clearing first is always safe (removes index
        # entries); setting the target TRUE second is then safe too, since by
        # then no other row for this client is TRUE.
        def _work(cursor):
            cursor.execute(
                'UPDATE crm_client_contacts SET is_primary = FALSE '
                'WHERE client_id = %s AND is_primary = TRUE', (client_id,))
            cursor.execute(
                'UPDATE crm_client_contacts SET is_primary = TRUE, updated_at = NOW() '
                'WHERE id = %s AND client_id = %s', (contact_id, client_id))
        self.execute_many(_work)
