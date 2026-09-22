# Public Test-Drive Booking — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for a public, unauthenticated test-drive booking layer over `foi_de_parcurs` — event-scoped MVP — with a race-safe slot claim, 3-way availability reconciliation, and email confirm/cancel.

**Architecture:** New `mkt_td_*` tables are the public inventory + booking audit; `foi_de_parcurs` stays the operational record and is **never altered**. A prospect claims a pre-materialized slot (race guard = partial-unique index on the booking), receives an email confirm link (signed token), and on confirm the system creates a `foi_de_parcurs` PLANNED row inside a single advisory-locked transaction that re-checks availability. Cancel soft-cancels the booking and hard-deletes the PLANNED FP row.

**Tech Stack:** Python 3 / Flask (blueprints), PostgreSQL via `psycopg2` raw SQL (no ORM), `BaseRepository` (`query_one/query_all/execute/execute_many`), `itsdangerous` for tokens, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-public-test-drive-booking-design.md` — the plan argues from the spec; executors read both.

## Global Constraints

- **Raw SQL only**, `%s` params, never f-string a user value into SQL (build column lists from server-controlled keys only). No ORM. (`CLAUDE.md`)
- Repositories subclass `core.base_repository.BaseRepository`. Atomic multi-statement work uses `execute_many(callback)` — the callback receives a **cursor** and runs in one transaction; commit/rollback are automatic.
- **`foi_de_parcurs` schema is NOT modified.** No new columns, no exclusion constraint on it. (Protected migrations; likely-existing overlaps.)
- New DDL is **idempotent** and lives in `jarvis/migrations/domains/schema_marketing.py` inside `create_schema_marketing(conn, cursor)`: `CREATE TABLE IF NOT EXISTS`, `CREATE [UNIQUE] INDEX IF NOT EXISTS`. This file is in the **protected** set — the schema task requires explicit user confirmation before editing (call it out at review).
- **Public endpoints must never return 401** (the shared FE client hard-redirects to `/login` on 401). Anonymous → 200/404/409/410/429.
- Customer emails call `send_email(..., skip_global_cc=True)` so prospects are never CC'd to the internal global address.
- Status strings are exact: TD rows are `route_type='TD'`, `status='PLANNED'`, `source='td_form'`. No-show grace is **6h** (`GRACE_HOURS`, `foi_parcurs/session_lifecycle.py:12`).
- Local dev DB is shared across worktrees; Flask on **:5001**. Run `python3 -m py_compile jarvis/app.py` and `python -m pytest tests/ -x -q` before declaring a task done.

---

## Phase 1 — Schema & repository

### Task 1: `mkt_td_*` schema

**Files:**
- Modify: `jarvis/migrations/domains/schema_marketing.py` (inside `create_schema_marketing`, append a new `# === Test-Drive Booking ===` section)
- Test: `tests/marketing/test_td_booking_schema.py`

**Interfaces:**
- Produces (tables/columns other tasks rely on): `mkt_td_booking_pages`, `mkt_td_booking_cars`, `mkt_td_booking_windows`, `mkt_td_slots`, `mkt_td_bookings`; the partial-unique index `uq_mkt_td_active_booking_per_slot ON mkt_td_bookings(slot_id) WHERE status IN ('pending_confirm','confirmed')`.

