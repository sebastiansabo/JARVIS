# export_pontaje Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-side `export_pontaje` endpoint that streams an XLSX of Pontaje data — one row per employee-contract per calendar day for a selected period — with per-contract Sincron schedule/lunch and the exact daily Sincron code.

**Architecture:** All SQL lives in repositories (`biostar_repository`, `sincron_repository`); a pure service module (`pontaje_export_service`) turns the joined data into rows and builds the workbook; a thin route wires it up and streams the file. Frontend adds From/To pickers + an "Export Pontaje" button calling the endpoint and downloading the blob.

**Tech Stack:** Python/Flask, psycopg2 (via repo base `query_all`), openpyxl; React/TypeScript, `xlsx` not used (server builds the file).

## Global Constraints

- **Routes must not contain SQL** — no `cursor.execute`, `psycopg2`, `SELECT ... FROM`, or `from database import get_db` inside `routes.py`. All queries go in repository methods. (JARVIS architecture hook.)
- **Git workflow:** work on `dev` only. Commit per task. Do NOT push to staging/main.
- **Timestamps are Romania-local naive** — render `HH:MM` by string slice, never via timezone conversion.
- **Lunch is verbatim:** print the DB value as `N min`; `0` → `0 min`; **NULL → blank (no fallback)**. The same value feeds the Duration deduction (`COALESCE(lunch, 0)`).
- **Manager scope:** the endpoint uses `_resolve_manager_filter()` — identical visibility to `/hr/pontaje`.
- **Per-contract, never summed:** Schedule + Lunch come from the specific contract's Sincron data, keyed by `(jarvis_user_id, company_id, day)`.
- Local test env: `http://localhost:5001`, login `admin@test.local` / `test1234`.

## Shared data shapes (used across tasks)

`biostar_repo.get_pontaje_rows(start, end, jarvis_user_ids)` → list of dicts, one per (contract × day):
```
{ 'day': date, 'jarvis_user_id': int|None, 'biostar_user_id': str, 'name': str,
  'group': str|None, 'company_id': int|None, 'company': str|None,
  'static_start': str|None, 'static_end': str|None,
  'first_punch': datetime|None, 'last_punch': datetime|None,
  'total_punches': int, 'duration_seconds': float|None,
  'adjusted_first_punch': datetime|None, 'adjusted_last_punch': datetime|None }
```

`sincron_repo.get_day_schedules_for_users(jarvis_user_ids, start, end)` → list of dicts:
```
{ 'jarvis_user_id': int, 'company_id': int|None, 'day': date,
  'schedule_start': str|None, 'schedule_end': str|None, 'lunch_break_minutes': int|None }
```

`sincron_repo.get_day_codes_for_users(jarvis_user_ids, year, month)` → existing, rows of
`{ 'mapped_jarvis_user_id': int, 'day': date, 'short_code': str }`.

**Output columns (15, in order):**
`Date · Weekday · Name · Group · Company · Checked In · Checked Out · Actual In · Actual Out · Lunch · Duration · Punches · Schedule · Sincron · Status`

---

### Task 1: Pure row-building + formatters (`pontaje_export_service`)

**Files:**
- Create: `jarvis/core/connectors/biostar/services/pontaje_export_service.py`
- Test: `jarvis/tests/biostar/test_pontaje_export.py`

**Interfaces:**
- Produces: `HEADERS: list[str]`, `build_rows(punch_rows, sched_map, code_map) -> list[list]`,
  and helpers `_fmt_time`, `_fmt_hm`, `_net_seconds`, `_lunch_cell`, `_status`.
  - `sched_map`: `dict[(jarvis_user_id, company_id, day)] -> {'schedule_start','schedule_end','lunch_break_minutes'}`
  - `code_map`: `dict[(jarvis_user_id, day)] -> short_code`

- [ ] **Step 1: Write the failing tests**

