# Cost Centers — Phase 1 (Finance dimension) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone **Cost Center** dimension (per-company `code` + `name`, seeded once from the AW Excel) with a Finance → "Centre de cost" CRUD section and an optional default `cost_center → structure_node` map — with **zero impact** on invoices, allocation, or notification.

**Architecture:** New idempotent migration (`cost_centers` + `cost_center_structure_map` tables, one-time seed) auto-applied on boot; a `CostCenterRepository` (subclass of `BaseRepository`) holding all SQL; a dedicated Flask blueprint `accounting/cost_centers/` (routes contain no SQL); a React page under `pages/Accounting/CostCenters/` wired into `App.tsx` + `Sidebar.tsx`. Everything mirrors the recently-shipped HR Divisions feature.

**Tech Stack:** Python 3 / Flask / psycopg2 (RealDictCursor) / PostgreSQL; React 19 + Vite + TypeScript + Tailwind 4 + shadcn/ui + TanStack Query; pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-cost-centers-budgeting-dissociation-design.md`

## Global Constraints

- **Code is a zero-padded string** stored as-is (e.g. `'0211'`), column `VARCHAR(8)`. This is the EuroFib form; never store it as an integer. Any comparison to BAB `kostenstelle` (integer `211`) pads/strips at the boundary only.
- **A cost center is identified by `(company_id, code)`** — codes repeat across companies (`0281 IT`, `0291 Conducere`, `0292 Contabilitate`). Enforce `UNIQUE (company_id, code)`; never treat `code` as globally unique.
- **In-app CRUD is the source of truth.** The Excel is a **one-time seed**, guarded by `COUNT(*)==0`; migrations must never re-clobber in-app edits.
- **Default map = exact name-matches only.** Auto-seed `cost_center → structure_node` only where names match unambiguously (case-insensitive, same company); accounting fills the rest in-app.
- **Home = Accounting/Finance**, gated by the `can_access_accounting` feature flag (no new v2 permission in Phase 1).
- **All user-facing strings are Romanian.**
- **Routes contain zero SQL** — all data access goes through `CostCenterRepository`, which subclasses `core.base_repository.BaseRepository` (`query_one`/`query_all`/`execute`/`execute_many`).
- **Migrations are idempotent** (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ON CONFLICT DO NOTHING`) and auto-apply on every worker boot via `database.init_db()` → `create_schema()`.
- **Tests are CI-safe:** module-level `pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, ...)`; test rows use a `ZZ`-prefix marker; teardown in `finally` relying on FK cascades.
- **Phase 1 does NOT touch** `allocations`, `notification_service.py`, `structure_node_repository.py` resolution, EuroFib export, or any invoice flow. Those are Phases 2–3 (separate plans).

---

## File Structure

**Backend (new unless noted):**
- `jarvis/migrations/domains/schema_cost_centers.py` — the two tables + one-time seed helper.
- `jarvis/migrations/domains/cost_centers_seed.py` — `SEED_ROWS` (the 59 Excel rows) + `SHEET_TO_COMPANY` mapping.
- `jarvis/migrations/init_schema.py` *(modify)* — import + call `create_schema_cost_centers`, after `create_schema_divisions`.
- `jarvis/accounting/cost_centers/__init__.py` — `cost_centers_bp` blueprint + `from . import routes`.
- `jarvis/accounting/cost_centers/routes.py` — permission decorators + CRUD + map routes (no SQL).
- `jarvis/accounting/cost_centers/repositories/__init__.py` — empty package marker.
- `jarvis/accounting/cost_centers/repositories/cost_center_repository.py` — `CostCenterRepository(BaseRepository)`.
- `jarvis/app.py` *(modify)* — register `cost_centers_bp` after `vouchers_bp`.

**Frontend (new unless noted):**
- `jarvis/frontend/src/types/costCenters.ts` — `CostCenter`, `CostCenterCompany`, `StructureNodeOption` interfaces.
- `jarvis/frontend/src/api/costCenters.ts` — `costCentersApi` typed endpoints (shared `api` client).
- `jarvis/frontend/src/pages/Accounting/CostCenters/index.tsx` — the CRUD page (table + dialogs + map picker).
- `jarvis/frontend/src/App.tsx` *(modify)* — lazy import + guarded route `accounting/cost-centers`.
- `jarvis/frontend/src/components/Sidebar.tsx` *(modify)* — new child in the Accounting `children` array.

**Tests (new):**
- `jarvis/tests/cost_centers/__init__.py`
- `jarvis/tests/cost_centers/conftest.py` — `cc_fixture` (a company + 2 structure nodes + a couple cost centers).
- `jarvis/tests/cost_centers/test_cost_center_repository.py` — CRUD + map + auto-seed behavior.

---

## Task 1: Migration — `cost_centers` + `cost_center_structure_map` tables

**Files:**
- Create: `jarvis/migrations/domains/schema_cost_centers.py`
- Modify: `jarvis/migrations/init_schema.py`
- Test: `jarvis/tests/cost_centers/test_cost_center_repository.py` (schema-presence test only, this task)
- Create: `jarvis/tests/cost_centers/__init__.py`, `jarvis/tests/cost_centers/conftest.py`

**Interfaces:**
- Produces: `create_schema_cost_centers(conn, cursor)` — creates `cost_centers(id, company_id, code, name, active, display_order, created_at, updated_at)` and `cost_center_structure_map(id, cost_center_id, structure_node_id, created_at)`.
- Consumes: `companies(id)`, `structure_nodes(id)` from `schema_core`.

- [ ] **Step 1: Write the schema module** (no seed yet — seed is Task 2)