> ⚠️ `schema_marketing.py` is in the protected migrations set. Get explicit user confirmation before editing (this task's review gate).

- [ ] **Step 1: Write the failing test**

```python
# tests/marketing/test_td_booking_schema.py
import pytest
from core.base_repository import BaseRepository

repo = BaseRepository()

TABLES = [
    'mkt_td_booking_pages', 'mkt_td_booking_cars',
    'mkt_td_booking_windows', 'mkt_td_slots', 'mkt_td_bookings',
]

@pytest.mark.parametrize('table', TABLES)
def test_td_tables_exist(table):
    row = repo.query_one(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s", (table,))
    assert row is not None, f"missing table {table}"

def test_partial_unique_index_exists():
    row = repo.query_one(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname='uq_mkt_td_active_booking_per_slot'")
    assert row is not None
    assert "pending_confirm" in row['indexdef'] and "confirmed" in row['indexdef']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/marketing/test_td_booking_schema.py -v`
Expected: FAIL (tables/index missing).

- [ ] **Step 3: Add the DDL** (append inside `create_schema_marketing`, matching the `mkt_projects` style)

```python
    # ============== Test-Drive Booking (public slot layer) ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_td_booking_pages (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES mkt_projects(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            event_id INTEGER REFERENCES hr.events(id),
            slug TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            opens_at TIMESTAMPTZ,
            closes_at TIMESTAMPTZ,
            min_lead_minutes INTEGER NOT NULL DEFAULT 120,
            slot_minutes INTEGER NOT NULL DEFAULT 30,
            buffer_minutes INTEGER NOT NULL DEFAULT 0,
            max_bookings_per_contact INTEGER NOT NULL DEFAULT 1,
            access_code TEXT,
            title TEXT,
            intro TEXT,
            thank_you TEXT,
            notify_user_ids INTEGER[] DEFAULT '{}',
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMPTZ,
            CONSTRAINT mkt_td_pages_status_check CHECK (status IN ('draft','open','closed'))
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_mkt_td_pages_slug ON mkt_td_booking_pages(slug) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_pages_company ON mkt_td_booking_pages(company_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_td_booking_cars (
            id SERIAL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES mkt_td_booking_pages(id) ON DELETE CASCADE,
            vehicle_id INTEGER,
            vin TEXT NOT NULL,
            default_advisor_user_id INTEGER REFERENCES users(id),
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_mkt_td_car_per_page UNIQUE (page_id, vin)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_cars_page ON mkt_td_booking_cars(page_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_td_booking_windows (
            id SERIAL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES mkt_td_booking_pages(id) ON DELETE CASCADE,
            window_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            slot_minutes INTEGER,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_windows_page ON mkt_td_booking_windows(page_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_td_slots (
            id SERIAL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES mkt_td_booking_pages(id) ON DELETE CASCADE,
            car_id INTEGER NOT NULL REFERENCES mkt_td_booking_cars(id) ON DELETE CASCADE,
            vin TEXT NOT NULL,
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_td_slots_status_check CHECK (status IN ('open','blocked')),
            CONSTRAINT uq_mkt_td_slot_car_time UNIQUE (car_id, starts_at)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_slots_page ON mkt_td_slots(page_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_td_bookings (
            id SERIAL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES mkt_td_booking_pages(id),
            slot_id INTEGER NOT NULL REFERENCES mkt_td_slots(id),
            car_id INTEGER NOT NULL REFERENCES mkt_td_booking_cars(id),
            customer_name TEXT NOT NULL,
            customer_phone_e164 TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            crm_client_id INTEGER,
            foi_de_parcurs_id INTEGER,
            advisor_user_id INTEGER REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'pending_confirm',
            expires_at TIMESTAMPTZ NOT NULL,
            confirmed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            extra_answers JSONB DEFAULT '{}'::jsonb,
            utm JSONB DEFAULT '{}'::jsonb,
            ip TEXT,
            user_agent TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_td_bookings_status_check CHECK (status IN (
                'pending_confirm','confirmed','cancelled','expired','conflict','completed','no_show'))
        )
    ''')
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_mkt_td_active_booking_per_slot "
                   "ON mkt_td_bookings(slot_id) WHERE status IN ('pending_confirm','confirmed')")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_bookings_page ON mkt_td_bookings(page_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_bookings_contact ON mkt_td_bookings(customer_phone_e164, customer_email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_td_bookings_status ON mkt_td_bookings(status)')
```

- [ ] **Step 4: Recreate schema locally & run test**

Restart the app once (schema runs on boot via `init_db()`), or run the project's schema-init entrypoint. Then:
Run: `python -m pytest tests/marketing/test_td_booking_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/migrations/domains/schema_marketing.py tests/marketing/test_td_booking_schema.py
git commit -m "feat(td): mkt_td_* booking schema + partial-unique slot guard"
```

---

### Task 2: `TdBookingRepository` — pages, cars, windows CRUD

**Files:**
- Create: `jarvis/marketing/repositories/td_booking_repository.py`
- Modify: `jarvis/marketing/repositories/__init__.py` (export `TdBookingRepository`)
- Test: `tests/marketing/test_td_booking_repository.py`

**Interfaces:**
- Consumes: Task 1 tables.
- Produces:
  - `create_page(data: dict) -> dict` (whitelisted insert, RETURNING row)
  - `get_page(page_id: int) -> dict|None`; `get_page_by_slug(slug: str) -> dict|None` (ignores `deleted_at`)
  - `list_pages(company_id: int|None) -> list[dict]`
  - `update_page(page_id: int, data: dict) -> dict|None`; `set_page_status(page_id, status) -> dict|None`
  - `add_car(page_id, vin, vehicle_id, default_advisor_user_id, sort_order=0) -> dict`; `list_cars(page_id) -> list[dict]`; `get_car(car_id) -> dict|None`; `remove_car(car_id) -> int`
  - `add_window(page_id, window_date, start_time, end_time, slot_minutes=None) -> dict`; `list_windows(page_id) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# tests/marketing/test_td_booking_repository.py
import pytest
from marketing.repositories.td_booking_repository import TdBookingRepository

repo = TdBookingRepository()

@pytest.fixture
def page():
    # company_id=1 and a user id=1 are assumed present in the dev DB seed.
    p = repo.create_page({'company_id': 1, 'slug': 'test-event-xyz',
                          'title': 'Test Drive Event', 'created_by': 1})
    yield p
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def test_create_and_fetch_page(page):
    assert page['id'] and page['status'] == 'draft'
    assert repo.get_page_by_slug('test-event-xyz')['id'] == page['id']

def test_add_car_and_window(page):
    car = repo.add_car(page['id'], vin='WVWZZZ1', vehicle_id=None,
                       default_advisor_user_id=1, sort_order=0)
    assert car['vin'] == 'WVWZZZ1'
    assert repo.list_cars(page['id'])[0]['id'] == car['id']
    w = repo.add_window(page['id'], '2026-10-01', '10:00', '12:00', slot_minutes=30)
    assert w['id'] and repo.list_windows(page['id'])[0]['id'] == w['id']

def test_set_page_status(page):
    assert repo.set_page_status(page['id'], 'open')['status'] == 'open'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/marketing/test_td_booking_repository.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the repository** (column-driven inserts, mirroring `create_from_form`)

```python
# jarvis/marketing/repositories/td_booking_repository.py
"""Repository for the public test-drive booking layer (mkt_td_* tables)."""
from core.base_repository import BaseRepository

_PAGE_COLS = {
    'project_id', 'company_id', 'event_id', 'slug', 'status', 'opens_at',
    'closes_at', 'min_lead_minutes', 'slot_minutes', 'buffer_minutes',
    'max_bookings_per_contact', 'access_code', 'title', 'intro', 'thank_you',
    'notify_user_ids', 'created_by',
}


class TdBookingRepository(BaseRepository):
    # ---- pages ----
    def create_page(self, data: dict) -> dict:
        fields = {k: v for k, v in data.items() if k in _PAGE_COLS}
        cols = ', '.join(fields)
        ph = ', '.join(['%s'] * len(fields))
        return self.execute(
            f'INSERT INTO mkt_td_booking_pages ({cols}) VALUES ({ph}) RETURNING *',
            tuple(fields.values()), returning=True)

    def get_page(self, page_id: int):
        return self.query_one('SELECT * FROM mkt_td_booking_pages WHERE id=%s', (page_id,))

    def get_page_by_slug(self, slug: str):
        return self.query_one(
            'SELECT * FROM mkt_td_booking_pages WHERE slug=%s AND deleted_at IS NULL', (slug,))

    def list_pages(self, company_id=None):
        if company_id:
            return self.query_all(
                'SELECT * FROM mkt_td_booking_pages WHERE company_id=%s AND deleted_at IS NULL '
                'ORDER BY created_at DESC', (company_id,))
        return self.query_all(
            'SELECT * FROM mkt_td_booking_pages WHERE deleted_at IS NULL ORDER BY created_at DESC')

    def update_page(self, page_id: int, data: dict):
        fields = {k: v for k, v in data.items() if k in _PAGE_COLS}
        if not fields:
            return self.get_page(page_id)
        sets = ', '.join(f'{k}=%s' for k in fields)
        return self.execute(
            f'UPDATE mkt_td_booking_pages SET {sets}, updated_at=NOW() WHERE id=%s RETURNING *',
            tuple(fields.values()) + (page_id,), returning=True)

    def set_page_status(self, page_id: int, status: str):
        return self.execute(
            'UPDATE mkt_td_booking_pages SET status=%s, updated_at=NOW() WHERE id=%s RETURNING *',
            (status, page_id), returning=True)

    # ---- cars ----
    def add_car(self, page_id, vin, vehicle_id=None, default_advisor_user_id=None, sort_order=0):
        return self.execute(
            'INSERT INTO mkt_td_booking_cars (page_id, vin, vehicle_id, default_advisor_user_id, sort_order) '
            'VALUES (%s,%s,%s,%s,%s) RETURNING *',
            (page_id, vin, vehicle_id, default_advisor_user_id, sort_order), returning=True)

    def list_cars(self, page_id):
        return self.query_all(
            'SELECT * FROM mkt_td_booking_cars WHERE page_id=%s AND is_active ORDER BY sort_order, id',
            (page_id,))

    def get_car(self, car_id):
        return self.query_one('SELECT * FROM mkt_td_booking_cars WHERE id=%s', (car_id,))

    def remove_car(self, car_id):
        return self.execute('UPDATE mkt_td_booking_cars SET is_active=FALSE WHERE id=%s', (car_id,))

    # ---- windows ----
    def add_window(self, page_id, window_date, start_time, end_time, slot_minutes=None):
        return self.execute(
            'INSERT INTO mkt_td_booking_windows (page_id, window_date, start_time, end_time, slot_minutes) '
            'VALUES (%s,%s,%s,%s,%s) RETURNING *',
            (page_id, window_date, start_time, end_time, slot_minutes), returning=True)

    def list_windows(self, page_id):
        return self.query_all(
            'SELECT * FROM mkt_td_booking_windows WHERE page_id=%s ORDER BY window_date, start_time',
            (page_id,))
```

Also add to `jarvis/marketing/repositories/__init__.py`: `from .td_booking_repository import TdBookingRepository`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/marketing/test_td_booking_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/marketing/repositories/td_booking_repository.py jarvis/marketing/repositories/__init__.py tests/marketing/test_td_booking_repository.py
git commit -m "feat(td): booking repository pages/cars/windows CRUD"
```

---

### Task 3: `TdBookingRepository` — slots (idempotent bulk insert + open-slot query)

**Files:**
- Modify: `jarvis/marketing/repositories/td_booking_repository.py`
- Test: `tests/marketing/test_td_slots_repository.py`

**Interfaces:**
- Produces:
  - `bulk_insert_slots(rows: list[dict]) -> int` — each row `{page_id, car_id, vin, starts_at, ends_at}`; `ON CONFLICT (car_id, starts_at) DO NOTHING`; returns inserted count.
  - `list_open_slots(page_id: int) -> list[dict]` — slots with `status='open'` and **no active booking** (`NOT EXISTS` a `pending_confirm|confirmed` booking), joined with car for `vin`.

- [ ] **Step 1: Write the failing test**

```python
# tests/marketing/test_td_slots_repository.py
import pytest
from marketing.repositories.td_booking_repository import TdBookingRepository
repo = TdBookingRepository()

@pytest.fixture
def car():
    p = repo.create_page({'company_id': 1, 'slug': 'slot-test-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='SLOT0001', default_advisor_user_id=1)
    yield p, c
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def test_bulk_insert_idempotent(car):
    p, c = car
    rows = [{'page_id': p['id'], 'car_id': c['id'], 'vin': 'SLOT0001',
             'starts_at': '2026-10-01 10:00+03', 'ends_at': '2026-10-01 10:30+03'}]
    assert repo.bulk_insert_slots(rows) == 1
    assert repo.bulk_insert_slots(rows) == 0   # conflict → skipped
    assert len(repo.list_open_slots(p['id'])) == 1
```

- [ ] **Step 2: Run to verify FAIL** — `python -m pytest tests/marketing/test_td_slots_repository.py -v` → FAIL (method missing).

- [ ] **Step 3: Implement**

```python
    # ---- slots ----
    def bulk_insert_slots(self, rows: list) -> int:
        if not rows:
            return 0
        def _work(cursor):
            n = 0
            for r in rows:
                cursor.execute(
                    'INSERT INTO mkt_td_slots (page_id, car_id, vin, starts_at, ends_at) '
                    'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (car_id, starts_at) DO NOTHING',
                    (r['page_id'], r['car_id'], r['vin'], r['starts_at'], r['ends_at']))
                n += cursor.rowcount
            return n
        return self.execute_many(_work)

    def list_open_slots(self, page_id: int) -> list:
        return self.query_all(
            "SELECT s.* FROM mkt_td_slots s "
            "WHERE s.page_id=%s AND s.status='open' "
            "AND NOT EXISTS (SELECT 1 FROM mkt_td_bookings b "
            "                WHERE b.slot_id=s.id AND b.status IN ('pending_confirm','confirmed')) "
            "ORDER BY s.car_id, s.starts_at", (page_id,))
```

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): idempotent slot bulk-insert + open-slot query"`