```python
# jarvis/tests/biostar/test_pontaje_export.py
import datetime as dt
from core.connectors.biostar.services import pontaje_export_service as pes

def _dt(day, hhmm):
    h, m = map(int, hhmm.split(':'))
    return dt.datetime(2026, 7, 1, h, m) if day == 1 else dt.datetime(2026, 7, day, h, m)

BASE = dict(jarvis_user_id=10, biostar_user_id='b1', name='Dan P.', group='AW ONE',
            company_id=5, company='AW ONE', static_start='08:00', static_end='17:00',
            first_punch=None, last_punch=None, total_punches=0, duration_seconds=None,
            adjusted_first_punch=None, adjusted_last_punch=None)

def row(**kw):
    r = dict(BASE); r.update(kw); r['day'] = dt.date(2026, 7, kw.get('_d', 1)); return r

def test_present_uses_contract_lunch_and_net_duration():
    pr = [row(first_punch=_dt(1,'08:03'), last_punch=_dt(1,'17:12'), total_punches=4,
              duration_seconds=9*3600+9*60)]
    sched = {(10, 5, dt.date(2026,7,1)): {'schedule_start':'09:00','schedule_end':'12:00','lunch_break_minutes':3}}
    out = pes.build_rows(pr, sched, {})
    r = out[0]
    assert r[pes.HEADERS.index('Checked In')] == '08:03'
    assert r[pes.HEADERS.index('Lunch')] == '3 min'
    assert r[pes.HEADERS.index('Schedule')] == '09:00–12:00'
    # net = 9:09 gross - 3 min = 9:06
    assert r[pes.HEADERS.index('Duration')] == '9:06'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_adjusted_overrides_raw():
    pr = [row(first_punch=_dt(1,'09:14'), last_punch=_dt(1,'17:22'), total_punches=3,
              duration_seconds=8*3600,
              adjusted_first_punch=_dt(1,'09:00'), adjusted_last_punch=_dt(1,'17:30'))]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'09:00','schedule_end':'18:00','lunch_break_minutes':30}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Checked In')] == '09:00'   # adjusted
    assert r[pes.HEADERS.index('Actual In')] == '09:14'    # raw

def test_single_punch_is_not_exited():
    pr = [row(first_punch=_dt(1,'08:12'), last_punch=_dt(1,'08:12'), total_punches=1)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':30}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Checked Out')] == ''
    assert r[pes.HEADERS.index('Duration')] == ''
    assert r[pes.HEADERS.index('Status')] == 'Not exited'

def test_absent_on_holiday_shows_code_and_absent():
    pr = [row()]  # no punches
    codes = {(10, dt.date(2026,7,1)): 'CO'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Sincron')] == 'CO'
    assert r[pes.HEADERS.index('Status')] == 'Absent'
    assert r[pes.HEADERS.index('Punches')] == '0'

def test_null_lunch_stays_blank_and_duration_deducts_zero():
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2,
              duration_seconds=8*3600)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':None}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Lunch')] == ''      # null -> blank
    assert r[pes.HEADERS.index('Duration')] == '8:00'  # deducts 0

def test_work_code_os_is_present_not_leave():
    pr = [row(first_punch=_dt(1,'07:58'), last_punch=_dt(1,'18:20'), total_punches=5,
              duration_seconds=10*3600)]
    codes = {(10, dt.date(2026,7,1)): 'OS'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Sincron')] == 'OS'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_weekday_and_zero_lunch():
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2, duration_seconds=8*3600)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':0}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Weekday')] == 'Wed'
    assert r[pes.HEADERS.index('Lunch')] == '0 min'
    assert r[pes.HEADERS.index('Duration')] == '8:00'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && python -m pytest tests/biostar/test_pontaje_export.py -v`
Expected: FAIL — `ModuleNotFoundError: pontaje_export_service`.

- [ ] **Step 3: Implement the module**