Create `jarvis/migrations/domains/schema_cost_centers.py`:
```python
"""Cost Centers schema — Finance budgeting dimension (a.k.a. kostenstelle).

Depends on schema_core (companies, structure_nodes). Registered in
init_schema AFTER create_schema_core and create_schema_divisions.
Fully idempotent; auto-applied on boot via database.init_db().
"""
import logging

logger = logging.getLogger(__name__)


def create_schema_cost_centers(conn, cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_centers (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            code VARCHAR(8) NOT NULL,
            name VARCHAR(255) NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, code)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_centers_company ON cost_centers(company_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_center_structure_map (
            id SERIAL PRIMARY KEY,
            cost_center_id INTEGER NOT NULL REFERENCES cost_centers(id) ON DELETE CASCADE,
            structure_node_id INTEGER REFERENCES structure_nodes(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (cost_center_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cc_map_node ON cost_center_structure_map(structure_node_id)")

    conn.commit()
    logger.info('Cost Centers schema created/verified')
```

- [ ] **Step 2: Register it in `init_schema.py`**

In `jarvis/migrations/init_schema.py`, add the import next to the divisions import:
```python
from .domains.schema_divisions import create_schema_divisions
from .domains.schema_cost_centers import create_schema_cost_centers
```
And the call immediately after `create_schema_divisions(conn, cursor)` inside `create_schema(...)`:
```python
    create_schema_divisions(conn, cursor)
    create_schema_cost_centers(conn, cursor)
```
(Leave `create_schema_incremental` and `run_pending_migrations` last, untouched.)

- [ ] **Step 3: Create the test package + fixture**

Create `jarvis/tests/cost_centers/__init__.py` (empty).

Create `jarvis/tests/cost_centers/conftest.py`:
```python
import os
import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

try:
    import psycopg2
    _c = psycopg2.connect(os.environ['DATABASE_URL'])
    _c.cursor().execute('SELECT 1')
    _c.close()
    REAL_DB_AVAILABLE = True
except Exception:
    REAL_DB_AVAILABLE = False

_MARK = 'ZZ_CC_TEST_CO'

if REAL_DB_AVAILABLE:
    from database import get_db, get_cursor, release_db


@pytest.fixture
def cc_fixture():
    if not REAL_DB_AVAILABLE:
        pytest.skip('no real DB available (CI)')
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute("INSERT INTO companies (company, vat) VALUES (%s, %s) RETURNING id",
                    (_MARK, 'ZZCCVAT'))
        ids['company_id'] = cur.fetchone()['id']
        cid = ids['company_id']
        # two structure nodes for map tests; 'IT' name matches a cost center exactly
        for nm in ('IT', 'Reparatii generale VW'):
            cur.execute(
                "INSERT INTO structure_nodes (company_id, parent_id, name, level) "
                "VALUES (%s, NULL, %s, 1) RETURNING id",
                (cid, nm),
            )
            ids[f'node_{nm[:2]}'] = cur.fetchone()['id']
        conn.commit()
        yield ids
    finally:
        cur.execute("DELETE FROM cost_centers WHERE company_id = %s", (ids.get('company_id'),))
        cur.execute("DELETE FROM structure_nodes WHERE company_id = %s", (ids.get('company_id'),))
        cur.execute("DELETE FROM companies WHERE id = %s", (ids.get('company_id'),))
        conn.commit()
        release_db(conn)
```

Create `jarvis/tests/cost_centers/test_cost_center_repository.py` with the schema-presence test:
```python
import pytest
from tests.cost_centers.conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


def test_cost_center_tables_exist():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT to_regclass('public.cost_centers') AS t")
        assert cur.fetchone()['t'] == 'cost_centers'
        cur.execute("SELECT to_regclass('public.cost_center_structure_map') AS t")
        assert cur.fetchone()['t'] == 'cost_center_structure_map'
    finally:
        release_db(conn)
```

- [ ] **Step 4: Run the test to verify tables were created on boot**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_cost_center_repository.py::test_cost_center_tables_exist -v`
Expected: PASS (importing `database` runs `init_db()` → `create_schema()` → `create_schema_cost_centers`). If it FAILS with `t == None`, the registration in Step 2 is wrong.

- [ ] **Step 5: Commit**

```bash
git add jarvis/migrations/domains/schema_cost_centers.py jarvis/migrations/init_schema.py jarvis/tests/cost_centers/
git commit -m "feat(cost-centers): cost_centers + cost_center_structure_map schema"
```

---

## Task 2: One-time seed from the AW Excel

**Files:**
- Create: `jarvis/migrations/domains/cost_centers_seed.py`
- Modify: `jarvis/migrations/domains/schema_cost_centers.py` (add `_seed_cost_centers` + `COUNT==0` guard)
- Test: `jarvis/tests/cost_centers/test_schema_seed.py`

**Interfaces:**
- Produces: `SEED_ROWS: list[tuple[str, str, str]]` = `(sheet_key, code, name)`; `SHEET_TO_COMPANY: dict[str, str]` = sheet_key → exact `companies.company`.
- Consumes: `cost_centers` table from Task 1.

**Phase-0 prerequisite (do this first, in this task):** resolve the 6 sheet labels to exact `companies.company` values. Run:
```sql
SELECT id, company FROM companies ORDER BY company;
```
Map each sheet to the matching company row and fill `SHEET_TO_COMPANY` below. `AW` is the holding entity (only IT/Conducere/Contabilitate/Administrativ); the others are the operating companies. If a sheet has no matching `companies` row, leave it mapped to the best exact string and the seed will log-and-skip it (non-fatal) — record the gap in the commit message.

- [ ] **Step 1: Write the seed data module**

Create `jarvis/migrations/domains/cost_centers_seed.py`:
```python
"""Cost-center seed rows, extracted verbatim from
'centre cost firme grup AW 2026.xlsx' (6 sheets). One-time seed only;
in-app CRUD is authoritative afterwards. Code kept zero-padded (EuroFib form)."""

