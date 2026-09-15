"""Shared supplier-master data access: identity lookup, master CRUD, aliases, merge."""
from core.base_repository import BaseRepository
from core.suppliers.normalize import normalize_cui, normalize_nr_reg

_FUZZY_THRESHOLD = 0.55

_EDITABLE = (
    'name', 'supplier_type', 'cui', 'nr_reg_com', 'ref_no', 'address', 'city', 'county',
    'iban', 'bank_account', 'bank_name', 'phone', 'email', 'is_active',
    'konto_debit', 'konto_credit', 'klient',
    'gegenkonto_debit', 'gegenkonto_credit', 'kostenstelle_debit', 'kostenstelle_credit',
    'extbeleg_debit', 'extbeleg_credit',
)

# Per-(supplier, company) EuroFib posting config ("Table 2"). The first 9 fields also exist as
# flat columns on `suppliers` (the per-supplier DEFAULT/fallback); steuercode/text_template/
# belegart exist only on supplier_konto_config (no flat fallback for those).
KONTO_FIELDS = (
    'konto_debit', 'konto_credit', 'klient', 'gegenkonto_debit', 'gegenkonto_credit',
    'kostenstelle_debit', 'kostenstelle_credit', 'extbeleg_debit', 'extbeleg_credit',
    'steuercode', 'text_template', 'belegart',
)

# Subset of KONTO_FIELDS that also exists as a flat column on `suppliers` (per-supplier default).
_KONTO_FLAT_FIELDS = KONTO_FIELDS[:9]

# A supplier×company may hold at most this many named EuroFib presets.
MAX_PRESETS_PER_SUPPLIER_COMPANY = 5


class PresetLimitError(Exception):
    """Raised when creating a preset would exceed MAX_PRESETS_PER_SUPPLIER_COMPANY."""