```python
# jarvis/core/connectors/biostar/services/pontaje_export_service.py
"""Pure builders + workbook generation for the Pontaje export.

No SQL here — callers pass already-fetched rows/maps. Kept pure so the row
logic is unit-testable under the psycopg2-mocked test harness.
"""
from io import BytesIO

HEADERS = ['Date', 'Weekday', 'Name', 'Group', 'Company', 'Checked In', 'Checked Out',
           'Actual In', 'Actual Out', 'Lunch', 'Duration', 'Punches', 'Schedule',
           'Sincron', 'Status']

# Sincron codes that mean the person is NOT at work (absence is motivated).
LEAVE_CODES = {'CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV'}
LEAVE_LABELS = {'CO': 'Annual Leave', 'CM': 'Medical', 'CES': 'Unpaid', 'CIC': 'Child Care',
                'CMS': 'Sick Family', 'DLG': 'Delegation'}

_WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _fmt_time(value):
    """Return 'HH:MM' from a datetime/str, by slice (no tz conversion)."""
    if value is None:
        return ''
    s = str(value)
    # match 'T08:03' or ' 08:03'
    for sep in ('T', ' '):
        i = s.find(sep)
        if i != -1 and len(s) >= i + 6 and s[i + 3] == ':':
            return s[i + 1:i + 6]
    return s[11:16] if len(s) >= 16 else s


def _fmt_hm(total_sec):
    if not total_sec or total_sec <= 0:
        return ''
    h = int(total_sec // 3600)
    m = round((total_sec % 3600) / 60)
    return f'{h}:{m:02d}'


def _net_seconds(gross_sec, lunch_min):
    if not gross_sec or gross_sec <= 0:
        return 0
    lunch_sec = (lunch_min or 0) * 60
    return gross_sec - lunch_sec if gross_sec > lunch_sec else gross_sec


def _lunch_cell(lunch_min):
    return '' if lunch_min is None else f'{int(lunch_min)} min'


def _span_seconds(a, b):
    if not a or not b:
        return None
    return (b - a).total_seconds()


def _status(has_punch, has_adj, single_punch_no_adj, code):
    if single_punch_no_adj:
        return 'Not exited'
    if code in LEAVE_CODES:
        return LEAVE_LABELS.get(code, code)
    return 'Present' if (has_punch or has_adj) else 'Absent'


def build_rows(punch_rows, sched_map, code_map):
    out = []
    for r in punch_rows:
        day = r['day']
        juid = r.get('jarvis_user_id')
        sched = sched_map.get((juid, r.get('company_id'), day)) or {}
        lunch = sched.get('lunch_break_minutes')  # None allowed -> blank
        sstart = sched.get('schedule_start') or r.get('static_start')
        send = sched.get('schedule_end') or r.get('static_end')

        adj_first = r.get('adjusted_first_punch')
        adj_last = r.get('adjusted_last_punch')
        has_adj = bool(adj_first or adj_last)
        raw_first = r.get('first_punch')
        raw_last = r.get('last_punch')
        total = r.get('total_punches') or 0
        single_no_adj = total == 1 and not has_adj

        eff_in = adj_first or raw_first
        eff_out = adj_last or raw_last
        checked_out = eff_out if (eff_out and eff_out != eff_in) else None

        # gross seconds: adjusted span if both adjusted, else duration_seconds
        if adj_first and adj_last:
            gross = _span_seconds(adj_first, adj_last)
        else:
            gross = r.get('duration_seconds')
        duration = '' if (single_no_adj or not eff_in or not checked_out) else _fmt_hm(_net_seconds(gross, lunch))

        code = code_map.get((juid, day), '')
        wd = _WEEKDAYS[day.weekday()]

        out.append([
            day.isoformat(),
            wd,
            r.get('name') or '',
            r.get('group') or '',
            r.get('company') or '',
            _fmt_time(eff_in) if eff_in else '',
            _fmt_time(checked_out) if checked_out else ('' if single_no_adj else ''),
            _fmt_time(raw_first) if raw_first else '',
            _fmt_time(raw_last) if (raw_last and raw_last != raw_first) else '',
            _lunch_cell(lunch),
            duration,
            str(total),
            f'{sstart or ""}–{send or ""}' if (sstart or send) else '',
            code,
            _status(bool(raw_first), has_adj, single_no_adj, code),
        ])
    return out


def build_workbook(rows):
    """rows: list of 15-col lists (no header). Returns xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = 'Pontaje'
    fill = PatternFill(start_color='0F6D63', end_color='0F6D63', fill_type='solid')
    font = Font(bold=True, color='FFFFFF')
    for col, h in enumerate(HEADERS, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = fill
        c.font = font
        c.alignment = Alignment(horizontal='center')
    for i, r in enumerate(rows, 2):
        for col, val in enumerate(r, 1):
            ws.cell(row=i, column=col, value=val)
    widths = [11, 8, 22, 16, 16, 10, 11, 10, 10, 8, 9, 8, 14, 9, 12]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w
    ws.freeze_panes = 'A2'
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && python -m pytest tests/biostar/test_pontaje_export.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/connectors/biostar/services/pontaje_export_service.py jarvis/tests/biostar/test_pontaje_export.py
git commit -m "feat(pontaje): pure row-builder + workbook for export_pontaje"
```