# sheet_key -> exact companies.company value (FILL from the SELECT above).
SHEET_TO_COMPANY = {
    'AW':            'Autoworld S.R.L.',            # holding — VERIFY exact string
    'AW INTERNATIONAL': 'Autoworld INTERNATIONAL S.R.L.',  # VERIFY
    'AW PREMIUM':    'Autoworld PREMIUM S.R.L.',    # VERIFY
    'AW PRESTIGE':   'Autoworld PRESTIGE S.R.L.',   # VERIFY
    'AW PLUS':       'Autoworld PLUS S.R.L.',       # VERIFY
    'AW NEXT':       'Autoworld NEXT S.R.L.',       # VERIFY
}

SEED_ROWS = [
    # AW (holding)
    ('AW', '0281', 'IT'),
    ('AW', '0291', 'Conducere'),
    ('AW', '0292', 'Contabilitate'),
    ('AW', '0293', 'Administrativ VW'),
    # AW INTERNATIONAL
    ('AW INTERNATIONAL', '0211', 'Masini noi VW PKW'),
    ('AW INTERNATIONAL', '0212', 'Masini noi VW LNF'),
    ('AW INTERNATIONAL', '0231', 'Reparatii generale VW'),
    ('AW INTERNATIONAL', '0232', 'Tinichigerie VW'),
    ('AW INTERNATIONAL', '0233', 'Vopsitorie VW'),
    ('AW INTERNATIONAL', '0235', 'Piese de schimb VW'),
    ('AW INTERNATIONAL', '0234', 'Centru daune Oradiei'),
    ('AW INTERNATIONAL', '0240', 'Logistica'),
    ('AW INTERNATIONAL', '0241', 'Spalatorie VW'),
    ('AW INTERNATIONAL', '0281', 'IT'),
    ('AW INTERNATIONAL', '0291', 'Conducere'),
    ('AW INTERNATIONAL', '0292', 'Contabilitate'),
    ('AW INTERNATIONAL', '0293', 'Administrativ VW'),
    # AW PREMIUM
    ('AW PREMIUM', '0281', 'IT'),
    ('AW PREMIUM', '0291', 'Conducere'),
    ('AW PREMIUM', '0292', 'Contabilitate'),
    ('AW PREMIUM', '0313', 'Masini noi AUDI'),
    ('AW PREMIUM', '0322', 'AAP'),
    ('AW PREMIUM', '0331', 'Reparatii generale AUDI'),
    ('AW PREMIUM', '0335', 'Piese de schimb AUDI'),
    ('AW PREMIUM', '0341', 'Spalatorie AUDI'),
    ('AW PREMIUM', '0393', 'Administrativ AUDI'),
    ('AW PREMIUM', '0451', 'Asigurari'),
    # AW PRESTIGE
    ('AW PRESTIGE', '0411', 'Masini noi VOLVO'),
    ('AW PRESTIGE', '0431', 'Reparatii generale Volvo'),
    ('AW PRESTIGE', '0432', 'Tinichigerie VOLVO'),
    ('AW PRESTIGE', '0433', 'Vopsitorie VOLVO'),
    ('AW PRESTIGE', '0435', 'Piese de schimb VOLVO'),
    ('AW PRESTIGE', '0441', 'Spalatorie VOLVO'),
    ('AW PRESTIGE', '0481', 'IT VOLVO'),
    ('AW PRESTIGE', '0491', 'Conducere VOLVO'),
    ('AW PRESTIGE', '0492', 'Contabilitate VOLVO'),
    ('AW PRESTIGE', '0493', 'Administrativ VOLVO'),
    # AW PLUS
    ('AW PLUS', '0281', 'IT'),
    ('AW PLUS', '0291', 'Conducere'),
    ('AW PLUS', '0292', 'Contabilitate'),
    ('AW PLUS', '0611', 'Masini noi MG'),
    ('AW PLUS', '0612', 'Masini noi Mazda'),
    ('AW PLUS', '0631', 'Reparatii generale MG'),
    ('AW PLUS', '0632', 'Tinichigerie MG'),
    ('AW PLUS', '0633', 'Vopsitorie MG'),
    ('AW PLUS', '0635', 'Piese de schimb MG'),
    ('AW PLUS', '0641', 'Reparatii generale Mazda'),
    ('AW PLUS', '0642', 'Tinichigerie Mazda'),
    ('AW PLUS', '0643', 'Vopsitorie Mazda'),
    ('AW PLUS', '0645', 'Piese de schimb Mazda'),
    ('AW PLUS', '0654', 'Spalatorie'),
    ('AW PLUS', '0693', 'Administrativ'),
    # AW NEXT
    ('AW NEXT', '0281', 'IT'),
    ('AW NEXT', '0291', 'Conducere'),
    ('AW NEXT', '0292', 'Contabilitate'),
    ('AW NEXT', '0293', 'Administrativ VW'),
    ('AW NEXT', '0421', 'Masini Weltauto CarCloud'),
    ('AW NEXT', '0452', 'Motion'),
]
```

- [ ] **Step 2: Add the seed helper + guard to `schema_cost_centers.py`**

At the top of `schema_cost_centers.py`:
```python
from .cost_centers_seed import SEED_ROWS, SHEET_TO_COMPANY
```
Before `conn.commit()` in `create_schema_cost_centers`, add the guarded seed:
```python
    cursor.execute('SELECT COUNT(*) FROM cost_centers')
    if cursor.fetchone()['count'] == 0:
        _seed_cost_centers(cursor)
