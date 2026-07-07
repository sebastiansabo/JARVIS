# BAB (Controlling) Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a BAB import + Marja margin report module under Accounting → Controlling in JARVIS.

**Architecture:** Flask blueprint (`controlling_bab_bp`) with raw SQL via `BaseRepository`, openpyxl for xlsx parsing/export, React 19 + TypeScript + shadcn/ui frontend with TanStack Query for data fetching.

**Tech Stack:** Flask, psycopg2 (BaseRepository), openpyxl, React 19, TypeScript, Tailwind 4, shadcn/ui, TanStack Query

## Global Constraints

- All SQL parameterized (`%s` placeholders, never f-strings)
- All routes require `@login_required`
- Permission checks via V2 system: `_check_bab_perm(action)`
- company_id INTEGER (not tenant_id UUID)
- No Redis caching — compute on-the-fly
- Branch: `dev` only
- Tables use `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`
- API envelope: `{"success": true, ...}` or `{"success": false, "error": "..."}`

---

### Task 1: Database Schema

**Files:**
- Create: `jarvis/migrations/domains/schema_controlling_bab.py`
- Modify: `jarvis/migrations/init_schema.py:1-65`

**Interfaces:**
- Produces: `create_schema_controlling_bab(conn, cursor)` function that creates 3 tables + indexes + seeds permissions

- [ ] **Step 1: Create schema file**

Create `jarvis/migrations/domains/schema_controlling_bab.py`:

```python
"""Controlling BAB module — database schema."""


def create_schema_controlling_bab(conn, cursor):
    """Create BAB tables, indexes, and seed permissions."""

    # ── bab_uploads ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_uploads (
            id              SERIAL PRIMARY KEY,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            period_year     SMALLINT NOT NULL,
            period_month    SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
            filename        TEXT NOT NULL,
            uploaded_by     INTEGER NOT NULL REFERENCES users(id),
            uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            row_count       INTEGER,
            status          TEXT NOT NULL DEFAULT 'processing'
                              CHECK (status IN ('processing', 'ready', 'error')),
            error_msg       TEXT,
            locked_at       TIMESTAMPTZ,
            locked_by       INTEGER REFERENCES users(id),
            unlocked_at     TIMESTAMPTZ,
            unlocked_by     INTEGER REFERENCES users(id),
            import_count    SMALLINT NOT NULL DEFAULT 1,
            UNIQUE (company_id, period_year, period_month)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_uploads_company ON bab_uploads(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_uploads_period ON bab_uploads(period_year, period_month)')

    # ── bab_entries ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_entries (
            id              SERIAL PRIMARY KEY,
            upload_id       INTEGER NOT NULL REFERENCES bab_uploads(id) ON DELETE CASCADE,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            konto           INTEGER NOT NULL,
            konto_bez       TEXT,
            saldo1          NUMERIC(18,2) NOT NULL,
            kostenstelle    INTEGER NOT NULL,
            kst_bez1        TEXT
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_upload ON bab_entries(upload_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_konto ON bab_entries(upload_id, konto)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_kst ON bab_entries(upload_id, kostenstelle)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_company ON bab_entries(company_id)')

    # ── bab_eur_rates ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_eur_rates (
            id              SERIAL PRIMARY KEY,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            period_year     SMALLINT NOT NULL,
            period_month    SMALLINT NOT NULL,
            eur_rate        NUMERIC(10,4) NOT NULL,
            set_by          INTEGER REFERENCES users(id),
            set_at          TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, period_year, period_month)
        )
    ''')

    # ── Permissions V2 ──
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'controlling'")
    if cursor.fetchone()['cnt'] == 0:
        controlling_perms = [
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'view', 'View', 'View BAB uploads and margin reports', False, 1),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'add', 'Add', 'Import and re-import BAB files', False, 2),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'edit', 'Edit', 'Set EUR exchange rate', False, 3),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'delete', 'Delete', 'Delete BAB uploads', False, 4),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'lock', 'Lock', 'Lock and unlock periods', False, 5),
        ]
        for p in controlling_perms:
            cursor.execute('''
                INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
            ''', p)

        # Admin gets all
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Admin' AND p.module_key = 'controlling'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        # Manager gets view + add + edit
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Manager' AND p.module_key = 'controlling'
            AND p.action_key IN ('view', 'add', 'edit')
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        # User + Viewer get view only
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name IN ('User', 'Viewer') AND p.module_key = 'controlling'
            AND p.action_key = 'view'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

    conn.commit()
```

- [ ] **Step 2: Register in init_schema.py**

Add import at top of `jarvis/migrations/init_schema.py` (after line 29, the `schema_ticketing` import):

```python
from .domains.schema_controlling_bab import create_schema_controlling_bab
```

Add call in `create_schema()` function (before `create_schema_incremental` on line 63):

```python
    create_schema_controlling_bab(conn, cursor)
```

- [ ] **Step 3: Add menu registry entry**

In `jarvis/core/settings/menus/registry.py`, find the `accounting` module's `children` list and add after the `accounting_facturare` entry:

```python
            {'module_key': 'accounting_controlling', 'name': 'Controlling', 'description': 'BAB import and margin reports', 'icon': 'bi-bar-chart', 'url': '/accounting/controlling', 'sort_order': 6},
```

Then increment the `sort_order` of `accounting_add` (to 7) and `accounting_templates` (to 8).

- [ ] **Step 4: Verify tables create successfully**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -c "
from migrations.domains.schema_controlling_bab import create_schema_controlling_bab
print('Module imports OK')
"
```

Expected: `Module imports OK`

---

### Task 2: Repository

**Files:**
- Create: `jarvis/accounting/controlling_bab/__init__.py`
- Create: `jarvis/accounting/controlling_bab/repository.py`

**Interfaces:**
- Consumes: `BaseRepository` from `core.base_repository`
- Produces:
  - `BabRepository.get_upload(upload_id: int) -> dict | None`
  - `BabRepository.get_upload_by_period(company_id: int, year: int, month: int) -> dict | None`
  - `BabRepository.get_periods(company_id: int) -> list[dict]`
  - `BabRepository.list_uploads(company_id: int) -> list[dict]`
  - `BabRepository.create_upload(company_id, year, month, filename, uploaded_by, row_count, status) -> dict`
  - `BabRepository.reimport_upload(upload_id, filename, uploaded_by, row_count) -> dict`
  - `BabRepository.delete_upload(upload_id) -> int`
  - `BabRepository.lock_upload(upload_id, user_id) -> dict`
  - `BabRepository.unlock_upload(upload_id, user_id) -> dict`
  - `BabRepository.insert_entries(upload_id, company_id, entries: list[dict]) -> int`
  - `BabRepository.delete_entries(upload_id) -> int`
  - `BabRepository.get_entries(upload_id) -> list[dict]`
  - `BabRepository.get_eur_rate(company_id, year, month) -> dict | None`
  - `BabRepository.set_eur_rate(company_id, year, month, rate, user_id) -> dict`

- [ ] **Step 1: Create blueprint __init__.py**

Create `jarvis/accounting/controlling_bab/__init__.py`:

```python
"""Controlling BAB — BAB import and Marja margin reports."""
from flask import Blueprint

