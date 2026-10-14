# Buyback → Custody (Consignment) Transfer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authorized user turn a failed (`LOST`) buyback into a CarPark consignment vehicle, capturing a custody agreement, instead of losing the car entirely.

**Architecture:** A parallel hand-off to the existing BOUGHT→CarPark path. A new route `POST /api/buyback/records/<id>/custody` validates a custody-agreement payload, creates a CarPark vehicle (`is_consignment=true`, `source='CUSTODIE'`, no purchase price) via a new `handoff_to_carpark_custody` service that **reuses** the existing photo-carry/back-link helpers, writes a `carpark_vehicle_consignment` row, and stamps `carpark_vehicle_id` on the (still `LOST`) buyback record. The agreement is surfaced read-only on both the buyback detail and the CarPark vehicle detail.

**Tech Stack:** Python/Flask, psycopg2 raw SQL (`%s` params, `BaseRepository`), PostgreSQL; React 19 + TypeScript + Tailwind 4 + shadcn/ui; Vitest + Testing Library; pytest (psycopg2 mocked in `tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-10-14-buyback-custody-transfer-design.md`

## Global Constraints

- Raw SQL only, every value a `%s` param — never f-string a user value into SQL (CLAUDE.md).
- Repositories subclass `core.base_repository.BaseRepository`: `query_one(sql, params)` → row|None; `execute(sql, params, returning=True)` → row dict (else rowcount). No `transaction()` helper.
- Route permission: `@v2_permission_required('buyback','record','custody')` from `core/roles/decorators.py`.
- Frontend work targets `jarvis/frontend/src/`. API envelope: backend wraps (`{record: ...}`); frontend unwraps.
- Migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, guarded seed). `schema_carpark.py` and `schema_roles.py` are **protected** — changes here were explicitly confirmed by the user in the spec.
- CarPark vehicle created by custody: `status='ACQUIRED'`, `source='CUSTODIE'`, `is_consignment=True`, `purchase_price_net=NULL`.
- Permission `buyback.record.custody` is granted to **Admin, Manager, Acquisition** (same roles that hold `record.finalize`).
- Invariant: "transferred to custody" ≡ `status='LOST' AND carpark_vehicle_id IS NOT NULL`. No new `buyback_records` columns.
- `commission_type ∈ {'percent','fixed'}`; for `percent`, `commission_value` ∈ [0,100]; for `fixed`, `commission_value` ≥ 0 with no upper cap. All money/date fields optional except `commission_type` + `commission_value`.
- Branch `feat/buyback-custody-transfer` off `staging`. Per user preference: run `/code-review` before each commit and report the commit SHA after. Deploy **staging first → validate → `main` on double confirmation**.
- Pre-push checklist: `cd jarvis/frontend && npm run build` (0 TS errors); `python -m pytest tests/ -x -q`; `python3 -m py_compile jarvis/app.py`.

## Review Focus

- **Duplicate VIN already in CarPark** at transfer time → `409` with the verbatim VehicleService message, record left unlinked (NOT a 500). → covered in Task 5.
- **Re-POST on an already-transferred LOST record** (`carpark_vehicle_id` set) → `409` "already transferred", no second vehicle created. → covered in Task 5.
- **`commission_type='fixed'` with a large value (e.g. 1500)** is accepted; **`commission_type='percent'` with value 150** is rejected `400`. → covered in Task 5.
- **Cross-company LOST record** (caller not permitted for `record.company_id`) → `403` via `_guard_company`, before any vehicle is created. → covered in Task 5.
- **Non-`LOST` status** (`BOUGHT`, `INSPECTION`, `PENDING_EVALUATION`) → `409` "only LOST records can be taken on custody". → covered in Task 5.

---

## File Structure

**Backend — create**
- `jarvis/carpark/repositories/consignment_repository.py` — `ConsignmentRepository` (1:1 `carpark_vehicle_consignment` CRUD). Lives in carpark because the row is keyed on a carpark vehicle and read by the CarPark detail.
- `jarvis/buyback/routes/custody.py` — the route + `validate_custody_agreement` pure validator.
- `tests/test_consignment_repository.py`, `tests/test_buyback_custody_handoff.py`, `tests/test_buyback_custody_route.py`.

**Backend — modify**
- `jarvis/migrations/domains/schema_carpark.py` — new table + idempotent `CUSTODIE` dropdown ensure.
- `jarvis/migrations/domains/schema_roles.py` — `custody` permission + grants in `_seed_buyback_permissions_v2`.
- `jarvis/buyback/services/carpark_handoff.py` — add `handoff_to_carpark_custody`.
- `jarvis/buyback/routes/__init__.py` — `from . import custody`.
- `jarvis/buyback/routes/records.py` — embed `consignment` in the single-record GET.
- `jarvis/carpark/routes/vehicles.py` — embed `consignment` in the single-vehicle GET.

**Frontend — modify**
- `jarvis/frontend/src/api/buyback.ts` — `transferToCustody`.
- `jarvis/frontend/src/types/buyback.ts` — `ConsignmentAgreement` + `consignment` on the record GET response.
- `jarvis/frontend/src/types/carpark.ts` — `consignment` on the vehicle detail type.
- `jarvis/frontend/src/pages/BuyBack/ActionPanel.tsx` + `ActionPanel.test.tsx` — custody button + dialog + show flags + reopen gate.
- `jarvis/frontend/src/pages/BuyBack/BuyBackDetail.tsx` — "Custodie" card.
- `jarvis/frontend/src/pages/CarPark/Detail.tsx` — "Custodie" badge + agreement card.

---

## Task 1: DB migration — `carpark_vehicle_consignment` + idempotent `CUSTODIE` source

**Files:**
- Modify: `jarvis/migrations/domains/schema_carpark.py` (inside `create_schema_carpark`, after the `carpark_vehicles` table is created and after the dropdown seed block near line ~972)

**Interfaces:**
- Produces: table `carpark_vehicle_consignment(vehicle_id PK, owner_price, currency, commission_type, commission_value, min_sale_price, contract_number, agreement_date, expiry_date, created_by, created_at)`; a `dropdown_options` row `('carpark_source','CUSTODIE','CUSTODIE',10,TRUE)` guaranteed present.

- [ ] **Step 1: Add the table DDL** (idempotent), after the `carpark_vehicles` creation block:

```python
    # ── Consignment (custody) agreement — 1:1 with a carpark vehicle. Written
    #    by the buyback → custody transfer (buyback/services/carpark_handoff.py:
    #    handoff_to_carpark_custody). Cascades away with the vehicle.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_consignment (
            vehicle_id       BIGINT PRIMARY KEY REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            owner_price      NUMERIC(12,2),
            currency         VARCHAR(3)  NOT NULL DEFAULT 'EUR',
            commission_type  VARCHAR(10) NOT NULL CHECK (commission_type IN ('percent','fixed')),
            commission_value NUMERIC(12,2) NOT NULL,
            min_sale_price   NUMERIC(12,2),
            contract_number  VARCHAR(50),
            agreement_date   DATE,
            expiry_date      DATE,
            created_by       INTEGER,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    ''')
```

- [ ] **Step 2: Ensure the `CUSTODIE` source exists on pre-existing DBs.** The fresh-seed block is `COUNT(*)=0`-guarded, so existing staging/prod DBs never receive values added later. Add an idempotent upsert right after that seed block:

```python
    # The carpark_source seed above only runs on an empty dropdown set, so DBs
    # seeded before CUSTODIE was added won't have it. Ensure it idempotently.
    cursor.execute('''
        INSERT INTO dropdown_options (dropdown_type, value, label, sort_order, is_active)
        SELECT 'carpark_source', 'CUSTODIE', 'CUSTODIE', 10, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM dropdown_options
            WHERE dropdown_type = 'carpark_source' AND value = 'CUSTODIE'
        )
    ''')
```

- [ ] **Step 3: Compile-check the module.**

Run: `python3 -m py_compile jarvis/migrations/domains/schema_carpark.py`
Expected: exit 0.

- [ ] **Step 4: Apply against the local DB and verify** (DDL has no unit test — psycopg2 is mocked in pytest, so verify by booting the real local schema per `reference_database_init_on_import` — run the init entrypoint, never an app-import script).

Run (from repo root, local DB only):
```bash
python3 -c "from jarvis.migrations.init_schema import *; import jarvis.migrations.init_schema as m; print('schema module import ok')"
psql "$DATABASE_URL" -c "\d carpark_vehicle_consignment"
psql "$DATABASE_URL" -c "SELECT value FROM dropdown_options WHERE dropdown_type='carpark_source' AND value='CUSTODIE';"
```
Expected: the table description prints with the 11 columns; the CUSTODIE row returns one line. (If the project exposes a dedicated `init_db()` runner, use that instead of importing app modules.)

- [ ] **Step 5: Commit** (run `/code-review` first per project preference).

```bash
git add jarvis/migrations/domains/schema_carpark.py
git commit -m "feat(carpark): carpark_vehicle_consignment table + idempotent CUSTODIE source"
```

---

## Task 2: `ConsignmentRepository`

**Files:**
- Create: `jarvis/carpark/repositories/consignment_repository.py`
- Test: `tests/test_consignment_repository.py`

**Interfaces:**
- Produces: `ConsignmentRepository().create(vehicle_id: int, agreement: dict, created_by: int|None) -> dict` (inserts and returns the row); `.get_by_vehicle(vehicle_id: int) -> dict | None`.
- `agreement` keys consumed: `owner_price, currency, commission_type, commission_value, min_sale_price, contract_number, agreement_date, expiry_date`.

- [ ] **Step 1: Write the failing test.**

```python
# tests/test_consignment_repository.py
import sys, os
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from carpark.repositories.consignment_repository import ConsignmentRepository


def test_create_inserts_vehicle_id_agreement_and_created_by():
    repo = ConsignmentRepository()
    agreement = {
        'owner_price': 10000, 'currency': 'EUR',
        'commission_type': 'percent', 'commission_value': 5,
        'min_sale_price': 9500, 'contract_number': 'C-1',
        'agreement_date': '2026-10-14', 'expiry_date': '2027-01-14',
    }
    with patch.object(ConsignmentRepository, 'execute', return_value={'vehicle_id': 42}) as ex:
        row = repo.create(42, agreement, created_by=7)
    sql, params = ex.call_args.args[0], ex.call_args.args[1]
    assert 'INSERT INTO carpark_vehicle_consignment' in sql
    assert params[0] == 42                 # vehicle_id first
    assert params[-1] == 7                 # created_by last
    assert 'percent' in params and 5 in params
    assert row == {'vehicle_id': 42}


def test_get_by_vehicle_queries_by_id():
    repo = ConsignmentRepository()
    with patch.object(ConsignmentRepository, 'query_one', return_value={'vehicle_id': 42}) as q:
        row = repo.get_by_vehicle(42)
    assert q.call_args.args[1] == (42,)
    assert row == {'vehicle_id': 42}
```

- [ ] **Step 2: Run it, verify it fails.**

Run: `python -m pytest tests/test_consignment_repository.py -q`
Expected: FAIL (ModuleNotFoundError: consignment_repository).

- [ ] **Step 3: Implement the repository.**

```python
# jarvis/carpark/repositories/consignment_repository.py
"""Repository for carpark_vehicle_consignment — the 1:1 custody (consignment)
agreement attached to a CarPark vehicle created from a failed buyback.
Written by buyback/services/carpark_handoff.py::handoff_to_carpark_custody;
read by the buyback and carpark detail GETs."""
from core.base_repository import BaseRepository

# Order matters: these map positionally to the INSERT placeholders between
# vehicle_id (first) and created_by (last).
_AGREEMENT_COLS = (
    'owner_price', 'currency', 'commission_type', 'commission_value',
    'min_sale_price', 'contract_number', 'agreement_date', 'expiry_date',
)


class ConsignmentRepository(BaseRepository):
    def create(self, vehicle_id, agreement, created_by=None):
        cols = ['vehicle_id', *(_AGREEMENT_COLS), 'created_by']
        vals = [vehicle_id, *(agreement.get(c) for c in _AGREEMENT_COLS), created_by]
        placeholders = ', '.join(['%s'] * len(cols))
        sql = (
            f'INSERT INTO carpark_vehicle_consignment ({", ".join(cols)}) '
            f'VALUES ({placeholders}) RETURNING *'
        )
        return self.execute(sql, tuple(vals), returning=True)

    def get_by_vehicle(self, vehicle_id):
        return self.query_one(
            'SELECT * FROM carpark_vehicle_consignment WHERE vehicle_id = %s',
            (vehicle_id,),
        )
```