class SupplierMasterRepository(BaseRepository):

    # ---- lookup protocol (consumed by SupplierResolver) ----
    def find_by_cui_normalized(self, cui):
        row = self.query_one("SELECT id FROM suppliers WHERE cui_normalized = %s AND is_active AND deleted_at IS NULL LIMIT 1", (cui,))
        return row['id'] if row else None

    def find_by_nr_reg_normalized(self, nr):
        row = self.query_one("SELECT id FROM suppliers WHERE nr_reg_normalized = %s AND is_active AND deleted_at IS NULL LIMIT 1", (nr,))
        return row['id'] if row else None

    def find_by_ref_no(self, ref):
        row = self.query_one("SELECT id FROM suppliers WHERE ref_no = %s AND is_active AND deleted_at IS NULL LIMIT 1", (ref,))
        return row['id'] if row else None

    def find_by_alias(self, name=None, cui_normalized=None):
        # Aliases of a soft-deleted supplier must not resolve back to it.
        row = self.query_one(
            """SELECT sa.supplier_id FROM supplier_aliases sa
               JOIN suppliers s ON s.id = sa.supplier_id AND s.deleted_at IS NULL
               WHERE (sa.alias_cui_normalized IS NOT NULL AND sa.alias_cui_normalized = %s)
                  OR (%s IS NOT NULL AND lower(sa.alias_name) = lower(%s))
               LIMIT 1""",
            (cui_normalized, name, name))
        return row['supplier_id'] if row else None

    def find_by_name_exact(self, name):
        row = self.query_one("SELECT id FROM suppliers WHERE lower(name) = lower(%s) AND is_active AND deleted_at IS NULL LIMIT 1", (name,))
        return row['id'] if row else None

    def find_by_fuzzy_name(self, name):
        row = self.query_one(
            """SELECT id, similarity(name, %s) AS score FROM suppliers
               WHERE is_active AND deleted_at IS NULL AND similarity(name, %s) >= %s
               ORDER BY score DESC LIMIT 1""",
            (name, name, _FUZZY_THRESHOLD))
        return (row['id'], float(row['score'])) if row else None

    # ---- master reads / writes ----
    def list_master(self, search=None, limit=100, offset=0, company_id=None, only_deleted=False):
        """List master suppliers. When company_id is given, each row carries that company's
        EFFECTIVE konto (supplier_konto_config child row, falling back to the flat suppliers.*
        defaults for the 9 flat-backed fields) plus has_company_config. Without company_id,
        behaves as before (flat columns only, no steuercode/text_template/belegart).

        only_deleted=True returns the soft-deleted suppliers instead (the 'Șterse' view), each
        row carrying deleted_by_name; deleted rows never appear in the default (active) list."""
        if only_deleted:
            where, params = "WHERE s.deleted_at IS NOT NULL", []
            if search:
                where += " AND (s.name ILIKE %s OR s.cui ILIKE %s OR s.ref_no ILIKE %s)"
                like = f"%{search}%"
                params += [like, like, like]
            params += [limit, offset]
            return self.query_all(
                "SELECT s.*, du.name AS deleted_by_name FROM suppliers s "
                "LEFT JOIN users du ON du.id = s.deleted_by "
                f"{where} ORDER BY s.deleted_at DESC LIMIT %s OFFSET %s", tuple(params))

        where, params = "WHERE s.is_active AND s.deleted_at IS NULL", []
        if search:
            where += " AND (s.name ILIKE %s OR s.cui ILIKE %s OR s.ref_no ILIKE %s)"
            like = f"%{search}%"
            params += [like, like, like]

        if company_id is not None:
            effective_cols = ', '.join(
                f"COALESCE(kc.{f}, s.{f}) AS {f}" for f in _KONTO_FLAT_FIELDS)
            child_only_cols = ', '.join(f"kc.{f} AS {f}" for f in KONTO_FIELDS[9:])
            # Master-list konto reflects the ACTIVE preset for the company (kc.is_active).
            sql = (
                f"SELECT s.*, {effective_cols}, {child_only_cols}, (kc.id IS NOT NULL) AS has_company_config "
                f"FROM suppliers s LEFT JOIN supplier_konto_config kc "
                f"ON kc.supplier_id = s.id AND kc.company_id = %s AND kc.is_active {where} "
                f"ORDER BY s.name LIMIT %s OFFSET %s")
            return self.query_all(sql, tuple([company_id] + params + [limit, offset]))

        params += [limit, offset]
        return self.query_all(f"SELECT s.* FROM suppliers s {where} ORDER BY s.name LIMIT %s OFFSET %s", tuple(params))

    def _apply_flat_fallback(self, child, supplier_id):
        """Merge a preset row (dict of KONTO_FIELDS, or None) with the flat suppliers.*
        defaults: a NULL/absent field on the preset falls back to the flat column for the 9
        flat-backed fields (steuercode/text_template/belegart have no flat fallback). Returns
        a plain {field: value} dict over KONTO_FIELDS."""
        flat = self.query_one(
            f"SELECT {', '.join(_KONTO_FLAT_FIELDS)} FROM suppliers WHERE id = %s",
            (supplier_id,)) or {}
        konto = {}
        for field in KONTO_FIELDS:
            child_val = child.get(field) if child else None
            konto[field] = child_val if child_val is not None else flat.get(field)
        return konto

    def get_effective_konto(self, supplier_id, company_id):
        """Effective Table-2 konto for (supplier, company): the ACTIVE preset (if any) resolved
        against the flat suppliers.* defaults field-by-field. NULL/absent fields on the preset
        fall back to the flat columns (steuercode/text_template/belegart stay NULL).

        Returns {'konto': {...KONTO_FIELDS...}, 'has_company_config': bool,
                 'konto_config_id': int|None, 'name': str|None}.
        """
        child = self.query_one(
            f"SELECT id, name, {', '.join(KONTO_FIELDS)} FROM supplier_konto_config "
            f"WHERE supplier_id = %s AND company_id = %s AND is_active",
            (supplier_id, company_id))
        return {
            'konto': self._apply_flat_fallback(child, supplier_id),
            'has_company_config': child is not None,
            'konto_config_id': child['id'] if child else None,
            'name': child['name'] if child else None,
        }

    def get_konto_by_id(self, preset_id):
        """Resolve a specific preset (by id) against its supplier's flat defaults. Returns
        {'konto': {...}, 'konto_config_id': int, 'name': str} or None if the preset is gone."""
        child = self.query_one(
            f"SELECT id, name, supplier_id, {', '.join(KONTO_FIELDS)} "
            f"FROM supplier_konto_config WHERE id = %s",
            (preset_id,))
        if not child:
            return None
        return {
            'konto': self._apply_flat_fallback(child, child['supplier_id']),
            'konto_config_id': child['id'],
            'name': child['name'],
        }

    # ---- preset CRUD (up to MAX_PRESETS_PER_SUPPLIER_COMPANY per supplier×company) ----
    def list_presets(self, supplier_id, company_id):
        """All presets for (supplier, company), active one first. Each row carries its raw
        KONTO_FIELDS (no flat fallback — the editor shows exactly what's stored)."""
        return self.query_all(
            f"SELECT id, name, is_active, {', '.join(KONTO_FIELDS)} FROM supplier_konto_config "
            f"WHERE supplier_id = %s AND company_id = %s ORDER BY is_active DESC, lower(name)",
            (supplier_id, company_id))

    def get_preset_owner(self, preset_id):
        """(supplier_id, company_id) dict for a preset, or None — used to validate overrides."""
        return self.query_one(
            "SELECT supplier_id, company_id FROM supplier_konto_config WHERE id = %s", (preset_id,))

    def create_preset(self, supplier_id, company_id, name, is_active=False, created_by=None, **fields):
        """Create a named preset. The first preset for a pair is always active; otherwise the
        caller decides. Activating one deactivates the rest atomically. Raises PresetLimitError
        if the pair already has MAX_PRESETS_PER_SUPPLIER_COMPANY presets. Unique-name violations
        surface as the driver's UniqueViolation. Returns the new preset id."""
        name = (name or '').strip() or 'Implicit'
        cols = [f for f in KONTO_FIELDS if f in fields]
        vals = [fields[f] for f in cols]

        def _work(cursor):
            cursor.execute(
                "SELECT COUNT(*) AS n FROM supplier_konto_config WHERE supplier_id = %s AND company_id = %s",
                (supplier_id, company_id))
            existing = cursor.fetchone()['n']
            if existing >= MAX_PRESETS_PER_SUPPLIER_COMPANY:
                raise PresetLimitError(
                    f"maximum {MAX_PRESETS_PER_SUPPLIER_COMPANY} presets per supplier/company reached")
            active = bool(is_active) or existing == 0  # first preset must be active
            if active:
                cursor.execute(
                    "UPDATE supplier_konto_config SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP "
                    "WHERE supplier_id = %s AND company_id = %s", (supplier_id, company_id))
            insert_cols = ['supplier_id', 'company_id', 'name', 'is_active', 'created_by'] + cols
            insert_vals = [supplier_id, company_id, name, active, created_by] + vals
            placeholders = ', '.join(['%s'] * len(insert_vals))
            cursor.execute(
                f"INSERT INTO supplier_konto_config ({', '.join(insert_cols)}) "
                f"VALUES ({placeholders}) RETURNING id",
                tuple(insert_vals))
            return cursor.fetchone()['id']

        return self.execute_many(_work)

    def update_preset(self, preset_id, name=None, is_active=None, **fields):
        """Update a preset's konto fields and/or name; is_active=True activates it (and
        deactivates its siblings). Activation is one-way here — pass is_active=False is ignored
        so the pair never ends up with zero active presets. Returns 1 if the preset exists."""
        cols = [f for f in KONTO_FIELDS if f in fields]

        def _work(cursor):
            cursor.execute(
                "SELECT supplier_id, company_id FROM supplier_konto_config WHERE id = %s", (preset_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            sets, vals = [], []
            for f in cols:
                sets.append(f"{f} = %s"); vals.append(fields[f])
            if name is not None:
                sets.append("name = %s"); vals.append((name or '').strip() or 'Implicit')
            if is_active is True:
                cursor.execute(
                    "UPDATE supplier_konto_config SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP "
                    "WHERE supplier_id = %s AND company_id = %s AND id <> %s",
                    (row['supplier_id'], row['company_id'], preset_id))
                sets.append("is_active = TRUE")
            if not sets:
                return 0
            sets.append("updated_at = CURRENT_TIMESTAMP")
            vals.append(preset_id)
            cursor.execute(f"UPDATE supplier_konto_config SET {', '.join(sets)} WHERE id = %s", tuple(vals))
            return 1

        return self.execute_many(_work)

    def set_active(self, preset_id):
        """Make `preset_id` the active preset for its (supplier, company), deactivating the
        rest atomically. Returns 1 if the preset exists, else 0."""
        def _work(cursor):
            cursor.execute(
                "SELECT supplier_id, company_id FROM supplier_konto_config WHERE id = %s", (preset_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            cursor.execute(
                "UPDATE supplier_konto_config SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP "
                "WHERE supplier_id = %s AND company_id = %s", (row['supplier_id'], row['company_id']))
            cursor.execute(
                "UPDATE supplier_konto_config SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (preset_id,))
            return 1
        return self.execute_many(_work)

    def delete_preset(self, preset_id, actor_user_id=None, actor_name=None):
        """Delete a preset (schema). If it was the active one and siblings remain, promote the
        first sibling (alphabetical) to active so the pair never has zero active presets.
        Overrides pointing at the deleted preset cascade away (ON DELETE CASCADE). Snapshots the
        row into supplier_audit_log before deleting (schemas are hard-deleted). Returns 1 if deleted."""
        def _work(cursor):
            cursor.execute(
                f"SELECT supplier_id, company_id, name, is_active, {', '.join(KONTO_FIELDS)} "
                f"FROM supplier_konto_config WHERE id = %s",
                (preset_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            cursor.execute("DELETE FROM supplier_konto_config WHERE id = %s", (preset_id,))
            if row['is_active']:
                cursor.execute(
                    "UPDATE supplier_konto_config SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = (SELECT id FROM supplier_konto_config "
                    "            WHERE supplier_id = %s AND company_id = %s ORDER BY lower(name) LIMIT 1)",
                    (row['supplier_id'], row['company_id']))
            self._log_audit(
                cursor, 'schema', preset_id, 'delete', actor_user_id, actor_name, row.get('company_id'),
                {'name': row.get('name'), 'supplier_id': row.get('supplier_id'),
                 'konto': {f: row.get(f) for f in KONTO_FIELDS}})
            return 1
        return self.execute_many(_work)

    # ---- soft delete (Furnizori) + deletion audit ----
    def _log_audit(self, cursor, entity_type, entity_id, action, actor_user_id, actor_name,
                   company_id, details):
        """Append a supplier_audit_log row inside the caller's transaction (shared cursor)."""
        import json
        cursor.execute(
            "INSERT INTO supplier_audit_log "
            "(entity_type, entity_id, action, actor_user_id, actor_name, company_id, details) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
            (entity_type, entity_id, action, actor_user_id, actor_name, company_id,
             json.dumps(details) if details is not None else None))

    def soft_delete_supplier(self, supplier_id, actor_user_id=None, actor_name=None):
        """Soft-delete a Furnizor: stamp deleted_at/deleted_by (orthogonal to is_active) and
        record an audit snapshot. No-op (returns 0) if the supplier is missing or already
        deleted. Excluded from every resolver lookup and the active list thereafter."""
        def _work(cursor):
            cursor.execute(
                "SELECT id, name, cui, company_id FROM suppliers WHERE id = %s AND deleted_at IS NULL",
                (supplier_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            cursor.execute(
                "UPDATE suppliers SET deleted_at = CURRENT_TIMESTAMP, deleted_by = %s, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (actor_user_id, supplier_id))
            self._log_audit(cursor, 'supplier', supplier_id, 'delete', actor_user_id, actor_name,
                            row.get('company_id'), {'name': row.get('name'), 'cui': row.get('cui')})
            return 1
        return self.execute_many(_work)

    def restore_supplier(self, supplier_id, actor_user_id=None, actor_name=None):
        """Restore a soft-deleted Furnizor (deleted_at→NULL) and record an audit row. No-op
        (returns 0) if the supplier is missing or not deleted. May raise a UniqueViolation if
        another active supplier has since claimed this one's normalized CUI — the caller should
        surface that as a conflict."""
        def _work(cursor):
            cursor.execute(
                "SELECT id, name, cui, company_id FROM suppliers WHERE id = %s AND deleted_at IS NOT NULL",
                (supplier_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            cursor.execute(
                "UPDATE suppliers SET deleted_at = NULL, deleted_by = NULL, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (supplier_id,))
            self._log_audit(cursor, 'supplier', supplier_id, 'restore', actor_user_id, actor_name,
                            row.get('company_id'), {'name': row.get('name'), 'cui': row.get('cui')})
            return 1
        return self.execute_many(_work)

    # ---- per-invoice preset override (Procesare worklist) ----
    def set_invoice_override(self, invoice_id, konto_config_id, created_by=None):
        """Pin `invoice_id` to a specific preset for export. Upsert on invoice_id."""
        return self.execute(
            """INSERT INTO invoice_konto_override (invoice_id, konto_config_id, created_by)
               VALUES (%s, %s, %s)
               ON CONFLICT (invoice_id) DO UPDATE SET
                   konto_config_id = EXCLUDED.konto_config_id, updated_at = CURRENT_TIMESTAMP""",
            (invoice_id, konto_config_id, created_by))

    def clear_invoice_override(self, invoice_id):
        """Drop an invoice's preset override → it falls back to the supplier's active preset."""
        return self.execute("DELETE FROM invoice_konto_override WHERE invoice_id = %s", (invoice_id,))

    def get_invoice_override(self, invoice_id):
        """The pinned konto_config_id for an invoice, or None if it uses the active preset."""
        row = self.query_one(
            "SELECT konto_config_id FROM invoice_konto_override WHERE invoice_id = %s", (invoice_id,))
        return row['konto_config_id'] if row else None

    def invoice_supplier_name(self, invoice_id):
        """The free-text supplier name on an invoice (used to resolve its master supplier)."""
        row = self.query_one("SELECT supplier FROM invoices WHERE id = %s", (invoice_id,))
        return row['supplier'] if row else None

    # ---- per-line schema (Phase 3) ----
    def get_invoice_override_full(self, invoice_id):
        """Per-invoice override state: {'konto_config_id': int|None, 'per_line': bool} or None."""
        row = self.query_one(
            "SELECT konto_config_id, per_line FROM invoice_konto_override WHERE invoice_id = %s",
            (invoice_id,))
        return {'konto_config_id': row['konto_config_id'], 'per_line': row['per_line']} if row else None

    def set_invoice_per_line(self, invoice_id, per_line, konto_config_id=None, created_by=None):
        """Set per-line mode for an invoice. `konto_config_id` is the base (credit) schema — NULL
        means fall back to the supplier's active preset. per_line False clears all line overrides."""
        def _work(cursor):
            cursor.execute(
                """INSERT INTO invoice_konto_override (invoice_id, konto_config_id, per_line, created_by)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (invoice_id) DO UPDATE SET
                       konto_config_id = EXCLUDED.konto_config_id, per_line = EXCLUDED.per_line,
                       updated_at = CURRENT_TIMESTAMP""",
                (invoice_id, konto_config_id, bool(per_line), created_by))
            if not per_line:
                cursor.execute("DELETE FROM invoice_line_konto_override WHERE invoice_id = %s", (invoice_id,))
            return True
        return self.execute_many(_work)

    def set_invoice_line_preset(self, invoice_id, line_index, konto_config_id, created_by=None):
        """Pin (or clear when konto_config_id is None) one line's preset."""
        if konto_config_id is None:
            return self.execute(
                "DELETE FROM invoice_line_konto_override WHERE invoice_id = %s AND line_index = %s",
                (invoice_id, line_index))
        return self.execute(
            """INSERT INTO invoice_line_konto_override (invoice_id, line_index, konto_config_id, created_by)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (invoice_id, line_index) DO UPDATE SET
                   konto_config_id = EXCLUDED.konto_config_id, updated_at = CURRENT_TIMESTAMP""",
            (invoice_id, line_index, konto_config_id, created_by))

    def list_line_overrides(self, invoice_id):
        """{line_index: konto_config_id} for an invoice's per-line schema choices."""
        rows = self.query_all(
            "SELECT line_index, konto_config_id FROM invoice_line_konto_override WHERE invoice_id = %s",
            (invoice_id,))
        return {r['line_index']: r['konto_config_id'] for r in rows}

    # ---- back-compat single-config writers (target the ACTIVE preset) ----
    def upsert_konto(self, supplier_id, company_id, created_by=None, **fields):
        """Back-compat: create/update the ACTIVE preset for (supplier, company). Creates the
        'Implicit' active preset if the pair has none yet. Only KONTO_FIELDS are written.
        Returns the affected preset id."""
        cols = [f for f in KONTO_FIELDS if f in fields]
        vals = [fields[f] for f in cols]

        def _work(cursor):
            cursor.execute(
                "SELECT id FROM supplier_konto_config "
                "WHERE supplier_id = %s AND company_id = %s AND is_active", (supplier_id, company_id))
            active = cursor.fetchone()
            if active:
                if cols:
                    set_sql = ', '.join(f"{f} = %s" for f in cols)
                    cursor.execute(
                        f"UPDATE supplier_konto_config SET {set_sql}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        tuple(vals + [active['id']]))
                return active['id']
            insert_cols = ['supplier_id', 'company_id', 'name', 'is_active', 'created_by'] + cols
            insert_vals = [supplier_id, company_id, 'Implicit', True, created_by] + vals
            placeholders = ', '.join(['%s'] * len(insert_vals))
            cursor.execute(
                f"INSERT INTO supplier_konto_config ({', '.join(insert_cols)}) "
                f"VALUES ({placeholders}) RETURNING id", tuple(insert_vals))
            return cursor.fetchone()['id']

        return self.execute_many(_work)

    def replicate_konto(self, supplier_id, fields, created_by=None, name='Implicit', is_active=True):
        """Copy a preset (by `name`) to EVERY company for this supplier, atomically. Upserts on
        (supplier, company, name): updates the same-named preset where it exists, else inserts a
        new one when the company is under the preset cap (companies at the cap without that name
        are skipped). When is_active, the copy becomes the active preset in each company. Only
        KONTO_FIELDS are written. Returns the number of companies written."""
        name = (name or '').strip() or 'Implicit'
        cols = [f for f in KONTO_FIELDS if f in fields]
        vals = [fields[f] for f in cols]

        def _work(cursor):
            cursor.execute("SELECT id FROM companies")
            company_ids = [r['id'] for r in cursor.fetchall()]
            written = 0
            for company_id in company_ids:
                if is_active:
                    cursor.execute(
                        "UPDATE supplier_konto_config SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP "
                        "WHERE supplier_id = %s AND company_id = %s", (supplier_id, company_id))
                cursor.execute(
                    "SELECT id FROM supplier_konto_config "
                    "WHERE supplier_id = %s AND company_id = %s AND name = %s",
                    (supplier_id, company_id, name))
                existing = cursor.fetchone()
                if existing:
                    set_sql = (', '.join(f"{f} = %s" for f in cols) + ', ') if cols else ''
                    cursor.execute(
                        f"UPDATE supplier_konto_config SET {set_sql}is_active = %s, updated_at = CURRENT_TIMESTAMP "
                        f"WHERE id = %s", tuple(vals + [is_active, existing['id']]))
                    written += 1
                    continue
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM supplier_konto_config WHERE supplier_id = %s AND company_id = %s",
                    (supplier_id, company_id))
                if cursor.fetchone()['n'] >= MAX_PRESETS_PER_SUPPLIER_COMPANY:
                    continue  # company at the cap and no same-named preset to overwrite → skip
                insert_cols = ['supplier_id', 'company_id', 'name', 'is_active', 'created_by'] + cols
                placeholders = ', '.join(['%s'] * len(insert_cols))
                cursor.execute(
                    f"INSERT INTO supplier_konto_config ({', '.join(insert_cols)}) VALUES ({placeholders})",
                    tuple([supplier_id, company_id, name, is_active, created_by] + vals))
                written += 1
            return written

        return self.execute_many(_work)

    def get_master(self, supplier_id):
        sup = self.query_one("SELECT * FROM suppliers WHERE id = %s", (supplier_id,))
        if sup:
            sup['aliases'] = self.query_all(
                "SELECT id, alias_name, alias_cui_normalized, source FROM supplier_aliases WHERE supplier_id = %s ORDER BY id",
                (supplier_id,))
        return sup

    def create_master(self, name, created_by=None, **fields):
        cui = fields.get('cui')
        nr = fields.get('nr_reg_com')
        cols = ['name', 'created_by', 'cui_normalized', 'nr_reg_normalized']
        vals = [name, created_by, normalize_cui(cui), normalize_nr_reg(nr)]
        for k in _EDITABLE:
            if k != 'name' and k in fields:
                cols.append(k)
                vals.append(fields[k])
        placeholders = ', '.join(['%s'] * len(vals))
        row = self.execute(
            f"INSERT INTO suppliers ({', '.join(cols)}) VALUES ({placeholders}) RETURNING id",
            tuple(vals), returning=True)
        return row['id']

    def update_master(self, supplier_id, **fields):
        sets, vals = [], []
        for k in _EDITABLE:
            if k in fields:
                sets.append(f"{k} = %s")
                vals.append(fields[k])
        if 'cui' in fields:
            sets.append("cui_normalized = %s"); vals.append(normalize_cui(fields['cui']))
        if 'nr_reg_com' in fields:
            sets.append("nr_reg_normalized = %s"); vals.append(normalize_nr_reg(fields['nr_reg_com']))
        if not sets:
            return 0
        sets.append("updated_at = CURRENT_TIMESTAMP")
        vals.append(supplier_id)
        return self.execute(f"UPDATE suppliers SET {', '.join(sets)} WHERE id = %s", tuple(vals))

    def add_alias(self, supplier_id, alias_name=None, alias_cui=None, source='manual', created_by=None):
        return self.execute(
            """INSERT INTO supplier_aliases (supplier_id, alias_name, alias_cui_normalized, source, created_by)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (supplier_id, alias_name, normalize_cui(alias_cui), source, created_by), returning=True)['id']

    def set_efactura_supplier_id(self, supplier_id, partner_name=None, partner_cif=None):
        """Bind all matching e-Factura rows (by name or CIF) to a master supplier."""
        ncui = normalize_cui(partner_cif)
        return self.execute(
            """UPDATE efactura_invoices SET supplier_id = %s
               WHERE supplier_id IS NULL
                 AND ( (%s IS NOT NULL AND lower(partner_name) = lower(%s))
                    OR (%s IS NOT NULL AND regexp_replace(COALESCE(partner_cif,''),'\\D','','g') = %s) )""",
            (supplier_id, partner_name, partner_name, ncui, ncui))

    def merge(self, survivor_id, duplicate_id, created_by=None):
        """Repoint aliases + efactura FKs from duplicate to survivor, alias the dup name, soft-delete dup."""
        def _work(cursor):
            cursor.execute("UPDATE supplier_aliases SET supplier_id = %s WHERE supplier_id = %s", (survivor_id, duplicate_id))
            cursor.execute("UPDATE efactura_invoices SET supplier_id = %s WHERE supplier_id = %s", (survivor_id, duplicate_id))
            cursor.execute("SELECT name, cui_normalized FROM suppliers WHERE id = %s", (duplicate_id,))
            dup = cursor.fetchone()
            if dup:
                cursor.execute(
                    """INSERT INTO supplier_aliases (supplier_id, alias_name, alias_cui_normalized, source, created_by)
                       VALUES (%s, %s, %s, 'merge', %s)""",
                    (survivor_id, dup['name'], dup['cui_normalized'], created_by))
            cursor.execute(
                """UPDATE suppliers
                   SET is_active = FALSE, cui_normalized = NULL, nr_reg_normalized = NULL, ref_no = NULL,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = %s""", (duplicate_id,))
            return True
        return self.execute_many(_work)

    # ---- worklist sources ----
    def unresolved_efactura(self, limit=200, company_id=None):
        sql = """SELECT DISTINCT partner_name, partner_cif FROM efactura_invoices
                 WHERE supplier_id IS NULL AND deleted_at IS NULL"""
        params = []
        if company_id is not None:
            sql += " AND company_id = %s"
            params.append(company_id)
        sql += " ORDER BY partner_name LIMIT %s"
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def list_efactura_partners(self, company_id=None, limit=500):
        """Distinct e-Factura SUPPLIER partners (direction='received') not yet linked to a master
        supplier — the candidate list for the "Sync cu e-Factura" import modal. Only received
        invoices are considered, so the partner is always the furnizor (never a client). Each row
        carries the invoice count. Optionally scoped to one company."""
        sql = """SELECT partner_name, partner_cif, COUNT(*) AS n
                 FROM efactura_invoices
                 WHERE supplier_id IS NULL AND deleted_at IS NULL AND direction = 'received'
                   AND partner_name IS NOT NULL AND partner_name <> ''"""
        params = []
        if company_id is not None:
            sql += " AND company_id = %s"
            params.append(company_id)
        sql += " GROUP BY partner_name, partner_cif ORDER BY partner_name LIMIT %s"
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def names_by_ids(self, ids):
        """Map {supplier_id: name} for the given ids — used to label the 'există deja' badge in
        the sync modal. Falsy/duplicate ids are dropped; an empty input returns {}."""
        ids = [i for i in {*ids} if i]
        if not ids:
            return {}
        rows = self.query_all("SELECT id, name FROM suppliers WHERE id = ANY(%s)", (ids,))
        return {r['id']: r['name'] for r in rows}

    def list_budgeted_invoices(self, company_id, company_name, start_date, end_date, limit=500,
                                status='Bugetata'):
        """Invoices in the given `status` (default 'Bugetata') allocated to `company_name`,
        within [start_date, end_date] on invoice_date, whose free-text supplier resolves (by
        exact name or alias) to a master supplier with a COMPLETE Table-2 konto config for
        `company_id` (all key posting fields non-empty). GROUP BY i.id collapses the allocation
        fan-out (an invoice can have multiple allocation rows for the same company, split
        across departments)."""
        # kc = the EFFECTIVE preset for each invoice: the per-invoice override if one is pinned
        # (invoice_konto_override), otherwise the supplier's active preset. The completeness gate
        # and the returned konto_config_id/konto_name all reflect that chosen preset.
        sql = """
            SELECT i.id, i.supplier, i.invoice_number, i.invoice_date, i.net_value,
                   i.invoice_value, i.value_ron, i.value_eur, i.currency, i.status,
                   i.subtract_vat,
                   MAX(ef.due_date) AS due_date,
                   -- EuroFib `text` = the first line's article name (e-Factura cbc:Name); fall back
                   -- to its description for AI-parsed invoices that carry only a description.
                   COALESCE(NULLIF(i.line_items->0->>'name', ''), i.line_items->0->>'description') AS line_description,
                   MIN(s.id) AS supplier_id,
                   kc.id AS konto_config_id,
                   kc.name AS konto_name,
                   (ov.konto_config_id IS NOT NULL) AS konto_overridden,
                   COALESCE(ov.per_line, FALSE) AS per_line,
                   i.line_items AS line_items_json
            FROM invoices i
            JOIN allocations a ON a.invoice_id = i.id AND lower(a.company) = lower(%s)
            JOIN suppliers s ON s.deleted_at IS NULL AND (
                lower(s.name) = lower(i.supplier)
                OR EXISTS (
                    SELECT 1 FROM supplier_aliases al
                    WHERE al.supplier_id = s.id AND lower(al.alias_name) = lower(i.supplier)
                )
            )
            LEFT JOIN invoice_konto_override ov ON ov.invoice_id = i.id
            JOIN supplier_konto_config kc
                ON kc.supplier_id = s.id AND kc.company_id = %s
               AND kc.id = COALESCE(
                       ov.konto_config_id,
                       (SELECT act.id FROM supplier_konto_config act
                        WHERE act.supplier_id = s.id AND act.company_id = %s AND act.is_active))
            -- e-Factura source carries the due date (data scadență) → valuta; null for parsed/manual
            LEFT JOIN efactura_invoices ef ON ef.jarvis_invoice_id = i.id
            WHERE lower(i.status) = lower(%s)
              AND i.deleted_at IS NULL
              AND i.invoice_date BETWEEN %s AND %s
              AND NULLIF(kc.konto_debit, '') IS NOT NULL
              AND NULLIF(kc.konto_credit, '') IS NOT NULL
              AND NULLIF(kc.klient, '') IS NOT NULL
              AND NULLIF(kc.steuercode, '') IS NOT NULL
              AND NULLIF(kc.belegart, '') IS NOT NULL
            GROUP BY i.id, i.supplier, i.invoice_number, i.invoice_date, i.net_value,
                     i.invoice_value, i.value_ron, i.value_eur, i.currency, i.status,
                     i.subtract_vat, i.line_items, kc.id, kc.name, ov.konto_config_id, ov.per_line
            ORDER BY i.invoice_date DESC, i.id DESC
            LIMIT %s
        """
        return self.query_all(sql, (company_name, company_id, company_id, status, start_date, end_date, limit))

    def mark_invoices_imported(self, invoice_ids):
        """Flip the given invoices from 'Bugetata' to 'Importat' after a successful EuroFib
        export. Only rows still in 'Bugetata' are touched — any invoice that changed status in
        the meantime (or was never Bugetata) is left alone. 'Importat' is deliberately distinct
        from the legacy 'processed' status. Returns the number of rows updated."""
        if not invoice_ids:
            return 0
        return self.execute(
            "UPDATE invoices SET status = 'Importat', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ANY(%s) AND lower(status) = 'bugetata'",
            (list(invoice_ids),))

    def unmark_imported_invoices(self, invoice_ids):
        """Revert the given invoices from 'Importat' back to 'Bugetata' (send them back to the
        In-lucru worklist). Only rows still in 'Importat' are touched. Returns rows updated."""
        if not invoice_ids:
            return 0
        return self.execute(
            "UPDATE invoices SET status = 'Bugetata', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ANY(%s) AND lower(status) = 'importat'",
            (list(invoice_ids),))

    def import_ready_ids(self, invoice_ids, company_id=None):
        """Of the given invoice ids, return those that are READY to export to EuroFib: status
        'Bugetata', not deleted, whose free-text supplier resolves (name/alias) to a master
        supplier with a COMPLETE active konto preset for a company the invoice is allocated to.
        When company_id is given, only that company counts; otherwise any allocated company does.
        Powers the Accounting "Pregătită de import" badge. Returns a list of invoice ids."""
        if not invoice_ids:
            return []
        rows = self.query_all(
            """
            SELECT DISTINCT i.id
            FROM invoices i
            JOIN allocations a ON a.invoice_id = i.id
            JOIN companies co ON lower(co.company) = lower(a.company)
            JOIN suppliers s ON s.deleted_at IS NULL AND (
                lower(s.name) = lower(i.supplier)
                OR EXISTS (SELECT 1 FROM supplier_aliases al
                           WHERE al.supplier_id = s.id AND lower(al.alias_name) = lower(i.supplier))
            )
            JOIN supplier_konto_config kc
                ON kc.supplier_id = s.id AND kc.company_id = co.id AND kc.is_active
            WHERE i.id = ANY(%s)
              AND i.deleted_at IS NULL
              AND lower(i.status) = 'bugetata'
              AND (%s IS NULL OR co.id = %s)
              AND NULLIF(kc.konto_debit, '') IS NOT NULL
              AND NULLIF(kc.konto_credit, '') IS NOT NULL
              AND NULLIF(kc.klient, '') IS NOT NULL
              AND NULLIF(kc.steuercode, '') IS NOT NULL
              AND NULLIF(kc.belegart, '') IS NOT NULL
            """,
            (list(invoice_ids), company_id, company_id))
        return [r['id'] for r in rows]

    def unresolved_invoice_suppliers(self, limit=200, company_name=None):
        if company_name is not None:
            # allocations can hold multiple rows per invoice for the same company (split across
            # departments) — DISTINCT (i.id, partner_name) before the count(*) so the JOIN's
            # fan-out doesn't inflate the per-supplier invoice count.
            sql = """SELECT partner_name, count(*) AS n FROM (
                         SELECT DISTINCT i.id, i.supplier AS partner_name
                         FROM invoices i
                         JOIN allocations a ON a.invoice_id = i.id AND lower(a.company) = lower(%s)
                         WHERE i.deleted_at IS NULL
                           AND NOT EXISTS (SELECT 1 FROM suppliers s WHERE lower(s.name) = lower(i.supplier) AND s.is_active AND s.deleted_at IS NULL)
                           AND NOT EXISTS (SELECT 1 FROM supplier_aliases al JOIN suppliers s2 ON s2.id = al.supplier_id
                                           WHERE lower(al.alias_name) = lower(i.supplier) AND s2.deleted_at IS NULL)
                     ) sub
                     GROUP BY partner_name ORDER BY n DESC LIMIT %s"""
            return self.query_all(sql, (company_name, limit))
        return self.query_all(
            """SELECT i.supplier AS partner_name, count(*) AS n
               FROM invoices i
               WHERE i.deleted_at IS NULL
                 AND NOT EXISTS (SELECT 1 FROM suppliers s WHERE lower(s.name) = lower(i.supplier) AND s.is_active AND s.deleted_at IS NULL)
                 AND NOT EXISTS (SELECT 1 FROM supplier_aliases a JOIN suppliers s2 ON s2.id = a.supplier_id
                                 WHERE lower(a.alias_name) = lower(i.supplier) AND s2.deleted_at IS NULL)
               GROUP BY i.supplier ORDER BY n DESC LIMIT %s""", (limit,))