controlling_bab_bp = Blueprint('controlling_bab', __name__)

from . import routes  # noqa: E402, F401
```

- [ ] **Step 2: Create repository.py**

Create `jarvis/accounting/controlling_bab/repository.py`:

```python
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
```

- [ ] **Step 3: Verify import**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -c "
from accounting.controlling_bab.repository import BabRepository
print('BabRepository imports OK')
"
```

Expected: `BabRepository imports OK`

---

### Task 3: Parser

**Files:**
- Create: `jarvis/accounting/controlling_bab/parser.py`

**Interfaces:**
- Produces: `parse_bab_xlsx(file_bytes: bytes) -> list[dict]`
  - Each dict: `{konto: int, konto_bez: str|None, saldo1: Decimal, kostenstelle: int, kst_bez1: str|None}`

- [ ] **Step 1: Create parser.py**

Create `jarvis/accounting/controlling_bab/parser.py`:

```python
"""BAB .xlsx parser — extracts account lines from ERP BAB export."""
import io
from decimal import Decimal, InvalidOperation

import openpyxl


# Column name mappings (case-insensitive)
COLUMN_MAP = {
    'konto': 'konto',
    'saldo1': 'saldo1',
    'kostenstelle': 'kostenstelle',
    'konto_bez': 'konto_bez',
    'kst_bez1': 'kst_bez1',
}


def parse_bab_xlsx(file_bytes):
    """Parse BAB xlsx file bytes into a list of entry dicts.

    Returns:
        list[dict] with keys: konto, konto_bez, saldo1, kostenstelle, kst_bez1

    Raises:
        ValueError: if required columns are missing or file is invalid
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Cannot open xlsx file: {e}")

    ws = wb.active
    if ws is None:
        raise ValueError("Workbook has no active sheet")

    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        raise ValueError("Workbook is empty")

    # Find header row (row 0)
    header_row = rows[0]
    col_idx = _map_columns(header_row)

    # Validate required columns
    for required in ('konto', 'saldo1', 'kostenstelle'):
        if required not in col_idx:
            raise ValueError(f"Required column '{required}' not found in header: {list(header_row)}")

    entries = []
    for row_num, row in enumerate(rows[1:], start=2):
        konto_raw = row[col_idx['konto']]

        # Skip rows with no konto (summary/header rows)
        if konto_raw is None:
            continue

        try:
            konto = int(float(konto_raw))
        except (ValueError, TypeError):
            continue  # skip non-numeric konto rows

        # Parse saldo1 as Decimal — never through float
        saldo1_raw = row[col_idx['saldo1']]
        if saldo1_raw is None:
            saldo1 = Decimal('0')
        else:
            try:
                saldo1 = Decimal(str(saldo1_raw))
            except (InvalidOperation, ValueError):
                raise ValueError(f"Row {row_num}: invalid saldo1 value '{saldo1_raw}'")

        # Parse kostenstelle
        kst_raw = row[col_idx['kostenstelle']]
        if kst_raw is None:
            continue  # skip rows without cost center
        try:
            kostenstelle = int(float(kst_raw))
        except (ValueError, TypeError):
            continue

        entry = {
            'konto': konto,
            'konto_bez': _get_cell(row, col_idx, 'konto_bez'),
            'saldo1': saldo1,
            'kostenstelle': kostenstelle,
            'kst_bez1': _get_cell(row, col_idx, 'kst_bez1'),
        }
        entries.append(entry)

    return entries


def _map_columns(header_row):
    """Map header names to column indices (case-insensitive)."""
    col_idx = {}
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        name = str(cell).strip().lower()
        if name in COLUMN_MAP:
            col_idx[COLUMN_MAP[name]] = i
    return col_idx


def _get_cell(row, col_idx, key):
    """Safely get a cell value by column key, or None."""
    idx = col_idx.get(key)
    if idx is None or idx >= len(row):
        return None
    val = row[idx]
    return str(val).strip() if val is not None else None
```

- [ ] **Step 2: Verify import**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -c "
from accounting.controlling_bab.parser import parse_bab_xlsx
print('Parser imports OK')
"
```

Expected: `Parser imports OK`

---

### Task 4: Calculator

**Files:**
- Create: `jarvis/accounting/controlling_bab/calculator.py`

**Interfaces:**
- Consumes: list of entry dicts from `BabRepository.get_entries()`
- Produces: `compute_marja_report(entries: list[dict], eur_rate: Decimal) -> dict`
  - Returns: `{sections: [...], marja_finala_lei: Decimal, marja_finala_eur: Decimal, eur_rate: Decimal}`

- [ ] **Step 1: Create calculator.py**

Create `jarvis/accounting/controlling_bab/calculator.py`:

```python
"""Marja (margin) calculation engine — pure function, no DB access."""
from decimal import Decimal, ROUND_HALF_UP


