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


class SupplierMasterRepository(BaseRepository):

    # ---- lookup protocol (consumed by SupplierResolver) ----
    def find_by_cui_normalized(self, cui):
        row = self.query_one("SELECT id FROM suppliers WHERE cui_normalized = %s AND is_active LIMIT 1", (cui,))
        return row['id'] if row else None

    def find_by_nr_reg_normalized(self, nr):
        row = self.query_one("SELECT id FROM suppliers WHERE nr_reg_normalized = %s AND is_active LIMIT 1", (nr,))
        return row['id'] if row else None

    def find_by_ref_no(self, ref):
        row = self.query_one("SELECT id FROM suppliers WHERE ref_no = %s AND is_active LIMIT 1", (ref,))
        return row['id'] if row else None

    def find_by_alias(self, name=None, cui_normalized=None):
        row = self.query_one(
            """SELECT supplier_id FROM supplier_aliases
               WHERE (alias_cui_normalized IS NOT NULL AND alias_cui_normalized = %s)
                  OR (%s IS NOT NULL AND lower(alias_name) = lower(%s))
               LIMIT 1""",
            (cui_normalized, name, name))
        return row['supplier_id'] if row else None

    def find_by_name_exact(self, name):
        row = self.query_one("SELECT id FROM suppliers WHERE lower(name) = lower(%s) AND is_active LIMIT 1", (name,))
        return row['id'] if row else None

    def find_by_fuzzy_name(self, name):
        row = self.query_one(
            """SELECT id, similarity(name, %s) AS score FROM suppliers
               WHERE is_active AND similarity(name, %s) >= %s
               ORDER BY score DESC LIMIT 1""",
            (name, name, _FUZZY_THRESHOLD))
        return (row['id'], float(row['score'])) if row else None

    # ---- master reads / writes ----
    def list_master(self, search=None, limit=100, offset=0, company_id=None):
        """List master suppliers. When company_id is given, each row carries that company's
        EFFECTIVE konto (supplier_konto_config child row, falling back to the flat suppliers.*
        defaults for the 9 flat-backed fields) plus has_company_config. Without company_id,
        behaves as before (flat columns only, no steuercode/text_template/belegart)."""
        where, params = "WHERE s.is_active", []
        if search:
            where += " AND (s.name ILIKE %s OR s.cui ILIKE %s OR s.ref_no ILIKE %s)"
            like = f"%{search}%"
            params += [like, like, like]

        if company_id is not None:
            effective_cols = ', '.join(
                f"COALESCE(kc.{f}, s.{f}) AS {f}" for f in _KONTO_FLAT_FIELDS)
            child_only_cols = ', '.join(f"kc.{f} AS {f}" for f in KONTO_FIELDS[9:])
            sql = (
                f"SELECT s.*, {effective_cols}, {child_only_cols}, (kc.id IS NOT NULL) AS has_company_config "
                f"FROM suppliers s LEFT JOIN supplier_konto_config kc "
                f"ON kc.supplier_id = s.id AND kc.company_id = %s {where} "
                f"ORDER BY s.name LIMIT %s OFFSET %s")
            return self.query_all(sql, tuple([company_id] + params + [limit, offset]))

        params += [limit, offset]
        return self.query_all(f"SELECT s.* FROM suppliers s {where} ORDER BY s.name LIMIT %s OFFSET %s", tuple(params))

    def get_effective_konto(self, supplier_id, company_id):
        """Effective Table-2 konto for (supplier, company): the supplier_konto_config child
        row (if present) overrides the flat suppliers.* defaults field-by-field. NULL/absent
        fields on the child fall back to the flat columns (steuercode/text_template/belegart
        have no flat fallback — they stay NULL when no child row/value exists).

        Returns {'konto': {...KONTO_FIELDS...}, 'has_company_config': bool}.
        """
        child = self.query_one(
            f"SELECT {', '.join(KONTO_FIELDS)} FROM supplier_konto_config "
            f"WHERE supplier_id = %s AND company_id = %s",
            (supplier_id, company_id))
        flat = self.query_one(
            f"SELECT {', '.join(_KONTO_FLAT_FIELDS)} FROM suppliers WHERE id = %s",
            (supplier_id,)) or {}
        konto = {}
        for field in KONTO_FIELDS:
            child_val = child.get(field) if child else None
            konto[field] = child_val if child_val is not None else flat.get(field)
        return {'konto': konto, 'has_company_config': child is not None}

    def upsert_konto(self, supplier_id, company_id, created_by=None, **fields):
        """Create/update the supplier_konto_config row for (supplier_id, company_id).
        Only KONTO_FIELDS are ever written — arbitrary kwargs are silently dropped, never
        interpolated as SQL identifiers."""
        cols = [f for f in KONTO_FIELDS if f in fields]
        vals = [fields[f] for f in cols]
        insert_cols = ['supplier_id', 'company_id', 'created_by'] + cols
        insert_vals = [supplier_id, company_id, created_by] + vals
        placeholders = ', '.join(['%s'] * len(insert_vals))
        update_sets = ', '.join(f"{f} = EXCLUDED.{f}" for f in cols)
        update_clause = (update_sets + ', ') if update_sets else ''
        row = self.execute(
            f"""INSERT INTO supplier_konto_config ({', '.join(insert_cols)})
                VALUES ({placeholders})
                ON CONFLICT (supplier_id, company_id) DO UPDATE SET
                    {update_clause}updated_at = CURRENT_TIMESTAMP
                RETURNING id""",
            tuple(insert_vals), returning=True)
        return row['id']

    def replicate_konto(self, supplier_id, fields, created_by=None):
        """Upsert the given (whitelisted) KONTO_FIELDS into supplier_konto_config for EVERY
        company, atomically in a single transaction. Mirrors upsert_konto's INSERT ... ON
        CONFLICT per company. Only KONTO_FIELDS are ever written — arbitrary keys in `fields`
        are silently dropped, never interpolated as SQL identifiers.

        Returns the number of companies written.
        """
        cols = [f for f in KONTO_FIELDS if f in fields]
        vals = [fields[f] for f in cols]
        insert_cols = ['supplier_id', 'company_id', 'created_by'] + cols
        placeholders = ', '.join(['%s'] * len(insert_cols))
        update_sets = ', '.join(f"{f} = EXCLUDED.{f}" for f in cols)
        update_clause = (update_sets + ', ') if update_sets else ''
        sql = (
            f"""INSERT INTO supplier_konto_config ({', '.join(insert_cols)})
                VALUES ({placeholders})
                ON CONFLICT (supplier_id, company_id) DO UPDATE SET
                    {update_clause}updated_at = CURRENT_TIMESTAMP""")

        def _work(cursor):
            cursor.execute("SELECT id FROM companies")
            company_ids = [row['id'] for row in cursor.fetchall()]
            for company_id in company_ids:
                cursor.execute(sql, tuple([supplier_id, company_id, created_by] + vals))
            return len(company_ids)

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

    def list_budgeted_invoices(self, company_id, company_name, start_date, end_date, limit=500):
        """Budgeted ('bugetata') invoices allocated to `company_name`, within [start_date,
        end_date] on invoice_date, whose free-text supplier resolves (by exact name or alias)
        to a master supplier with a COMPLETE Table-2 konto config for `company_id` (all key
        posting fields non-empty). GROUP BY i.id collapses the allocation fan-out (an invoice
        can have multiple allocation rows for the same company, split across departments)."""
        sql = """
            SELECT i.id, i.supplier, i.invoice_number, i.invoice_date, i.net_value,
                   i.invoice_value, i.value_ron, i.value_eur, i.currency, i.status,
                   MIN(s.id) AS supplier_id
            FROM invoices i
            JOIN allocations a ON a.invoice_id = i.id AND lower(a.company) = lower(%s)
            JOIN suppliers s ON (
                lower(s.name) = lower(i.supplier)
                OR EXISTS (
                    SELECT 1 FROM supplier_aliases al
                    WHERE al.supplier_id = s.id AND lower(al.alias_name) = lower(i.supplier)
                )
            )
            JOIN supplier_konto_config kc ON kc.supplier_id = s.id AND kc.company_id = %s
            WHERE lower(i.status) = 'bugetata'
              AND i.deleted_at IS NULL
              AND i.invoice_date BETWEEN %s AND %s
              AND NULLIF(kc.konto_debit, '') IS NOT NULL
              AND NULLIF(kc.konto_credit, '') IS NOT NULL
              AND NULLIF(kc.klient, '') IS NOT NULL
              AND NULLIF(kc.steuercode, '') IS NOT NULL
              AND NULLIF(kc.belegart, '') IS NOT NULL
            GROUP BY i.id, i.supplier, i.invoice_number, i.invoice_date, i.net_value,
                     i.invoice_value, i.value_ron, i.value_eur, i.currency, i.status
            ORDER BY i.invoice_date DESC, i.id DESC
            LIMIT %s
        """
        return self.query_all(sql, (company_name, company_id, start_date, end_date, limit))

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
                           AND NOT EXISTS (SELECT 1 FROM suppliers s WHERE lower(s.name) = lower(i.supplier) AND s.is_active)
                           AND NOT EXISTS (SELECT 1 FROM supplier_aliases al WHERE lower(al.alias_name) = lower(i.supplier))
                     ) sub
                     GROUP BY partner_name ORDER BY n DESC LIMIT %s"""
            return self.query_all(sql, (company_name, limit))
        return self.query_all(
            """SELECT i.supplier AS partner_name, count(*) AS n
               FROM invoices i
               WHERE i.deleted_at IS NULL
                 AND NOT EXISTS (SELECT 1 FROM suppliers s WHERE lower(s.name) = lower(i.supplier) AND s.is_active)
                 AND NOT EXISTS (SELECT 1 FROM supplier_aliases a WHERE lower(a.alias_name) = lower(i.supplier))
               GROUP BY i.supplier ORDER BY n DESC LIMIT %s""", (limit,))