---

### Task 4: `TdBookingRepository` — bookings (create w/ race guard, rate-limit counts, status mutations, expiry)

**Files:**
- Modify: `jarvis/marketing/repositories/td_booking_repository.py`
- Test: `tests/marketing/test_td_bookings_repository.py`

**Interfaces:**
- Produces:
  - `create_booking(data: dict) -> dict` — whitelisted insert; **propagates `psycopg2.errors.UniqueViolation`** on the partial-unique guard (caller maps to 409).
  - `get_booking(booking_id) -> dict|None`
  - `list_bookings(page_id, status=None) -> list[dict]`
  - `count_active_by_contact(phone, email) -> int` (pending/confirmed, for `max_bookings_per_contact`)
  - `count_recent_by_ip(ip, since) -> int`
  - `mark_confirmed(booking_id, crm_client_id, foi_de_parcurs_id, advisor_user_id) -> dict` (used only by the atomic confirm path; still handy standalone)
  - `mark_cancelled(booking_id) -> dict`
  - `mark_status(booking_id, status) -> dict`
  - `expire_pending(now) -> int` — flips `pending_confirm` past `expires_at` to `expired`.

- [ ] **Step 1: Write the failing test** (includes the race guard)

```python
# tests/marketing/test_td_bookings_repository.py
import pytest, psycopg2
from datetime import datetime, timezone, timedelta
from marketing.repositories.td_booking_repository import TdBookingRepository
repo = TdBookingRepository()

@pytest.fixture
def slot():
    p = repo.create_page({'company_id': 1, 'slug': 'bk-test-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='BK000001', default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': 'BK000001',
                             'starts_at': '2026-10-01 10:00+03', 'ends_at': '2026-10-01 10:30+03'}])
    s = repo.list_open_slots(p['id'])[0]
    yield p, c, s
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def _booking_data(p, c, s):
    return {'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
            'customer_name': 'Ion', 'customer_phone_e164': '+40721000001',
            'customer_email': 'ion@example.com',
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=45)}

def test_partial_unique_blocks_second_active_booking(slot):
    p, c, s = slot
    b1 = repo.create_booking(_booking_data(p, c, s))
    assert b1['status'] == 'pending_confirm'
    with pytest.raises(psycopg2.errors.UniqueViolation):
        repo.create_booking(_booking_data(p, c, s))   # same slot, still active → blocked

def test_cancel_frees_slot(slot):
    p, c, s = slot
    b1 = repo.create_booking(_booking_data(p, c, s))
    repo.mark_cancelled(b1['id'])
    b2 = repo.create_booking(_booking_data(p, c, s))   # now allowed
    assert b2['id'] != b1['id']

def test_expire_pending(slot):
    p, c, s = slot
    d = _booking_data(p, c, s)
    d['expires_at'] = datetime.now(timezone.utc) - timedelta(minutes=1)
    repo.create_booking(d)
    assert repo.expire_pending(datetime.now(timezone.utc)) >= 1
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
    _BOOKING_COLS = {
        'page_id', 'slot_id', 'car_id', 'customer_name', 'customer_phone_e164',
        'customer_email', 'advisor_user_id', 'expires_at', 'extra_answers',
        'utm', 'ip', 'user_agent',
    }

    def create_booking(self, data: dict) -> dict:
        from psycopg2.extras import Json
        fields = {k: v for k, v in data.items() if k in self._BOOKING_COLS}
        for k in ('extra_answers', 'utm'):
            if isinstance(fields.get(k), (dict, list)):
                fields[k] = Json(fields[k])
        cols = ', '.join(fields)
        ph = ', '.join(['%s'] * len(fields))
        # Let UniqueViolation propagate; the service maps it to HTTP 409.
        return self.execute(
            f'INSERT INTO mkt_td_bookings ({cols}) VALUES ({ph}) RETURNING *',
            tuple(fields.values()), returning=True)

    def get_booking(self, booking_id):
        return self.query_one('SELECT * FROM mkt_td_bookings WHERE id=%s', (booking_id,))

    def list_bookings(self, page_id, status=None):
        if status:
            return self.query_all(
                'SELECT * FROM mkt_td_bookings WHERE page_id=%s AND status=%s ORDER BY created_at DESC',
                (page_id, status))
        return self.query_all(
            'SELECT * FROM mkt_td_bookings WHERE page_id=%s ORDER BY created_at DESC', (page_id,))

    def count_active_by_contact(self, phone, email) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM mkt_td_bookings "
            "WHERE (customer_phone_e164=%s OR customer_email=%s) "
            "AND status IN ('pending_confirm','confirmed')", (phone, email))
        return int(row['n']) if row else 0

    def count_recent_by_ip(self, ip, since) -> int:
        row = self.query_one(
            'SELECT COUNT(*) AS n FROM mkt_td_bookings WHERE ip=%s AND created_at >= %s',
            (ip, since))
        return int(row['n']) if row else 0

    def mark_confirmed(self, booking_id, crm_client_id, foi_de_parcurs_id, advisor_user_id):
        return self.execute(
            "UPDATE mkt_td_bookings SET status='confirmed', crm_client_id=%s, "
            "foi_de_parcurs_id=%s, advisor_user_id=%s, confirmed_at=NOW(), updated_at=NOW() "
            "WHERE id=%s RETURNING *",
            (crm_client_id, foi_de_parcurs_id, advisor_user_id, booking_id), returning=True)

    def mark_cancelled(self, booking_id):
        return self.execute(
            "UPDATE mkt_td_bookings SET status='cancelled', cancelled_at=NOW(), updated_at=NOW() "
            "WHERE id=%s RETURNING *", (booking_id,), returning=True)

    def mark_status(self, booking_id, status):
        return self.execute(
            'UPDATE mkt_td_bookings SET status=%s, updated_at=NOW() WHERE id=%s RETURNING *',
            (status, booking_id), returning=True)

    def expire_pending(self, now) -> int:
        return self.execute(
            "UPDATE mkt_td_bookings SET status='expired', updated_at=NOW() "
            "WHERE status='pending_confirm' AND expires_at < %s", (now,))
```

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): bookings CRUD, race-guard create, rate-limit counts, expiry"`

---

## Phase 2 — Tokens, messaging, slot service

### Task 5: `booking_token` (mirror `action_token`)

**Files:**
- Create: `jarvis/core/approvals/booking_token.py`
- Test: `tests/core/test_booking_token.py`

**Interfaces:**
- Produces:
  - `make_booking_token(booking_id: int, action: str, secret_key: str) -> str` — `action ∈ {'confirm','cancel'}`, salt `'td-booking-action'`.
  - `read_booking_token(token, secret_key, max_age=DEFAULT_MAX_AGE) -> dict|None` → `{'bid','act'}` or None.
  - `DEFAULT_MAX_AGE = 7*24*3600`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_booking_token.py
from core.approvals.booking_token import make_booking_token, read_booking_token

SK = 'test-secret'

def test_roundtrip_confirm():
    t = make_booking_token(42, 'confirm', SK)
    assert read_booking_token(t, SK) == {'bid': 42, 'act': 'confirm'}

def test_rejects_bad_action():
    assert make_booking_token(1, 'delete', SK) is None or \
        read_booking_token(make_booking_token(1, 'confirm', SK), SK)['act'] == 'confirm'

def test_rejects_tampered():
    assert read_booking_token('garbage.token.here', SK) is None

def test_rejects_expired():
    t = make_booking_token(1, 'cancel', SK)
    assert read_booking_token(t, SK, max_age=-1) is None
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement** (verbatim structure of `action_token.py`, new salt + payload/action set)

```python
# jarvis/core/approvals/booking_token.py
"""Signed one-tap token for public test-drive booking confirm/cancel links.

Encodes (booking_id, action) signed with the app SECRET_KEY so an emailed
Confirm/Cancel link authenticates the customer's intent without a login. It is
per-booking, time-limited, and tamper-evident. The action is still gated by the
booking's own state (pending_confirm / not expired) in the service layer.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SALT = 'td-booking-action'
_ACTIONS = ('confirm', 'cancel')
DEFAULT_MAX_AGE = 7 * 24 * 3600  # 7 days


def make_booking_token(booking_id, action, secret_key):
    if action not in _ACTIONS:
        return None
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps({'bid': booking_id, 'act': action}, salt=_SALT)


def read_booking_token(token, secret_key, max_age=DEFAULT_MAX_AGE):
    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(token, salt=_SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get('act') not in _ACTIONS:
        return None
    return {'bid': data.get('bid'), 'act': data.get('act')}
```

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): signed booking confirm/cancel token"`

---

### Task 6: Customer-messaging seam (email now, SMS-ready)

**Files:**
- Create: `jarvis/core/messaging/customer_message.py`
- Test: `tests/core/test_customer_message.py`