---

### Task 2: `biostar_repo.get_pontaje_rows` (per-contract × day, single query)

**Files:**
- Modify: `jarvis/core/connectors/biostar/repositories/biostar_repository.py` (add method near `get_range_summary`, ~line 508)

**Interfaces:**
- Produces: `get_pontaje_rows(start, end, jarvis_user_ids=None) -> list[dict]` (shape in "Shared data shapes").

- [ ] **Step 1: Add the method**

Param order matches the `%s` order in the SQL: `days` generate_series (start, end) → optional `scope` `ANY(%s)` → `deduped` BETWEEN (start, end).

```python
    def get_pontaje_rows(self, start_date, end_date, jarvis_user_ids=None):
        """One row per active BioStar contract per calendar day in [start, end].

        Absent days appear with NULL punches (roster CROSS JOIN generate_series).
        Company is the contract's mapped company (company_aliases-derived).
        """
        user_filter = ''
        args = [start_date, end_date]           # days generate_series
        if jarvis_user_ids:
            user_filter = ' AND be.mapped_jarvis_user_id = ANY(%s)'
            args.append(jarvis_user_ids)        # scope ANY
        args += [start_date, end_date]          # deduped BETWEEN
        return self.query_all(f'''
            WITH days AS (
                SELECT generate_series(%s::date, %s::date, interval '1 day')::date AS day
            ),
            scope AS (
                SELECT be.biostar_user_id,
                       be.mapped_jarvis_user_id AS jarvis_user_id,
                       COALESCE(u.name, be.name) AS name,
                       be.user_group_name AS "group",
                       COALESCE(ca.company_id, be.company_id) AS company_id,
                       COALESCE(co.company, cob.company, u.company) AS company,
                       be.schedule_start AS static_start,
                       be.schedule_end   AS static_end
                FROM biostar_employees be
                LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
                -- Authoritative group -> company mapping table (alias = BioStar group name)
                LEFT JOIN company_aliases ca
                       ON lower(ca.alias) = lower(be.user_group_name) AND ca.source = 'biostar'
                LEFT JOIN companies co  ON co.id = ca.company_id
                LEFT JOIN companies cob ON cob.id = be.company_id   -- denormalized fallback
                WHERE be.status = 'active'
                  AND (be.is_blacklisted IS NULL OR be.is_blacklisted = FALSE)
                  AND (be.user_group_name IS NULL
                       OR (be.user_group_name NOT ILIKE '%%plecati%%'
                           AND be.user_group_name NOT ILIKE '%%contracte inchise%%'))
                  AND (be.mapped_jarvis_user_id IS NULL
                       OR (u.is_active = TRUE AND COALESCE(u.contract_status, 'active') != 'closed'))
                  {user_filter}
            ),
            deduped AS (
                SELECT DISTINCT ON (pl.biostar_user_id, date_trunc('minute', pl.event_datetime))
                    pl.biostar_user_id, pl.event_datetime,
                    pl.event_datetime::date AS day
                FROM biostar_punch_logs pl
                WHERE pl.event_datetime::date BETWEEN %s::date AND %s::date
                ORDER BY pl.biostar_user_id, date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            punches AS (
                SELECT d.biostar_user_id, d.day,
                       MIN(d.event_datetime) AS first_punch,
                       MAX(d.event_datetime) AS last_punch,
                       COUNT(*) AS total_punches,
                       EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds
                FROM deduped d
                GROUP BY d.biostar_user_id, d.day
            )
            SELECT s.biostar_user_id, s.jarvis_user_id, s.name, s."group",
                   s.company_id, s.company, s.static_start, s.static_end,
                   dd.day,
                   p.first_punch, p.last_punch,
                   COALESCE(p.total_punches, 0) AS total_punches,
                   p.duration_seconds,
                   adj.adjusted_first_punch, adj.adjusted_last_punch
            FROM scope s
            CROSS JOIN days dd
            LEFT JOIN punches p
                   ON p.biostar_user_id = s.biostar_user_id AND p.day = dd.day
            LEFT JOIN biostar_daily_adjustments adj
                   ON adj.biostar_user_id = s.biostar_user_id AND adj.date = dd.day
            ORDER BY s.company NULLS LAST, s.name, dd.day, s."group"
        ''', args)
```