```
And the helper at module bottom:
```python
def _seed_cost_centers(cursor):
    inserted, skipped = 0, 0
    for sheet_key, code, name in SEED_ROWS:
        company_name = SHEET_TO_COMPANY.get(sheet_key)
        cursor.execute('SELECT id FROM companies WHERE company = %s', (company_name,))
        row = cursor.fetchone()
        if not row:
            logger.warning('cost_centers seed: no company for sheet %r (%r) — skipping %s %s',
                           sheet_key, company_name, code, name)
            skipped += 1
            continue
        cursor.execute(
            "INSERT INTO cost_centers (company_id, code, name) VALUES (%s, %s, %s) "
            "ON CONFLICT (company_id, code) DO NOTHING",
            (row['id'], code, name),
        )
        inserted += 1
    logger.info('cost_centers seeded: %s inserted, %s skipped', inserted, skipped)
```

- [ ] **Step 3: Write the seed test** (uses a real company + verifies guard is idempotent)

Create `jarvis/tests/cost_centers/test_schema_seed.py`:
```python
import pytest
from tests.cost_centers.conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db
from migrations.domains.schema_cost_centers import _seed_cost_centers

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


def test_seed_is_idempotent_and_skips_unknown_company(monkeypatch):
    # Point the seed at a temp company so the real seed is untouched
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO companies (company, vat) VALUES ('ZZ_CC_SEED_CO','ZZS') RETURNING id")
        cid = cur.fetchone()['id']
        conn.commit()
        import migrations.domains.schema_cost_centers as m
        monkeypatch.setattr(m, 'SEED_ROWS', [('S', '0281', 'IT'), ('S', '0291', 'Conducere')])
        monkeypatch.setattr(m, 'SHEET_TO_COMPANY', {'S': 'ZZ_CC_SEED_CO'})
        _seed_cost_centers(cur); conn.commit()
        _seed_cost_centers(cur); conn.commit()  # second run must not duplicate
        cur.execute("SELECT COUNT(*) AS n FROM cost_centers WHERE company_id = %s", (cid,))
        assert cur.fetchone()['n'] == 2
    finally:
        cur.execute("DELETE FROM cost_centers WHERE company_id = %s", (cid,))
        cur.execute("DELETE FROM companies WHERE id = %s", (cid,))
        conn.commit()
        release_db(conn)
```

- [ ] **Step 4: Run the seed test**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_schema_seed.py -v`
Expected: PASS (2 rows after two seed runs → idempotent via `ON CONFLICT`).

- [ ] **Step 5: Commit**

```bash
git add jarvis/migrations/domains/cost_centers_seed.py jarvis/migrations/domains/schema_cost_centers.py jarvis/tests/cost_centers/test_schema_seed.py
git commit -m "feat(cost-centers): one-time Excel seed (COUNT==0 guarded, idempotent)"
```

---

## Task 3: `CostCenterRepository` — CRUD

**Files:**
- Create: `jarvis/accounting/cost_centers/__init__.py`, `jarvis/accounting/cost_centers/repositories/__init__.py`
- Create: `jarvis/accounting/cost_centers/repositories/cost_center_repository.py`
- Test: `jarvis/tests/cost_centers/test_cost_center_repository.py` (extend)

**Interfaces:**
- Produces:
  - `list_companies() -> list[dict]` — companies that have ≥1 cost center: `{company_id, company, count}`.
  - `list_by_company(company_id: int) -> list[dict]` — `{id, company_id, code, name, active, display_order, structure_node_id, structure_node_name}` ordered by `code`.
  - `create(company_id: int, code: str, name: str) -> int` (new id).
  - `update(cc_id: int, code: str|None, name: str|None, active: bool|None) -> None`.
  - `delete(cc_id: int) -> None`.
- Consumes: `BaseRepository` helpers; `cost_centers`, `cost_center_structure_map`, `structure_nodes`, `companies` tables.

- [ ] **Step 1: Write failing tests for create/list/update/delete**

Append to `jarvis/tests/cost_centers/test_cost_center_repository.py`:
```python
from accounting.cost_centers.repositories.cost_center_repository import CostCenterRepository

_repo = CostCenterRepository()


def test_create_and_list_by_company(cc_fixture):
    cid = cc_fixture['company_id']
    a = _repo.create(cid, '0281', 'IT')
    b = _repo.create(cid, '0291', 'Conducere')
    rows = _repo.list_by_company(cid)
    codes = [r['code'] for r in rows]
    assert codes == ['0281', '0291']            # ordered by code
    assert {r['id'] for r in rows} == {a, b}
    assert all(r['structure_node_id'] is None for r in rows)


def test_duplicate_code_same_company_rejected(cc_fixture):
    cid = cc_fixture['company_id']
    _repo.create(cid, '0281', 'IT')
    with pytest.raises(Exception):
        _repo.create(cid, '0281', 'IT again')   # UNIQUE(company_id, code)


def test_update_and_delete(cc_fixture):
    cid = cc_fixture['company_id']
    cc = _repo.create(cid, '0281', 'IT')
    _repo.update(cc, code=None, name='IT & Systems', active=False)
    row = next(r for r in _repo.list_by_company(cid) if r['id'] == cc)
    assert row['name'] == 'IT & Systems' and row['active'] is False
    _repo.delete(cc)
    assert all(r['id'] != cc for r in _repo.list_by_company(cid))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_cost_center_repository.py -k "create_and_list or duplicate_code or update_and_delete" -v`
Expected: FAIL with `ModuleNotFoundError: accounting.cost_centers...`.

- [ ] **Step 3: Write the repository**

