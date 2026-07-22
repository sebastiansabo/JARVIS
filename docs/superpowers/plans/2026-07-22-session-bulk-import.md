# Bulk Session Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import historical driving sessions from an Excel file, tenant-scoped by company, keyed by VIN, auto-creating unknown cars and skipping duplicates.

**Architecture:** A new `session_import_service.py` (template builder + parse/validate/insert) behind two Flask routes, following the existing `route_sheet` pattern. Frontend adds an "Importă sesiuni" modal to the Foi de Parcurs tab. openpyxl for xlsx read/write; sessions become `foi_de_parcurs` rows (`source='import'`).

**Tech Stack:** Python/Flask, psycopg2 (via `BaseRepository`/`FoiParcursRepository`/`FPVehicleRepository`), openpyxl, React 19 + TypeScript, `@tanstack/react-query`, shadcn/ui.

## Global Constraints

- Backend on port 5001; Flask (not Django/FastAPI); PostgreSQL only.
- Layering: routes → services → repositories. Routes contain no SQL.
- SQL always parameterized (`%s`); never f-string interpolation into SQL.
- All endpoints `@login_required`.
- Tenant = the selected company. A VIN owned by another company is rejected; new cars attach to the selected company.
- Template columns (verbatim, in order): `VIN`, `Marcă`, `Model`, `Nr. înmatriculare`, `Combustibil`, `Capacitate rezervor (L)`, `Brand`, `Plecare`, `Sosire`, `KM start`, `KM end`, `Șofer`.
- Session rows: `status='COMPLETED'`, `source='import'`, `route_type` = `TD` if `distance ≤ fp_km_configs.td_km_max` (default 50) else `Comodat`, fuel gauges `'1'/'1'`, fuel liters `0/0/0`.
- `contract_id` = `IMPORT_{safe_vin}_{yyyymmdd}_{km_start}_{km_end}` where `safe_vin = re.sub(r'[^A-Za-z0-9]','',vin)`.
- Run tests with the venv: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q` (env `DATABASE_URL` is set by the test module).
- Frontend gate: `cd jarvis/frontend && npx tsc --noEmit -p tsconfig.json` must exit 0.

---

### Task 1: Service scaffold — columns + date parsing + row mapping (pure)

**Files:**
- Create: `jarvis/foi_parcurs/services/session_import_service.py`
- Test: `jarvis/tests/foi_parcurs/test_session_import.py`

**Interfaces:**
- Produces:
  - `SESSION_COLUMNS: list[str]` — the 12 header strings (verbatim, in order).
  - `parse_dt(v) -> datetime | None` — parses a cell value (datetime, `dd.mm.yyyy HH:MM`, `dd.mm.yyyy`, or ISO) to `datetime`, else `None`.
  - `row_error(row: dict, vehicle: dict | None, company_id: int) -> str | None` — validation message or `None`. `row` keys are the 12 column names.

- [ ] **Step 1: Write the failing tests**

```python
# jarvis/tests/foi_parcurs/test_session_import.py
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime
from foi_parcurs.services import session_import_service as sis


def test_parse_dt_accepts_romanian_and_iso():
    assert sis.parse_dt('02.07.2026 10:00') == datetime(2026, 7, 2, 10, 0)
    assert sis.parse_dt('02.07.2026') == datetime(2026, 7, 2, 0, 0)
    assert sis.parse_dt('2026-07-02 10:00') == datetime(2026, 7, 2, 10, 0)
    assert sis.parse_dt(datetime(2026, 7, 2, 8, 30)) == datetime(2026, 7, 2, 8, 30)
    assert sis.parse_dt('') is None
    assert sis.parse_dt('nonsense') is None


def _row(**kw):
    base = {c: '' for c in sis.SESSION_COLUMNS}
    base.update(kw)
    return base


def test_row_error_missing_vin():
    assert sis.row_error(_row(VIN=''), None, 1) == 'VIN lipsă'


def test_row_error_wrong_company():
    veh = {'vin': 'V1', 'company_id': 99}
    assert sis.row_error(_row(VIN='V1', **{'KM start': '10', 'KM end': '20', 'Plecare': '02.07.2026'}), veh, 1) \
        == 'VIN aparține altei companii'