- [ ] **Step 2: Sanity-check placeholder/param counts**

Run: `cd jarvis && python -c "import inspect;from core.connectors.biostar.repositories.biostar_repository import BioStarRepository as R;print(inspect.getsource(R.get_pontaje_rows).count('%s'))"`
Expected: `5` (two `generate_series`, one `ANY`, two `BETWEEN`). With `jarvis_user_ids` set, `args` has 5 entries; when `None`, `user_filter` is empty so the `ANY(%s)` is absent and `args` has 4 — matching.

- [ ] **Step 3: Smoke-test against the running app DB**

Start the app if needed, then in a Python shell wired to the dev DB:
Run: `cd jarvis && python -c "from core.connectors.biostar.repositories.biostar_repository import BioStarRepository as R; rows=R().get_pontaje_rows('2026-07-01','2026-07-02'); print(len(rows)); print(rows[0] if rows else 'none')"`
Expected: prints a nonzero count and a dict with `day`, `company`, `total_punches` keys; multi-company employees appear once per company per day.

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/connectors/biostar/repositories/biostar_repository.py
git commit -m "feat(pontaje): get_pontaje_rows — per-contract attendance across a date range"
```

---

### Task 3: `sincron_repo.get_day_schedules_for_users` (per-contract schedule + lunch across range)

**Files:**
- Modify: `jarvis/core/connectors/sincron/repositories/sincron_repository.py` (add near `get_full_day_schedule_by_jarvis_user`, ~line 490)

**Interfaces:**
- Produces: `get_day_schedules_for_users(jarvis_user_ids, start, end) -> list[dict]` (shape in "Shared data shapes"). One row per `(jarvis_user_id, company_id, day)`; lunch = `COALESCE(program_break, static_lunch)` (may be NULL).

- [ ] **Step 1: Add the method**

```python
    def get_day_schedules_for_users(self, jarvis_user_ids, start_date, end_date):
        """Per-contract schedule + lunch for each day in [start, end].

        One row per (jarvis_user, company, day). Daily OZ/OS program overrides
        the static contract schedule; lunch = COALESCE(program_break, static_lunch),
        which may be NULL (caller renders NULL as blank).
        """
        if not jarvis_user_ids:
            return []
        return self.query_all('''
            WITH days AS (
                SELECT generate_series(%s::date, %s::date, interval '1 day')::date AS day
            ),
            contracts AS (
                SELECT se.sincron_employee_id, se.company_name, se.company_id,
                       se.mapped_jarvis_user_id AS jarvis_user_id,
                       se.schedule_start AS static_start,
                       se.schedule_end   AS static_end,
                       se.lunch_break_minutes AS static_lunch
                FROM sincron_employees se
                WHERE se.mapped_jarvis_user_id = ANY(%s)
                  AND se.is_active = TRUE
                  AND se.exclude_from_pontaje = FALSE
            )
            SELECT DISTINCT ON (c.jarvis_user_id, c.company_id, d.day)
                   c.jarvis_user_id, c.company_id, d.day,
                   COALESCE(to_char(st.program_in, 'HH24:MI'), c.static_start)  AS schedule_start,
                   COALESCE(to_char(st.program_out, 'HH24:MI'), c.static_end)   AS schedule_end,
                   COALESCE(st.program_break, c.static_lunch)                    AS lunch_break_minutes
            FROM contracts c
            CROSS JOIN days d
            LEFT JOIN sincron_timesheets st
                   ON st.sincron_employee_id = c.sincron_employee_id
                  AND st.company_name = c.company_name
                  AND st.day = d.day
                  AND st.short_code IN ('OZ', 'OS')
            ORDER BY c.jarvis_user_id, c.company_id, d.day, st.program_in NULLS LAST
        ''', (start_date, end_date, jarvis_user_ids))
