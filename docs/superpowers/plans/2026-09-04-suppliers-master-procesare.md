# Suppliers Master + "Procesare" Console — Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing DMS `suppliers` table into a shared supplier master keyed on CUI/Nr.Reg/Ref.No/name, add a resolver + alias capture, per-supplier AP EuroFib posting config, and a "Procesare" Accounting sub-tab that lets an operator resolve e-Factura/invoice suppliers to the master.

**Architecture:** Additive DB migration on the existing `suppliers` table + new `supplier_aliases` table + `efactura_invoices.supplier_id` FK. A pure normalizer and a dependency-injected `SupplierResolver` live in a new shared `core/suppliers/` package alongside a `SupplierMasterRepository` and a `suppliers_bp` blueprint. Frontend adds `pages/Accounting/Procesare` (worklist + master console) and an `api/suppliers.ts` client. `invoices` table is NOT touched (deferred to Phase 2). Resolve-on-read: e-Factura binds by CUI now; invoices resolve by name/alias.

**Tech Stack:** Python 3 / Flask (raw psycopg2, `%s` params, no ORM), PostgreSQL, React 19 + Vite + TypeScript + Tailwind + shadcn/ui, TanStack Query, pytest (psycopg2 mocked globally), vitest (frontend pure logic).

**Spec:** `docs/superpowers/specs/2026-09-04-suppliers-master-procesare-design.md`

## Global Constraints