def compute_marja_report(entries, eur_rate):
    """Compute structured margin report from BAB entries.

    Args:
        entries: list[dict] with keys konto, saldo1, kostenstelle, konto_bez, kst_bez1
        eur_rate: Decimal — LEI/EUR exchange rate

    Returns:
        dict with sections, marja_finala_lei, marja_finala_eur, eur_rate
    """
    if not isinstance(eur_rate, Decimal):
        eur_rate = Decimal(str(eur_rate))

    if eur_rate == 0:
        raise ValueError("EUR rate cannot be zero")

    def _sum(konto_list, kst):
        """Sum saldo1 for entries matching konto codes and cost center."""
        total = Decimal('0')
        for e in entries:
            if e['kostenstelle'] == kst and e['konto'] in konto_list:
                total += Decimal(str(e['saldo1']))
        return total

    def _to_eur(lei):
        return (lei / eur_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def _line(label, lei, accounts, kst):
        return {
            'label': label,
            'lei': lei,
            'eur': _to_eur(lei),
            'accounts': accounts,
            'kst': kst,
        }

    # ── KST 211 — PKW INTERN ──

    retail_venit_sales  = _sum([707111, 707116], 211)
    retail_marja_bruta  = _sum([707111, 707116, 607111], 211)
    retail_bonus_import = _sum([609010], 211)
    retail_venit_td     = _sum([707112], 211)
    retail_marja_td     = _sum([707112, 607112], 211)

    flote_venit_sales   = _sum([707110, 707115], 211)
    flote_marja_bruta   = _sum([707110, 707115, 607110], 211)
    flote_bonus_import  = _sum([609011], 211)

    bonus_pfg           = _sum([708001], 211)
    discount_accesorii  = _sum([704315, 902700], 211)

    # MARJA FINALA PKW — 7 components
    marja_finala = (
        retail_marja_bruta + retail_bonus_import + retail_marja_td
        + flote_marja_bruta + flote_bonus_import
        + bonus_pfg + discount_accesorii
    )

    # ── KST 215 — PKW EXTERN ──

    extern_venit_sales  = _sum([707127], 215)
    extern_marja_bruta  = _sum([707127, 607127], 215)
    extern_bonus_import = _sum([609012], 215)
    extern_marja_total  = extern_marja_bruta + extern_bonus_import

    # ── Build report structure ──

    sections = [
        {
            'section': 'VW PKW INTERN (retail) — KST 211',
            'rows': [
                _line('Venit Sales realizat', retail_venit_sales, [707111, 707116], 211),
                _line('Marjă Brută realizată', retail_marja_bruta, [707111, 707116, 607111], 211),
                _line('Bonus trimestrial (importator)', retail_bonus_import, [609010], 211),
                _line('Venit Test Drive', retail_venit_td, [707112], 211),
                _line('Marjă Test Drive', retail_marja_td, [707112, 607112], 211),
            ],
        },
        {
            'section': 'VW PKW INTERN (flote) — KST 211',
            'rows': [
                _line('Venit Sales realizat', flote_venit_sales, [707110, 707115], 211),
                _line('Marjă Brută realizată', flote_marja_bruta, [707110, 707115, 607110], 211),
                _line('Bonus trimestrial (importator)', flote_bonus_import, [609011], 211),
            ],
        },
        {
            'section': 'Bonus & Discount — KST 211',
            'rows': [
                _line('Bonus PFG', bonus_pfg, [708001], 211),
                _line('Discount accesorii', discount_accesorii, [704315, 902700], 211),
            ],
        },
        {
            'section': 'MARJA FINALĂ PKW',
            'rows': [
                _line('MARJA FINALĂ', marja_finala, [], 211),
            ],
        },
        {
            'section': 'VW PKW EXTERN — KST 215',
            'rows': [
                _line('Venit Sales realizat', extern_venit_sales, [707127], 215),
                _line('Marjă Brută realizată', extern_marja_bruta, [707127, 607127], 215),
                _line('Bonus trimestrial (importator)', extern_bonus_import, [609012], 215),
                _line('Marjă Totală Extern', extern_marja_total, [], 215),
            ],
        },
    ]

    return {
        'sections': sections,
        'marja_finala_lei': marja_finala,
        'marja_finala_eur': _to_eur(marja_finala),
        'eur_rate': eur_rate,
    }
```

- [ ] **Step 2: Verify with a quick smoke test**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -c "
from decimal import Decimal
from accounting.controlling_bab.calculator import compute_marja_report

entries = [
    {'konto': 707111, 'saldo1': Decimal('100000'), 'kostenstelle': 211, 'konto_bez': 'Retail sales', 'kst_bez1': 'PKW'},
    {'konto': 607111, 'saldo1': Decimal('-60000'), 'kostenstelle': 211, 'konto_bez': 'Cost retail', 'kst_bez1': 'PKW'},
    {'konto': 609010, 'saldo1': Decimal('5000'), 'kostenstelle': 211, 'konto_bez': 'Bonus Q', 'kst_bez1': 'PKW'},
]
report = compute_marja_report(entries, Decimal('5.0'))
print(f'Marja finala LEI: {report[\"marja_finala_lei\"]}')
print(f'Marja finala EUR: {report[\"marja_finala_eur\"]}')
assert report['marja_finala_lei'] == Decimal('45000'), f'Expected 45000, got {report[\"marja_finala_lei\"]}'
print('Calculator OK')
"
```

Expected: `Marja finala LEI: 45000`, `Marja finala EUR: 9000.00`, `Calculator OK`

---

### Task 5: Exporter

**Files:**
- Create: `jarvis/accounting/controlling_bab/exporter.py`

**Interfaces:**
- Consumes: report dict from `compute_marja_report()`
- Produces: `export_marja_xlsx(report: dict, period_year: int, period_month: int) -> bytes`

- [ ] **Step 1: Create exporter.py**

Create `jarvis/accounting/controlling_bab/exporter.py`:

```python
"""Marja report xlsx export — styled openpyxl output."""
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Style definitions ──
NAVY = PatternFill(start_color='1B2A4A', end_color='1B2A4A', fill_type='solid')
DARK_BLUE = PatternFill(start_color='2C3E6B', end_color='2C3E6B', fill_type='solid')
DARKER_BLUE = PatternFill(start_color='1A2744', end_color='1A2744', fill_type='solid')
GREEN = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
BROWN = PatternFill(start_color='5D4037', end_color='5D4037', fill_type='solid')
LIGHT_GREY = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')

WHITE_BOLD = Font(name='Arial', size=9, bold=True, color='FFFFFF')
WHITE_NORMAL = Font(name='Arial', size=9, color='FFFFFF')
BLACK_NORMAL = Font(name='Arial', size=9)
RED_NORMAL = Font(name='Arial', size=9, color='FF0000')
HEADER_FONT = Font(name='Arial', size=11, bold=True, color='FFFFFF')

THIN_BORDER = Border(
    bottom=Side(style='thin', color='CCCCCC'),
)

MONTH_NAMES_RO = [
    '', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
    'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie',
]

# Section header colors
SECTION_FILLS = {
    'VW PKW INTERN (retail)': DARK_BLUE,
    'VW PKW INTERN (flote)': DARKER_BLUE,
    'Bonus & Discount': BROWN,
    'MARJA FINALĂ': NAVY,
    'VW PKW EXTERN': GREEN,
}


def export_marja_xlsx(report, period_year, period_month):
    """Generate styled Marja report xlsx.

    Args:
        report: dict from compute_marja_report()
        period_year: int
        period_month: int (1-12)

    Returns:
        bytes — xlsx file content
    """
    wb = Workbook()
    ws = wb.active
    ws.title = 'Raport Marjă'

    eur_rate = report['eur_rate']
    month_name = MONTH_NAMES_RO[period_month]

    # Column widths
    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 25
    ws.column_dimensions['E'].width = 10

    # ── Row 1: Title header ──
    ws.merge_cells('A1:E1')
    cell = ws.cell(row=1, column=1,
                   value=f'RAPORT MARJĂ VÂNZĂRI — {month_name} {period_year}  |  Curs: {eur_rate} LEI/EUR')
    cell.font = HEADER_FONT
    cell.fill = NAVY
    cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 30

    # ── Row 2: Column headers ──
    headers = ['Indicator', 'Valoare (LEI)', 'Valoare (EUR)', 'Conturi', 'KST']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = WHITE_BOLD
        cell.fill = NAVY
        cell.alignment = Alignment(horizontal='center')
    ws.row_dimensions[2].height = 22

    # Freeze panes at row 3
    ws.freeze_panes = 'A3'

    # ── Data rows ──
    row_num = 3

    for section in report['sections']:
        section_name = section['section']

        # Section header
        ws.merge_cells(f'A{row_num}:E{row_num}')
        cell = ws.cell(row=row_num, column=1, value=section_name)
        cell.font = WHITE_BOLD

        # Match section fill color
        fill = LIGHT_GREY
        for key, f in SECTION_FILLS.items():
            if key in section_name:
                fill = f
                cell.font = WHITE_BOLD
                break
        cell.fill = fill
        ws.row_dimensions[row_num].height = 22
        row_num += 1

        # Section rows
        for line in section['rows']:
            is_marja_finala = 'MARJA FINALĂ' in line['label']
            is_negative = line['lei'] < 0

            # Label
            cell_a = ws.cell(row=row_num, column=1, value=f'  {line["label"]}')
            # LEI
            cell_b = ws.cell(row=row_num, column=2, value=float(line['lei']))
            cell_b.number_format = '#,##0.00'
            cell_b.alignment = Alignment(horizontal='right')
            # EUR
            cell_c = ws.cell(row=row_num, column=3, value=float(line['eur']))
            cell_c.number_format = '#,##0.00'
            cell_c.alignment = Alignment(horizontal='right')
            # Accounts
            accts = ', '.join(str(a) for a in line['accounts']) if line['accounts'] else ''
            ws.cell(row=row_num, column=4, value=accts).font = BLACK_NORMAL
            # KST
            ws.cell(row=row_num, column=5, value=line['kst']).font = BLACK_NORMAL

            if is_marja_finala:
                for col in range(1, 6):
                    c = ws.cell(row=row_num, column=col)
                    c.fill = NAVY
                    c.font = WHITE_BOLD
                cell_a.value = line['label']  # no indent for marja finala
                ws.row_dimensions[row_num].height = 24
            elif is_negative:
                cell_b.font = RED_NORMAL
                cell_c.font = RED_NORMAL
                cell_a.font = BLACK_NORMAL
            else:
                cell_a.font = BLACK_NORMAL
                cell_b.font = BLACK_NORMAL
                cell_c.font = BLACK_NORMAL

            # Thin bottom border
            for col in range(1, 6):
                ws.cell(row=row_num, column=col).border = THIN_BORDER

            row_num += 1

    # Write to bytes
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
```

- [ ] **Step 2: Verify import**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -c "
from accounting.controlling_bab.exporter import export_marja_xlsx
print('Exporter imports OK')
"
```

Expected: `Exporter imports OK`

---

### Task 6: Routes + Blueprint Registration

**Files:**
- Create: `jarvis/accounting/controlling_bab/routes.py`
- Modify: `jarvis/app.py:201-202` (add blueprint registration)

**Interfaces:**
- Consumes: `BabRepository`, `parse_bab_xlsx()`, `compute_marja_report()`, `export_marja_xlsx()`
- Produces: 10 API endpoints under `/controlling/bab/api/`

- [ ] **Step 1: Create routes.py**

Create `jarvis/accounting/controlling_bab/routes.py`:

```python
"""Controlling BAB API routes."""
import logging
from datetime import date
from decimal import Decimal

from flask import request, jsonify, send_file
from flask_login import login_required, current_user

from . import controlling_bab_bp
from .repository import BabRepository
from .parser import parse_bab_xlsx
from .calculator import compute_marja_report
from .exporter import export_marja_xlsx
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

import io

logger = logging.getLogger('jarvis.controlling_bab')

_repo = BabRepository()
_perm_repo = PermissionRepository()


def _check_bab_perm(action):
    """Check controlling.bab.{action} V2 permission."""
    if getattr(current_user, 'is_admin', False):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'controlling', 'bab', action)
    return perm.get('has_permission', False)