```

- [ ] **Step 2: Smoke-test against the running app DB**

Run: `cd jarvis && python -c "from core.connectors.sincron.repositories.sincron_repository import SincronRepository as S; r=S().get_day_schedules_for_users([<a-real-jarvis-id>], '2026-07-01','2026-07-02'); print(r[:3])"`
Expected: rows with `company_id`, `day`, `schedule_start` like `'08:00'`, `lunch_break_minutes` an int or None.

- [ ] **Step 3: Commit**

```bash
git add jarvis/core/connectors/sincron/repositories/sincron_repository.py
git commit -m "feat(pontaje): get_day_schedules_for_users — per-contract schedule/lunch across range"
```

---

### Task 4: Orchestration in `pontaje_export_service`

**Files:**
- Modify: `jarvis/core/connectors/biostar/services/pontaje_export_service.py`
- Test: `jarvis/tests/biostar/test_pontaje_export.py` (add map-assembly test)

**Interfaces:**
- Consumes: `biostar_repo.get_pontaje_rows`, `sincron_repo.get_day_schedules_for_users`, `sincron_repo.get_day_codes_for_users`.
- Produces: `generate(start, end, jarvis_user_ids) -> (bytes, filename)`; `_months_between(start, end) -> list[(year, month)]`.

- [ ] **Step 1: Write the failing test for the month helper**

```python
def test_months_between_spans_year_boundary():
    from core.connectors.biostar.services import pontaje_export_service as pes
    assert pes._months_between('2025-12-20', '2026-02-03') == [(2025,12),(2026,1),(2026,2)]
```

- [ ] **Step 2: Run it, expect fail**

Run: `cd jarvis && python -m pytest tests/biostar/test_pontaje_export.py::test_months_between_spans_year_boundary -v`
Expected: FAIL — `_months_between` not defined.

- [ ] **Step 3: Implement orchestration**

```python
# add to pontaje_export_service.py
import datetime as _dt


def _months_between(start, end):
    s = _dt.date.fromisoformat(str(start)[:10])
    e = _dt.date.fromisoformat(str(end)[:10])
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