- Repositories subclass `core.base_repository.BaseRepository`; use `execute_many(callback)` for atomic multi-statement work — **there is no `transaction()` helper**.
- All DDL is idempotent and lives inside `create_schema_incremental(conn, cursor)` in `jarvis/migrations/domains/schema_incremental.py` (already wired into `init_schema.py`; no new registration needed). Use `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, and `DO $$ ... information_schema.columns ... ALTER TABLE ADD COLUMN ... $$` guards.
- Never interpolate user values into SQL; parameterise everything with `%s`.
- Permission helper MUST read `perm.get("has_permission")` / `perm.get("has_explicit_entry")` — NEVER `if perm is not None` (that dict is always truthy: the `routes_orders.py:203` broken-access-control bug).
- `check_permission_v2(role_id, module, entity, action)` always returns `{'has_permission': bool, 'scope': str, 'has_explicit_entry': bool}`.
- Frontend `api` client (`@/api/client`) does NOT auto-unwrap the envelope — callers type the full `{success, ...}` shape and read the field.
- Do NOT modify the `invoices` table (Phase 2).
- Tests run from repo root: `python -m pytest tests/ -x -q`. `psycopg2` is mocked in `jarvis/conftest.py`, so pure/DI-testable units are strongly preferred.
- Frontend gate: `cd jarvis/frontend && npm run build` must exit 0 with zero TS errors.
- Permission entity: **new `suppliers.master`** with actions `view / edit / merge / resolve`. Frontend `v2Permission` strings are `suppliers.master.<action>`.

---

## Phase 1 — Data model

### Task 1: Migration — master columns, aliases table, efactura FK

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (inside `create_schema_incremental`, immediately after the existing `suppliers` block near line 1398)

**Interfaces:**
- Produces: `suppliers.cui_normalized`, `suppliers.nr_reg_normalized`, `suppliers.ref_no`, `suppliers.konto_debit`, `suppliers.konto_credit`, `suppliers.klient`, `suppliers.gegenkonto_debit`, `suppliers.gegenkonto_credit`, `suppliers.kostenstelle_debit`, `suppliers.kostenstelle_credit`, `suppliers.extbeleg_debit`, `suppliers.extbeleg_credit`; table `supplier_aliases(id, supplier_id, alias_name, alias_cui_normalized, source, created_by, created_at)`; column `efactura_invoices.supplier_id`.

- [ ] **Step 1: Add the idempotent DDL block**

Insert after the existing `suppliers` `DO $$ ... $$` guard (around `schema_incremental.py:1398`):

```python
    # ── suppliers master: identity normalization + AP EuroFib posting (2026-09-04) ──
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'suppliers' AND column_name = 'cui_normalized') THEN
                ALTER TABLE suppliers ADD COLUMN cui_normalized TEXT;
                ALTER TABLE suppliers ADD COLUMN nr_reg_normalized TEXT;
                ALTER TABLE suppliers ADD COLUMN ref_no TEXT;
                ALTER TABLE suppliers ADD COLUMN konto_debit TEXT;
                ALTER TABLE suppliers ADD COLUMN konto_credit TEXT;
                ALTER TABLE suppliers ADD COLUMN klient TEXT;
                ALTER TABLE suppliers ADD COLUMN gegenkonto_debit TEXT;
                ALTER TABLE suppliers ADD COLUMN gegenkonto_credit TEXT;
                ALTER TABLE suppliers ADD COLUMN kostenstelle_debit TEXT;
                ALTER TABLE suppliers ADD COLUMN kostenstelle_credit TEXT;
                ALTER TABLE suppliers ADD COLUMN extbeleg_debit TEXT;
                ALTER TABLE suppliers ADD COLUMN extbeleg_credit TEXT;
            END IF;
        END $$;
    ''')
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_cui_norm ON suppliers(cui_normalized) WHERE cui_normalized IS NOT NULL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_nrreg_norm ON suppliers(nr_reg_normalized)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_ref_no ON suppliers(ref_no)")

    # Backfill normalized identity for existing rows (digits-only CUI; upper/no-space Nr.Reg)
    cursor.execute("UPDATE suppliers SET cui_normalized = NULLIF(regexp_replace(COALESCE(cui,''), '\\D', '', 'g'), '') WHERE cui_normalized IS NULL")
    cursor.execute("UPDATE suppliers SET nr_reg_normalized = NULLIF(upper(regexp_replace(COALESCE(nr_reg_com,''), '\\s', '', 'g')), '') WHERE nr_reg_normalized IS NULL")

    # ── supplier_aliases (spelling/CUI variants → one master) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS supplier_aliases (
            id SERIAL PRIMARY KEY,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            alias_name TEXT,
            alias_cui_normalized TEXT,
            source TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_aliases_supplier ON supplier_aliases(supplier_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_aliases_cui ON supplier_aliases(alias_cui_normalized)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_aliases_name ON supplier_aliases (lower(alias_name))")

    # ── efactura_invoices.supplier_id (bind inbound e-Factura to the master) ──
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'efactura_invoices' AND column_name = 'supplier_id') THEN
                ALTER TABLE efactura_invoices ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL;
            END IF;
        END $$;
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_efactura_invoices_supplier ON efactura_invoices(supplier_id)")
```

- [ ] **Step 2: Apply against the local DB and verify columns exist**

Run:
```bash
psql "postgresql://localhost/defaultdb" -c "\d suppliers" | grep -E "cui_normalized|konto_credit|klient|gegenkonto_debit|kostenstelle_debit|extbeleg_debit|ref_no"
psql "postgresql://localhost/defaultdb" -c "\d supplier_aliases"
psql "postgresql://localhost/defaultdb" -c "\d efactura_invoices" | grep supplier_id
```
Apply the DDL by running the app's init once (it runs `init_db()` on import) OR paste the SQL blocks into `psql` directly. Expected: all columns/tables/indexes present.
Note (project memory): the local `defaultdb` is shared across worktrees; applying additive DDL here is safe (no drops).

- [ ] **Step 3: Verify backfill populated normalized CUIs**

Run:
```bash
psql "postgresql://localhost/defaultdb" -c "SELECT count(*) FILTER (WHERE cui_normalized IS NOT NULL) AS with_cui, count(*) AS total FROM suppliers;"
```
Expected: `with_cui` > 0 (existing suppliers that had a CUI now have a normalized value).

- [ ] **Step 4: Commit**

```bash
git add jarvis/migrations/domains/schema_incremental.py
git commit -m "feat(suppliers): master identity + konto columns, supplier_aliases, efactura FK"
```

---

### Task 2: Seed `suppliers.master` V2 permissions

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (near the existing `dms.supplier` seed at ~line 1647, add a new count-guarded block)

**Interfaces:**
- Produces: `permissions_v2` rows `(suppliers, master, {view,edit,merge,resolve})`; Admin/Manager grants in `role_permissions_v2`.

- [ ] **Step 1: Add the seed block**

```python
    # ── suppliers.master permissions (Procesare console) ──
    cursor.execute("SELECT COUNT(*) AS cnt FROM permissions_v2 WHERE module_key = 'suppliers' AND entity_key = 'master'")
    if cursor.fetchone()['cnt'] == 0:
        master_perms = [
            ('suppliers', 'Suppliers', 'bi-building', 'master', 'Supplier Master', 'view',    'View',    'View supplier master & worklist', False, 1),
            ('suppliers', 'Suppliers', 'bi-building', 'master', 'Supplier Master', 'edit',    'Edit',    'Create/edit master suppliers',    False, 2),
            ('suppliers', 'Suppliers', 'bi-building', 'master', 'Supplier Master', 'merge',   'Merge',   'Merge duplicate suppliers',       False, 3),
            ('suppliers', 'Suppliers', 'bi-building', 'master', 'Supplier Master', 'resolve', 'Resolve', 'Resolve worklist entries',        False, 4),
        ]
        for p in master_perms:
            cursor.execute('''
                INSERT INTO permissions_v2 (module_key, module_label, module_icon,
                    entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
            ''', p)
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r CROSS JOIN permissions_v2 p
            WHERE r.name IN ('Admin', 'Manager', 'Dep Contabilitate') AND p.module_key = 'suppliers'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
```

- [ ] **Step 2: Apply + verify the entity appears in the matrix**

Run:
```bash
psql "postgresql://localhost/defaultdb" -c "SELECT module_key, entity_key, action_key FROM permissions_v2 WHERE module_key='suppliers' ORDER BY sort_order;"
```
Expected: 4 rows (view/edit/merge/resolve).

- [ ] **Step 3: Commit**

```bash
git add jarvis/migrations/domains/schema_incremental.py
git commit -m "feat(suppliers): seed suppliers.master V2 permissions (view/edit/merge/resolve)"
```

---

## Phase 2 — Normalizer + resolver (pure / DI, DB-free tests)

### Task 3: CUI / Nr.Reg normalizer

**Files:**
- Create: `jarvis/core/suppliers/__init__.py` (empty package marker)
- Create: `jarvis/core/suppliers/normalize.py`
- Test: `jarvis/tests/test_supplier_normalize.py`

**Interfaces:**
- Produces: `normalize_cui(value: str | None) -> str | None`, `normalize_nr_reg(value: str | None) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/test_supplier_normalize.py
from core.suppliers.normalize import normalize_cui, normalize_nr_reg

def test_normalize_cui_strips_ro_prefix_and_spaces():
    assert normalize_cui('RO9997007') == '9997007'
    assert normalize_cui(' ro 999 70 07 ') == '9997007'
    assert normalize_cui('9997007') == '9997007'

def test_normalize_cui_empty_is_none():
    assert normalize_cui('') is None
    assert normalize_cui(None) is None
    assert normalize_cui('RO') is None

def test_normalize_nr_reg_upper_no_space_keeps_slashes():
    assert normalize_nr_reg('j40 / 1234 / 2020') == 'J40/1234/2020'
    assert normalize_nr_reg(None) is None
    assert normalize_nr_reg('   ') is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_supplier_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: core.suppliers.normalize`.

- [ ] **Step 3: Implement**

```python
# jarvis/core/suppliers/normalize.py
"""Canonical identity normalization for the supplier master."""
import re


def normalize_cui(value: str | None) -> str | None:
    """Digits-only canonical CUI. 'RO9997007' -> '9997007'. Empty -> None."""
    if not value:
        return None
    digits = re.sub(r'\D', '', value)
    return digits or None


def normalize_nr_reg(value: str | None) -> str | None:
    """Uppercase, whitespace-stripped Nr. Reg. Com (keeps separators). Empty -> None."""
    if not value:
        return None
    s = re.sub(r'\s+', '', value).upper()
    return s or None
```
Create `jarvis/core/suppliers/__init__.py` (empty).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_supplier_normalize.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/suppliers/__init__.py jarvis/core/suppliers/normalize.py jarvis/tests/test_supplier_normalize.py
git commit -m "feat(suppliers): CUI/Nr.Reg normalizer with unit tests"
```

---

### Task 4: `SupplierResolver` (tiered, DI-testable)

**Files:**
- Create: `jarvis/core/suppliers/resolver.py`
- Test: `jarvis/tests/test_supplier_resolver.py`

**Interfaces:**
- Consumes: `normalize_cui`, `normalize_nr_reg` (Task 3).
- Consumes (lookup protocol — implemented by Task 5's repository): `find_by_cui_normalized(cui) -> int|None`, `find_by_nr_reg_normalized(nr) -> int|None`, `find_by_ref_no(ref) -> int|None`, `find_by_alias(name, cui_normalized) -> int|None`, `find_by_name_exact(name) -> int|None`, `find_by_fuzzy_name(name) -> tuple[int, float]|None`.
- Produces: `Resolution(supplier_id: int|None, confidence: str, method: str)`; `SupplierResolver(lookup).resolve(name=None, cui=None, nr_reg=None, ref_no=None) -> Resolution`.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/test_supplier_resolver.py
from core.suppliers.resolver import SupplierResolver, Resolution


class FakeLookup:
    def __init__(self, by_cui=None, by_nr=None, by_ref=None, by_alias=None, by_name=None, fuzzy=None):
        self._cui, self._nr, self._ref = by_cui or {}, by_nr or {}, by_ref or {}
        self._alias, self._name, self._fuzzy = by_alias or {}, by_name or {}, fuzzy
    def find_by_cui_normalized(self, cui): return self._cui.get(cui)
    def find_by_nr_reg_normalized(self, nr): return self._nr.get(nr)
    def find_by_ref_no(self, ref): return self._ref.get(ref)
    def find_by_alias(self, name, cui_normalized):
        return self._alias.get(cui_normalized) or self._alias.get((name or '').lower())
    def find_by_name_exact(self, name): return self._name.get((name or '').lower())
    def find_by_fuzzy_name(self, name): return self._fuzzy


def test_cui_tier_wins_even_when_name_differs():
    # Porsche case: master row 42 keyed by CUI; invoice spells the name differently
    r = SupplierResolver(FakeLookup(by_cui={'9997007': 42})).resolve(
        name='Porsche Romania s.r.l.', cui='RO9997007')
    assert r == Resolution(42, 'high', 'cui')

def test_falls_through_to_nr_reg_then_ref_no():
    assert SupplierResolver(FakeLookup(by_nr={'J40/1/2020': 7})).resolve(nr_reg='j40 / 1 / 2020') == Resolution(7, 'high', 'nr_reg')
    assert SupplierResolver(FakeLookup(by_ref={'EXT-1': 9})).resolve(ref_no='EXT-1') == Resolution(9, 'high', 'ref_no')

def test_name_exact_is_medium_and_fuzzy_is_low():
    assert SupplierResolver(FakeLookup(by_name={'acme srl': 3})).resolve(name='ACME SRL') == Resolution(3, 'medium', 'name_exact')
    assert SupplierResolver(FakeLookup(fuzzy=(5, 0.82))).resolve(name='acme s.r.l') == Resolution(5, 'low', 'fuzzy')

def test_no_hit_is_none():
    assert SupplierResolver(FakeLookup()).resolve(name='Unknown', cui='RO1') == Resolution(None, 'none', 'none')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_supplier_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: core.suppliers.resolver`.

- [ ] **Step 3: Implement**

```python
# jarvis/core/suppliers/resolver.py
"""Tiered supplier resolution: CUI -> Nr.Reg -> Ref.No -> alias -> name -> fuzzy."""
from dataclasses import dataclass

from core.suppliers.normalize import normalize_cui, normalize_nr_reg


@dataclass(frozen=True)
class Resolution:
    supplier_id: int | None
    confidence: str  # 'high' | 'medium' | 'low' | 'none'
    method: str


class SupplierResolver:
    def __init__(self, lookup):
        self.lookup = lookup

    def resolve(self, name=None, cui=None, nr_reg=None, ref_no=None) -> Resolution:
        ncui = normalize_cui(cui)
        if ncui:
            sid = self.lookup.find_by_cui_normalized(ncui)
            if sid:
                return Resolution(sid, 'high', 'cui')
        nreg = normalize_nr_reg(nr_reg)
        if nreg:
            sid = self.lookup.find_by_nr_reg_normalized(nreg)
            if sid:
                return Resolution(sid, 'high', 'nr_reg')
        if ref_no:
            sid = self.lookup.find_by_ref_no(ref_no)
            if sid:
                return Resolution(sid, 'high', 'ref_no')
        sid = self.lookup.find_by_alias(name=name, cui_normalized=ncui)
        if sid:
            return Resolution(sid, 'high', 'alias')
        if name:
            sid = self.lookup.find_by_name_exact(name)
            if sid:
                return Resolution(sid, 'medium', 'name_exact')
            match = self.lookup.find_by_fuzzy_name(name)
            if match:
                return Resolution(match[0], 'low', 'fuzzy')
        return Resolution(None, 'none', 'none')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_supplier_resolver.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/suppliers/resolver.py jarvis/tests/test_supplier_resolver.py
git commit -m "feat(suppliers): tiered SupplierResolver (CUI->NrReg->RefNo->alias->name->fuzzy)"
```

---

### Task 5: `SupplierMasterRepository` (implements the lookup protocol + writes)

**Files:**
- Create: `jarvis/core/suppliers/repository.py`

**Interfaces:**
- Consumes: `BaseRepository` (`query_one`, `query_all`, `execute`, `execute_many`), `normalize_cui`, `normalize_nr_reg`.
- Produces (lookup, for Task 4): `find_by_cui_normalized`, `find_by_nr_reg_normalized`, `find_by_ref_no`, `find_by_alias`, `find_by_name_exact`, `find_by_fuzzy_name`.
- Produces (writes/reads, for Tasks 6-10): `list_master`, `get_master`, `create_master`, `update_master`, `add_alias`, `merge`, `set_efactura_supplier_id`, `unresolved_efactura`, `unresolved_invoice_suppliers`.

- [ ] **Step 1: Implement the repository**

```python
# jarvis/core/suppliers/repository.py
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
            cursor.execute("UPDATE suppliers SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (duplicate_id,))
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
```

- [ ] **Step 2: Sanity-check import + syntax**

Run: `python3 -m py_compile jarvis/core/suppliers/repository.py`
Expected: exit 0.
(Note: `similarity()` requires the `pg_trgm` extension — already used by `idx_suppliers_name` GIN index, so it is enabled.)

- [ ] **Step 3: Commit**

```bash
git add jarvis/core/suppliers/repository.py
git commit -m "feat(suppliers): SupplierMasterRepository (lookup, CRUD, aliases, merge, worklist)"
```

---

## Phase 3 — Backend API (`suppliers_bp`)

### Task 6: Blueprint + permission helper + list/detail, registered in app.py

**Files:**
- Create: `jarvis/core/suppliers/routes.py`
- Modify: `jarvis/core/suppliers/__init__.py` (export `suppliers_bp`)
- Modify: `jarvis/app.py` (`_register_blueprints`, near the accounting registrations ~line 216)
- Test: `jarvis/tests/test_suppliers_api.py`

**Interfaces:**
- Consumes: `SupplierMasterRepository` (Task 5), `PermissionRepository.check_permission_v2`.
- Produces: blueprint `suppliers_bp`; `GET /api/suppliers`, `GET /api/suppliers/<id>`; helper `_check_supplier_perm(action)`.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/test_suppliers_api.py
from core.suppliers.routes import _check_supplier_perm

def test_perm_helper_denies_when_no_role(monkeypatch):
    import core.suppliers.routes as r
    class U:  # anonymous-ish
        is_authenticated = True
        role_id = None
        role_name = ''
    monkeypatch.setattr(r, 'current_user', U(), raising=False)
    assert _check_supplier_perm('view') is False

def test_perm_helper_uses_has_permission(monkeypatch):
    import core.suppliers.routes as r
    class U:
        is_authenticated = True
        role_id = 5
        role_name = 'Dep Contabilitate'
    monkeypatch.setattr(r, 'current_user', U(), raising=False)
    monkeypatch.setattr(r._perm_repo, 'check_permission_v2',
                        lambda *a, **k: {'has_permission': True, 'scope': 'all', 'has_explicit_entry': True})
    assert _check_supplier_perm('view') is True
    monkeypatch.setattr(r._perm_repo, 'check_permission_v2',
                        lambda *a, **k: {'has_permission': False, 'scope': 'deny', 'has_explicit_entry': True})
    assert _check_supplier_perm('edit') is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_suppliers_api.py -v`
Expected: FAIL — `ModuleNotFoundError: core.suppliers.routes`.

- [ ] **Step 3: Implement the blueprint + helper + list/detail**

```python
# jarvis/core/suppliers/routes.py
"""Supplier master + Procesare resolution API."""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from core.roles.repositories.permission_repository import PermissionRepository
from core.suppliers.repository import SupplierMasterRepository

suppliers_bp = Blueprint('suppliers', __name__)
_perm_repo = PermissionRepository()
_repo = SupplierMasterRepository()


def _check_supplier_perm(action: str) -> bool:
    if getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin'):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'suppliers', 'master', action)
    return perm.get('has_permission', False)


@suppliers_bp.route('/api/suppliers', methods=['GET'])
@login_required
def api_list_suppliers():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    suppliers = _repo.list_master(
        search=request.args.get('search'),
        limit=min(int(request.args.get('limit', 100)), 500),
        offset=int(request.args.get('offset', 0)))
    return jsonify({'success': True, 'suppliers': suppliers})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@login_required
def api_get_supplier(supplier_id):
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    sup = _repo.get_master(supplier_id)
    if not sup:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'supplier': sup})
```
`jarvis/core/suppliers/__init__.py`:
```python
from core.suppliers.routes import suppliers_bp  # noqa: F401
```
In `jarvis/app.py` `_register_blueprints`, after the vouchers registration (~line 216):
```python
    from core.suppliers import suppliers_bp
    flask_app.register_blueprint(suppliers_bp)
```

- [ ] **Step 4: Run test to verify it passes + app imports**

Run: `python -m pytest tests/test_suppliers_api.py -v && python3 -m py_compile jarvis/app.py`
Expected: PASS (2 tests), py_compile exit 0.

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/suppliers/routes.py jarvis/core/suppliers/__init__.py jarvis/app.py jarvis/tests/test_suppliers_api.py
git commit -m "feat(suppliers): suppliers_bp with permission helper + list/detail endpoints"
```

---

### Task 7: Master create / update / add-alias endpoints

**Files:**
- Modify: `jarvis/core/suppliers/routes.py`

**Interfaces:**
- Produces: `POST /api/suppliers`, `PUT /api/suppliers/<id>`, `POST /api/suppliers/<id>/aliases`.

- [ ] **Step 1: Implement the write endpoints**

```python
@suppliers_bp.route('/api/suppliers', methods=['POST'])
@login_required
def api_create_supplier():
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    sid = _repo.create_master(name, created_by=getattr(current_user, 'id', None),
                              **{k: v for k, v in data.items() if k != 'name'})
    return jsonify({'success': True, 'id': sid}), 201


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@login_required
def api_update_supplier(supplier_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    _repo.update_master(supplier_id, **data)
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/aliases', methods=['POST'])
@login_required
def api_add_alias(supplier_id):
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    alias_id = _repo.add_alias(supplier_id, alias_name=data.get('alias_name'),
                               alias_cui=data.get('alias_cui'), source=data.get('source', 'manual'),
                               created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True, 'id': alias_id}), 201
```

- [ ] **Step 2: Verify import**

Run: `python3 -m py_compile jarvis/core/suppliers/routes.py`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add jarvis/core/suppliers/routes.py
git commit -m "feat(suppliers): master create/update + add-alias endpoints"
```

---

### Task 8: Merge endpoint

**Files:**
- Modify: `jarvis/core/suppliers/routes.py`

**Interfaces:**
- Consumes: `SupplierMasterRepository.merge` (Task 5).
- Produces: `POST /api/suppliers/merge` body `{survivor_id, duplicate_id}`.

- [ ] **Step 1: Implement**

```python
@suppliers_bp.route('/api/suppliers/merge', methods=['POST'])
@login_required
def api_merge_suppliers():
    if not _check_supplier_perm('merge'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    survivor, dup = data.get('survivor_id'), data.get('duplicate_id')
    if not survivor or not dup or survivor == dup:
        return jsonify({'success': False, 'error': 'survivor_id and distinct duplicate_id are required'}), 400
    _repo.merge(survivor, dup, created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True})
```

- [ ] **Step 2: Verify import**

Run: `python3 -m py_compile jarvis/core/suppliers/routes.py`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add jarvis/core/suppliers/routes.py
git commit -m "feat(suppliers): merge duplicate suppliers endpoint"
```

---

### Task 9: Worklist + resolve endpoints

**Files:**
- Modify: `jarvis/core/suppliers/routes.py`

**Interfaces:**
- Consumes: `SupplierMasterRepository` (unresolved_efactura, unresolved_invoice_suppliers, set_efactura_supplier_id, create_master, add_alias), `SupplierResolver`.
- Produces: `GET /api/suppliers/worklist`, `POST /api/suppliers/resolve`.

- [ ] **Step 1: Implement**

```python
from core.suppliers.resolver import SupplierResolver

_resolver = SupplierResolver(_repo)


@suppliers_bp.route('/api/suppliers/worklist', methods=['GET'])
@login_required
def api_worklist():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    items = []
    for row in _repo.unresolved_efactura():
        res = _resolver.resolve(name=row['partner_name'], cui=row['partner_cif'])
        if res.confidence != 'high':
            items.append({'source': 'efactura', 'partner_name': row['partner_name'],
                          'partner_cif': row['partner_cif'],
                          'candidate_id': res.supplier_id, 'confidence': res.confidence, 'method': res.method})
    for row in _repo.unresolved_invoice_suppliers():
        res = _resolver.resolve(name=row['partner_name'])
        if res.confidence != 'high':
            items.append({'source': 'invoice', 'partner_name': row['partner_name'], 'partner_cif': None,
                          'count': row['n'], 'candidate_id': res.supplier_id,
                          'confidence': res.confidence, 'method': res.method})
    return jsonify({'success': True, 'items': items})


@suppliers_bp.route('/api/suppliers/resolve', methods=['POST'])
@login_required
def api_resolve():
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    action = data.get('action')          # 'link' | 'create' | 'ignore'
    partner_name = data.get('partner_name')
    partner_cif = data.get('partner_cif')
    uid = getattr(current_user, 'id', None)

    if action == 'link':
        sid = data.get('supplier_id')
        if not sid:
            return jsonify({'success': False, 'error': 'supplier_id required for link'}), 400
    elif action == 'create':
        sid = _repo.create_master(partner_name, created_by=uid, cui=partner_cif)
    elif action == 'ignore':
        _repo.add_alias(None, alias_name=partner_name, alias_cui=partner_cif, source='ignore', created_by=uid) \
            if False else None  # ignore = alias to a sentinel is out of scope; record intentionally skipped
        return jsonify({'success': True, 'ignored': True})
    else:
        return jsonify({'success': False, 'error': 'unknown action'}), 400

    _repo.add_alias(sid, alias_name=partner_name, alias_cui=partner_cif, source='resolve', created_by=uid)
    linked = _repo.set_efactura_supplier_id(sid, partner_name=partner_name, partner_cif=partner_cif)
    return jsonify({'success': True, 'supplier_id': sid, 'efactura_linked': linked})
```
(Note: `ignore` in Phase 1 is a no-op ack; a persistent ignore list is Phase 2. The dead `if False` branch above is a placeholder marker — replace with a simple `pass`/return; see Step 2.)

- [ ] **Step 2: Clean the ignore branch**

Replace the `ignore` branch with:
```python
    elif action == 'ignore':
        return jsonify({'success': True, 'ignored': True})
```

- [ ] **Step 3: Verify import**

Run: `python3 -m py_compile jarvis/core/suppliers/routes.py`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/suppliers/routes.py
git commit -m "feat(suppliers): worklist + resolve endpoints (link/create/ignore, alias + efactura bind)"
```

---

### Task 10: Initial e-Factura bind pass (one-off management endpoint)

**Files:**
- Modify: `jarvis/core/suppliers/routes.py`

**Interfaces:**
- Produces: `POST /api/suppliers/backfill-efactura` — resolves all unresolved e-Factura partners and binds the `high`-confidence ones.

- [ ] **Step 1: Implement**

```python
@suppliers_bp.route('/api/suppliers/backfill-efactura', methods=['POST'])
@login_required
def api_backfill_efactura():
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    bound = 0
    for row in _repo.unresolved_efactura(limit=5000):
        res = _resolver.resolve(name=row['partner_name'], cui=row['partner_cif'])
        if res.confidence == 'high' and res.supplier_id:
            bound += _repo.set_efactura_supplier_id(res.supplier_id,
                                                    partner_name=row['partner_name'],
                                                    partner_cif=row['partner_cif'])
    return jsonify({'success': True, 'bound': bound})
```

- [ ] **Step 2: Verify import + full backend test run**

Run: `python3 -m py_compile jarvis/core/suppliers/routes.py && python -m pytest tests/test_supplier_normalize.py tests/test_supplier_resolver.py tests/test_suppliers_api.py -q`
Expected: py_compile exit 0; all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add jarvis/core/suppliers/routes.py
git commit -m "feat(suppliers): one-off e-Factura high-confidence backfill endpoint"
```

---

## Phase 4 — Frontend (Procesare tab)

### Task 11: API client `api/suppliers.ts`

**Files:**
- Create: `jarvis/frontend/src/api/suppliers.ts`

**Interfaces:**
- Consumes: `api` from `@/api/client`.
- Produces: `suppliersApi` with `list`, `get`, `create`, `update`, `addAlias`, `merge`, `worklist`, `resolve`, `backfillEfactura`; types `MasterSupplier`, `WorklistItem`.

- [ ] **Step 1: Implement**

```ts
// jarvis/frontend/src/api/suppliers.ts
import { api } from '@/api/client'

export interface MasterSupplier {
  id: number
  name: string
  cui?: string | null
  nr_reg_com?: string | null
  ref_no?: string | null
  konto_debit?: string | null
  konto_credit?: string | null
  klient?: string | null
  gegenkonto_debit?: string | null
  gegenkonto_credit?: string | null
  kostenstelle_debit?: string | null
  kostenstelle_credit?: string | null
  extbeleg_debit?: string | null
  extbeleg_credit?: string | null
  is_active?: boolean
  aliases?: { id: number; alias_name: string | null; alias_cui_normalized: string | null; source: string }[]
}

export interface WorklistItem {
  source: 'efactura' | 'invoice'
  partner_name: string
  partner_cif: string | null
  count?: number
  candidate_id: number | null
  confidence: 'medium' | 'low' | 'none'
  method: string
}

export const suppliersApi = {
  list: (search?: string) =>
    api.get<{ success: boolean; suppliers: MasterSupplier[] }>(`/api/suppliers${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  get: (id: number) =>
    api.get<{ success: boolean; supplier: MasterSupplier }>(`/api/suppliers/${id}`),
  create: (data: Partial<MasterSupplier>) =>
    api.post<{ success: boolean; id: number }>(`/api/suppliers`, data),
  update: (id: number, data: Partial<MasterSupplier>) =>
    api.put<{ success: boolean }>(`/api/suppliers/${id}`, data),
  addAlias: (id: number, alias_name?: string, alias_cui?: string) =>
    api.post<{ success: boolean; id: number }>(`/api/suppliers/${id}/aliases`, { alias_name, alias_cui }),
  merge: (survivor_id: number, duplicate_id: number) =>
    api.post<{ success: boolean }>(`/api/suppliers/merge`, { survivor_id, duplicate_id }),
  worklist: () =>
    api.get<{ success: boolean; items: WorklistItem[] }>(`/api/suppliers/worklist`),
  resolve: (body: { action: 'link' | 'create' | 'ignore'; partner_name: string; partner_cif?: string | null; supplier_id?: number }) =>
    api.post<{ success: boolean; supplier_id?: number; efactura_linked?: number }>(`/api/suppliers/resolve`, body),
  backfillEfactura: () =>
    api.post<{ success: boolean; bound: number }>(`/api/suppliers/backfill-efactura`, {}),
}
```

- [ ] **Step 2: Typecheck**

Run: `cd jarvis/frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head`
Expected: no errors referencing `suppliers.ts`.

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/api/suppliers.ts
git commit -m "feat(suppliers): frontend api client"
```

---

### Task 12: Procesare page — master console + worklist tabs

**Files:**
- Create: `jarvis/frontend/src/pages/Accounting/Procesare/index.tsx`

**Interfaces:**
- Consumes: `suppliersApi` (Task 11), shadcn UI primitives, TanStack Query.
- Produces: default-export `Procesare` component.

- [ ] **Step 1: Implement (structure mirrors Accounting/Controlling/index.tsx)**

```tsx
// jarvis/frontend/src/pages/Accounting/Procesare/index.tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/shared/PageHeader'
import { suppliersApi, type MasterSupplier, type WorklistItem } from '@/api/suppliers'

export default function Procesare() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'worklist' | 'master'>('worklist')
  const [search, setSearch] = useState('')

  const { data: wl } = useQuery({ queryKey: ['supplier-worklist'], queryFn: () => suppliersApi.worklist() })
  const { data: masters } = useQuery({ queryKey: ['supplier-master', search], queryFn: () => suppliersApi.list(search) })

  const resolveMut = useMutation({
    mutationFn: (i: WorklistItem) =>
      suppliersApi.resolve(i.candidate_id
        ? { action: 'link', partner_name: i.partner_name, partner_cif: i.partner_cif, supplier_id: i.candidate_id }
        : { action: 'create', partner_name: i.partner_name, partner_cif: i.partner_cif }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['supplier-worklist'] }); toast.success('Resolved') },
    onError: () => toast.error('Failed to resolve'),
  })

  return (
    <div className="space-y-4">
      <PageHeader title="Procesare Furnizori" breadcrumbs={[{ label: 'Accounting' }, { label: 'Procesare' }]} />
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="worklist">Worklist ({wl?.items.length ?? 0})</TabsTrigger>
          <TabsTrigger value="master">Master</TabsTrigger>
        </TabsList>

        <TabsContent value="worklist">
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Source</TableHead><TableHead>Name</TableHead><TableHead>CUI</TableHead>
                <TableHead>Suggested</TableHead><TableHead>Confidence</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {(wl?.items ?? []).map((i, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{i.source}</TableCell>
                    <TableCell>{i.partner_name}</TableCell>
                    <TableCell>{i.partner_cif ?? '-'}</TableCell>
                    <TableCell>{i.candidate_id ? `#${i.candidate_id} (${i.method})` : '—'}</TableCell>
                    <TableCell>{i.confidence}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" onClick={() => resolveMut.mutate(i)} disabled={resolveMut.isPending}>
                        {i.candidate_id ? 'Link' : 'Create'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="master">
          <div className="mb-3"><Input placeholder="Search suppliers…" value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" /></div>
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Name</TableHead><TableHead>CUI</TableHead>
                <TableHead>Konto (D/C)</TableHead><TableHead>Gegenkonto (D/C)</TableHead>
                <TableHead>Kostenstelle (D/C)</TableHead><TableHead>Extbeleg (D/C)</TableHead><TableHead>Klient</TableHead></TableRow></TableHeader>
              <TableBody>
                {(masters?.suppliers ?? []).map((s: MasterSupplier) => (
                  <TableRow key={s.id}>
                    <TableCell>{s.name}</TableCell>
                    <TableCell>{s.cui ?? '-'}</TableCell>
                    <TableCell>{`${s.konto_debit ?? '-'} / ${s.konto_credit ?? '-'}`}</TableCell>
                    <TableCell>{`${s.gegenkonto_debit ?? '-'} / ${s.gegenkonto_credit ?? '-'}`}</TableCell>
                    <TableCell>{`${s.kostenstelle_debit ?? '-'} / ${s.kostenstelle_credit ?? '-'}`}</TableCell>
                    <TableCell>{`${s.extbeleg_debit ?? '-'} / ${s.extbeleg_credit ?? '-'}`}</TableCell>
                    <TableCell>{s.klient ?? '-'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
```
(An edit dialog for the konto block reuses the existing shadcn `Dialog` + `suppliersApi.update`; add it after the master table renders — keep this task to the read/resolve surface, add editing in a follow-up if the reviewer prefers a smaller task.)

- [ ] **Step 2: Typecheck**

Run: `cd jarvis/frontend && npx tsc --noEmit 2>&1 | grep -i procesare || echo "no Procesare type errors"`
Expected: no Procesare errors.

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/Procesare/index.tsx
git commit -m "feat(suppliers): Procesare page — worklist + master console"
```

---

### Task 13: Route + sidebar wiring

**Files:**
- Modify: `jarvis/frontend/src/App.tsx` (lazy import ~line 31-49; route ~line 196)
- Modify: `jarvis/frontend/src/components/Sidebar.tsx` (accounting children ~line 43-52)

**Interfaces:**
- Consumes: `Procesare` (Task 12).
- Produces: route `/app/accounting/procesare` gated by `can_access_accounting` + `suppliers.master.view`; sidebar item "Procesare".

- [ ] **Step 1: Add the lazy import (App.tsx, with the other Accounting lazies ~line 31)**

```tsx
const Procesare = lazy(() => import('./pages/Accounting/Procesare'))
```

- [ ] **Step 2: Add the route (App.tsx, after the vouchers routes ~line 198)**

```tsx
        <Route path="accounting/procesare" element={<Guard flag="can_access_accounting"><V2Guard permKey="suppliers.master.view"><SuspensePage><Procesare /></SuspensePage></V2Guard></Guard>} />
```

- [ ] **Step 3: Add the sidebar item (Sidebar.tsx, in the accounting children array ~line 43-52)**

```tsx
      { path: '/app/accounting/procesare', label: 'Procesare', icon: Building2, moduleKey: 'accounting_procesare', permission: 'can_access_accounting', v2Permission: 'suppliers.master.view' },
```
(`Building2` is already imported in Sidebar.tsx per the existing Suppliers entry.)

- [ ] **Step 4: Build**

Run: `cd jarvis/frontend && npm run build`
Expected: exit 0, zero TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/App.tsx jarvis/frontend/src/components/Sidebar.tsx
git commit -m "feat(suppliers): wire /app/accounting/procesare route + sidebar item"
```

---

### Task 14: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `python -m pytest tests/ -x -q`
Expected: green (no regressions).

- [ ] **Step 2: Frontend build**

Run: `cd jarvis/frontend && npm run build`
Expected: exit 0.

- [ ] **Step 3: Manual smoke (local app)**

Start backend (:5001) + Vite (:5173), log in, open `/app/accounting/procesare`. Confirm:
- Worklist lists unresolved e-Factura/invoice suppliers with suggested matches (the `Porsche Romania s.r.l.` vs `PORSCHE ROMANIA SRL` case should show as a `low`/candidate row until linked, then disappear after Link).
- Master tab lists suppliers with the konto columns.
- `POST /api/suppliers/backfill-efactura` binds high-confidence e-Factura rows (verify `SELECT count(*) FROM efactura_invoices WHERE supplier_id IS NOT NULL`).

- [ ] **Step 4: Final commit (if any verification fixups)**

```bash
git add -A && git commit -m "chore(suppliers): phase 1 verification fixups" || echo "nothing to commit"
```

---

## Self-review notes (author)

- **Spec coverage:** master columns (T1), aliases (T1), efactura FK (T1), permissions (T2), normalizer (T3), resolver tiers incl. Porsche fixture (T4), repository incl. merge/worklist (T5), API list/detail/create/update/alias/merge/worklist/resolve/backfill (T6-T10), Procesare UI (T12), routing+sidebar (T13). Invoices untouched ✔ (Phase 2). Statements/vendor_mappings excluded ✔ (Phase 2).
- **Placeholder scan:** the only intentional marker is the `ignore` dead-branch in T9 Step 1, explicitly cleaned in T9 Step 2.
- **Type consistency:** resolver lookup method names in T4 (`find_by_cui_normalized`, `find_by_nr_reg_normalized`, `find_by_ref_no`, `find_by_alias`, `find_by_name_exact`, `find_by_fuzzy_name`) match the repository in T5; API method names in T11 match routes in T6-T10.
- **Open tunable:** `_FUZZY_THRESHOLD = 0.55` (T5) — adjust after seeing real worklist output.