Create `jarvis/accounting/cost_centers/__init__.py`:
```python
"""Cost Centers module — Finance budgeting dimension (kostenstelle)."""
from flask import Blueprint

cost_centers_bp = Blueprint('cost_centers', __name__)

from . import routes  # noqa: E402, F401
```
Create `jarvis/accounting/cost_centers/repositories/__init__.py` (empty).

Create `jarvis/accounting/cost_centers/repositories/cost_center_repository.py`:
```python
from core.base_repository import BaseRepository


class CostCenterRepository(BaseRepository):

    def list_companies(self):
        return self.query_all("""
            SELECT c.id AS company_id, c.company, COUNT(cc.id) AS count
            FROM companies c
            JOIN cost_centers cc ON cc.company_id = c.id
            GROUP BY c.id, c.company
            ORDER BY c.company
        """)

    def list_by_company(self, company_id):
        return self.query_all("""
            SELECT cc.id, cc.company_id, cc.code, cc.name, cc.active, cc.display_order,
                   m.structure_node_id,
                   sn.name AS structure_node_name
            FROM cost_centers cc
            LEFT JOIN cost_center_structure_map m ON m.cost_center_id = cc.id
            LEFT JOIN structure_nodes sn ON sn.id = m.structure_node_id
            WHERE cc.company_id = %s
            ORDER BY cc.code
        """, (company_id,))

    def create(self, company_id, code, name):
        row = self.query_one(
            "INSERT INTO cost_centers (company_id, code, name) VALUES (%s, %s, %s) RETURNING id",
            (company_id, code.strip(), name.strip()),
        )
        return row['id'] if row else None

    def update(self, cc_id, code=None, name=None, active=None):
        sets, params = [], []
        if code is not None:
            sets.append('code = %s'); params.append(code.strip())
        if name is not None:
            sets.append('name = %s'); params.append(name.strip())
        if active is not None:
            sets.append('active = %s'); params.append(bool(active))
        if not sets:
            return
        sets.append('updated_at = NOW()')
        params.append(cc_id)
        self.execute(f"UPDATE cost_centers SET {', '.join(sets)} WHERE id = %s", tuple(params))

    def delete(self, cc_id):
        self.execute("DELETE FROM cost_centers WHERE id = %s", (cc_id,))  # cascades map row
```

- [ ] **Step 4: Run to verify pass**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_cost_center_repository.py -k "create_and_list or duplicate_code or update_and_delete" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/accounting/cost_centers/__init__.py jarvis/accounting/cost_centers/repositories/ jarvis/tests/cost_centers/test_cost_center_repository.py
git commit -m "feat(cost-centers): CostCenterRepository CRUD"
```

---

## Task 4: Default map — set + auto-seed exact name-matches

**Files:**
- Modify: `jarvis/accounting/cost_centers/repositories/cost_center_repository.py`
- Test: `jarvis/tests/cost_centers/test_cost_center_repository.py` (extend)

**Interfaces:**
- Produces:
  - `set_map(cc_id: int, structure_node_id: int|None) -> None` — upsert the single default node (or clear when `None`).
  - `list_structure_nodes(company_id: int) -> list[dict]` — `{id, name, level}` for the map picker.
  - `auto_seed_map_exact(company_id: int) -> int` — for each unmapped cost center, if exactly one `structure_nodes` row in the same company has a case-insensitive equal name, insert the map; returns count inserted. Ambiguous (>1 match) or no match → skip.
- Consumes: Task 3 repository; `structure_nodes`.

- [ ] **Step 1: Write failing tests**

Append to `test_cost_center_repository.py`:
```python
def test_set_and_clear_map(cc_fixture):
    cid = cc_fixture['company_id']
    cc = _repo.create(cid, '0281', 'IT')
    _repo.set_map(cc, cc_fixture['node_IT'])
    row = next(r for r in _repo.list_by_company(cid) if r['id'] == cc)
    assert row['structure_node_id'] == cc_fixture['node_IT']
    assert row['structure_node_name'] == 'IT'
    _repo.set_map(cc, None)
    row = next(r for r in _repo.list_by_company(cid) if r['id'] == cc)
    assert row['structure_node_id'] is None


def test_auto_seed_map_exact_matches_only(cc_fixture):
    cid = cc_fixture['company_id']
    it = _repo.create(cid, '0281', 'IT')                    # matches node 'IT'
    rep = _repo.create(cid, '0231', 'Reparatii generale VW')  # matches node 'Reparatii generale VW'
    none = _repo.create(cid, '0291', 'Conducere')           # no node -> stays unmapped
    n = _repo.auto_seed_map_exact(cid)
    assert n == 2
    by_id = {r['id']: r for r in _repo.list_by_company(cid)}
    assert by_id[it]['structure_node_id'] == cc_fixture['node_IT']
    assert by_id[rep]['structure_node_id'] == cc_fixture['node_Re']
    assert by_id[none]['structure_node_id'] is None
    assert _repo.auto_seed_map_exact(cid) == 0              # idempotent: nothing new
```

- [ ] **Step 2: Run to verify failure**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_cost_center_repository.py -k "set_and_clear_map or auto_seed_map" -v`
Expected: FAIL with `AttributeError: 'CostCenterRepository' object has no attribute 'set_map'`.

- [ ] **Step 3: Implement the map methods**