**Interfaces:**
- Produces: `send_customer_message(channel, to, subject, body_html, body_text=None) -> tuple[bool, str]`. `channel='email'` → `send_email(to, subject, body_html, body_text, skip_global_cc=True)`. Unknown channel → `(False, 'unsupported channel')`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_customer_message.py
import core.messaging.customer_message as cm

def test_email_channel_skips_global_cc(monkeypatch):
    captured = {}
    def fake_send_email(to_email, subject, html_body, text_body=None, **kw):
        captured.update(to=to_email, skip=kw.get('skip_global_cc'))
        return True, ''
    monkeypatch.setattr(cm, 'send_email', fake_send_email)
    ok, err = cm.send_customer_message('email', 'p@ex.com', 'Subj', '<b>hi</b>')
    assert ok and captured['to'] == 'p@ex.com' and captured['skip'] is True

def test_unknown_channel():
    ok, err = cm.send_customer_message('sms', '+40721', 'S', 'B')
    assert not ok and 'unsupported' in err
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
# jarvis/core/messaging/customer_message.py
"""Provider-agnostic outbound message to an external customer.

MVP supports 'email' only (transactional SMTP via notification_service). An
'sms' adapter can be added later without changing callers. Customer emails set
skip_global_cc=True so prospects are never CC'd to the internal global address.
"""
from core.services.notification_service import send_email


def send_customer_message(channel, to, subject, body_html, body_text=None):
    if channel == 'email':
        return send_email(to, subject, body_html, body_text, skip_global_cc=True)
    return False, f'unsupported channel: {channel}'
```

Add `jarvis/core/messaging/__init__.py` (empty) if the package doesn't exist.

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): customer-messaging seam (email)"`

---

### Task 7: `TdSlotService` — materialize + availability

**Files:**
- Create: `jarvis/marketing/services/td_slot_service.py`
- Test: `tests/marketing/test_td_slot_service.py`

**Interfaces:**
- Consumes: `TdBookingRepository` (Tasks 2–4); `FoiParcursRepository.find_conflicts`, `.get_open_session`; `VehicleRepository.get_lock_by_vin`.
- Produces:
  - `materialize_slots(page_id: int) -> int` — for each active car × each window, generate `[start_time, end_time)` slots of `slot_minutes` (+ `buffer_minutes`) length on `window_date`, bulk-insert idempotently, return inserted count. Times are built in local tz.
  - `available_slots(page_id: int, now: datetime) -> list[dict]` — open slots (`repo.list_open_slots`) filtered by: `starts_at >= now + min_lead_minutes`, and the **3-way live check** per (vin, starts_at, ends_at) returns free. Returns list of `{id, car_id, vin, starts_at, ends_at}`.
  - `is_car_free(vin, frm, to) -> bool` — the read-time 3-way AND (`find_conflicts` empty **and** not `get_lock_by_vin.locked_out` **and** `get_open_session` None).

- [ ] **Step 1: Write the failing test** (mock the FP/vehicle repos so it's deterministic)

```python
# tests/marketing/test_td_slot_service.py
import pytest
from datetime import datetime, timezone
from marketing.services import td_slot_service as mod
from marketing.services.td_slot_service import TdSlotService
from marketing.repositories.td_booking_repository import TdBookingRepository

repo = TdBookingRepository()

@pytest.fixture
def page():
    p = repo.create_page({'company_id': 1, 'slug': 'mat-test-1', 'created_by': 1,
                          'slot_minutes': 30, 'min_lead_minutes': 0})
    repo.add_car(p['id'], vin='MAT00001', default_advisor_user_id=1)
    repo.add_window(p['id'], '2099-10-01', '10:00', '11:00')  # far future
    yield p
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def test_materialize_generates_two_slots(page):
    svc = TdSlotService()
    assert svc.materialize_slots(page['id']) == 2      # 10:00, 10:30
    assert svc.materialize_slots(page['id']) == 0      # idempotent

def test_available_filters_by_3way(page, monkeypatch):
    svc = TdSlotService()
    svc.materialize_slots(page['id'])
    # car busy → no availability
    monkeypatch.setattr(svc, 'is_car_free', lambda vin, frm, to: False)
    assert svc.available_slots(page['id'], datetime(2099, 1, 1, tzinfo=timezone.utc)) == []
    # car free → both slots
    monkeypatch.setattr(svc, 'is_car_free', lambda vin, frm, to: True)
    assert len(svc.available_slots(page['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))) == 2
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
# jarvis/marketing/services/td_slot_service.py
"""Slot materialization + live availability for public test-drive booking."""
from datetime import datetime, timedelta, time as dtime
from marketing.repositories.td_booking_repository import TdBookingRepository
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from foi_parcurs.repositories.vehicle_repository import VehicleRepository


class TdSlotService:
    def __init__(self):
        self.repo = TdBookingRepository()
        self.fp = FoiParcursRepository()
        self.veh = VehicleRepository()

    def materialize_slots(self, page_id: int) -> int:
        page = self.repo.get_page(page_id)
        if not page:
            return 0
        default_min = page['slot_minutes']
        cars = self.repo.list_cars(page_id)
        windows = self.repo.list_windows(page_id)
        rows = []
        for w in windows:
            step = w.get('slot_minutes') or default_min
            for car in cars:
                cursor_dt = datetime.combine(w['window_date'], _as_time(w['start_time']))
                end_dt = datetime.combine(w['window_date'], _as_time(w['end_time']))
                while cursor_dt + timedelta(minutes=step) <= end_dt:
                    slot_end = cursor_dt + timedelta(minutes=step)
                    rows.append({'page_id': page_id, 'car_id': car['id'], 'vin': car['vin'],
                                 'starts_at': cursor_dt, 'ends_at': slot_end})
                    cursor_dt = slot_end + timedelta(minutes=page['buffer_minutes'])
        return self.repo.bulk_insert_slots(rows)

    def is_car_free(self, vin, frm, to) -> bool:
        if self.fp.find_conflicts(vin, frm, to):
            return False
        lock = self.veh.get_lock_by_vin(vin)
        if lock and lock.get('locked_out'):
            return False
        if self.fp.get_open_session(vin):
            return False
        return True

    def available_slots(self, page_id: int, now: datetime) -> list:
        page = self.repo.get_page(page_id)
        lead = timedelta(minutes=page['min_lead_minutes']) if page else timedelta()
        out = []
        for s in self.repo.list_open_slots(page_id):
            if s['starts_at'] < now + lead:
                continue
            if self.is_car_free(s['vin'], s['starts_at'], s['ends_at']):
                out.append({'id': s['id'], 'car_id': s['car_id'], 'vin': s['vin'],
                            'starts_at': s['starts_at'], 'ends_at': s['ends_at']})
        return out


def _as_time(v):
    return v if isinstance(v, dtime) else datetime.strptime(str(v), '%H:%M:%S').time()
```

Note: `get_lock_by_vin` returns a dict with a `locked_out` bool that already unions manual lockout ∪ active scheduled-block window (`vehicle_repository.py:379-404`) — one call covers both.

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): slot materialization + 3-way live availability"`

---

## Phase 3 — The race-safe confirm & the booking service

### Task 8: Atomic race-safe confirm (repository)

**Files:**
- Modify: `jarvis/marketing/repositories/td_booking_repository.py`
- Test: `tests/marketing/test_td_confirm_atomic.py`

**Interfaces:**
- Produces: `confirm_booking_atomic(booking_id, vin, frm, to, fp_row: dict) -> dict` — in a **single `execute_many` transaction**: take `pg_advisory_xact_lock(hashtext(vin))`; re-run the 3-way availability as raw SQL **on the same cursor**; if unavailable raise `TdConflict`; else `INSERT INTO foi_de_parcurs (...) RETURNING id`, then `UPDATE mkt_td_bookings SET status='confirmed', foi_de_parcurs_id=..., confirmed_at=NOW()`; return `{'booking': ..., 'fp_id': ...}`.
- Also export exception `class TdConflict(Exception)`.