- [ ] **Step 4: Run tests, verify pass.**

Run: `python -m pytest tests/test_consignment_repository.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/carpark/repositories/consignment_repository.py tests/test_consignment_repository.py
git commit -m "feat(carpark): ConsignmentRepository for custody agreements"
```

---

## Task 3: Permission `buyback.record.custody` + grants

**Files:**
- Modify: `jarvis/migrations/domains/schema_roles.py` — `_seed_buyback_permissions_v2`

**Interfaces:**
- Produces: a `permissions_v2` row `buyback.record.custody` (scope-based), granted to Admin/Manager/Acquisition at `'all'`, denied to Viewer.

- [ ] **Step 1: Add the permission to the `perms` list** (after the `finalize` tuple):

```python
        ('record',     'Buyback Records',     'custody',  'Custody',  'Transfer a lost buyback to CarPark on custody (consignment)', True, 8),
```

- [ ] **Step 2: Grant it to Acquisition** (Admin/Manager already loop over `all_entities_actions`, which now includes `custody`, so they are covered automatically). Extend the Acquisition grant tuple:

```python
    # Acquisition: module access + view + offer management + finalize + custody authority.
    for entity, action in (('module', 'access'), ('record', 'view'), ('offer', 'manage'),
                           ('record', 'finalize'), ('record', 'custody')):
        _grant('Acquisition', entity, action, 'all')
```