Append to `CostCenterRepository`:
```python
    def list_structure_nodes(self, company_id):
        return self.query_all(
            "SELECT id, name, level FROM structure_nodes WHERE company_id = %s ORDER BY level, name",
            (company_id,),
        )

    def set_map(self, cc_id, structure_node_id):
        if structure_node_id is None:
            self.execute("DELETE FROM cost_center_structure_map WHERE cost_center_id = %s", (cc_id,))
            return
        self.execute("""
            INSERT INTO cost_center_structure_map (cost_center_id, structure_node_id)
            VALUES (%s, %s)
            ON CONFLICT (cost_center_id)
            DO UPDATE SET structure_node_id = EXCLUDED.structure_node_id
        """, (cc_id, int(structure_node_id)))

    def auto_seed_map_exact(self, company_id):
        """Map each still-unmapped cost center to the ONLY structure node in the
        same company whose name matches case-insensitively. Skips ambiguous/none."""
        rows = self.query_all("""
            SELECT cc.id AS cc_id,
                   (SELECT sn.id FROM structure_nodes sn
                     WHERE sn.company_id = cc.company_id
                       AND LOWER(sn.name) = LOWER(cc.name)) AS node_id,
                   (SELECT COUNT(*) FROM structure_nodes sn
                     WHERE sn.company_id = cc.company_id
                       AND LOWER(sn.name) = LOWER(cc.name)) AS match_count
            FROM cost_centers cc
            WHERE cc.company_id = %s
              AND NOT EXISTS (SELECT 1 FROM cost_center_structure_map m WHERE m.cost_center_id = cc.id)
        """, (company_id,))
        inserted = 0
        for r in rows:
            if r['match_count'] == 1 and r['node_id'] is not None:
                self.execute(
                    "INSERT INTO cost_center_structure_map (cost_center_id, structure_node_id) "
                    "VALUES (%s, %s) ON CONFLICT (cost_center_id) DO NOTHING",
                    (r['cc_id'], r['node_id']),
                )
                inserted += 1
        return inserted
```

- [ ] **Step 4: Run to verify pass**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_cost_center_repository.py -k "set_and_clear_map or auto_seed_map" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/accounting/cost_centers/repositories/cost_center_repository.py jarvis/tests/cost_centers/test_cost_center_repository.py
git commit -m "feat(cost-centers): default-map set/clear + exact-match auto-seed"
```

---

## Task 5: Blueprint routes + app registration

**Files:**
- Create: `jarvis/accounting/cost_centers/routes.py`
- Modify: `jarvis/app.py`
- Test: `jarvis/tests/cost_centers/test_routes.py`

**Interfaces:**
- Produces HTTP endpoints (all under `can_access_accounting`):
  - `GET  /api/cost-centers/companies` → `{success, data:[{company_id, company, count}]}`
  - `GET  /api/cost-centers?company_id=<id>` → `{success, data:[cost center rows]}`
  - `GET  /api/cost-centers/structure-nodes?company_id=<id>` → `{success, data:[{id,name,level}]}`
  - `POST /api/cost-centers` `{company_id, code, name}` → `201 {success, data:{id}}`
  - `PATCH /api/cost-centers/<id>` `{code?, name?, active?}` → `{success}`
  - `DELETE /api/cost-centers/<id>` → `{success}`
  - `PUT  /api/cost-centers/<id>/map` `{structure_node_id|null}` → `{success}`
  - `POST /api/cost-centers/seed-map-exact` `{company_id}` → `{success, data:{inserted}}`
- Consumes: `CostCenterRepository`; `safe_error_response`; `flask_login.current_user`.

- [ ] **Step 1: Write the routes** (no SQL — all via `_repo`)

Create `jarvis/accounting/cost_centers/routes.py`:
```python
from functools import wraps
from flask import request, jsonify
from flask_login import current_user, login_required

from core.utils.api_helpers import safe_error_response
from accounting.cost_centers import cost_centers_bp
from accounting.cost_centers.repositories.cost_center_repository import CostCenterRepository

_repo = CostCenterRepository()


def _accounting_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if getattr(current_user, 'can_access_accounting', False) or \
           getattr(current_user, 'can_access_settings', False):
            return f(*args, **kwargs)
        return jsonify({'success': False, 'error': 'Permission denied: accounting required'}), 403
    return decorated


def _is_duplicate(e):
    s = str(e).lower()
    return 'unique' in s or 'duplicate' in s


@cost_centers_bp.route('/api/cost-centers/companies', methods=['GET'])
@_accounting_required
def api_cc_companies():
    try:
        return jsonify({'success': True, 'data': _repo.list_companies()})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers', methods=['GET'])