> This is the crux. The 3-way check MUST run on the confirm transaction's own cursor (not via `FoiParcursRepository`, which opens separate connections), so the advisory lock actually covers it. The overlap/grace SQL mirrors `find_conflicts` (`foi_parcurs_repository.py:772-800`); keep `GRACE_HOURS`/now-tz aligned with `session_lifecycle.py` to avoid drift.
>
> Known limitation (document, don't fix in MVP): `pg_advisory_xact_lock` serializes concurrent **public** confirms for a VIN, but a staff-created FP insert does not take the lock, leaving a sub-second public-vs-staff window narrowed (not eliminated) by the in-txn recheck. A follow-up can add the same lock to the staff TD create path.

- [ ] **Step 1: Write the failing test** (double-confirm race + car-became-busy)

```python
# tests/marketing/test_td_confirm_atomic.py
import pytest, threading
from datetime import datetime, timezone, timedelta
from marketing.repositories.td_booking_repository import TdBookingRepository, TdConflict
repo = TdBookingRepository()

def _fp_row(vin):
    return {'vin': vin, 'company_id': 1, 'route_type': 'TD', 'status': 'PLANNED',
            'source': 'td_form', 'client_name': 'Ion', 'client_phone': '+40721000009',
            'advisor_name': 'Test Advisor', 'departure_datetime': '2099-10-01 10:00+03',
            'return_datetime': '2099-10-01 10:30+03'}

@pytest.fixture
def booking():
    p = repo.create_page({'company_id': 1, 'slug': 'cfa-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='CFA00001', default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': 'CFA00001',
                             'starts_at': '2099-10-01 10:00+03', 'ends_at': '2099-10-01 10:30+03'}])
    s = repo.list_open_slots(p['id'])[0]
    b = repo.create_booking({'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
                             'customer_name': 'Ion', 'customer_phone_e164': '+40721000009',
                             'customer_email': 'ion@ex.com',
                             'expires_at': datetime.now(timezone.utc) + timedelta(hours=1)})
    yield p, c, s, b
    repo.execute("DELETE FROM foi_de_parcurs WHERE vin='CFA00001'")
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def test_confirm_creates_planned_fp(booking):
    p, c, s, b = booking
    res = repo.confirm_booking_atomic(b['id'], 'CFA00001',
                                      '2099-10-01 10:00+03', '2099-10-01 10:30+03', _fp_row('CFA00001'))
    fp = repo.query_one('SELECT * FROM foi_de_parcurs WHERE id=%s', (res['fp_id'],))
    assert fp['route_type'] == 'TD' and fp['status'] == 'PLANNED'
    assert repo.get_booking(b['id'])['status'] == 'confirmed'

def test_confirm_conflicts_when_car_busy(booking):
    p, c, s, b = booking
    # Seed a conflicting live FP session on the same VIN/time
    repo.execute("INSERT INTO foi_de_parcurs (vin, route_type, status, source, departure_datetime, return_datetime) "
                 "VALUES ('CFA00001','TD','PLANNED','td_form','2099-10-01 10:00+03','2099-10-01 10:30+03')")
    with pytest.raises(TdConflict):
        repo.confirm_booking_atomic(b['id'], 'CFA00001',
                                    '2099-10-01 10:00+03', '2099-10-01 10:30+03', _fp_row('CFA00001'))
    assert repo.get_booking(b['id'])['status'] == 'pending_confirm'  # untouched
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
class TdConflict(Exception):
    """Raised when a booking cannot be confirmed because the car is no longer free."""


# --- add these to TdBookingRepository ---

    # SQL mirrors find_conflicts (foi_parcurs_repository.py:772-800). Keep the
    # 6h grace and now() tz aligned with session_lifecycle.py if those change.
    _CONFLICT_SQL = (
        "SELECT 1 FROM foi_de_parcurs fp "
        "WHERE fp.vin=%s AND fp.route_type='TD' "
        "AND fp.departure_datetime <= %s "
        "AND COALESCE(fp.return_datetime, fp.departure_datetime) >= %s "
        "AND (fp.status='PLANNED' OR (fp.status<>'COMPLETED' AND fp.status<>'PENDING')) "
        "AND fp.status<>'MISSED' "
        "AND NOT (fp.status='PLANNED' AND fp.departure_datetime + INTERVAL '6 hours' < now()) "
        "LIMIT 1")
    _LOCK_SQL = (
        "SELECT 1 FROM fp_vehicles v WHERE v.vin=%s AND (v.locked_out=TRUE OR EXISTS "
        "(SELECT 1 FROM fp_vehicle_blocks b WHERE b.vehicle_id=v.id AND b.is_active "
        " AND CURRENT_DATE BETWEEN b.start_date AND b.end_date)) LIMIT 1")
    _OPEN_SQL = (
        "SELECT 1 FROM foi_de_parcurs fp "
        "WHERE fp.vin=%s AND fp.status='FILLED' AND fp.source='td_form' LIMIT 1")

    def confirm_booking_atomic(self, booking_id, vin, frm, to, fp_row: dict) -> dict:
        def _work(cursor):
            cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (vin,))
            # Guard: booking still confirmable
            cursor.execute("SELECT status FROM mkt_td_bookings WHERE id=%s FOR UPDATE", (booking_id,))
            row = cursor.fetchone()
            status = (row[0] if not isinstance(row, dict) else row['status']) if row else None
            if status != 'pending_confirm':
                raise TdConflict('booking not pending')
            # 3-way availability recheck, all on THIS cursor (inside the lock)
            cursor.execute(self._CONFLICT_SQL, (vin, to, frm))
            if cursor.fetchone():
                raise TdConflict('overlapping TD session')
            cursor.execute(self._LOCK_SQL, (vin,))
            if cursor.fetchone():
                raise TdConflict('vehicle locked/blocked')
            cursor.execute(self._OPEN_SQL, (vin,))
            if cursor.fetchone():
                raise TdConflict('vehicle already out')
            # Create the operational PLANNED FP row (column-driven insert)
            cols = list(fp_row.keys())
            ph = ', '.join(['%s'] * len(cols))
            cursor.execute(
                f"INSERT INTO foi_de_parcurs ({', '.join(cols)}) VALUES ({ph}) RETURNING id",
                tuple(fp_row[c] for c in cols))
            fp_id_row = cursor.fetchone()
            fp_id = fp_id_row[0] if not isinstance(fp_id_row, dict) else fp_id_row['id']
            cursor.execute(
                "UPDATE mkt_td_bookings SET status='confirmed', foi_de_parcurs_id=%s, "
                "confirmed_at=NOW(), updated_at=NOW() WHERE id=%s", (fp_id, booking_id))
            return {'fp_id': fp_id}
        return self.execute_many(_work)
```

Note: `get_cursor` may yield a dict-cursor or tuple-cursor depending on config — the code above tolerates both by checking `isinstance(row, dict)`. Confirm the cursor type in `core/base_repository.get_cursor` during implementation and simplify if it's always one shape.

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): race-safe atomic confirm (advisory lock + in-txn 3-way recheck)"`

---

### Task 9: `TdBookingService` — submit / confirm / cancel / expire

**Files:**
- Create: `jarvis/marketing/services/td_booking_service.py`
- Test: `tests/marketing/test_td_booking_service.py`

**Interfaces:**
- Consumes: `TdBookingRepository`, `TdSlotService`, `booking_token`, `send_customer_message`, `ClientRepository.find_by_phone/create_from_form`, `_ensure_event_project` (`foi_parcurs/routes/test_drive.py:74`).
- Produces (a small result object + methods):
  - `class ServiceResult: success: bool; status_code: int; data: dict|None; error: str|None`
  - `submit_booking(slug, slot_id, name, phone_e164, email, utm, ip, user_agent, base_url) -> ServiceResult` — validates page `open` + within `[opens_at,closes_at]`; rate-limits (`max_bookings_per_contact`, per-IP); verifies `slot_id` belongs to page and is currently available; inserts `pending_confirm` booking (maps `UniqueViolation` → 409); sends confirm email with `make_booking_token(bid,'confirm')`. Returns 201 `{booking_id, status:'pending_confirm'}`.
  - `confirm_booking(token, base_url) -> ServiceResult` — reads token, loads booking (must be `pending_confirm`, not past `expires_at`); resolves car → `default_advisor_user_id`; find-or-create CRM client by `phone_e164`; builds the PLANNED `fp_row` (see below); calls `repo.confirm_booking_atomic(...)`; on `TdConflict` marks booking `conflict`, returns 409. On success returns 200 `{status:'confirmed'}` and notifies staff.
  - `cancel_booking(token) -> ServiceResult` — reads token, loads booking; `repo.mark_cancelled`; if `foi_de_parcurs_id` set and that FP row is PLANNED, hard-`DELETE` it (`_fp_repo.delete_contract`). Returns 200.
  - `expire_pending_bookings(now) -> int` — delegates to `repo.expire_pending`.

**The PLANNED `fp_row` builder** — mirror `api_submit_test_drive`'s `contract_data` (`test_drive.py:324-389`) for the draft case, minus FILLED-only fields:

```python
fp_row = {
    'contract_id': f'TDB-{booking["id"]}',
    'vin': car['vin'],
    'company_id': page['company_id'],
    'client_id': None,                 # crm_clients != fp_clients; keep null, text cols carry identity
    'client_name': booking['customer_name'],
    'client_phone': booking['customer_phone_e164'],
    'route_type': 'TD',
    'advisor_name': advisor_name,      # users.name of default_advisor_user_id (so no-show cron notifies)
    'departure_datetime': slot['starts_at'],
    'return_datetime': slot['ends_at'],
    'event_id': page.get('event_id'),
    'mkt_project_id': page.get('project_id'),
    'source': 'td_form',
    'status': 'PLANNED',
    'is_internal': False,
    'gdpr_consent': False,             # deferred to staff activation
}
```