# ── Import ──

@controlling_bab_bp.route('/controlling/bab/api/import', methods=['POST'])
@login_required
@handle_api_errors
def api_import_bab():
    """Import BAB xlsx for a period. Handles first import and re-import."""
    if not _check_bab_perm('add'):
        return error_response('Permission denied', 403)

    file = request.files.get('file')
    if not file:
        return error_response('File is required', 400)

    filename = file.filename or ''
    if not filename.lower().endswith('.xlsx'):
        return error_response('Only .xlsx files are accepted', 415)

    try:
        period_year = int(request.form.get('period_year', 0))
        period_month = int(request.form.get('period_month', 0))
        company_id = int(request.form.get('company_id', 0))
    except (ValueError, TypeError):
        return error_response('period_year, period_month, and company_id are required integers', 400)

    if not (1 <= period_month <= 12) or period_year < 2000 or company_id <= 0:
        return error_response('Invalid period or company_id', 400)

    # Check for locked period
    existing = _repo.get_upload_by_period(company_id, period_year, period_month)
    if existing and existing.get('locked_at'):
        return error_response(f'Period {period_month}/{period_year} is locked', 423)

    # Parse xlsx
    file_bytes = file.read()
    entries = parse_bab_xlsx(file_bytes)

    if not entries:
        return error_response('No valid entries found in BAB file', 400)

    if existing:
        # Re-import: delete old entries, insert new, update upload
        _repo.delete_entries(existing['id'])
        _repo.insert_entries(existing['id'], company_id, entries)
        upload = _repo.reimport_upload(existing['id'], filename, current_user.id, len(entries))
        logger.info(f'BAB re-import: company={company_id} period={period_year}-{period_month} '
                     f'rows={len(entries)} import_count={upload["import_count"]}')
    else:
        # First import
        upload = _repo.create_upload(company_id, period_year, period_month,
                                     filename, current_user.id, len(entries))
        _repo.insert_entries(upload['id'], company_id, entries)
        logger.info(f'BAB import: company={company_id} period={period_year}-{period_month} rows={len(entries)}')

    return jsonify({
        'success': True,
        'upload_id': upload['id'],
        'period': f'{period_year}-{period_month:02d}',
        'status': upload['status'],
        'import_count': upload['import_count'],
        'row_count': len(entries),
    })


# ── Periods (12-month grid) ──

@controlling_bab_bp.route('/controlling/bab/api/periods', methods=['GET'])
@login_required
@handle_api_errors
def api_get_periods():
    """Return 12-month rolling grid with status and marja KPI."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)

    uploads = _repo.get_periods(company_id)
    upload_map = {}
    for u in uploads:
        key = (u['period_year'], u['period_month'])
        upload_map[key] = u

    # Build 12-month grid (current month + 11 prior)
    today = date.today()
    periods = []
    for i in range(11, -1, -1):
        # Calculate month offset
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1

        key = (year, month)
        upload = upload_map.get(key)

        if upload is None:
            periods.append({
                'year': year, 'month': month,
                'status': 'MISSING',
            })
        elif upload.get('locked_at'):
            entry = {
                'year': year, 'month': month,
                'status': 'LOCKED',
                'upload_id': upload['id'],
                'import_count': upload['import_count'],
                'filename': upload['filename'],
                'uploaded_at': upload['uploaded_at'].isoformat() if upload.get('uploaded_at') else None,
            }
            # Compute marja KPI
            marja = _compute_marja_kpi(upload['id'], company_id, year, month)
            if marja is not None:
                entry['marja_finala_eur'] = float(marja)
            periods.append(entry)
        else:
            entry = {
                'year': year, 'month': month,
                'status': 'IMPORTED',
                'upload_id': upload['id'],
                'import_count': upload['import_count'],
                'filename': upload['filename'],
                'uploaded_at': upload['uploaded_at'].isoformat() if upload.get('uploaded_at') else None,
            }
            marja = _compute_marja_kpi(upload['id'], company_id, year, month)
            if marja is not None:
                entry['marja_finala_eur'] = float(marja)
            periods.append(entry)

    return jsonify({'success': True, 'periods': periods})


def _compute_marja_kpi(upload_id, company_id, year, month):
    """Compute marja_finala_eur for a period, or None if EUR rate missing."""
    rate_row = _repo.get_eur_rate(company_id, year, month)
    if not rate_row:
        return None
    try:
        entries = _repo.get_entries(upload_id)
        report = compute_marja_report(entries, Decimal(str(rate_row['eur_rate'])))
        return report['marja_finala_eur']
    except Exception:
        return None


# ── Uploads ──

@controlling_bab_bp.route('/controlling/bab/api/uploads', methods=['GET'])
@login_required
@handle_api_errors
def api_list_uploads():
    """List all uploads for a company."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)

    uploads = _repo.list_uploads(company_id)
    return jsonify({'success': True, 'uploads': uploads})