def generate(start, end, jarvis_user_ids):
    """Fetch + assemble + build workbook. Returns (xlsx_bytes, filename)."""
    from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    b_repo = BioStarRepository()
    s_repo = SincronRepository()

    punch_rows = b_repo.get_pontaje_rows(start, end, jarvis_user_ids)

    ids = sorted({r['jarvis_user_id'] for r in punch_rows if r.get('jarvis_user_id')})
    sched_map = {}
    code_map = {}
    if ids:
        for s in s_repo.get_day_schedules_for_users(ids, start, end):
            sched_map[(s['jarvis_user_id'], s['company_id'], s['day'])] = s
        for (y, m) in _months_between(start, end):
            for row in s_repo.get_day_codes_for_users(ids, y, m):
                code_map[(row['mapped_jarvis_user_id'], row['day'])] = row['short_code']

    rows = build_rows(punch_rows, sched_map, code_map)
    xlsx = build_workbook(rows)
    filename = f'pontaje_{start}_{end}.xlsx'
    return xlsx, filename
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd jarvis && python -m pytest tests/biostar/test_pontaje_export.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/connectors/biostar/services/pontaje_export_service.py jarvis/tests/biostar/test_pontaje_export.py
git commit -m "feat(pontaje): assemble maps + generate workbook (export_pontaje service)"
```

---

### Task 5: Route `export_pontaje`

**Files:**
- Modify: `jarvis/core/connectors/biostar/routes.py` (add after `get_attendance_week`, ~line 436)

**Interfaces:**
- Consumes: `pontaje_export_service.generate`, `_resolve_manager_filter`.
- Produces: `GET /biostar/api/attendance/export?start&end` → xlsx download.

- [ ] **Step 1: Add the route (no SQL — service does data)**

```python
@biostar_bp.route('/api/attendance/export', methods=['GET'])
@api_login_required
def export_pontaje():
    """Stream a Pontaje XLSX for [start, end], one row per contract per day."""
    from flask import Response
    from datetime import date
    from core.connectors.biostar.services import pontaje_export_service

    start = request.args.get('start')
    end = request.args.get('end')
    if not start or not end:
        return jsonify({'success': False, 'error': 'start and end are required'}), 400
    try:
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end)
    except ValueError:
        return jsonify({'success': False, 'error': 'invalid date format (YYYY-MM-DD)'}), 400
    if d0 > d1:
        return jsonify({'success': False, 'error': 'start must be on or before end'}), 400
    if (d1 - d0).days > 366:
        return jsonify({'success': False, 'error': 'range too large (max 366 days)'}), 400

    jarvis_user_ids = _resolve_manager_filter()
    xlsx, filename = pontaje_export_service.generate(start, end, jarvis_user_ids)
    return Response(
        xlsx,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
```

- [ ] **Step 2: Verify no architecture violation**

Run: `cd jarvis && grep -nE "cursor\.execute|psycopg2|SELECT\s+.*\s+FROM|from database import get_db" core/connectors/biostar/routes.py`
Expected: no new matches from the added route (only pre-existing lines elsewhere, if any).

- [ ] **Step 3: End-to-end smoke test**

Run: `curl -s -c /tmp/j.txt -b /tmp/j.txt -X POST http://localhost:5001/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@test.local","password":"test1234"}' >/dev/null; curl -s -b /tmp/j.txt "http://localhost:5001/biostar/api/attendance/export?start=2026-07-01&end=2026-07-02" -o /tmp/pontaje.xlsx -D -; python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/pontaje.xlsx'); ws=wb.active; print([c.value for c in ws[1]]); print('rows', ws.max_row)"`
Expected: 200 with a `Content-Disposition` header; header row prints the 15 columns; `rows` > 1.

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/connectors/biostar/routes.py
git commit -m "feat(pontaje): export_pontaje route — GET /biostar/api/attendance/export"
```

---

### Task 6: Frontend — API client + From/To pickers + button

**Files:**
- Modify: `jarvis/frontend/src/api/biostar.ts` (add `exportPontaje`, after `getRangeSummary` ~line 194)
- Modify: `jarvis/frontend/src/pages/Hr/PontajeTab.tsx` (toolbar: add From/To + button, near the existing export dropdown ~line 830)

**Interfaces:**
- Consumes: `GET /biostar/api/attendance/export`.
- Produces: `biostarApi.exportPontaje(start: string, end: string): Promise<boolean>` (false on error).

- [ ] **Step 1: Add the API client method (mirror bilant download pattern)**

```typescript
  // in biostar.ts, inside the biostarApi object
  exportPontaje: async (start: string, end: string): Promise<boolean> => {
    const res = await fetch(`${BASE}/attendance/export?start=${start}&end=${end}`, {
      credentials: 'same-origin',
    })
    if (!res.ok) return false
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download =
      res.headers.get('content-disposition')?.match(/filename="?(.+?)"?$/)?.[1] ||
      `pontaje_${start}_${end}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return true
  },
```

- [ ] **Step 2: Add state + handler in PontajeTab** (near the existing `exporting` state ~line 351)

```tsx
  const monthStartStr = date.slice(0, 8) + '01'
  const [exportStart, setExportStart] = useState(monthStartStr)
  const [exportEnd, setExportEnd] = useState(date)

  const handleExportPontaje = useCallback(async () => {
    setExporting(true)
    const toastId = toast.loading('Exporting pontaje…')
    try {
      const ok = await biostarApi.exportPontaje(exportStart, exportEnd)
      if (ok) toast.success('Export complete', { id: toastId })
      else toast.error('Export failed', { id: toastId })
    } finally {
      setExporting(false)
    }
  }, [exportStart, exportEnd])
```

- [ ] **Step 3: Add the controls to the toolbar** (just before the existing `{/* Export Excel dropdown */}` block, ~line 830)

```tsx
            {/* Export Pontaje (period) */}
            <div className="flex items-center gap-1">
              <DateField value={exportStart} onChange={setExportStart} className="h-8 w-[130px]" />
              <span className="text-muted-foreground text-xs">→</span>
              <DateField value={exportEnd} onChange={setExportEnd} className="h-8 w-[130px]" />
              <Button variant="outline" size="sm" className="h-8" disabled={exporting}
                      onClick={handleExportPontaje} title="Export Pontaje for the selected period">
                <Download className={cn('h-4 w-4 mr-1', exporting && 'animate-pulse')} />
                Export Pontaje
              </Button>
            </div>
```

(Verify `DateField`'s prop names against its definition at `jarvis/frontend/src/components/ui/date-field.tsx`; adjust `value`/`onChange` if the component uses different names.)

- [ ] **Step 4: Typecheck + build**

Run: `cd jarvis/frontend && npm run build`
Expected: build succeeds, no TS errors referencing PontajeTab or biostar.ts.

- [ ] **Step 5: Manual UI check**

Open `http://localhost:5001`, go to Pontaje, pick a From/To, click **Export Pontaje**, confirm the `.xlsx` downloads and opens with the 15 columns and per-contract rows.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/api/biostar.ts jarvis/frontend/src/pages/Hr/PontajeTab.tsx
git commit -m "feat(pontaje): Export Pontaje button with From/To period pickers"
```

---

### Task 7: End-to-end verification against real data

**Files:** none (verification only)

- [ ] **Step 1: Multi-company / split-shift spot check**

Pick a known multi-company employee. Export a period covering a day they worked two contracts. Confirm two rows that day, each with its own Group=Company, its own Schedule, and its own Lunch (not summed).

- [ ] **Step 2: Absence-explained check**

Find an employee on `CO`/`CM` for a day. Confirm the row shows `Status = Absent` and `Sincron = CO`/`CM`; a no-code no-punch day shows blank Sincron.

- [ ] **Step 3: Lunch fidelity check**

Confirm a `0`-break employee shows `0 min`, a 30 and a 60 show correctly, and Duration reconciles: `Duration == span(Checked In, Checked Out) − Lunch`.

- [ ] **Step 4: Scope check**

Log in as a non-L0 manager (if available) and confirm the export contains only their managed employees — matching what `/hr/pontaje` shows them.

- [ ] **Step 5: Guardrail check**

Run: `curl -s -b /tmp/j.txt "http://localhost:5001/biostar/api/attendance/export?start=2026-07-10&end=2026-07-01" -D - -o /dev/null | head -1`
Expected: `HTTP/1.1 400` (start after end). Repeat with a >366-day range → 400.

---

## Self-Review

**Spec coverage:**
- Endpoint + manager scope → Task 5. ✅
- One row per contract × calendar day, absent days included → Task 2 (CROSS JOIN generate_series). ✅
- Group↔Company paired via `company_aliases` (company_id) → Task 2 (`be.company_id → companies`). ✅
- Per-contract Schedule + Lunch (never summed) → Task 3 + Task 1 join by `(juid, company_id, day)`. ✅
- Lunch verbatim, NULL→blank, Duration deducts COALESCE(lunch,0) → Task 1 (`_lunch_cell`, `_net_seconds`). ✅
- Exact Sincron code → Task 4 (`get_day_codes_for_users` → `code_map`), Task 1 Sincron column. ✅
- 15 columns, adjusted-vs-raw, not-exited, status → Task 1. ✅
- XLSX styled + streamed → Task 1 `build_workbook`, Task 5 Response. ✅
- From/To pickers + button, existing dropdown untouched → Task 6. ✅
- Guardrails (start≤end, ≤366d) → Task 5. ✅
- No SQL in routes → Tasks 2/3 hold SQL; Task 5 Step 2 verifies. ✅

**Placeholder scan:** Task 6 Step 3 flags a runtime check of `DateField` prop names — this is a real verification instruction, not a placeholder (the props are `value`/`onChange` per the import). No TBDs elsewhere.

**Type consistency:** `get_pontaje_rows` dict keys (`group`, `company_id`, `static_start`…) match Task 1's `build_rows` reads and Task 4's map keys. `code_map` keyed `(jarvis_user_id, day)` in Task 4 matches Task 1's `code_map.get((juid, day))`. `sched_map` keyed `(jarvis_user_id, company_id, day)` consistent across Tasks 1/4. ✅

**Note on Task 2 params:** Steps 2–3 deliberately catch and fix the `%s`/params mismatch — implementer must apply Step 3's `args` construction (single `generate_series`, one optional ANY, one `deduped` BETWEEN).