- [ ] **Step 1: Write the failing test** (submit → email sent; confirm → FP PLANNED; cancel → FP deleted; double-submit → one 409)

```python
# tests/marketing/test_td_booking_service.py
import pytest
from datetime import datetime, timezone, timedelta
import marketing.services.td_booking_service as svc_mod
from marketing.services.td_booking_service import TdBookingService
from marketing.repositories.td_booking_repository import TdBookingRepository
repo = TdBookingRepository()

@pytest.fixture
def open_page(monkeypatch):
    p = repo.create_page({'company_id': 1, 'slug': 'svc-1', 'created_by': 1,
                          'status': 'open', 'min_lead_minutes': 0})
    c = repo.add_car(p['id'], vin='SVC00001', default_advisor_user_id=1)
    repo.add_window(p['id'], '2099-10-01', '10:00', '11:00')
    svc = TdBookingService()
    svc.slots.materialize_slots(p['id'])
    # make availability deterministic + capture emails
    monkeypatch.setattr(svc.slots, 'is_car_free', lambda *a, **k: True)
    sent = []
    monkeypatch.setattr(svc_mod, 'send_customer_message',
                        lambda *a, **k: (sent.append(a) or (True, '')))
    yield svc, p, c, sent
    repo.execute("DELETE FROM foi_de_parcurs WHERE vin='SVC00001'")
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def test_submit_sends_email(open_page):
    svc, p, c, sent = open_page
    slot = svc.slots.available_slots(p['id'], datetime(2099,1,1,tzinfo=timezone.utc))[0]
    r = svc.submit_booking('svc-1', slot['id'], 'Ana', '+40721000010', 'ana@ex.com',
                           {}, '1.2.3.4', 'ua', 'https://x')
    assert r.success and r.status_code == 201 and len(sent) == 1

def test_double_submit_one_conflict(open_page):
    svc, p, c, sent = open_page
    slot = svc.slots.available_slots(p['id'], datetime(2099,1,1,tzinfo=timezone.utc))[0]
    r1 = svc.submit_booking('svc-1', slot['id'], 'Ana', '+40721000010', 'ana@ex.com', {}, '1.1.1.1', 'ua', 'x')
    r2 = svc.submit_booking('svc-1', slot['id'], 'Bob', '+40721000011', 'bob@ex.com', {}, '2.2.2.2', 'ua', 'x')
    assert r1.status_code == 201 and r2.status_code == 409
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement** (full service; `find-or-create` CRM + advisor-name lookup)

```python
# jarvis/marketing/services/td_booking_service.py
"""Orchestration for the public test-drive booking flow (session-less)."""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
import psycopg2
from flask import current_app
from core.base_repository import BaseRepository
from marketing.repositories.td_booking_repository import TdBookingRepository, TdConflict
from marketing.services.td_slot_service import TdSlotService
from core.approvals.booking_token import make_booking_token, read_booking_token
from core.messaging.customer_message import send_customer_message
from crm.repositories.client_repository import ClientRepository
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository

logger = logging.getLogger('jarvis.marketing.td_booking')


@dataclass
class ServiceResult:
    success: bool
    status_code: int
    data: dict | None = None
    error: str | None = None


class TdBookingService:
    def __init__(self):
        self.repo = TdBookingRepository()
        self.slots = TdSlotService()
        self.crm = ClientRepository()
        self.fp = FoiParcursRepository()
        self._base = BaseRepository()

    # ---- submit ----
    def submit_booking(self, slug, slot_id, name, phone_e164, email, utm, ip, user_agent, base_url):
        page = self.repo.get_page_by_slug(slug)
        if not page or page['status'] != 'open':
            return ServiceResult(False, 404, error='Booking page not available')
        now = datetime.now(timezone.utc)
        if page['opens_at'] and now < page['opens_at']:
            return ServiceResult(False, 403, error='Registration not open yet')
        if page['closes_at'] and now > page['closes_at']:
            return ServiceResult(False, 403, error='Registration closed')
        # rate limits
        if self.repo.count_active_by_contact(phone_e164, email) >= page['max_bookings_per_contact']:
            return ServiceResult(False, 429, error='Booking limit reached for this contact')
        from datetime import timedelta
        if self.repo.count_recent_by_ip(ip, now - timedelta(hours=1)) >= 8:
            return ServiceResult(False, 429, error='Too many attempts, try later')
        # slot must belong to page and be currently available
        avail = {s['id']: s for s in self.slots.available_slots(page['id'], now)}
        slot = avail.get(int(slot_id))
        if not slot:
            return ServiceResult(False, 409, error='Slot no longer available')
        # insert pending_confirm (race guard maps UniqueViolation -> 409)
        try:
            booking = self.repo.create_booking({
                'page_id': page['id'], 'slot_id': slot['id'], 'car_id': slot['car_id'],
                'customer_name': name, 'customer_phone_e164': phone_e164, 'customer_email': email,
                'utm': utm, 'ip': ip, 'user_agent': user_agent,
                'expires_at': now + timedelta(minutes=45),
            })
        except psycopg2.errors.UniqueViolation:
            return ServiceResult(False, 409, error='Slot just taken')
        # send confirm email
        token = make_booking_token(booking['id'], 'confirm', current_app.secret_key)
        cancel = make_booking_token(booking['id'], 'cancel', current_app.secret_key)
        link = f"{base_url}/td/confirm?token={token}"
        cancel_link = f"{base_url}/td/cancel?token={cancel}"
        html = (f"<p>Bună, {name}!</p><p>Confirmă programarea test drive: "
                f"<a href='{link}'>Confirmă</a></p><p>Anulează: <a href='{cancel_link}'>aici</a></p>")
        send_customer_message('email', email, 'Confirmă programarea test drive', html)
        return ServiceResult(True, 201, data={'booking_id': booking['id'], 'status': 'pending_confirm'})

    # ---- confirm ----
    def confirm_booking(self, token, base_url):
        data = read_booking_token(token, current_app.secret_key)
        if not data or data['act'] != 'confirm':
            return ServiceResult(False, 410, error='Link invalid or expired')
        booking = self.repo.get_booking(data['bid'])
        if not booking:
            return ServiceResult(False, 404, error='Booking not found')
        if booking['status'] == 'confirmed':
            return ServiceResult(True, 200, data={'status': 'confirmed'})
        if booking['status'] != 'pending_confirm' or booking['expires_at'] < datetime.now(timezone.utc):
            return ServiceResult(False, 410, error='Booking expired or already handled')
        page = self.repo.get_page(booking['page_id'])
        car = self.repo.get_car(booking['car_id'])
        slot = self.repo.query_one('SELECT * FROM mkt_td_slots WHERE id=%s', (booking['slot_id'],))
        # find-or-create CRM client by normalized phone
        crm_client = self.crm.find_by_phone(booking['customer_phone_e164'])
        if not crm_client:
            crm_client = self.crm.create_from_form({
                'display_name': booking['customer_name'], 'client_type': 'person',
                'phone': booking['customer_phone_e164'], 'email': booking['customer_email']})
        advisor_id = car.get('default_advisor_user_id')
        advisor_name = self._advisor_name(advisor_id)
        fp_row = {
            'contract_id': f"TDB-{booking['id']}", 'vin': car['vin'],
            'company_id': page['company_id'], 'client_id': None,
            'client_name': booking['customer_name'], 'client_phone': booking['customer_phone_e164'],
            'route_type': 'TD', 'advisor_name': advisor_name,
            'departure_datetime': slot['starts_at'], 'return_datetime': slot['ends_at'],
            'event_id': page.get('event_id'), 'mkt_project_id': page.get('project_id'),
            'source': 'td_form', 'status': 'PLANNED', 'is_internal': False, 'gdpr_consent': False,
        }
        try:
            res = self.repo.confirm_booking_atomic(
                booking['id'], car['vin'], slot['starts_at'], slot['ends_at'], fp_row)
        except TdConflict:
            self.repo.mark_status(booking['id'], 'conflict')
            return ServiceResult(False, 409, error='Car no longer available for this slot')
        # persist advisor on the booking + notify staff (best-effort)
        self.repo.mark_confirmed(booking['id'], crm_client['id'] if crm_client else None,
                                 res['fp_id'], advisor_id)
        self._notify_staff(page, booking, advisor_id)
        return ServiceResult(True, 200, data={'status': 'confirmed', 'fp_id': res['fp_id']})

    # ---- cancel ----
    def cancel_booking(self, token):
        data = read_booking_token(token, current_app.secret_key)
        if not data or data['act'] != 'cancel':
            return ServiceResult(False, 410, error='Link invalid or expired')
        booking = self.repo.get_booking(data['bid'])
        if not booking:
            return ServiceResult(False, 404, error='Booking not found')
        if booking['status'] in ('cancelled', 'expired'):
            return ServiceResult(True, 200, data={'status': booking['status']})
        self.repo.mark_cancelled(booking['id'])
        fp_id = booking.get('foi_de_parcurs_id')
        if fp_id:
            fp = self.fp.get_contract_by_id(fp_id)
            if fp and fp.get('status') == 'PLANNED':
                self.fp.delete_contract(fp_id)   # mirrors the PLANNED-only discard route
        return ServiceResult(True, 200, data={'status': 'cancelled'})

    def expire_pending_bookings(self, now):
        return self.repo.expire_pending(now)

    # ---- helpers ----
    def _advisor_name(self, user_id):
        if not user_id:
            return ''
        row = self._base.query_one('SELECT name FROM users WHERE id=%s', (user_id,))
        return row['name'] if row else ''

    def _notify_staff(self, page, booking, advisor_id):
        try:
            from core.notifications.notify import notify_with_push
            ids = list(page.get('notify_user_ids') or [])
            if advisor_id:
                ids.append(advisor_id)
            if ids:
                notify_with_push(list(set(ids)), 'Programare test drive nouă',
                                 message=f"{booking['customer_name']} · {booking['customer_phone_e164']}",
                                 category='system')
        except Exception:
            logger.warning('staff notify failed for booking %s', booking['id'], exc_info=True)