def test_row_error_new_vin_needs_make_model():
    r = _row(VIN='NEW', **{'KM start': '10', 'KM end': '20', 'Plecare': '02.07.2026'})
    assert sis.row_error(r, None, 1) == 'Mașină nouă necesită Marcă și Model'


def test_row_error_bad_km():
    veh = {'vin': 'V1', 'company_id': 1}
    r = _row(VIN='V1', **{'KM start': '20', 'KM end': '20', 'Plecare': '02.07.2026'})
    assert sis.row_error(r, veh, 1) == 'KM invalizi (KM end trebuie > KM start)'


def test_row_error_ok():
    veh = {'vin': 'V1', 'company_id': 1}
    r = _row(VIN='V1', **{'KM start': '10', 'KM end': '25', 'Plecare': '02.07.2026 10:00'})
    assert sis.row_error(r, veh, 1) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'foi_parcurs.services.session_import_service'`

- [ ] **Step 3: Write the minimal implementation**

```python
# jarvis/foi_parcurs/services/session_import_service.py
"""Bulk import of driving sessions from an Excel file (tenant-scoped, keyed by
VIN). Unknown VINs auto-create the car; duplicates are skipped. See
docs/superpowers/specs/2026-07-22-session-bulk-import-design.md"""
import io
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SESSION_COLUMNS = [
    'VIN', 'Marcă', 'Model', 'Nr. înmatriculare', 'Combustibil',
    'Capacitate rezervor (L)', 'Brand', 'Plecare', 'Sosire',
    'KM start', 'KM end', 'Șofer',
]

_DT_FORMATS = ('%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y-%m-%dT%H:%M')