@_accounting_required
def api_cc_list():
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        return jsonify({'success': True, 'data': _repo.list_by_company(company_id)})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/structure-nodes', methods=['GET'])
@_accounting_required
def api_cc_structure_nodes():
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        return jsonify({'success': True, 'data': _repo.list_structure_nodes(company_id)})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers', methods=['POST'])
@_accounting_required
def api_cc_create():
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not company_id or not code or not name:
        return jsonify({'success': False, 'error': 'company_id, code și name sunt obligatorii'}), 400
    try:
        cc_id = _repo.create(company_id, code, name)
        return jsonify({'success': True, 'data': {'id': cc_id}}), 201
    except Exception as e:
        if _is_duplicate(e):
            return jsonify({'success': False, 'error': 'Un centru de cost cu acest cod există deja'}), 409
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/<int:cc_id>', methods=['PATCH'])
@_accounting_required
def api_cc_update(cc_id):
    data = request.get_json(silent=True) or {}
    try:
        _repo.update(cc_id, code=data.get('code'), name=data.get('name'), active=data.get('active'))
        return jsonify({'success': True})
    except Exception as e:
        if _is_duplicate(e):
            return jsonify({'success': False, 'error': 'Un centru de cost cu acest cod există deja'}), 409
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/<int:cc_id>', methods=['DELETE'])
@_accounting_required
def api_cc_delete(cc_id):
    try:
        _repo.delete(cc_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/<int:cc_id>/map', methods=['PUT'])
@_accounting_required
def api_cc_set_map(cc_id):
    data = request.get_json(silent=True) or {}
    try:
        _repo.set_map(cc_id, data.get('structure_node_id'))
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/seed-map-exact', methods=['POST'])
@_accounting_required
def api_cc_seed_map():
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        return jsonify({'success': True, 'data': {'inserted': _repo.auto_seed_map_exact(company_id)}})
    except Exception as e:
        return safe_error_response(e)
```

- [ ] **Step 2: Register the blueprint in `app.py`**

In `jarvis/app.py`, after the vouchers registration (`flask_app.register_blueprint(vouchers_bp)` ~line 216):
```python
    from accounting.cost_centers import cost_centers_bp
    flask_app.register_blueprint(cost_centers_bp)
```

- [ ] **Step 3: Write a route smoke test** (auth-gated → unauthenticated returns 401)

Create `jarvis/tests/cost_centers/test_routes.py`:
```python
import pytest
from tests.cost_centers.conftest import REAL_DB_AVAILABLE

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


@pytest.fixture
def client():
    from app import create_app          # adjust if factory name differs
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_cost_centers_requires_auth(client):
    r = client.get('/api/cost-centers/companies')
    assert r.status_code == 401
    assert r.get_json()['success'] is False
```
Note: if `app.py` exposes the Flask app differently (e.g. a module-level `app` rather than `create_app()`), import that instead — check `jarvis/app.py` for the factory/app symbol before running.

- [ ] **Step 4: Run the smoke test**

Run: `cd jarvis && python -m pytest tests/cost_centers/test_routes.py -v`
Expected: PASS (401 for unauthenticated). If it errors on app import, fix the import to match `app.py`'s actual app/factory symbol, then re-run.

- [ ] **Step 5: Commit**

```bash
git add jarvis/accounting/cost_centers/routes.py jarvis/app.py jarvis/tests/cost_centers/test_routes.py
git commit -m "feat(cost-centers): CRUD + map blueprint routes, registered in app"
```

---

## Task 6: Frontend types + API module

**Files:**
- Create: `jarvis/frontend/src/types/costCenters.ts`
- Create: `jarvis/frontend/src/api/costCenters.ts`

**Interfaces:**
- Produces `costCentersApi` (typed, uses shared `api` client) and the `CostCenter`, `CostCenterCompany`, `StructureNodeOption` types consumed by Task 7.
- Consumes: `jarvis/frontend/src/api/client.ts` (`api.get/post/patch/put/delete`).

- [ ] **Step 1: Write the types**

Create `jarvis/frontend/src/types/costCenters.ts`:
```typescript
export interface CostCenterCompany {
  company_id: number
  company: string
  count: number
}

export interface CostCenter {
  id: number
  company_id: number
  code: string
  name: string
  active: boolean
  display_order: number
  structure_node_id: number | null
  structure_node_name: string | null
}

export interface StructureNodeOption {
  id: number
  name: string
  level: number
}
```

- [ ] **Step 2: Write the API module**

Create `jarvis/frontend/src/api/costCenters.ts`:
```typescript
import { api } from './client'
import type { CostCenter, CostCenterCompany, StructureNodeOption } from '@/types/costCenters'

export const costCentersApi = {
  companies: () =>
    api.get<{ success: boolean; data: CostCenterCompany[] }>('/api/cost-centers/companies'),
  list: (companyId: number) =>
    api.get<{ success: boolean; data: CostCenter[] }>(`/api/cost-centers?company_id=${companyId}`),
  structureNodes: (companyId: number) =>
    api.get<{ success: boolean; data: StructureNodeOption[] }>(
      `/api/cost-centers/structure-nodes?company_id=${companyId}`),
  create: (payload: { company_id: number; code: string; name: string }) =>
    api.post<{ success: boolean; data: { id: number } }>('/api/cost-centers', payload),
  update: (id: number, payload: { code?: string; name?: string; active?: boolean }) =>
    api.patch<{ success: boolean }>(`/api/cost-centers/${id}`, payload),
  remove: (id: number) =>
    api.delete<{ success: boolean }>(`/api/cost-centers/${id}`),
  setMap: (id: number, structureNodeId: number | null) =>
    api.put<{ success: boolean }>(`/api/cost-centers/${id}/map`, { structure_node_id: structureNodeId }),
  seedMapExact: (companyId: number) =>
    api.post<{ success: boolean; data: { inserted: number } }>(
      '/api/cost-centers/seed-map-exact', { company_id: companyId }),
}
```
Before writing, open `jarvis/frontend/src/api/client.ts` and confirm the method names (`get/post/patch/put/delete`) and whether they return the parsed body directly; adjust generics to match the existing style (see `api/organization.ts` for the canonical usage).

- [ ] **Step 3: Typecheck**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no new errors referencing `costCenters.ts`.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/types/costCenters.ts jarvis/frontend/src/api/costCenters.ts
git commit -m "feat(cost-centers): frontend types + costCentersApi"
```

---

## Task 7: Frontend page — `pages/Accounting/CostCenters/index.tsx`

**Files:**
- Create: `jarvis/frontend/src/pages/Accounting/CostCenters/index.tsx`
- Test: manual (build + click-through)

**Interfaces:**
- Consumes: `costCentersApi` (Task 6); shadcn `Table/Dialog/Button/Input/Label/Select/Badge/Switch`, `ConfirmDialog`, `toast` (sonner), TanStack Query.
- Produces: default-exported `CostCenters` page component consumed by Task 8.

- [ ] **Step 1: Build the page**

Create `jarvis/frontend/src/pages/Accounting/CostCenters/index.tsx` modeled on `pages/Hr/DivisionsTab.tsx`:
  - A company selector (shadcn `Select`) fed by `costCentersApi.companies()`; default to the first.
  - `useQuery(['cost-centers', companyId], () => costCentersApi.list(companyId))` for the table; `useQuery(['cc-structure-nodes', companyId], ...)` for the map picker options.
  - A shadcn `Table` with columns: **Cod**, **Denumire**, **Nod structură (mapare)**, **Activ**, actions. The map cell is a `Select` of structure nodes (with an empty "— Nemapat —" option) calling `costCentersApi.setMap`; the Activ cell is a `Switch` calling `update`.
  - Toolbar buttons: **Adaugă centru de cost** (opens a create `Dialog` with Cod + Denumire inputs) and **Auto-mapează (nume identice)** calling `costCentersApi.seedMapExact(companyId)` then toasting `"{inserted} centre mapate"`.
  - Row actions: edit (pencil → dialog editing Cod + Denumire) and delete (shared `ConfirmDialog`, destructive, Romanian copy).
  - Every mutation's `onSuccess` invalidates `['cost-centers', companyId]` and `toast.success(...)`; `onError` → `toast.error(...)`. All strings Romanian.
  - Wrap the page in the standard page shell used by sibling Accounting pages (check `pages/Accounting/Vouchers/index.tsx` for the `PageHeader`/container idiom and copy it).

- [ ] **Step 2: Typecheck + build**

Run: `cd jarvis/frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds, no errors referencing `CostCenters`.

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/CostCenters/index.tsx
git commit -m "feat(cost-centers): Centre de cost CRUD page"
```

---

## Task 8: Navigation + routing

**Files:**
- Modify: `jarvis/frontend/src/App.tsx`
- Modify: `jarvis/frontend/src/components/Sidebar.tsx`
- Test: manual (nav appears, route loads)

**Interfaces:**
- Consumes: `CostCenters` page (Task 7).
- Produces: route `/app/accounting/cost-centers` + an Accounting sidebar child "Centre de cost".

- [ ] **Step 1: Add the route in `App.tsx`**

Lazy import alongside the other Accounting pages:
```tsx
const CostCenters = lazy(() => import('./pages/Accounting/CostCenters'))
```
Add the guarded route beside `accounting/vouchers` (feature-flag gate only — no V2Guard in Phase 1):
```tsx
        <Route path="accounting/cost-centers" element={<Guard flag="can_access_accounting"><SuspensePage><CostCenters /></SuspensePage></Guard>} />
```
(Match the exact `<Guard>`/`<SuspensePage>` wrapper names used by the neighbouring accounting routes.)

- [ ] **Step 2: Add the sidebar child in `Sidebar.tsx`**

In the Accounting group's `children` array, add:
```tsx
      { path: '/app/accounting/cost-centers', label: 'Centre de cost', icon: Coins, moduleKey: 'accounting_cost_centers', permission: 'can_access_accounting' },
```
Import an icon that exists in the file's `lucide-react` import (e.g. `Coins` or reuse `Calculator`); add it to that import if missing.

- [ ] **Step 3: Typecheck + build**

Run: `cd jarvis/frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual verification**

Start the app (backend `:5001` + Vite `:5173` per the local-dev routine), log in as an accounting/admin user, confirm the **Centre de cost** item appears under Accounting, the page loads, the company selector lists seeded companies, rows show, and Adaugă/edit/delete/map/Auto-mapează all work and persist across reload.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/App.tsx jarvis/frontend/src/components/Sidebar.tsx
git commit -m "feat(cost-centers): route + Accounting sidebar entry"
```

---

## Task 9: Full test run + phase wrap-up

- [ ] **Step 1: Run the whole cost-centers backend suite**

Run: `cd jarvis && python -m pytest tests/cost_centers/ -v`
Expected: all PASS locally; all SKIP on CI (no DB).

- [ ] **Step 2: Frontend gate**

Run: `cd jarvis/frontend && npx tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 3: Confirm zero impact on invoices**

Grep to confirm Phase 1 touched nothing in allocation/notification:
```bash
git diff --name-only dev...HEAD | grep -E "allocation|notification_service|invoice_service|structure_node_repository" || echo "OK: no invoice/notification files changed"
```
Expected: `OK: ...`.

- [ ] **Step 4: Update the "What's New" / changelog if this ships to the mobile-visible app** (skip if web-only). Follow the repo's changelog convention.

---

## Self-Review notes (author)

- **Spec coverage:** `cost_centers` table (Task 1), `cost_center_structure_map` (Task 1), one-time seed + COUNT==0 guard + in-app authority (Task 2), per-company uniqueness (Task 3 test), default-map + exact-match auto-seed (Task 4), Finance CRUD section + admin/accounting gating (Tasks 5–8), Romanian copy (Tasks 5–8). Phases 2–4 explicitly out of scope.
- **No-impact guarantee:** enforced by Task 9 Step 3.
- **Known follow-ups (not Phase 1):** granular `accounting.cost_centers.*` v2 permission (Phase 1 uses the `can_access_accounting` flag); `allocations.cost_center_id` + AllocationEditor picker (Phase 2); EuroFib export from cost center (Phase 3). The `schema_incremental.py` DO-block mechanism for adding `allocations.cost_center_id` is documented in the spec and will be its own task in the Phase 2 plan.
- **Verify-before-code checks the executor must do:** exact `companies.company` strings for `SHEET_TO_COMPANY` (Task 2), the `api` client method surface (Task 6), the `<Guard>`/`<SuspensePage>` wrapper + page-shell names (Tasks 7–8), and the `app.py` app/factory symbol (Task 5 test).