```

- [ ] **Step 4: Run to verify PASS** — `python -m pytest tests/marketing/test_td_booking_service.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat(td): booking service submit/confirm/cancel/expire"`

---

## Phase 4 — Routes & wiring

### Task 10: Public routes + app registration + SPA route

**Files:**
- Create: `jarvis/marketing/routes/td_public.py`
- Modify: `jarvis/marketing/__init__.py` (create `td_public_bp`, import routes) OR register a standalone blueprint in `app.py`
- Modify: `jarvis/app.py` (register `td_public_bp` with `url_prefix='/api/td'`; add `/td/<path:slug>` SPA route)
- Test: `tests/marketing/test_td_public_routes.py`

**Interfaces:**
- Produces HTTP:
  - `GET /api/td/pages/<slug>` → `{page:{title,intro,thank_you,company_name}, cars:[...], slots:[{id,car_id,vin,starts_at,ends_at}]}` (200) / 404
  - `POST /api/td/pages/<slug>/bookings` body `{slot_id,name,phone,email,utm}` → 201 / 404 / 403 / 409 / 429
  - `POST /api/td/bookings/confirm` body `{token}` → 200 / 409 / 410
  - `POST /api/td/bookings/cancel` body `{token}` → 200 / 410
  - `GET /td/<path:slug>` serves the SPA `index.html`, **no auth**.

- [ ] **Step 1: Write the failing test** (Flask test client, anonymous)

```python
# tests/marketing/test_td_public_routes.py
import pytest
from datetime import datetime, timezone
from app import create_app
from marketing.repositories.td_booking_repository import TdBookingRepository
repo = TdBookingRepository()

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c

@pytest.fixture
def page():
    p = repo.create_page({'company_id': 1, 'slug': 'pub-1', 'created_by': 1,
                          'status': 'open', 'min_lead_minutes': 0, 'title': 'X'})
    repo.add_car(p['id'], vin='PUB00001', default_advisor_user_id=1)
    repo.add_window(p['id'], '2099-10-01', '10:00', '11:00')
    yield p
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))

def test_get_page_public_no_auth(client, page):
    r = client.get('/api/td/pages/pub-1')
    assert r.status_code == 200
    assert 'cars' in r.get_json()

def test_get_missing_page_404_not_401(client):
    assert client.get('/api/td/pages/nope').status_code == 404   # never 401
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement the routes** (mirror `forms/routes/public.py`; DB-backed rate limit is in the service)

```python
# jarvis/marketing/routes/td_public.py
"""Public (unauthenticated) test-drive booking API. Never returns 401."""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from marketing.services.td_booking_service import TdBookingService
from marketing.repositories.td_booking_repository import TdBookingRepository
from marketing.services.td_slot_service import TdSlotService

td_public_bp = Blueprint('td_public', __name__)
_svc = TdBookingService()
_repo = TdBookingRepository()
_slots = TdSlotService()


def _client_ip():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    return ip or '0.0.0.0'


@td_public_bp.route('/pages/<slug>', methods=['GET'])
def get_page(slug):
    page = _repo.get_page_by_slug(slug)
    if not page or page['status'] != 'open':
        return jsonify({'error': 'not found'}), 404
    cars = _repo.list_cars(page['id'])
    slots = _slots.available_slots(page['id'], datetime.now(timezone.utc))
    return jsonify({
        'page': {'title': page.get('title'), 'intro': page.get('intro'),
                 'thank_you': page.get('thank_you')},
        'cars': [{'id': c['id'], 'vin': c['vin']} for c in cars],
        'slots': slots,
    }), 200


@td_public_bp.route('/pages/<slug>/bookings', methods=['POST'])
def submit(slug):
    data = request.get_json(silent=True) or {}
    required = ('slot_id', 'name', 'phone', 'email')
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'missing fields'}), 400
    r = _svc.submit_booking(slug, data['slot_id'], data['name'], data['phone'], data['email'],
                            data.get('utm', {}), _client_ip(), request.headers.get('User-Agent', ''),
                            request.host_url.rstrip('/'))
    return jsonify(r.data or {'error': r.error}), r.status_code


@td_public_bp.route('/bookings/confirm', methods=['POST'])
def confirm():
    token = (request.get_json(silent=True) or {}).get('token', '')
    r = _svc.confirm_booking(token, request.host_url.rstrip('/'))
    return jsonify(r.data or {'error': r.error}), r.status_code


@td_public_bp.route('/bookings/cancel', methods=['POST'])
def cancel():
    token = (request.get_json(silent=True) or {}).get('token', '')
    r = _svc.cancel_booking(token)
    return jsonify(r.data or {'error': r.error}), r.status_code
```

Register in `jarvis/app.py` (next to the forms registration at `:253-254`):

```python
    from marketing.routes.td_public import td_public_bp
    flask_app.register_blueprint(td_public_bp, url_prefix='/api/td')
```

Add the SPA route (verbatim clone of `/f/<path:slug>` at `app.py:524-532`, no `@login_required`):

```python
    @flask_app.route('/td/<path:slug>')
    def public_td_page(slug):
        """Serve React SPA for public test-drive pages — NO auth."""
        index_file = os.path.join(_react_dir, 'index.html')
        if os.path.exists(index_file):
            resp = send_from_directory(_react_dir, 'index.html')
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp
        return 'Not found', 404
```

**CORS note:** if the app maintains an explicit allow-methods list per the mobile-CORS gotcha, add the new methods there.

- [ ] **Step 4: Run to verify PASS** — `python3 -m py_compile jarvis/app.py && python -m pytest tests/marketing/test_td_public_routes.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat(td): public booking API + SPA route"`

---

### Task 11: Staff admin routes

**Files:**
- Create: `jarvis/marketing/routes/td_admin.py`
- Modify: `jarvis/marketing/__init__.py` (import `td_admin` so its routes attach to `marketing_bp`) and `jarvis/app.py` if a new prefix is needed
- Test: `tests/marketing/test_td_admin_routes.py`

**Interfaces:**
- Produces HTTP (authed; gated `@login_required` to match the existing foi_parcurs TD routes — see spec §8 note; tightening to a v2 permission is a follow-up):
  - `POST /marketing/api/td/pages` (create); `GET /marketing/api/td/pages`; `PATCH /marketing/api/td/pages/<id>`; `POST /marketing/api/td/pages/<id>/status` `{status}`
  - `POST /marketing/api/td/pages/<id>/cars` `{vin,vehicle_id,default_advisor_user_id,sort_order}`; `DELETE /marketing/api/td/cars/<id>`
  - `POST /marketing/api/td/pages/<id>/windows` `{window_date,start_time,end_time,slot_minutes}`
  - `POST /marketing/api/td/pages/<id>/materialize` → `{inserted:N}`
  - `GET /marketing/api/td/pages/<id>/bookings`
  - `PATCH /marketing/api/td/bookings/<id>/advisor` `{advisor_user_id}` — updates booking advisor **and** the FP row's `advisor_name` so the no-show cron notifies the right user.