@controlling_bab_bp.route('/controlling/bab/api/uploads/<int:upload_id>', methods=['DELETE'])
@login_required
@handle_api_errors
def api_delete_upload(upload_id):
    """Delete an upload. Blocked if period is locked."""
    if not _check_bab_perm('delete'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)
    if upload.get('locked_at'):
        return error_response('Period is locked', 423)

    _repo.delete_upload(upload_id)
    return jsonify({'success': True})


# ── Lock / Unlock ──

@controlling_bab_bp.route('/controlling/bab/api/uploads/<int:upload_id>/lock', methods=['POST'])
@login_required
@handle_api_errors
def api_lock_upload(upload_id):
    """Lock a period — requires controlling.bab.lock permission."""
    if not _check_bab_perm('lock'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)
    if upload.get('locked_at'):
        return error_response('Already locked', 409)

    result = _repo.lock_upload(upload_id, current_user.id)
    return jsonify({'success': True, 'upload': result})


@controlling_bab_bp.route('/controlling/bab/api/uploads/<int:upload_id>/unlock', methods=['POST'])
@login_required
@handle_api_errors
def api_unlock_upload(upload_id):
    """Unlock a period — requires controlling.bab.lock permission."""
    if not _check_bab_perm('lock'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)
    if not upload.get('locked_at'):
        return error_response('Period is not locked', 409)

    result = _repo.unlock_upload(upload_id, current_user.id)
    return jsonify({'success': True, 'upload': result})


# ── Report ──