def parse_dt(v):
    """Parse a cell value to datetime, or None."""
    if isinstance(v, datetime):
        return v
    s = str(v or '').strip()
    if not s:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _int(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def row_error(row: dict, vehicle: dict | None, company_id: int) -> str | None:
    """Validation message for a row, or None when valid."""
    vin = str(row.get('VIN') or '').strip()
    if not vin:
        return 'VIN lipsă'
    if vehicle is not None and vehicle.get('company_id') not in (None, company_id):
        return 'VIN aparține altei companii'
    if vehicle is None and not (str(row.get('Marcă') or '').strip() and str(row.get('Model') or '').strip()):
        return 'Mașină nouă necesită Marcă și Model'
    if parse_dt(row.get('Plecare')) is None:
        return 'Plecare invalidă'
    ks, ke = _int(row.get('KM start')), _int(row.get('KM end'))
    if ks is None or ke is None or ke <= ks:
        return 'KM invalizi (KM end trebuie > KM start)'
    sos = parse_dt(row.get('Sosire'))
    if sos is not None and sos < parse_dt(row.get('Plecare')):
        return 'Sosire înainte de Plecare'
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/services/session_import_service.py jarvis/tests/foi_parcurs/test_session_import.py
git commit -m "feat(foi-parcurs): session-import service scaffold (columns, parse, validate)"
```

---

### Task 2: Template builder (`.xlsx`)

**Files:**
- Modify: `jarvis/foi_parcurs/services/session_import_service.py`
- Test: `jarvis/tests/foi_parcurs/test_session_import.py`

**Interfaces:**
- Consumes: `SESSION_COLUMNS` (Task 1).
- Produces: `build_template_xlsx(company_id: int) -> bytes` — a workbook with sheet `Sesiuni` (header row = `SESSION_COLUMNS` + one example row) and sheet `Mașini` (columns `Marcă`, `Model`, `VIN` for the company's active cars). Reads cars via module-level `_veh_repo` (a `FPVehicleRepository`) so tests can monkeypatch it.

- [ ] **Step 1: Write the failing test**

```python
def test_build_template_has_sheets_and_headers(monkeypatch):
    from openpyxl import load_workbook
    monkeypatch.setattr(
        sis._veh_repo, 'get_all',
        lambda active_only=True: [
            {'vin': 'V1', 'mark': 'Audi', 'model': 'A4', 'company_id': 1},
            {'vin': 'V2', 'mark': 'VW', 'model': 'Golf', 'company_id': 2},
        ],
    )
    wb = load_workbook(io.BytesIO(sis.build_template_xlsx(1)))
    assert wb['Sesiuni'][1][0].value == 'VIN'
    assert [c.value for c in wb['Sesiuni'][1]] == sis.SESSION_COLUMNS
    # Mașini sheet lists only company 1's cars
    vins = [row[2].value for row in wb['Mașini'].iter_rows(min_row=2) if row[2].value]
    assert vins == ['V1']
```

(add `import io` at the top of the test file)

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py::test_build_template_has_sheets_and_headers -x -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_veh_repo'`

- [ ] **Step 3: Implement**

```python
# add to session_import_service.py (top, after imports)
from ..repositories.vehicle_repository import FPVehicleRepository
_veh_repo = FPVehicleRepository()


def build_template_xlsx(company_id: int) -> bytes:
    """Excel template: a 'Sesiuni' sheet (headers + example) and a 'Mașini'
    reference sheet with the company's cars."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = 'Sesiuni'
    head = Font(bold=True, color='FFFFFF')
    fill = PatternFill('solid', fgColor='1A1A2E')
    for col, name in enumerate(SESSION_COLUMNS, start=1):
        c = ws.cell(row=1, column=col, value=name)
        c.font = head; c.fill = fill
    example = ['WAUZZZ00000000000', 'Audi', 'A4', 'B 123 ABC', 'Diesel', 55, 'Audi',
               '02.07.2026 10:00', '02.07.2026 12:30', 13000, 13025, 'Ion Popescu']
    for col, val in enumerate(example, start=1):
        ws.cell(row=2, column=col, value=val)
    widths = [20, 12, 12, 16, 12, 16, 12, 18, 18, 10, 10, 20]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    ref = wb.create_sheet('Mașini')
    for col, name in enumerate(['Marcă', 'Model', 'VIN'], start=1):
        c = ref.cell(row=1, column=col, value=name)
        c.font = head; c.fill = fill
    cars = [v for v in (_veh_repo.get_all(active_only=False) or []) if v.get('company_id') == company_id]
    for r, v in enumerate(cars, start=2):
        ref.cell(row=r, column=1, value=v.get('mark') or '')
        ref.cell(row=r, column=2, value=v.get('model') or '')
        ref.cell(row=r, column=3, value=v.get('vin') or '')
    ref.column_dimensions['A'].width = 14
    ref.column_dimensions['B'].width = 14
    ref.column_dimensions['C'].width = 22

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/services/session_import_service.py jarvis/tests/foi_parcurs/test_session_import.py
git commit -m "feat(foi-parcurs): session-import Excel template builder"
```

---

### Task 3: Import orchestration (parse → resolve/create car → insert → dedup)

**Files:**
- Modify: `jarvis/foi_parcurs/services/session_import_service.py`
- Test: `jarvis/tests/foi_parcurs/test_session_import.py`

**Interfaces:**
- Consumes: `SESSION_COLUMNS`, `parse_dt`, `row_error`, `_int` (Task 1); module-level `_veh_repo` (Task 2).
- Produces:
  - module-level `_fp_repo` (a `FoiParcursRepository`).
  - `import_sessions(company_id: int, file_bytes: bytes, user_name: str | None) -> dict` returning `{'inserted': int, 'skipped': int, 'cars_created': int, 'errors': [{'row': int, 'message': str}]}`. Uses `_fp_repo.query_one` (existence check + td_km_max), `_fp_repo.execute` (INSERTs), `_veh_repo.get_by_vin`.

- [ ] **Step 1: Write the failing test**

```python
def test_import_inserts_skips_and_creates_car(monkeypatch):
    from openpyxl import Workbook
    # Build an in-memory xlsx with 3 data rows: existing car, dup, new car.
    wb = Workbook(); ws = wb.active; ws.title = 'Sesiuni'
    for col, name in enumerate(sis.SESSION_COLUMNS, start=1):
        ws.cell(row=1, column=col, value=name)
    rows = [
        ['V1', '', '', '', '', '', '', '02.07.2026 10:00', '', 100, 130, 'Ana'],      # existing → insert
        ['V1', '', '', '', '', '', '', '02.07.2026 10:00', '', 100, 130, 'Ana'],      # same → dup skip
        ['VNEW', 'Audi', 'A4', 'B1', '', '', '', '03.07.2026 09:00', '', 0, 40, 'Ion'],  # new car → create + insert
    ]
    for r, row in enumerate(rows, start=2):
        for col, val in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=val)
    import io as _io; buf = _io.BytesIO(); wb.save(buf); data = buf.getvalue()

    monkeypatch.setattr(sis._veh_repo, 'get_by_vin',
                        lambda vin: {'vin': 'V1', 'company_id': 1, 'fuel_tank_capacity_liters': 55,
                                     'registration_number': 'B-V1'} if vin == 'V1' else None)
    seen = {'inserted': [], 'vehicles': []}
    # existence check: the first V1 row is new, the second is a dup.
    calls = {'n': 0}
    def fake_query_one(sql, params=()):
        if 'td_km_max' in sql:
            return {'td_km_max': 50}
        if 'FROM foi_de_parcurs' in sql:  # dedup existence check by contract_id
            cid = params[0]
            exists = cid in seen['inserted']
            return {'x': 1} if exists else None
        return None
    def fake_execute(sql, params=(), **kw):
        if 'INTO fp_vehicles' in sql:
            seen['vehicles'].append(params[0])
        elif 'INTO foi_de_parcurs' in sql:
            seen['inserted'].append(params[0])  # contract_id is first param
        return 1
    monkeypatch.setattr(sis._fp_repo, 'query_one', fake_query_one)
    monkeypatch.setattr(sis._fp_repo, 'execute', fake_execute)

    res = sis.import_sessions(1, data, 'Tester')
    assert res['inserted'] == 2      # V1 once + VNEW once
    assert res['skipped'] == 1       # the duplicate V1 row
    assert res['cars_created'] == 1  # VNEW
    assert res['errors'] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py::test_import_inserts_skips_and_creates_car -x -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'import_sessions'`

- [ ] **Step 3: Implement**

```python
# add to session_import_service.py
from ..repositories.foi_parcurs_repository import FoiParcursRepository
_fp_repo = FoiParcursRepository()


def _td_max(company_id: int) -> int:
    try:
        r = _fp_repo.query_one('SELECT td_km_max FROM fp_km_configs WHERE company_id=%s', (company_id,))
        if r and r.get('td_km_max'):
            return int(r['td_km_max'])
    except Exception:
        logger.warning('td_km_max lookup failed', exc_info=True)
    return 50


def _create_vehicle(row: dict, company_id: int) -> None:
    vin = str(row['VIN']).strip()
    _fp_repo.execute(
        '''INSERT INTO fp_vehicles
             (vin, mark, model, registration_number, fuel_type,
              fuel_tank_capacity_liters, brand, company_id, is_active)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
           ON CONFLICT (vin) DO NOTHING''',
        (vin, str(row.get('Marcă') or '').strip() or '—',
         str(row.get('Model') or '').strip() or '—',
         str(row.get('Nr. înmatriculare') or '').strip() or None,
         str(row.get('Combustibil') or '').strip() or 'Diesel',
         _int(row.get('Capacitate rezervor (L)')) or 50,
         str(row.get('Brand') or row.get('Marcă') or '').strip() or None,
         company_id),
    )


def import_sessions(company_id: int, file_bytes: bytes, user_name: str | None) -> dict:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb['Sesiuni'] if 'Sesiuni' in wb.sheetnames else wb.active

    td_max = _td_max(company_id)
    inserted = skipped = cars_created = 0
    errors = []
    for i, raw in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if raw is None or all(c in (None, '') for c in raw):
            continue
        row = {SESSION_COLUMNS[j]: (raw[j] if j < len(raw) else '') for j in range(len(SESSION_COLUMNS))}
        vin = str(row.get('VIN') or '').strip()
        vehicle = _veh_repo.get_by_vin(vin) if vin else None
        err = row_error(row, vehicle, company_id)
        if err:
            errors.append({'row': i, 'message': err})
            continue
        if vehicle is None:
            _create_vehicle(row, company_id)
            cars_created += 1
            vehicle = {'fuel_tank_capacity_liters': _int(row.get('Capacitate rezervor (L)')) or 50,
                       'registration_number': str(row.get('Nr. înmatriculare') or '').strip()}

        dep = parse_dt(row['Plecare'])
        sos = parse_dt(row.get('Sosire'))
        ks, ke = _int(row['KM start']), _int(row['KM end'])
        dist = ke - ks
        safe_vin = re.sub(r'[^A-Za-z0-9]', '', vin)
        cid = f'IMPORT_{safe_vin}_{dep.strftime("%Y%m%d")}_{ks}_{ke}'
        if _fp_repo.query_one('SELECT 1 AS x FROM foi_de_parcurs WHERE contract_id=%s', (cid,)):
            skipped += 1
            continue
        route_type = 'TD' if dist <= td_max else 'Comodat'
        tank = (vehicle or {}).get('fuel_tank_capacity_liters') or 50
        reg = (vehicle or {}).get('registration_number') or ''
        _fp_repo.execute(
            '''INSERT INTO foi_de_parcurs
                 (contract_id, vin, company_id, year, month, route_type, slot_number,
                  km_start, km_end, distance_km, registration_number,
                  fuel_tank_capacity_liters, fuel_gauge_start_level, fuel_gauge_end_level,
                  fuel_start_liters, fuel_end_liters, fuel_consumed_liters,
                  status, advisor_name, client_name, itinerary,
                  departure_datetime, return_datetime, source)
               VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,'1','1',0,0,0,
                       'COMPLETED',%s,%s,'',%s,%s,'import')
               ON CONFLICT (contract_id) DO NOTHING''',
            (cid, vin, company_id, dep.year, dep.month, route_type, ks, ke, dist, reg, tank,
             (user_name or 'Import'), str(row.get('Șofer') or '').strip(),
             dep.strftime('%Y-%m-%d %H:%M:%S'),
             sos.strftime('%Y-%m-%d %H:%M:%S') if sos else None),
        )
        inserted += 1
    return {'inserted': inserted, 'skipped': skipped, 'cars_created': cars_created, 'errors': errors}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/services/session_import_service.py jarvis/tests/foi_parcurs/test_session_import.py
git commit -m "feat(foi-parcurs): session-import orchestration (parse, auto-create car, dedup insert)"
```

---

### Task 4: Routes — template download + import upload

**Files:**
- Create: `jarvis/foi_parcurs/routes/session_import.py`
- Modify: `jarvis/foi_parcurs/routes/__init__.py` (add `from . import session_import  # noqa: F401`)
- Test: `jarvis/tests/foi_parcurs/test_session_import.py`

**Interfaces:**
- Consumes: `build_template_xlsx`, `import_sessions` (Tasks 2–3); `_shared` blueprint helpers.
- Produces:
  - `GET /api/foi-parcurs/sessions/import-template?company_id=<int>` → xlsx (`Content-Disposition: attachment`).
  - `POST /api/foi-parcurs/sessions/import` (multipart: `file`, `company_id`) → `{success, inserted, skipped, cars_created, errors}`.

- [ ] **Step 1: Write the failing tests**

```python
import io
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.session_import as si_routes


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_template_route_returns_xlsx(client, monkeypatch):
    monkeypatch.setattr(si_routes, 'build_template_xlsx', lambda cid: b'PK\x03\x04xlsx')
    resp = client.get('/api/foi-parcurs/sessions/import-template?company_id=1')
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.headers['Content-Type']
    assert resp.data == b'PK\x03\x04xlsx'


def test_import_route_returns_report(client, monkeypatch):
    monkeypatch.setattr(si_routes, 'import_sessions',
                        lambda company_id, file_bytes, user_name: {
                            'inserted': 2, 'skipped': 1, 'cars_created': 1, 'errors': []})
    data = {'company_id': '1', 'file': (io.BytesIO(b'xlsxbytes'), 'sessions.xlsx')}
    resp = client.post('/api/foi-parcurs/sessions/import', data=data,
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True and body['inserted'] == 2 and body['cars_created'] == 1


def test_import_route_requires_file_and_company(client):
    resp = client.post('/api/foi-parcurs/sessions/import', data={'company_id': '1'},
                       content_type='multipart/form-data')
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'foi_parcurs.routes.session_import'`

- [ ] **Step 3: Implement the route + register it**

```python
# jarvis/foi_parcurs/routes/session_import.py
"""Bulk driving-session import: Excel template download + upload/parse."""
from flask import Response, send_file
import io
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..services.session_import_service import build_template_xlsx, import_sessions

_XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@foi_parcurs_bp.route('/api/foi-parcurs/sessions/import-template', methods=['GET'])
@login_required
def api_session_import_template():
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        content = build_template_xlsx(company_id)
    except Exception as e:
        logger.exception('Session import template failed for %s', company_id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return send_file(io.BytesIO(content), mimetype=_XLSX_MIME, as_attachment=True,
                     download_name=f'import-sesiuni-{company_id}.xlsx')


@foi_parcurs_bp.route('/api/foi-parcurs/sessions/import', methods=['POST'])
@login_required
def api_session_import():
    company_id = request.form.get('company_id', type=int)
    file = request.files.get('file')
    if not company_id or file is None:
        return jsonify({'success': False, 'error': 'company_id și file sunt obligatorii'}), 400
    try:
        report = import_sessions(
            company_id, file.read(),
            user_name=(getattr(current_user, 'name', None) or getattr(current_user, 'email', None)))
    except Exception as e:
        logger.exception('Session import failed for company %s', company_id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return jsonify({'success': True, **report})
```

```python
# jarvis/foi_parcurs/routes/__init__.py — add after the route_sheet import line
from . import session_import   # noqa: F401
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd jarvis && ../venv/bin/python -m pytest tests/foi_parcurs/test_session_import.py -x -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/routes/session_import.py jarvis/foi_parcurs/routes/__init__.py jarvis/tests/foi_parcurs/test_session_import.py
git commit -m "feat(foi-parcurs): session-import routes (template download + upload)"
```

---

### Task 5: Frontend API client

**Files:**
- Modify: `jarvis/frontend/src/api/foiParcurs.ts`

**Interfaces:**
- Consumes: the two routes from Task 4.
- Produces (on `foiParcursApi`):
  - `getSessionImportTemplateUrl(companyId: number): string` → the template URL.
  - `importSessions(companyId: number, file: File): Promise<SessionImportResult>` (raw `fetch`, multipart).
  - exported `interface SessionImportResult { success: boolean; inserted: number; skipped: number; cars_created: number; errors: { row: number; message: string }[] }`.

- [ ] **Step 1: Add the type + methods**

```typescript
// jarvis/frontend/src/api/foiParcurs.ts — near the other exported interfaces
export interface SessionImportResult {
  success: boolean
  inserted: number
  skipped: number
  cars_created: number
  errors: { row: number; message: string }[]
}
```

```typescript
// inside foiParcursApi, next to the route-sheet methods
  getSessionImportTemplateUrl: (companyId: number) =>
    `${BASE}/sessions/import-template${qs({ company_id: companyId })}`,

  importSessions: async (companyId: number, file: File): Promise<SessionImportResult> => {
    const fd = new FormData()
    fd.append('company_id', String(companyId))
    fd.append('file', file)
    const res = await fetch(`${BASE}/sessions/import`, {
      method: 'POST', credentials: 'same-origin', body: fd,
    })
    if (!res.ok) {
      let msg = 'Importul a eșuat'
      try { const j = await res.json(); msg = j.error || msg } catch { /* non-JSON */ }
      throw new Error(msg)
    }
    return res.json()
  },
```

- [ ] **Step 2: Typecheck**

Run: `cd jarvis/frontend && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0, no output.

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/api/foiParcurs.ts
git commit -m "feat(foi-parcurs): session-import api client (template url + upload)"
```

---

### Task 6: Frontend — Import modal + button on the Foi de Parcurs tab

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx`

**Interfaces:**
- Consumes: `getSessionImportTemplateUrl`, `importSessions`, `SessionImportResult` (Task 5); the tab's `companyId`.
- Produces: an "Importă sesiuni" button in `ContractsTab` header opening `SessionImportDialog`; on success it invalidates `['foi-contracts-all']` and `['fp-vehicles']` so the table refreshes.

- [ ] **Step 1: Add the type import**

```typescript
// change the existing foiParcurs import to include the result type
import { foiParcursApi, type StoredRouteSheet, type RouteSheetAlimentare, type RouteSheetEvent, type SessionImportResult } from '@/api/foiParcurs'
```

- [ ] **Step 2: Put the button + dialog into ContractsTab**

Replace the `ContractsTab` function with:

```tsx
function ContractsTab({ companyId }: { companyId: number }) {
  const [importOpen, setImportOpen] = useState(false)
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Foi de Parcurs</h3>
          <p className="text-sm text-muted-foreground">Sesiuni de rulare cumulate lunar, per mașină</p>
        </div>
        <Button variant="outline" onClick={() => setImportOpen(true)}>
          <Download className="mr-1.5 h-4 w-4" /> Importă sesiuni
        </Button>
      </div>
      <RouteSheetsTable companyId={companyId} />
      <SessionImportDialog companyId={companyId} open={importOpen} onOpenChange={setImportOpen} />
    </div>
  )
}
```

- [ ] **Step 3: Add the SessionImportDialog component (below ContractsTab)**

```tsx
function SessionImportDialog({ companyId, open, onOpenChange }: {
  companyId: number; open: boolean; onOpenChange: (o: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SessionImportResult | null>(null)

  useEffect(() => { if (open) { setFile(null); setError(''); setResult(null) } }, [open])

  const doImport = async () => {
    if (!file || !companyId) return
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await foiParcursApi.importSessions(companyId, file)
      setResult(r)
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
    } catch (e: any) {
      setError(e?.message || 'Import eșuat')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Importă sesiuni</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">
          Descarcă template-ul, completează sesiunile (o linie per cursă), apoi încarcă fișierul.
          VIN-urile inexistente creează mașina; duplicatele sunt ignorate.
        </p>
        <a href={foiParcursApi.getSessionImportTemplateUrl(companyId)} download>
          <Button variant="outline" size="sm" className="h-8" disabled={!companyId}>
            <Download className="mr-1.5 h-4 w-4" /> Descarcă template
          </Button>
        </a>
        <Input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {error && <div className="text-sm text-red-600">{error}</div>}
        {result && (
          <div className="rounded border p-3 text-sm space-y-1">
            <div className="flex flex-wrap gap-3">
              <Badge className="bg-green-600 text-white">Adăugate: {result.inserted}</Badge>
              <Badge variant="outline">Ignorate (dup): {result.skipped}</Badge>
              <Badge className="bg-blue-600 text-white">Mașini create: {result.cars_created}</Badge>
              {result.errors.length > 0 && <Badge variant="destructive">Erori: {result.errors.length}</Badge>}
            </div>
            {result.errors.length > 0 && (
              <ul className="mt-1 max-h-40 overflow-y-auto text-xs text-red-600">
                {result.errors.map((er, i) => <li key={i}>Linia {er.row}: {er.message}</li>)}
              </ul>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Închide</Button>
          <Button onClick={doImport} disabled={!file || busy}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
            Importă
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 4: Typecheck**

Run: `cd jarvis/frontend && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0.

- [ ] **Step 5: Manual verification**

Run the app (backend 5001 + vite 5173), open Foi de Parcurs → **Importă sesiuni** → Descarcă template → fill 2 rows (one existing VIN, one new) → upload → confirm the report shows inserted/cars_created and the route-sheets table refreshes with the new sessions.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): session-import modal (template download + upload + report)"
```

---

## Self-Review

**Spec coverage:**
- UX (button + modal, company, download, upload, report) → Task 6. ✅
- Template `.xlsx` (12 cols + Mașini sheet) → Task 2. ✅
- Endpoints (template GET, import POST) → Task 4. ✅
- Row→session mapping (source='import', derived route_type, contract_id) → Task 3. ✅
- Tenant scoping (selected company; foreign VIN rejected) → `row_error` (Task 1) + orchestration (Task 3). ✅
- Auto-create car on unknown VIN (needs Marcă/Model) → `row_error` + `_create_vehicle` (Tasks 1, 3). ✅
- Dedup skip via deterministic contract_id → Task 3. ✅
- Partial import with per-row errors → Task 3. ✅

**Placeholder scan:** none — all steps contain concrete code/commands.

**Type consistency:** `import_sessions(company_id, file_bytes, user_name)` and the report keys `{inserted, skipped, cars_created, errors}` are used identically in service (Task 3), route (Task 4), api client `SessionImportResult` (Task 5), and dialog (Task 6). `SESSION_COLUMNS` order matches the template builder and the parser. `getSessionImportTemplateUrl` / `importSessions` names match between Tasks 5 and 6.

**Note for implementer:** Tasks 1–4 are backend (pytest, no DB needed — repos are monkeypatched). Migration is unchanged (no new table/column; `source='import'` reuses the existing column). Deploy follows the standard dev → staging → (2-confirm) → main flow; no schema change to apply.