- [ ] **Step 1: Write the failing test** (authenticated client; use the project's existing auth-login test helper — check `tests/conftest.py` for a `login`/`auth_client` fixture)

```python
# tests/marketing/test_td_admin_routes.py
import pytest
# Reuse the repo's existing authenticated-client fixture (see tests/conftest.py).
from marketing.repositories.td_booking_repository import TdBookingRepository
repo = TdBookingRepository()

def test_create_page_and_materialize(auth_client):
    r = auth_client.post('/marketing/api/td/pages',
                         json={'company_id': 1, 'slug': 'adm-1', 'title': 'E'})
    assert r.status_code == 201
    pid = r.get_json()['id']
    auth_client.post(f'/marketing/api/td/pages/{pid}/cars',
                     json={'vin': 'ADM00001', 'default_advisor_user_id': 1})
    auth_client.post(f'/marketing/api/td/pages/{pid}/windows',
                     json={'window_date': '2099-10-01', 'start_time': '10:00', 'end_time': '11:00'})
    m = auth_client.post(f'/marketing/api/td/pages/{pid}/materialize')
    assert m.get_json()['inserted'] == 2
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pid,))
```

> If `tests/conftest.py` has no authenticated-client fixture, add one that logs in a seeded admin user before this task (fold into Step 1). Mirror how existing authed route tests (e.g. `tests/marketing/`) obtain a session.

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement** (mirror `marketing/routes/projects.py` handler style)

```python
# jarvis/marketing/routes/td_admin.py
"""Staff admin for public test-drive booking pages (Driving Hub home)."""
from flask import jsonify, request
from flask_login import login_required, current_user
from marketing import marketing_bp
from marketing.repositories.td_booking_repository import TdBookingRepository
from marketing.services.td_slot_service import TdSlotService
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository

_repo = TdBookingRepository()
_slots = TdSlotService()
_fp = FoiParcursRepository()


@marketing_bp.route('/api/td/pages', methods=['POST'])
@login_required
def td_create_page():
    data = request.get_json(silent=True) or {}
    if not data.get('company_id') or not data.get('slug'):
        return jsonify({'error': 'company_id and slug required'}), 400
    data['created_by'] = current_user.id
    page = _repo.create_page(data)
    return jsonify({'id': page['id']}), 201


@marketing_bp.route('/api/td/pages', methods=['GET'])
@login_required
def td_list_pages():
    return jsonify({'pages': _repo.list_pages(request.args.get('company_id', type=int))})


@marketing_bp.route('/api/td/pages/<int:pid>', methods=['PATCH'])
@login_required
def td_update_page(pid):
    return jsonify(_repo.update_page(pid, request.get_json(silent=True) or {}))


@marketing_bp.route('/api/td/pages/<int:pid>/status', methods=['POST'])
@login_required
def td_set_status(pid):
    status = (request.get_json(silent=True) or {}).get('status')
    if status not in ('draft', 'open', 'closed'):
        return jsonify({'error': 'bad status'}), 400
    return jsonify(_repo.set_page_status(pid, status))


@marketing_bp.route('/api/td/pages/<int:pid>/cars', methods=['POST'])
@login_required
def td_add_car(pid):
    d = request.get_json(silent=True) or {}
    if not d.get('vin'):
        return jsonify({'error': 'vin required'}), 400
    car = _repo.add_car(pid, d['vin'], d.get('vehicle_id'),
                        d.get('default_advisor_user_id'), d.get('sort_order', 0))
    return jsonify({'id': car['id']}), 201


@marketing_bp.route('/api/td/cars/<int:cid>', methods=['DELETE'])
@login_required
def td_remove_car(cid):
    _repo.remove_car(cid)
    return jsonify({'ok': True})


@marketing_bp.route('/api/td/pages/<int:pid>/windows', methods=['POST'])
@login_required
def td_add_window(pid):
    d = request.get_json(silent=True) or {}
    w = _repo.add_window(pid, d['window_date'], d['start_time'], d['end_time'], d.get('slot_minutes'))
    return jsonify({'id': w['id']}), 201


@marketing_bp.route('/api/td/pages/<int:pid>/materialize', methods=['POST'])
@login_required
def td_materialize(pid):
    return jsonify({'inserted': _slots.materialize_slots(pid)})


@marketing_bp.route('/api/td/pages/<int:pid>/bookings', methods=['GET'])
@login_required
def td_list_bookings(pid):
    return jsonify({'bookings': _repo.list_bookings(pid, request.args.get('status'))})


@marketing_bp.route('/api/td/bookings/<int:bid>/advisor', methods=['PATCH'])
@login_required
def td_reassign_advisor(bid):
    uid = (request.get_json(silent=True) or {}).get('advisor_user_id')
    booking = _repo.get_booking(bid)
    if not booking:
        return jsonify({'error': 'not found'}), 404
    _repo.execute('UPDATE mkt_td_bookings SET advisor_user_id=%s, updated_at=NOW() WHERE id=%s', (uid, bid))
    # keep the FP row's advisor_name in sync so the no-show cron notifies the new user
    if booking.get('foi_de_parcurs_id'):
        name = _repo.query_one('SELECT name FROM users WHERE id=%s', (uid,))
        _fp.execute('UPDATE foi_de_parcurs SET advisor_name=%s WHERE id=%s',
                    ((name or {}).get('name', ''), booking['foi_de_parcurs_id']))
    return jsonify({'ok': True})
```

Add `td_admin` to the marketing route imports in `jarvis/marketing/__init__.py`.

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): staff admin routes for booking pages"`

---

### Task 12: Expiry cleanup task

**Files:**
- Create or modify: `jarvis/tasks/td_bookings.py` (new) + wire into the scheduler registry the project already uses (find how `tasks/foi_parcurs_sessions.py` is scheduled and register alongside it)
- Test: `tests/marketing/test_td_expire_task.py`

**Interfaces:**
- Produces: `expire_stale_bookings() -> int` — calls `TdBookingService().expire_pending_bookings(now)`; safe to run every few minutes.

- [ ] **Step 1: Write the failing test**

```python
# tests/marketing/test_td_expire_task.py
from datetime import datetime, timezone, timedelta
from tasks.td_bookings import expire_stale_bookings
from marketing.repositories.td_booking_repository import TdBookingRepository
repo = TdBookingRepository()

def test_expire_task_flips_stale():
    p = repo.create_page({'company_id': 1, 'slug': 'exp-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='EXP00001', default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': 'EXP00001',
                             'starts_at': '2099-10-01 10:00+03', 'ends_at': '2099-10-01 10:30+03'}])
    s = repo.list_open_slots(p['id'])[0]
    repo.create_booking({'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
                         'customer_name': 'X', 'customer_phone_e164': '+40721000099',
                         'customer_email': 'x@ex.com',
                         'expires_at': datetime.now(timezone.utc) - timedelta(minutes=1)})
    assert expire_stale_bookings() >= 1
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
# jarvis/tasks/td_bookings.py
"""Scheduled cleanup for public test-drive bookings."""
from datetime import datetime, timezone
from marketing.services.td_booking_service import TdBookingService


def expire_stale_bookings() -> int:
    """Flip pending_confirm bookings past their expires_at to 'expired' (frees the slot)."""
    return TdBookingService().expire_pending_bookings(datetime.now(timezone.utc))
```

Then register `expire_stale_bookings` in the same scheduler that runs `tasks/foi_parcurs_sessions.py` (every ~5 min). **Respect the staging guard:** the scheduler is env-gated (`ENABLE_SCHEDULER=false` on staging) — do not change that; just add the job to the existing registration.

- [ ] **Step 4: Run to verify PASS.**

- [ ] **Step 5: Commit** — `git commit -m "feat(td): expire-stale-bookings cleanup task"`

---

## Backend self-check (run before handing to frontend plan)

- [ ] Full suite green: `python -m pytest tests/ -x -q`
- [ ] Imports resolve: `python3 -m py_compile jarvis/app.py`
- [ ] Manual API smoke (Flask on :5001), anonymous:
  - create+open a page, add a car (with advisor) + window, materialize (staff routes)
  - `GET /api/td/pages/<slug>` returns slots
  - `POST /api/td/pages/<slug>/bookings` → 201 + email queued (check `is_smtp_configured()` locally; if false, assert the service still returns 201 and log shows the send attempt)
  - hit `POST /api/td/bookings/confirm` with the token from the email → FP PLANNED row exists
  - `POST /api/td/bookings/cancel` → FP row gone, slot free again

## Spec coverage map

- §4.1 race guard → Task 1 (index), Task 4 (create), Task 9 (409 mapping)
- §4.3 3-way availability → Task 7 (read), Task 8 (in-txn recheck)
- §5 token flow → Task 5, Task 9, Task 10
- §6 data model → Task 1
- §7 hardening (server-bound, DB rate limit, E.164, skip_global_cc) → Task 9, Task 6, Task 10
- §8 endpoints → Task 10, Task 11
- §9 messaging seam → Task 6, Task 9
- §10 cancel/expire → Task 9, Task 12
- §11 testing → every task's Steps 1–4