@controlling_bab_bp.route('/controlling/bab/api/report/<int:upload_id>', methods=['GET'])
@login_required
@handle_api_errors
def api_get_report(upload_id):
    """Compute and return MarjaReport for an upload."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)

    rate_row = _repo.get_eur_rate(upload['company_id'], upload['period_year'], upload['period_month'])
    if not rate_row:
        return error_response(
            f'EUR rate not set for {upload["period_month"]}/{upload["period_year"]}', 422)

    entries = _repo.get_entries(upload_id)
    report = compute_marja_report(entries, Decimal(str(rate_row['eur_rate'])))

    # Serialize Decimals to float for JSON
    return jsonify({
        'success': True,
        'report': _serialize_report(report),
        'upload': upload,
    })


@controlling_bab_bp.route('/controlling/bab/api/report/<int:upload_id>/export', methods=['GET'])
@login_required
@handle_api_errors
def api_export_report(upload_id):
    """Export MarjaReport as styled xlsx."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)

    rate_row = _repo.get_eur_rate(upload['company_id'], upload['period_year'], upload['period_month'])
    if not rate_row:
        return error_response(
            f'EUR rate not set for {upload["period_month"]}/{upload["period_year"]}', 422)

    entries = _repo.get_entries(upload_id)
    report = compute_marja_report(entries, Decimal(str(rate_row['eur_rate'])))
    xlsx_bytes = export_marja_xlsx(report, upload['period_year'], upload['period_month'])

    month_name = ['', 'IAN', 'FEB', 'MAR', 'APR', 'MAI', 'IUN',
                  'IUL', 'AUG', 'SEP', 'OCT', 'NOI', 'DEC'][upload['period_month']]
    filename = f'Marja_{month_name}{upload["period_year"]}.xlsx'

    return send_file(
        io.BytesIO(xlsx_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )


# ── EUR Rate ──

@controlling_bab_bp.route('/controlling/bab/api/eur-rate/<int:year>/<int:month>', methods=['GET'])
@login_required
@handle_api_errors
def api_get_eur_rate(year, month):
    """Get EUR rate for a period."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)

    rate = _repo.get_eur_rate(company_id, year, month)
    return jsonify({'success': True, 'rate': rate})


@controlling_bab_bp.route('/controlling/bab/api/eur-rate/<int:year>/<int:month>', methods=['PUT'])
@login_required
@handle_api_errors
def api_set_eur_rate(year, month):
    """Set EUR rate for a period."""
    if not _check_bab_perm('edit'):
        return error_response('Permission denied', 403)

    data = request.get_json()
    if not data or 'eur_rate' not in data or 'company_id' not in data:
        return error_response('company_id and eur_rate are required', 400)

    try:
        eur_rate = Decimal(str(data['eur_rate']))
    except Exception:
        return error_response('Invalid eur_rate value', 400)

    if eur_rate <= 0:
        return error_response('EUR rate must be positive', 400)

    result = _repo.set_eur_rate(data['company_id'], year, month, eur_rate, current_user.id)
    return jsonify({'success': True, 'rate': result})


# ── Helpers ──

def _serialize_report(report):
    """Convert Decimal values to float for JSON serialization."""
    def _conv(v):
        if isinstance(v, Decimal):
            return float(v)
        return v

    serialized = {
        'eur_rate': float(report['eur_rate']),
        'marja_finala_lei': float(report['marja_finala_lei']),
        'marja_finala_eur': float(report['marja_finala_eur']),
        'sections': [],
    }
    for section in report['sections']:
        s = {'section': section['section'], 'rows': []}
        for row in section['rows']:
            s['rows'].append({
                'label': row['label'],
                'lei': float(row['lei']),
                'eur': float(row['eur']),
                'accounts': row['accounts'],
                'kst': row['kst'],
            })
        serialized['sections'].append(s)
    return serialized
```

- [ ] **Step 2: Register blueprint in app.py**

In `jarvis/app.py`, after the facturare blueprint registration (line ~202), add:

```python
    from accounting.controlling_bab import controlling_bab_bp
    flask_app.register_blueprint(controlling_bab_bp)
```

- [ ] **Step 3: Verify Python compilation**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -m py_compile jarvis/app.py && echo "app.py compiles OK"
```

Expected: `app.py compiles OK`

---

### Task 7: Frontend — Types + API Client

**Files:**
- Create: `jarvis/frontend/src/types/controlling.ts`
- Create: `jarvis/frontend/src/api/controlling.ts`

**Interfaces:**
- Produces:
  - Types: `BabPeriod`, `BabUpload`, `MarjaLine`, `MarjaSection`, `MarjaReport`, `BabEurRate`
  - API: `controllingApi` object with methods for all endpoints

- [ ] **Step 1: Create types**

Create `jarvis/frontend/src/types/controlling.ts`:

```typescript
export interface BabPeriod {
  year: number
  month: number
  status: 'MISSING' | 'IMPORTED' | 'LOCKED'
  upload_id?: number
  import_count?: number
  filename?: string
  uploaded_at?: string
  marja_finala_eur?: number
}

export interface BabUpload {
  id: number
  company_id: number
  period_year: number
  period_month: number
  filename: string
  uploaded_by: number
  uploaded_at: string
  row_count: number
  status: string
  error_msg: string | null
  locked_at: string | null
  locked_by: number | null
  unlocked_at: string | null
  unlocked_by: number | null
  import_count: number
}

export interface MarjaLine {
  label: string
  lei: number
  eur: number
  accounts: number[]
  kst: number
}

export interface MarjaSection {
  section: string
  rows: MarjaLine[]
}

export interface MarjaReportData {
  sections: MarjaSection[]
  marja_finala_lei: number
  marja_finala_eur: number
  eur_rate: number
}

export interface BabEurRate {
  id: number
  company_id: number
  period_year: number
  period_month: number
  eur_rate: number
  set_by: number | null
  set_at: string
}
```

- [ ] **Step 2: Create API client**

Create `jarvis/frontend/src/api/controlling.ts`:

```typescript
import { api } from './client'
import { buildQs } from './utils'
import type { BabPeriod, BabUpload, MarjaReportData, BabEurRate } from '@/types/controlling'

const BASE = '/controlling/bab/api'

export const controllingApi = {
  // Periods (12-month grid)
  getPeriods: (companyId: number) =>
    api.get<{ success: boolean; periods: BabPeriod[] }>(`${BASE}/periods${buildQs({ company_id: companyId })}`),

  // Uploads
  listUploads: (companyId: number) =>
    api.get<{ success: boolean; uploads: BabUpload[] }>(`${BASE}/uploads${buildQs({ company_id: companyId })}`),

  deleteUpload: (uploadId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/uploads/${uploadId}`),

  // Import BAB xlsx
  importBab: async (file: File, periodYear: number, periodMonth: number, companyId: number) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('period_year', String(periodYear))
    formData.append('period_month', String(periodMonth))
    formData.append('company_id', String(companyId))
    return api.post<{
      success: boolean
      upload_id: number
      period: string
      status: string
      import_count: number
      row_count: number
    }>(`${BASE}/import`, formData)
  },

  // Lock / Unlock
  lockUpload: (uploadId: number) =>
    api.post<{ success: boolean; upload: BabUpload }>(`${BASE}/uploads/${uploadId}/lock`),

  unlockUpload: (uploadId: number) =>
    api.post<{ success: boolean; upload: BabUpload }>(`${BASE}/uploads/${uploadId}/unlock`),

  // Report
  getReport: (uploadId: number) =>
    api.get<{ success: boolean; report: MarjaReportData; upload: BabUpload }>(`${BASE}/report/${uploadId}`),

  exportReport: (uploadId: number) =>
    `${BASE}/report/${uploadId}/export`,

  // EUR Rate
  getEurRate: (year: number, month: number, companyId: number) =>
    api.get<{ success: boolean; rate: BabEurRate | null }>(
      `${BASE}/eur-rate/${year}/${month}${buildQs({ company_id: companyId })}`),

  setEurRate: (year: number, month: number, companyId: number, eurRate: number) =>
    api.put<{ success: boolean; rate: BabEurRate }>(
      `${BASE}/eur-rate/${year}/${month}`, { company_id: companyId, eur_rate: eurRate }),
}
```

---

### Task 8: Frontend — Dashboard Page

**Files:**
- Create: `jarvis/frontend/src/pages/Accounting/Controlling/index.tsx`

**Interfaces:**
- Consumes: `controllingApi.getPeriods()`, `controllingApi.importBab()`, `controllingApi.lockUpload()`, `controllingApi.unlockUpload()`, `controllingApi.setEurRate()`, `controllingApi.getEurRate()`
- Produces: Dashboard page component (default export)

- [ ] **Step 1: Create the Controlling dashboard page**

Create `jarvis/frontend/src/pages/Accounting/Controlling/index.tsx`:

```tsx
import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Lock, Unlock, FileSpreadsheet, AlertTriangle, Eye } from 'lucide-react'
import { toast } from 'sonner'

import { controllingApi } from '@/api/controlling'
import { useAuthStore } from '@/stores/authStore'
import type { BabPeriod } from '@/types/controlling'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const MONTH_NAMES = ['', 'IAN', 'FEB', 'MAR', 'APR', 'MAI', 'IUN', 'IUL', 'AUG', 'SEP', 'OCT', 'NOI', 'DEC']

export default function Controlling() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)

  // Company selector — default to user's company or first available
  const [companyId, setCompanyId] = useState<number>(user?.company_id || 0)

  // Import modal state
  const [importModal, setImportModal] = useState<{ year: number; month: number; existing?: BabPeriod } | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [eurRateInput, setEurRateInput] = useState('')

  // Lock confirm state
  const [lockConfirm, setLockConfirm] = useState<BabPeriod | null>(null)

  // Fetch companies for selector
  const { data: companiesData } = useQuery({
    queryKey: ['companies'],
    queryFn: () => fetch('/hr/events/api/structure/companies', { credentials: 'same-origin' }).then(r => r.json()),
  })
  const companies: { id: number; company: string }[] = companiesData?.companies || companiesData || []

  // Set default company when loaded
  if (companyId === 0 && companies.length > 0) {
    setCompanyId(companies[0].id)
  }

  // Fetch periods
  const { data: periodsData, isLoading } = useQuery({
    queryKey: ['bab-periods', companyId],
    queryFn: () => controllingApi.getPeriods(companyId),
    enabled: companyId > 0,
  })
  const periods: BabPeriod[] = periodsData?.periods || []

  // Import mutation
  const importMutation = useMutation({
    mutationFn: async () => {
      if (!importFile || !importModal) throw new Error('No file selected')
      // Set EUR rate first if provided
      if (eurRateInput) {
        await controllingApi.setEurRate(importModal.year, importModal.month, companyId, parseFloat(eurRateInput))
      }
      return controllingApi.importBab(importFile, importModal.year, importModal.month, companyId)
    },
    onSuccess: (data) => {
      toast.success(`BAB importat: ${data.row_count} linii (import #${data.import_count})`)
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
      setImportModal(null)
      setImportFile(null)
      setEurRateInput('')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  // Lock mutation
  const lockMutation = useMutation({
    mutationFn: (uploadId: number) => controllingApi.lockUpload(uploadId),
    onSuccess: () => {
      toast.success('Perioadă blocată')
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
      setLockConfirm(null)
    },
    onError: (err: Error) => toast.error(err.message),
  })

  // Unlock mutation
  const unlockMutation = useMutation({
    mutationFn: (uploadId: number) => controllingApi.unlockUpload(uploadId),
    onSuccess: () => {
      toast.success('Perioadă deblocată')
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const openImportModal = useCallback((year: number, month: number, existing?: BabPeriod) => {
    setImportModal({ year, month, existing })
    setImportFile(null)
    setEurRateInput('')
    // Pre-fill EUR rate if exists
    if (companyId > 0) {
      controllingApi.getEurRate(year, month, companyId).then(res => {
        if (res?.rate) setEurRateInput(String(res.rate.eur_rate))
      }).catch(() => {})
    }
  }, [companyId])

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.name.toLowerCase().endsWith('.xlsx')) {
      setImportFile(file)
    } else {
      toast.error('Doar fișiere .xlsx')
    }
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setImportFile(file)
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Controlling — BAB</h1>
          <p className="text-sm text-muted-foreground">Import BAB lunar și raport marjă</p>
        </div>
        <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Selectează compania" />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c: { id: number; company: string }) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Period Grid */}
      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">Se încarcă...</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {periods.map((p) => (
            <PeriodCard
              key={`${p.year}-${p.month}`}
              period={p}
              onImport={() => openImportModal(p.year, p.month, p.status !== 'MISSING' ? p : undefined)}
              onView={() => p.upload_id && navigate(`/app/accounting/controlling/${p.upload_id}`)}
              onLock={() => setLockConfirm(p)}
              onUnlock={() => p.upload_id && unlockMutation.mutate(p.upload_id)}
            />
          ))}
        </div>
      )}

      {/* Import Modal */}
      <Dialog open={!!importModal} onOpenChange={() => setImportModal(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Import BAB — {importModal ? `${MONTH_NAMES[importModal.month]} ${importModal.year}` : ''}
            </DialogTitle>
            <DialogDescription>
              {importModal?.existing
                ? `Acest BAB va înlocui importul din ${importModal.existing.uploaded_at?.split('T')[0]} (${importModal.existing.filename}). Import #${(importModal.existing.import_count || 0) + 1}.`
                : 'Încarcă fișierul BAB (.xlsx) exportat din ERP.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* EUR Rate */}
            <div>
              <Label>Curs EUR (LEI/EUR)</Label>
              <Input
                type="number"
                step="0.0001"
                placeholder="ex: 4.9750"
                value={eurRateInput}
                onChange={(e) => setEurRateInput(e.target.value)}
              />
            </div>

            {/* File Drop Zone */}
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              onClick={() => document.getElementById('bab-file-input')?.click()}
            >
              {importFile ? (
                <div className="flex items-center justify-center gap-2">
                  <FileSpreadsheet className="h-5 w-5 text-green-600" />
                  <span className="text-sm font-medium">{importFile.name}</span>
                  <span className="text-xs text-muted-foreground">({(importFile.size / 1024).toFixed(0)} KB)</span>
                </div>
              ) : (
                <div>
                  <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Drag & drop .xlsx sau click pentru a selecta</p>
                </div>
              )}
              <input
                id="bab-file-input"
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>

            {importModal?.existing && (
              <div className="flex items-center gap-2 text-amber-600 bg-amber-50 rounded p-2 text-xs">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Re-import: datele existente vor fi înlocuite</span>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setImportModal(null)}>Anulează</Button>
            <Button
              onClick={() => importMutation.mutate()}
              disabled={!importFile || !eurRateInput || importMutation.isPending}
            >
              {importMutation.isPending ? 'Se importă...' : 'Importă BAB'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Lock Confirm Dialog */}
      <Dialog open={!!lockConfirm} onOpenChange={() => setLockConfirm(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Blochează perioada</DialogTitle>
            <DialogDescription>
              Blochezi perioada {lockConfirm ? `${MONTH_NAMES[lockConfirm.month]} ${lockConfirm.year}` : ''}?
              Perioada poate fi deblocată ulterior de un utilizator cu permisiune.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLockConfirm(null)}>Anulează</Button>
            <Button
              variant="destructive"
              onClick={() => lockConfirm?.upload_id && lockMutation.mutate(lockConfirm.upload_id)}
              disabled={lockMutation.isPending}
            >
              Blochează
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}


function PeriodCard({ period, onImport, onView, onLock, onUnlock }: {
  period: BabPeriod
  onImport: () => void
  onView: () => void
  onLock: () => void
  onUnlock: () => void
}) {
  const { status, year, month, marja_finala_eur } = period

  const bgClass = status === 'LOCKED'
    ? 'bg-blue-50 border-blue-200'
    : status === 'IMPORTED'
    ? 'bg-green-50 border-green-200'
    : 'bg-gray-50 border-gray-200'

  return (
    <Card className={`${bgClass} transition-all hover:shadow-md`}>
      <CardContent className="p-3 text-center space-y-2">
        <div className="font-semibold text-sm">{MONTH_NAMES[month]} {year}</div>

        {status === 'LOCKED' && (
          <>
            <div className="flex items-center justify-center gap-1 text-blue-600 text-xs font-medium">
              <Lock className="h-3 w-3" /> BLOCAT
            </div>
            {marja_finala_eur != null && (
              <div className="text-lg font-bold">{formatEur(marja_finala_eur)}</div>
            )}
            <div className="flex gap-1">
              <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={onView}>
                <Eye className="h-3 w-3 mr-1" /> Vezi
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 px-2" onClick={onUnlock} title="Deblochează">
                <Unlock className="h-3 w-3" />
              </Button>
            </div>
          </>
        )}

        {status === 'IMPORTED' && (
          <>
            <div className="text-green-600 text-xs font-medium">✓ IMPORTAT</div>
            {marja_finala_eur != null && (
              <div className="text-lg font-bold">{formatEur(marja_finala_eur)}</div>
            )}
            <div className="flex gap-1">
              <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={onView}>
                <Eye className="h-3 w-3 mr-1" /> Vezi
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 px-2" onClick={onImport} title="Re-import">
                <Upload className="h-3 w-3" />
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 px-2" onClick={onLock} title="Blochează">
                <Lock className="h-3 w-3" />
              </Button>
            </div>
          </>
        )}

        {status === 'MISSING' && (
          <>
            <div className="flex items-center justify-center gap-1 text-gray-400 text-xs">
              <AlertTriangle className="h-3 w-3" /> LIPSĂ
            </div>
            <Button size="sm" variant="default" className="w-full text-xs h-7" onClick={onImport}>
              <Upload className="h-3 w-3 mr-1" /> Import
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}


function formatEur(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(0)}k €`
  }
  return `${value.toFixed(0)} €`
}
```

---

### Task 9: Frontend — MarjaReport Page

**Files:**
- Create: `jarvis/frontend/src/pages/Accounting/Controlling/MarjaReport.tsx`

**Interfaces:**
- Consumes: `controllingApi.getReport()`, `controllingApi.exportReport()`
- Produces: MarjaReport page component (default export)

- [ ] **Step 1: Create MarjaReport page**

Create `jarvis/frontend/src/pages/Accounting/Controlling/MarjaReport.tsx`:

```tsx
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download } from 'lucide-react'

import { controllingApi } from '@/api/controlling'
import type { MarjaSection } from '@/types/controlling'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useState } from 'react'

const MONTH_NAMES = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
  'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

export default function MarjaReport() {
  const { uploadId } = useParams<{ uploadId: string }>()
  const navigate = useNavigate()
  const [showEur, setShowEur] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['bab-report', uploadId],
    queryFn: () => controllingApi.getReport(Number(uploadId)),
    enabled: !!uploadId,
  })

  if (isLoading) return <div className="p-6 text-center text-muted-foreground">Se încarcă raportul...</div>
  if (error) return <div className="p-6 text-center text-red-500">Eroare: {(error as Error).message}</div>

  const report = data?.report
  const upload = data?.upload
  if (!report || !upload) return <div className="p-6 text-center text-muted-foreground">Raport negăsit</div>

  const monthName = MONTH_NAMES[upload.period_month] || ''

  const handleExport = () => {
    window.open(controllingApi.exportReport(Number(uploadId)), '_blank')
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/app/accounting/controlling')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-xl font-semibold">Raport Marjă Vânzări</h1>
            <p className="text-sm text-muted-foreground">
              {monthName} {upload.period_year} &middot; Curs: {report.eur_rate} LEI/EUR
              {upload.locked_at && <span className="ml-2 text-blue-600 font-medium">🔒 BLOCAT</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowEur(!showEur)}
          >
            {showEur ? 'EUR → LEI' : 'LEI → EUR'}
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4 mr-1" /> Export XLSX
          </Button>
        </div>
      </div>

      {/* Report Table */}
      <Card>
        <CardHeader className="py-3 px-4 bg-[#1B2A4A] rounded-t-lg">
          <CardTitle className="text-white text-sm font-medium flex justify-between">
            <span>Indicator</span>
            <span>{showEur ? 'EUR' : 'LEI'}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <TooltipProvider>
            <table className="w-full text-sm">
              <tbody>
                {report.sections.map((section: MarjaSection) => (
                  <SectionBlock key={section.section} section={section} showEur={showEur} />
                ))}
              </tbody>
            </table>
          </TooltipProvider>
        </CardContent>
      </Card>

      {/* Summary */}
      <div className="mt-4 grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-xs text-muted-foreground mb-1">MARJA FINALĂ (LEI)</div>
            <div className={`text-2xl font-bold ${report.marja_finala_lei < 0 ? 'text-red-600' : ''}`}>
              {formatNumber(report.marja_finala_lei)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-xs text-muted-foreground mb-1">MARJA FINALĂ (EUR)</div>
            <div className={`text-2xl font-bold ${report.marja_finala_eur < 0 ? 'text-red-600' : ''}`}>
              {formatNumber(report.marja_finala_eur)}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}


function SectionBlock({ section, showEur }: { section: MarjaSection; showEur: boolean }) {
  const isMarjaFinala = section.section.includes('MARJA FINALĂ')

  return (
    <>
      {/* Section header */}
      <tr className={isMarjaFinala ? 'bg-[#1B2A4A]' : 'bg-gray-100'}>
        <td colSpan={2} className={`px-4 py-2 font-semibold text-xs ${isMarjaFinala ? 'text-white' : 'text-gray-700'}`}>
          {section.section}
        </td>
      </tr>
      {/* Rows */}
      {section.rows.map((row) => {
        const isMainMarja = row.label === 'MARJA FINALĂ'
        const value = showEur ? row.eur : row.lei
        const isNegative = value < 0

        return (
          <Tooltip key={row.label + row.kst}>
            <TooltipTrigger asChild>
              <tr className={`border-b border-gray-100 hover:bg-gray-50 cursor-default ${isMainMarja ? 'bg-[#1B2A4A]' : ''}`}>
                <td className={`px-4 py-2 ${isMainMarja ? 'text-white font-bold' : 'pl-8 text-gray-700'}`}>
                  {row.label}
                </td>
                <td className={`px-4 py-2 text-right font-mono tabular-nums ${
                  isMainMarja ? 'text-white font-bold'
                    : isNegative ? 'text-red-600'
                    : 'text-gray-900'
                }`}>
                  {formatNumber(value)}
                </td>
              </tr>
            </TooltipTrigger>
            {row.accounts.length > 0 && (
              <TooltipContent>
                <p className="text-xs">Conturi: {row.accounts.join(', ')} | KST {row.kst}</p>
              </TooltipContent>
            )}
          </Tooltip>
        )
      })}
    </>
  )
}


function formatNumber(value: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}
```

---

### Task 10: Frontend — Route + Nav Registration

**Files:**
- Modify: `jarvis/frontend/src/App.tsx` (add lazy import + routes)
- Modify: `jarvis/frontend/src/components/Sidebar.tsx` (add nav item)

**Interfaces:**
- Consumes: `Controlling` and `MarjaReport` page components

- [ ] **Step 1: Add lazy imports to App.tsx**

In `jarvis/frontend/src/App.tsx`, after the Facturare lazy import (line ~27):

```typescript
const Controlling = lazy(() => import('./pages/Accounting/Controlling'))
const MarjaReport = lazy(() => import('./pages/Accounting/Controlling/MarjaReport'))
```

- [ ] **Step 2: Add routes to App.tsx**

In `jarvis/frontend/src/App.tsx`, after the facturare route (line ~155):

```tsx
        <Route path="accounting/controlling" element={<Guard flag="can_access_accounting"><V2Guard permKey="controlling.bab.view"><SuspensePage><Controlling /></SuspensePage></V2Guard></Guard>} />
        <Route path="accounting/controlling/:uploadId" element={<Guard flag="can_access_accounting"><V2Guard permKey="controlling.bab.view"><SuspensePage><MarjaReport /></SuspensePage></V2Guard></Guard>} />
```

- [ ] **Step 3: Add nav item to Sidebar.tsx**

In `jarvis/frontend/src/components/Sidebar.tsx`, add the `BarChart3` icon import from `lucide-react`, then add to the Accounting children array, after the facturare entry (line ~42):

```typescript
      { path: '/app/accounting/controlling', label: 'Controlling', icon: BarChart3, moduleKey: 'accounting_controlling', v2Permission: 'controlling.bab.view' },
```

- [ ] **Step 4: Build frontend**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis/jarvis/frontend && npm run build
```

Expected: Build completes with zero errors.

- [ ] **Step 5: Verify Python app compiles**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/jarvis && python3 -m py_compile jarvis/app.py && echo "OK"
```

Expected: `OK`

---

### Task 11: Commit

- [ ] **Step 1: Stage all new and modified files**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis
git add jarvis/accounting/controlling_bab/__init__.py \
        jarvis/accounting/controlling_bab/repository.py \
        jarvis/accounting/controlling_bab/parser.py \
        jarvis/accounting/controlling_bab/calculator.py \
        jarvis/accounting/controlling_bab/exporter.py \
        jarvis/accounting/controlling_bab/routes.py \
        jarvis/migrations/domains/schema_controlling_bab.py \
        jarvis/migrations/init_schema.py \
        jarvis/core/settings/menus/registry.py \
        jarvis/app.py \
        jarvis/frontend/src/types/controlling.ts \
        jarvis/frontend/src/api/controlling.ts \
        jarvis/frontend/src/pages/Accounting/Controlling/index.tsx \
        jarvis/frontend/src/pages/Accounting/Controlling/MarjaReport.tsx \
        jarvis/frontend/src/App.tsx \
        jarvis/frontend/src/components/Sidebar.tsx \
        docs/superpowers/specs/2026-06-18-controlling-bab-design.md \
        docs/superpowers/plans/2026-06-18-controlling-bab.md
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(controlling): add BAB module with margin report

Adds monthly BAB xlsx import with period lifecycle (MISSING→IMPORTED→LOCKED),
margin (Marja) calculation engine, and styled xlsx export.
Backend: Flask blueprint, BaseRepository, openpyxl parser + exporter.
Frontend: 12-month period grid dashboard, MarjaReport detail view."
```
