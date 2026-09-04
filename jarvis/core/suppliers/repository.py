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
    def list_master(self, search=None, limit=100, offset=0):
        where, params = "WHERE is_active", []
        if search:
            where += " AND (name ILIKE %s OR cui ILIKE %s OR ref_no ILIKE %s)"
            like = f"%{search}%"
            params += [like, like, like]
        params += [limit, offset]
        return self.query_all(f"SELECT * FROM suppliers {where} ORDER BY name LIMIT %s OFFSET %s", tuple(params))

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
    def unresolved_efactura(self, limit=200):
        return self.query_all(
            """SELECT DISTINCT partner_name, partner_cif FROM efactura_invoices
               WHERE supplier_id IS NULL AND deleted_at IS NULL
               ORDER BY partner_name LIMIT %s""", (limit,))

    def unresolved_invoice_suppliers(self, limit=200):
        return self.query_all(
            """SELECT i.supplier AS partner_name, count(*) AS n
               FROM invoices i
               WHERE i.deleted_at IS NULL
                 AND NOT EXISTS (SELECT 1 FROM suppliers s WHERE lower(s.name) = lower(i.supplier) AND s.is_active)
                 AND NOT EXISTS (SELECT 1 FROM supplier_aliases a WHERE lower(a.alias_name) = lower(i.supplier))
               GROUP BY i.supplier ORDER BY n DESC LIMIT %s""", (limit,))