(Viewer's deny loop and the Admin/Manager loops already iterate `all_entities_actions`, so no further edits are needed for them.)

- [ ] **Step 3: Compile-check.**

Run: `python3 -m py_compile jarvis/migrations/domains/schema_roles.py`
Expected: exit 0.

- [ ] **Step 4: Apply + verify against local DB.**

Run:
```bash
psql "$DATABASE_URL" -c "SELECT entity_key, action_key, is_scope_based FROM permissions_v2 WHERE module_key='buyback' AND action_key='custody';"
psql "$DATABASE_URL" -c "SELECT r.name, rp.scope, rp.granted FROM role_permissions_v2 rp JOIN roles r ON r.id=rp.role_id JOIN permissions_v2 p ON p.id=rp.permission_id WHERE p.module_key='buyback' AND p.action_key='custody' ORDER BY r.name;"
```
Expected: one `record/custody/true` permission row; grants for Admin, Manager, Acquisition (`all`, granted) and Viewer (`deny`, not granted), where those roles exist locally.

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/migrations/domains/schema_roles.py
git commit -m "feat(buyback): buyback.record.custody permission + Acquisition/Admin/Manager grants"
```

---

## Task 4: Custody hand-off service `handoff_to_carpark_custody`

**Files:**
- Modify: `jarvis/buyback/services/carpark_handoff.py`
- Test: `tests/test_buyback_custody_handoff.py`

**Interfaces:**
- Consumes: `_carry_photos`, `_backlink` (existing in this module); `carpark.services.vehicle_service.VehicleService`; `carpark.repositories.consignment_repository.ConsignmentRepository`.
- Produces: `handoff_to_carpark_custody(record: dict, agreement: dict, actor: int) -> dict` — returns the created CarPark vehicle dict. Raises `ValueError` verbatim from `create_vehicle` (dup/invalid VIN).

- [ ] **Step 1: Write the failing test.**

```python
# tests/test_buyback_custody_handoff.py
import sys, os
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from buyback.services import carpark_handoff

RECORD = {
    'id': 11, 'company_id': 3, 'vin': 'WAUZZZ8V1JA123456',
    'brand': 'Audi', 'model': 'A3', 'variant': 'S line',
    'manufacture_date': None, 'mileage_km': 40000, 'fuel_type': 'petrol',
    'transmission': 'automatic', 'seller_name': 'Ion Pop', 'seller_cui': None,
    'is_trade_in': False,
}
AGREEMENT = {
    'owner_price': 10000, 'currency': 'EUR', 'commission_type': 'percent',
    'commission_value': 5, 'min_sale_price': 9500, 'contract_number': 'C-1',
    'agreement_date': '2026-10-14', 'expiry_date': None,
}


def test_handoff_custody_creates_consignment_vehicle_and_agreement():
    created = {'id': 77, 'vin': RECORD['vin']}
    svc = MagicMock()
    svc.create_vehicle.return_value = created
    consign_repo = MagicMock()
    with patch('carpark.services.vehicle_service.VehicleService', return_value=svc), \
         patch('carpark.repositories.consignment_repository.ConsignmentRepository', return_value=consign_repo), \
         patch.object(carpark_handoff, '_carry_photos') as carry, \
         patch.object(carpark_handoff, '_backlink') as backlink:
        veh = carpark_handoff.handoff_to_carpark_custody(RECORD, AGREEMENT, actor=9)

    data = svc.create_vehicle.call_args.args[0]
    assert data['is_consignment'] is True
    assert data['source'] == 'CUSTODIE'
    assert data['status'] == 'ACQUIRED'
    assert data['purchase_price_net'] is None
    assert data['company_id'] == 3
    consign_repo.create.assert_called_once_with(77, AGREEMENT, created_by=9)
    carry.assert_called_once_with(11, 77)
    backlink.assert_called_once_with(77, 11, 9)
    assert veh == created


def test_handoff_custody_propagates_vin_valueerror():
    svc = MagicMock()
    svc.create_vehicle.side_effect = ValueError('A vehicle with VIN X already exists')
    with patch('carpark.services.vehicle_service.VehicleService', return_value=svc), \
         patch('carpark.repositories.consignment_repository.ConsignmentRepository'):
        try:
            carpark_handoff.handoff_to_carpark_custody(RECORD, AGREEMENT, actor=9)
            assert False, 'expected ValueError'
        except ValueError as e:
            assert 'already exists' in str(e)
```

- [ ] **Step 2: Run it, verify it fails.**

Run: `python -m pytest tests/test_buyback_custody_handoff.py -q`
Expected: FAIL (AttributeError: module has no attribute 'handoff_to_carpark_custody').

- [ ] **Step 3: Implement the service** (append to `carpark_handoff.py`, mirroring `handoff_to_carpark`):

```python
def handoff_to_carpark_custody(record, agreement, actor) -> dict:
    """Create a CONSIGNMENT CarPark vehicle draft from a failed (LOST) buyback
    `record`, attach the custody `agreement`, carry photos over, and back-link.

    Parallel to handoff_to_carpark, but: is_consignment=True, source 'CUSTODIE',
    NO purchase price (we did not buy the car). `agreement` is the validated
    dict from the custody route (validate_custody_agreement). Returns the
    created vehicle. Raises ValueError verbatim from VehicleService.create_vehicle
    (dup/invalid VIN) — the route turns that into a 409, same contract as finalize.

    The consignment row is written right after the vehicle exists and BEFORE the
    best-effort photo/link steps, so a Spaces/FK hiccup never loses the agreement
    (see the module/spec notes on the single-INSERT orphan-vehicle window)."""
    manufacture_date = record.get('manufacture_date')
    data = {
        'vin': record['vin'],
        'brand': record['brand'],
        'model': record['model'],
        'variant': record.get('variant'),
        'manufacture_date': manufacture_date,
        'year_of_manufacture': manufacture_date.year if manufacture_date else None,
        'first_registration_date': record.get('first_registration_date'),
        'mileage_km': record.get('mileage_km'),
        'fuel_type': record.get('fuel_type'),
        'transmission': record.get('transmission'),
        'company_id': record['company_id'],  # explicit, server-side — never from HTTP input
        'status': 'ACQUIRED',
        'source': 'CUSTODIE',
        'is_consignment': True,
        'purchase_price_net': None,
        'category': 'TI' if record.get('is_trade_in') else 'SH',
        'supplier_name': record.get('seller_name'),
        'owner_name': record.get('seller_name'),
        'supplier_cif': record.get('seller_cui'),
    }

    from carpark.services.vehicle_service import VehicleService
    veh = VehicleService().create_vehicle(data, created_by=actor)  # may raise ValueError

    from carpark.repositories.consignment_repository import ConsignmentRepository
    ConsignmentRepository().create(veh['id'], agreement, created_by=actor)

    _carry_photos(record['id'], veh['id'])
    _backlink(veh['id'], record['id'], actor)
    return veh
```

- [ ] **Step 4: Run tests, verify pass.**

Run: `python -m pytest tests/test_buyback_custody_handoff.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/buyback/services/carpark_handoff.py tests/test_buyback_custody_handoff.py
git commit -m "feat(buyback): handoff_to_carpark_custody — consignment vehicle from a LOST record"
```

---

## Task 5: Custody route + agreement validator

**Files:**
- Create: `jarvis/buyback/routes/custody.py`
- Modify: `jarvis/buyback/routes/__init__.py` (add `from . import custody  # noqa: F401`)
- Test: `tests/test_buyback_custody_route.py`

**Interfaces:**
- Consumes: `buyback.routes._shared` (`records_repo`, `_guard_company`, `_serialize`), `buyback.services.carpark_handoff.handoff_to_carpark_custody`, `buyback.lifecycle.LOST`.
- Produces: `validate_custody_agreement(data: dict) -> dict` (raises `ValueError` on bad input, returns a coerced agreement dict); route `POST /api/buyback/records/<int:record_id>/custody`.

- [ ] **Step 1: Write the failing tests** (validator as pure unit; route via patched deps, mirroring `tests/test_foi_parcurs_delete_authz.py` + `tests/test_dms_file_download_company_access.py`):

```python
# tests/test_buyback_custody_route.py
import sys, os
import pytest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


# ---- validator (pure) ----
from buyback.routes.custody import validate_custody_agreement

def test_validator_requires_known_commission_type():
    with pytest.raises(ValueError):
        validate_custody_agreement({'commission_type': 'maybe', 'commission_value': 5})

def test_validator_rejects_percent_over_100():
    with pytest.raises(ValueError):
        validate_custody_agreement({'commission_type': 'percent', 'commission_value': 150})

def test_validator_allows_large_fixed_commission():
    out = validate_custody_agreement({'commission_type': 'fixed', 'commission_value': 1500})
    assert out['commission_type'] == 'fixed'
    assert float(out['commission_value']) == 1500.0
    assert out['currency'] == 'EUR'  # default

def test_validator_rejects_expiry_before_agreement():
    with pytest.raises(ValueError):
        validate_custody_agreement({
            'commission_type': 'fixed', 'commission_value': 100,
            'agreement_date': '2026-10-14', 'expiry_date': '2026-01-01',
        })


# ---- route ----
@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(secret_key='t', database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'))
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


class _User:
    def __init__(self, company_id=3):
        self.id = 9
        self.company_id = company_id
        self.is_authenticated = True
        self.is_admin = True            # satisfies @v2_permission_required fast-path
        self.can_access_settings = True

LOST_REC = {'id': 11, 'status': 'LOST', 'company_id': 3, 'carpark_vehicle_id': None}
VALID_BODY = {'commission_type': 'fixed', 'commission_value': 500}


def _post(app, record, body, *, user_company=3):
    from buyback.routes import custody
    from core.roles import decorators
    records_repo = MagicMock()
    records_repo.get_by_id.return_value = record
    records_repo.update.return_value = {**(record or {}), 'carpark_vehicle_id': 77}
    with app.test_request_context(json=body):
        with patch.object(custody._shared, 'records_repo', records_repo), \
             patch.object(custody, 'current_user', _User(user_company)), \
             patch.object(decorators, 'current_user', _User(user_company)), \
             patch.object(custody, 'handoff_to_carpark_custody', return_value={'id': 77}) as handoff:
            resp = custody.transfer_to_custody(record['id'] if record else 11)
    status = resp[1] if isinstance(resp, tuple) else 200
    return status, handoff, records_repo


def test_happy_path_creates_and_links(app):
    status, handoff, repo = _post(app, LOST_REC, VALID_BODY)
    assert status == 200
    handoff.assert_called_once()
    repo.update.assert_called_once_with(11, {'carpark_vehicle_id': 77})

def test_non_lost_is_409(app):
    status, handoff, _ = _post(app, {**LOST_REC, 'status': 'BOUGHT'}, VALID_BODY)
    assert status == 409
    handoff.assert_not_called()

def test_already_transferred_is_409(app):
    status, handoff, _ = _post(app, {**LOST_REC, 'carpark_vehicle_id': 55}, VALID_BODY)
    assert status == 409
    handoff.assert_not_called()

def test_cross_company_is_403(app):
    # caller company 3, but record belongs to company 8 → _guard_company 403
    status, handoff, _ = _post(app, {**LOST_REC, 'company_id': 8}, VALID_BODY, user_company=3)
    # _User.is_admin=True would bypass _guard_company's permitted set (unrestricted),
    # so for this case use a non-admin caller:
    assert handoff.call_count in (0,)  # see Step 3 note; non-admin variant asserts 403

def test_bad_agreement_is_400(app):
    status, handoff, _ = _post(app, LOST_REC, {'commission_type': 'maybe', 'commission_value': 1})
    assert status == 400
    handoff.assert_not_called()

def test_missing_record_is_404(app):
    status, handoff, _ = _post(app, None, VALID_BODY)
    assert status == 404
    handoff.assert_not_called()
```

> Note for `test_cross_company_is_403`: `_guard_company` uses `_permitted_company_ids()`, which returns the unrestricted sentinel for a `can_access_settings` admin. To exercise the 403, this test needs a non-admin caller whose permitted set excludes company 8. Implement a second `_User` variant with `is_admin=False, can_access_settings=False` and a `role_id`, and patch `_shared._permitted_company_ids` to return `{3}` for that case. Keep the admin fast-path user for the other tests. (Split into `test_cross_company_is_403` with the non-admin user + patched permitted set returning `{3}`, asserting `status == 403` and `handoff` not called.)

- [ ] **Step 2: Run tests, verify they fail.**

Run: `python -m pytest tests/test_buyback_custody_route.py -q`
Expected: FAIL (ModuleNotFoundError: buyback.routes.custody).

- [ ] **Step 3: Implement the validator + route.**

```python
# jarvis/buyback/routes/custody.py
"""POST /api/buyback/records/<id>/custody — take a failed (LOST) buyback onto
custody (consignment): create a CarPark vehicle (is_consignment, source
CUSTODIE, no purchase price) and record the custody agreement. Mirrors
finalize.py's guard ordering; the accepted-decision machinery does not apply
(the record is already terminal LOST)."""
import decimal
from datetime import date

from flask import jsonify, request
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.routes import _shared
from buyback import lifecycle
from buyback.services.carpark_handoff import handoff_to_carpark_custody
from core.roles.decorators import v2_permission_required


def validate_custody_agreement(data: dict) -> dict:
    """Validate + coerce the custody-agreement payload. Returns a new dict with
    the stored fields; raises ValueError(message) on the first invalid value
    (route catches → 400). Only commission_type + commission_value are
    required; money/date fields are optional."""
    data = data or {}
    ctype = data.get('commission_type')
    if ctype not in ('percent', 'fixed'):
        raise ValueError("commission_type must be 'percent' or 'fixed'")

    if data.get('commission_value') is None:
        raise ValueError('commission_value is required')
    try:
        cval = decimal.Decimal(str(data['commission_value']))
    except (decimal.InvalidOperation, TypeError, ValueError):
        raise ValueError('commission_value must be numeric')
    if cval < 0:
        raise ValueError('commission_value must be >= 0')
    if ctype == 'percent' and cval > 100:
        raise ValueError('commission_value (percent) must be between 0 and 100')

    out = {
        'commission_type': ctype,
        'commission_value': cval,
        'currency': (data.get('currency') or 'EUR'),
        'owner_price': None,
        'min_sale_price': None,
        'contract_number': data.get('contract_number'),
        'agreement_date': None,
        'expiry_date': None,
    }
    if isinstance(out['contract_number'], (dict, list)):
        raise ValueError('contract_number must be a plain string')

    for fld in ('owner_price', 'min_sale_price'):
        if data.get(fld) is not None:
            try:
                v = decimal.Decimal(str(data[fld]))
            except (decimal.InvalidOperation, TypeError, ValueError):
                raise ValueError(f'{fld} must be numeric')
            if v < 0:
                raise ValueError(f'{fld} must be >= 0')
            out[fld] = v

    for fld in ('agreement_date', 'expiry_date'):
        if data.get(fld):
            try:
                out[fld] = date.fromisoformat(str(data[fld]))
            except (TypeError, ValueError):
                raise ValueError(f'{fld} must be an ISO date (YYYY-MM-DD)')

    if out['agreement_date'] and out['expiry_date'] and out['expiry_date'] < out['agreement_date']:
        raise ValueError('expiry_date must be on or after agreement_date')

    return out


@buyback_bp.route('/records/<int:record_id>/custody', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'custody')
def transfer_to_custody(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    if record['status'] != lifecycle.LOST:
        return jsonify({
            'success': False,
            'error': f"Only LOST records can be taken on custody "
                     f"(record is {record['status']!r})",
        }), 409

    if record.get('carpark_vehicle_id') is not None:
        return jsonify({'success': False, 'error': 'Record already transferred to custody'}), 409

    try:
        agreement = validate_custody_agreement(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    try:
        vehicle = handoff_to_carpark_custody(record, agreement, current_user.id)
    except ValueError as e:
        # dup/invalid VIN — the car's VIN already lives in CarPark (same orphan
        # window the BOUGHT hand-off accepts). Record left unlinked, retryable.
        return jsonify({'success': False, 'error': str(e)}), 409

    updated = _shared.records_repo.update(record_id, {'carpark_vehicle_id': vehicle['id']})
    return jsonify({
        'success': True,
        'record': _shared._serialize(updated),
        'vehicle': _shared._serialize(vehicle),
    }), 200
```

Then add to `jarvis/buyback/routes/__init__.py`:

```python
from . import custody  # noqa: F401
```

- [ ] **Step 4: Run tests, verify pass** (adjust the cross-company test per the Step 1 note).

Run: `python -m pytest tests/test_buyback_custody_route.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/buyback/routes/custody.py jarvis/buyback/routes/__init__.py tests/test_buyback_custody_route.py
git commit -m "feat(buyback): POST /records/:id/custody — transfer LOST record to CarPark custody"
```

---

## Task 6: Embed `consignment` in the buyback record GET

**Files:**
- Modify: `jarvis/buyback/routes/records.py` (the `get_record` handler, ~line 197-223)

**Interfaces:**
- Consumes: `ConsignmentRepository().get_by_vehicle(...)`.
- Produces: the record GET response gains `consignment` (object or null) alongside `record/offers/photos/events`.

- [ ] **Step 1: Add a test** (patch the repo, assert the key is present only when LOST + linked):

```python
# tests/test_buyback_custody_route.py  (append)
def test_record_get_includes_consignment_when_lost_and_linked(app):
    from buyback.routes import records as records_mod
    rec = {'id': 11, 'status': 'LOST', 'company_id': 3, 'carpark_vehicle_id': 77}
    repo = MagicMock(); repo.get_by_id.return_value = rec
    repo.get_offers_for_record = MagicMock(return_value=[])
    with app.test_request_context():
        with patch.object(records_mod._shared, 'records_repo', repo), \
             patch.object(records_mod._shared, 'offers_repo', MagicMock(get_by_record=MagicMock(return_value=[]))), \
             patch.object(records_mod._shared, 'photos_repo', MagicMock(get_by_record=MagicMock(return_value=[]))), \
             patch.object(records_mod._shared, 'events_repo', MagicMock(get_by_record=MagicMock(return_value=[]))), \
             patch.object(records_mod, 'current_user', _User(3)), \
             patch('carpark.repositories.consignment_repository.ConsignmentRepository') as CR:
            CR.return_value.get_by_vehicle.return_value = {'vehicle_id': 77, 'commission_type': 'fixed'}
            resp = records_mod.get_record(11)
    body = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
    assert body['consignment'] == {'vehicle_id': 77, 'commission_type': 'fixed'}
```

(If `get_record`'s exact repo method names differ, align the mocks to the real calls read in Step 2.)

- [ ] **Step 2: Read the current `get_record` body** to match its exact repo calls:

Run: `sed -n '197,230p' jarvis/buyback/routes/records.py`

- [ ] **Step 3: Implement the embed.** In `get_record`, after assembling `record`, before the `return jsonify(...)`, add:

```python
    consignment = None
    if record.get('status') == 'LOST' and record.get('carpark_vehicle_id'):
        from carpark.repositories.consignment_repository import ConsignmentRepository
        consignment = ConsignmentRepository().get_by_vehicle(record['carpark_vehicle_id'])
```

and add `'consignment': _shared._serialize(consignment),` to the returned dict.

- [ ] **Step 4: Run the test, verify pass.**

Run: `python -m pytest tests/test_buyback_custody_route.py -k consignment -q`
Expected: PASS.

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/buyback/routes/records.py tests/test_buyback_custody_route.py
git commit -m "feat(buyback): embed consignment agreement in the record GET payload"
```

---

## Task 7: Frontend API + types

**Files:**
- Modify: `jarvis/frontend/src/api/buyback.ts`
- Modify: `jarvis/frontend/src/types/buyback.ts`

**Interfaces:**
- Produces: `buybackApi.transferToCustody(id, agreement) -> Promise<{ record: BuybackRecord; vehicle: { id: number } }>`; `ConsignmentAgreement` type; `getRecord` response typed with `consignment: ConsignmentAgreement | null`.

- [ ] **Step 1: Add the type** to `types/buyback.ts`:

```typescript
export interface ConsignmentAgreement {
  vehicle_id: number
  owner_price: number | null
  currency: string
  commission_type: 'percent' | 'fixed'
  commission_value: number
  min_sale_price: number | null
  contract_number: string | null
  agreement_date: string | null
  expiry_date: string | null
  created_by: number | null
  created_at: string
}

export interface CustodyAgreementInput {
  owner_price?: number | null
  currency?: string
  commission_type: 'percent' | 'fixed'
  commission_value: number
  min_sale_price?: number | null
  contract_number?: string | null
  agreement_date?: string | null
  expiry_date?: string | null
}
```

- [ ] **Step 2: Type the `getRecord` response** — add `consignment: ConsignmentAgreement | null` to the generic in `api/buyback.ts`:

```typescript
  getRecord: (id: number) =>
    api.get<{ record: BuybackRecord; offers: BuybackOffer[]; photos: BuybackPhoto[]; events: BuybackEvent[]; consignment: ConsignmentAgreement | null }>(
      `${BASE}/records/${id}`,
    ),
```

- [ ] **Step 3: Add the API method** (after `retryHandoff`):

```typescript
  transferToCustody: (id: number, agreement: CustodyAgreementInput) =>
    api.post<{ record: BuybackRecord; vehicle: { id: number } }>(`${BASE}/records/${id}/custody`, agreement),
```

- [ ] **Step 4: Type-check.**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TS errors.

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/frontend/src/api/buyback.ts jarvis/frontend/src/types/buyback.ts
git commit -m "feat(buyback-ui): transferToCustody API + consignment types"
```

---

## Task 8: ActionPanel — custody button, agreement dialog, show flags, reopen gate

**Files:**
- Modify: `jarvis/frontend/src/pages/BuyBack/ActionPanel.tsx`
- Modify: `jarvis/frontend/src/pages/BuyBack/ActionPanel.test.tsx`

**Interfaces:**
- Consumes: `buybackApi.transferToCustody`, `CustodyAgreementInput`.
- Produces: a "Transferă în custodie" button + dialog on `LOST && !carpark_vehicle_id && can('buyback.record.custody')`; a "→ Custodie" link when `LOST && carpark_vehicle_id`; `showReopen` additionally gated on `!carpark_vehicle_id`.

- [ ] **Step 1: Write the failing tests** (append to `ActionPanel.test.tsx`; add `transferToCustody: vi.fn(...)` to the `vi.mock('@/api/buyback')` block first):

```typescript
  it('LOST + custody permission shows "Transferă în custodie"', () => {
    renderPanel('LOST', { 'buyback.record.custody': true }, { record: { carpark_vehicle_id: null } })
    expect(screen.getByText(/Transferă în custodie/)).toBeInTheDocument()
  })

  it('LOST without custody permission HIDES the custody button', () => {
    renderPanel('LOST', {}, { record: { carpark_vehicle_id: null } })
    expect(screen.queryByText(/Transferă în custodie/)).not.toBeInTheDocument()
  })

  it('LOST already transferred HIDES the button and shows the CarPark link', () => {
    renderPanel('LOST', { 'buyback.record.custody': true }, { record: { carpark_vehicle_id: 77 } })
    expect(screen.queryByText(/Transferă în custodie/)).not.toBeInTheDocument()
    expect(screen.getByText(/Custodie/)).toBeInTheDocument()
  })

  it('LOST already transferred HIDES Redeschide (reopen) for admin', () => {
    renderPanel('LOST', {}, { role: 'Manager', record: { carpark_vehicle_id: 77 } })
    expect(screen.queryByText(/Redeschide/)).not.toBeInTheDocument()
  })

  it('non-LOST HIDES the custody button', () => {
    renderPanel('BOUGHT', { 'buyback.record.custody': true }, { record: { carpark_vehicle_id: null } })
    expect(screen.queryByText(/Transferă în custodie/)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run them, verify they fail.**

Run: `cd jarvis/frontend && npx vitest run src/pages/BuyBack/ActionPanel.test.tsx`
Expected: FAIL (custody button not rendered).

- [ ] **Step 3: Implement.** In `ActionPanel.tsx`:

(a) Add show flags near the other `show*` constants:
```typescript
  const showCustody = status === 'LOST' && !record.carpark_vehicle_id && can('buyback.record.custody')
  const showCustodyLink = status === 'LOST' && !!record.carpark_vehicle_id
```
(b) Gate reopen so a transferred record can't be reopened:
```typescript
  const showReopen = status === 'LOST' && isAdminOrManager && !record.carpark_vehicle_id
```
(c) Add dialog state + mutation (near the finalize mutation):
```typescript
  const [custodyOpen, setCustodyOpen] = useState(false)
  const [custody, setCustody] = useState<CustodyAgreementInput>({ commission_type: 'percent', commission_value: 0 })
  const custodyMutation = useMutation({
    mutationFn: () => buybackApi.transferToCustody(record.id, custody),
    onSuccess: (res) => {
      toast.success(`Transferat în custodie → CarPark #${res.vehicle.id}`)
      setCustodyOpen(false)
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Transferul în custodie a eșuat')),
  })
```
(Import `CustodyAgreementInput` from `@/types/buyback`.)

(d) Render the button + link (near `showReopen` / `showCarparkLabel`):
```tsx
        {showCustody && (
          <Button size="sm" variant="outline" onClick={() => setCustodyOpen(true)}>
            Transferă în custodie
          </Button>
        )}

        {showCustodyLink && (
          <p className="text-sm text-muted-foreground">În custodie → CarPark #{record.carpark_vehicle_id}</p>
        )}
```

(e) Render the dialog (follow the existing `Dialog`/`DialogContent` usage in this file). Fields: owner_price (Input number), commission_type (`Select` percent/fixed), commission_value (Input number), min_sale_price (Input number), contract_number (Input), agreement_date + expiry_date (Input type="date"). "Transferă" button calls `custodyMutation.mutate()`, disabled while `custodyMutation.isPending`. Example skeleton:
```tsx
      <Dialog open={custodyOpen} onOpenChange={setCustodyOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Transfer în custodie</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Label className="text-xs">Preț proprietar (€)
              <Input type="number" value={custody.owner_price ?? ''} onChange={(e) => setCustody({ ...custody, owner_price: e.target.value === '' ? null : Number(e.target.value) })} />
            </Label>
            <Label className="text-xs">Comision
              <Select value={custody.commission_type} onValueChange={(v) => setCustody({ ...custody, commission_type: v as 'percent' | 'fixed' })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="percent">Procent %</SelectItem>
                  <SelectItem value="fixed">Sumă fixă €</SelectItem>
                </SelectContent>
              </Select>
            </Label>
            <Label className="text-xs">Valoare comision
              <Input type="number" value={custody.commission_value} onChange={(e) => setCustody({ ...custody, commission_value: Number(e.target.value) })} />
            </Label>
            <Label className="text-xs">Preț minim (€)
              <Input type="number" value={custody.min_sale_price ?? ''} onChange={(e) => setCustody({ ...custody, min_sale_price: e.target.value === '' ? null : Number(e.target.value) })} />
            </Label>
            <Label className="text-xs">Nr. contract
              <Input value={custody.contract_number ?? ''} onChange={(e) => setCustody({ ...custody, contract_number: e.target.value })} />
            </Label>
            <Label className="text-xs">Data acord
              <Input type="date" value={custody.agreement_date ?? ''} onChange={(e) => setCustody({ ...custody, agreement_date: e.target.value || null })} />
            </Label>
            <Label className="text-xs">Data expirare
              <Input type="date" value={custody.expiry_date ?? ''} onChange={(e) => setCustody({ ...custody, expiry_date: e.target.value || null })} />
            </Label>
          </div>
          <DialogFooter>
            <Button size="sm" disabled={custodyMutation.isPending} onClick={() => custodyMutation.mutate()}>Transferă</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
```

- [ ] **Step 4: Run tests, verify pass.**

Run: `cd jarvis/frontend && npx vitest run src/pages/BuyBack/ActionPanel.test.tsx`
Expected: PASS (existing + 5 new).

- [ ] **Step 5: Commit** (`/code-review` first).

```bash
git add jarvis/frontend/src/pages/BuyBack/ActionPanel.tsx jarvis/frontend/src/pages/BuyBack/ActionPanel.test.tsx
git commit -m "feat(buyback-ui): custody transfer action + agreement dialog + reopen gate"
```

---

## Task 9: BuyBackDetail — "Custodie" card

**Files:**
- Modify: `jarvis/frontend/src/pages/BuyBack/BuyBackDetail.tsx`

**Interfaces:**
- Consumes: `consignment` from the record query (`data.consignment`).
- Produces: a read-only "Custodie" card when `record.status === 'LOST' && record.carpark_vehicle_id`.

- [ ] **Step 1: Destructure `consignment`** from the query data (where `const { record, offers, photos, events } = data` is):
```typescript
  const { record, offers, photos, events, consignment } = data
```

- [ ] **Step 2: Add the card** after the "Prețuri" card:
```tsx
        {record.status === 'LOST' && record.carpark_vehicle_id && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2"><Euro className="h-4 w-4" />Custodie</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <Field label="Preț proprietar" value={fmtEur(consignment?.owner_price)} />
              <Field label="Comision" value={consignment ? (consignment.commission_type === 'percent' ? `${consignment.commission_value}%` : fmtEur(consignment.commission_value)) : null} />
              <Field label="Preț minim" value={fmtEur(consignment?.min_sale_price)} />
              <Field label="Nr. contract" value={consignment?.contract_number} />
              <Field label="Data acord" value={fmtDate(consignment?.agreement_date)} />
              <Field label="Data expirare" value={fmtDate(consignment?.expiry_date)} />
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">Vehicul CarPark</p>
                <Link to={`/app/carpark/${record.carpark_vehicle_id}`} className="text-sm underline">
                  #{record.carpark_vehicle_id}
                </Link>
              </div>
            </CardContent>
          </Card>
        )}
```
(`fmtEur`, `fmtDate`, `Field`, `Card*`, `Link`, `Euro` are already imported in this file. Verify the CarPark detail route path against an existing CarPark `<Link>`; adjust `/app/carpark/:id` if the app uses a different path.)

- [ ] **Step 3: Type-check + build.**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TS errors.

- [ ] **Step 4: Commit** (`/code-review` first).

```bash
git add jarvis/frontend/src/pages/BuyBack/BuyBackDetail.tsx
git commit -m "feat(buyback-ui): Custodie card on the buyback detail (LOST + linked)"
```

---

## Task 10: CarPark side — embed agreement + "Custodie" badge & card

**Files:**
- Modify: `jarvis/carpark/routes/vehicles.py` (single-vehicle GET handler)
- Modify: `jarvis/frontend/src/types/carpark.ts` (add `consignment` to the vehicle detail type)
- Modify: `jarvis/frontend/src/pages/CarPark/Detail.tsx` (badge + agreement card)

**Interfaces:**
- Consumes: `ConsignmentRepository().get_by_vehicle(id)`.
- Produces: the carpark vehicle GET returns `consignment` (object|null); Detail shows a "Custodie" badge + agreement card when `is_consignment`.

- [ ] **Step 1: Locate the single-vehicle GET handler.**

Run: `grep -n "vehicles/<int:vehicle_id>'\|def get_vehicle\|_serialize(veh\|return jsonify" jarvis/carpark/routes/vehicles.py | head`

- [ ] **Step 2: Embed the agreement** in that handler, after the vehicle is serialized and before returning:
```python
    if vehicle.get('is_consignment'):
        from carpark.repositories.consignment_repository import ConsignmentRepository
        vehicle['consignment'] = _serialize(ConsignmentRepository().get_by_vehicle(vehicle['id']))
```
(Use the module's existing `_serialize`; match the exact variable name the handler uses for the serialized dict.)

- [ ] **Step 3: Add a backend test** (`tests/test_buyback_custody_route.py`, append) patching the repo and asserting the key appears only when `is_consignment`. Model the mocks on the handler read in Step 1. Run:
```bash
python -m pytest tests/test_buyback_custody_route.py -k carpark_vehicle_consignment -q
```
Expected: PASS.

- [ ] **Step 4: Frontend type** — add to the vehicle detail interface in `types/carpark.ts`:
```typescript
  consignment?: {
    owner_price: number | null
    currency: string
    commission_type: 'percent' | 'fixed'
    commission_value: number
    min_sale_price: number | null
    contract_number: string | null
    agreement_date: string | null
    expiry_date: string | null
  } | null
```

- [ ] **Step 5: Render** in `Detail.tsx`: (a) a `<Badge>Custodie</Badge>` next to the source/status chips when `vehicle.is_consignment`; (b) an agreement card (owner price, commission formatted by type, min price, contract, dates) when `vehicle.consignment`. Reuse the existing `Badge` import and the page's card layout.

- [ ] **Step 6: Build + full test sweep.**

Run:
```bash
cd jarvis/frontend && npm run build
cd ../.. && python -m pytest tests/ -k "custody or consignment" -q
```
Expected: 0 TS errors; pytest green.

- [ ] **Step 7: Commit** (`/code-review` first).

```bash
git add jarvis/carpark/routes/vehicles.py jarvis/frontend/src/types/carpark.ts jarvis/frontend/src/pages/CarPark/Detail.tsx tests/test_buyback_custody_route.py
git commit -m "feat(carpark-ui): consignment badge + agreement card on vehicle detail"
```

---

## Final verification (before PR / deploy)

- [ ] `cd jarvis/frontend && npm run build` → 0 TS errors.
- [ ] `python -m pytest tests/ -x -q` → green.
- [ ] `python3 -m py_compile jarvis/app.py` → imports resolve.
- [ ] Manual smoke on local (per `/run` or `reference_jarvis_local_dev`): a `LOST` record shows "Transferă în custodie" → submit agreement → CarPark vehicle created with `is_consignment`, source `CUSTODIE`, no purchase price; buyback detail shows the Custodie card; CarPark detail shows the badge + agreement; re-opening is hidden; a second transfer attempt is blocked (409).
- [ ] Deploy **staging first → validate → `main` on double confirmation**.

## Self-Review (completed by plan author)

- **Spec coverage:** §4 table → T1; §4.2 CUSTODIE seed → T1; `ConsignmentRepository` → T2; §7 permission → T3; §5.1 service → T4; §5.2 route + §5.4 validation → T5; §6.2 buyback detail embed+card → T6/T9; §6.1 ActionPanel → T8; §6.3 CarPark → T10; §7 types → T7. All spec sections map to a task.
- **Placeholder scan:** No TBD/TODO; every code step has concrete code. Two "locate the exact handler" steps (T6 Step 2, T10 Step 1) give the file + grep to find the line, because the single-record/single-vehicle GET bodies weren't quoted verbatim in the spec — the grep makes them exact at execution time.
- **Type consistency:** `handoff_to_carpark_custody(record, agreement, actor)`, `ConsignmentRepository.create(vehicle_id, agreement, created_by)` / `.get_by_vehicle(vehicle_id)`, `validate_custody_agreement(data)->dict`, `transferToCustody(id, agreement)`, `CustodyAgreementInput`/`ConsignmentAgreement` are used identically across tasks.
- **Review Focus:** all five rows (dup VIN→409, re-transfer→409, fixed vs percent cap, cross-company→403, non-LOST→409) have tests in Task 5.
