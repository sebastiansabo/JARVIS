# Foi de Parcurs — Service context ("Mașini de curtoazie"), Foundation + Standalone Web — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-tenant "Service / Mașini de curtoazie" contract context to the Driving Hub, working end-to-end on the standalone `/app/foi-parcurs` page (separate car pool, per-company+brand contract template, templated PDF), reusing the existing session/return engine.

**Architecture:** A generic `document_type` discriminator (`sales`|`service`) rides alongside the existing `route_type`/`source`/`is_internal` axes on `foi_de_parcurs` **and** on `fp_vehicles` (separate fleet pool, enforced at submit). Each `(company, brand)` gets an editable contract template row in a new `fp_contract_configs` table — the existence of an active Service row *is* the per-tenant enablement. The standalone page gains a header toggle; Service sessions render a per-company templated PDF. Hub tile (Phase 4) and mobile (Phase 5) are separate follow-up plans.

**Tech Stack:** Python/Flask + psycopg2 (raw SQL, `%s` params, no ORM), React 19 + Vite + TS + Tailwind + shadcn/ui, pytest (backend pure-logic units), vitest (frontend units).

**Spec:** `docs/superpowers/specs/2026-08-24-foi-parcurs-service-courtesy-cars-design.md`

## Global Constraints

- **Internal key vs label:** internal `document_type` values are exactly `'sales'` and `'service'`. User-facing labels are **"Vânzări"** (sales) and **"Mașini de curtoazie"** (service). Never surface the raw key.
- **No ORM, parameterised SQL only:** raw psycopg2 via `BaseRepository` (`query_one`/`query_all`/`execute(sql, params, returning=)`). Never f-string a user value into SQL.
- **Idempotent DDL only:** all schema changes use `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`, inside `create_schema_incremental` (`jarvis/migrations/domains/schema_incremental.py`). `init_schema.py` and `migrations/domains/` are protected — additive changes only, no edits to existing DDL.
- **Orthogonal to `route_type`:** Service rows carry `document_type='service'` with `route_type='Comodat'`; never add a new `route_type` value (dozens of `WHERE route_type='TD'` clauses must stay valid).
- **Backend blueprint:** all new routes hang off `foi_parcurs_bp` with hardcoded `/api/foi-parcurs/...` paths (no url_prefix). Repos subclass `core.base_repository.BaseRepository`.
- **Pre-push gate (run before every commit that touches Python or TS):** `cd jarvis/frontend && npm run build` (0 TS errors) · `cd ../.. && python -m pytest tests/ -x -q` (green) · `python3 -m py_compile jarvis/app.py`.
- **Branch:** work stays on `feature/foi-parcurs-service-context` (off `dev`). Do not push to `staging`/`main`.
- **Default safety:** existing rows default to `document_type='sales'` — no backfill. Service is live-session-only (never the monthly batch/route-sheet generator).

## File Structure

**Backend (create):**
- `jarvis/foi_parcurs/document_types.py` — the `sales`/`service` constants + pure helpers (`normalize`, `pools_match`).
- `jarvis/foi_parcurs/services/contract_template.py` — pure `render_contract_template(template, context)` placeholder substitution.
- `jarvis/foi_parcurs/repositories/contract_config_repository.py` — `ContractConfigRepository` (list/upsert/get_active/service_enabled).
- `jarvis/foi_parcurs/routes/contract_configs.py` — CRUD + `service-enabled` endpoints.
- `tests/test_foi_parcurs_service_context.py` — pytest units for the two pure modules.

**Backend (modify):**
- `jarvis/migrations/domains/schema_incremental.py` — new columns + `fp_contract_configs` table (Task 1).
- `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` — `_LIST_COLUMNS` + `get_contracts` filter (Task 2).
- `jarvis/foi_parcurs/routes/contracts.py` — list route `document_type` param (Task 2).
- `jarvis/foi_parcurs/routes/test_drive.py` — write-path threading + pool-match + service conditions (Task 7).
- `jarvis/foi_parcurs/repositories/vehicle_repository.py` + `jarvis/foi_parcurs/routes/vehicles.py` — pool filter + pool on create/edit (Task 8).
- `jarvis/foi_parcurs/routes/__init__.py` — register the new routes module (Task 6).
- `jarvis/foi_parcurs/services/pdf_service.py` + `jarvis/foi_parcurs/routes/pdf.py` — Service PDF (Task 14).

**Frontend (create):**
- `jarvis/frontend/src/pages/FoiParcurs/DocTypeToggle.tsx` (+ `.test.tsx`) — the `[Vânzări | Mașini de curtoazie]` control.
- `jarvis/frontend/src/pages/FoiParcurs/documentType.ts` (+ `.test.ts`) — shared FE constants/labels + context helpers.
- `jarvis/frontend/src/pages/FoiParcurs/ContractConfigSection.tsx` — the Settings setup zone.

**Frontend (modify):**
- `jarvis/frontend/src/api/foiParcurs.ts` — new API methods (Task 9).
- `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — header toggle wiring + context prop threading + Settings section mount (Tasks 10, 12).
- `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx` — `service_order_ref` field + relabel (Task 13).

---

## Phase 1 — Data model + backend

### Task 1: Schema migration — discriminators, pool, contract-config table

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (inside `_create_schema_incremental_continued`, near the existing `source`/`is_internal` blocks ~line 2318-2337)

**Interfaces:**
- Produces (DB): `foi_de_parcurs.document_type VARCHAR(16) NOT NULL DEFAULT 'sales'`, `foi_de_parcurs.service_order_ref VARCHAR(64)`, `fp_vehicles.document_type VARCHAR(16) NOT NULL DEFAULT 'sales'`, table `fp_contract_configs(id, company_id, brand_id, document_type, title, body_template, general_conditions, is_active, created_at, updated_at)` with `UNIQUE(company_id, brand_id, document_type)`.

- [ ] **Step 1: Add the DDL block.** In `_create_schema_incremental_continued`, after the `foi_de_parcurs` `source`/`general_conditions` DO-block (the one ending ~line 2337), add:

```python
    # ── Foi de Parcurs — Service context ("Mașini de curtoazie") ──
    # Generic document-type discriminator (sales|service), orthogonal to
    # route_type; a Service session is a courtesy-car handover.
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='document_type') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN document_type VARCHAR(16) NOT NULL DEFAULT 'sales';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='service_order_ref') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN service_order_ref VARCHAR(64);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='document_type') THEN
                ALTER TABLE fp_vehicles ADD COLUMN document_type VARCHAR(16) NOT NULL DEFAULT 'sales';
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_doctype ON foi_de_parcurs(company_id, document_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_doctype ON fp_vehicles(document_type)')
    # Per company+brand contract template (registry, Service-first). Existence of
    # an active document_type='service' row = Service enabled for that (company,brand).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_contract_configs (
            id            BIGSERIAL PRIMARY KEY,
            company_id    BIGINT NOT NULL,
            brand_id      BIGINT NOT NULL,
            document_type VARCHAR(16) NOT NULL DEFAULT 'service',
            title         VARCHAR(255),
            body_template TEXT,
            general_conditions TEXT,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, brand_id, document_type)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_contract_configs_lookup ON fp_contract_configs(company_id, brand_id, document_type, is_active)')
```

- [ ] **Step 2: Verify it compiles.** Run: `python3 -m py_compile jarvis/migrations/domains/schema_incremental.py` — Expected: exit 0.

- [ ] **Step 3: Verify idempotent apply against a scratch DB (no prod).** Create a throwaway local DB and apply the schema once, then twice, asserting no error the second time:

```bash
createdb fp_svc_test 2>/dev/null; \
DATABASE_URL='postgresql://localhost/fp_svc_test' python3 -c "
import os; os.environ.setdefault('DATABASE_URL','postgresql://localhost/fp_svc_test')
import sys; sys.path.insert(0,'jarvis')
from database import init_db
init_db(); init_db()  # second call must be a no-op, not error
import psycopg2
c=psycopg2.connect('postgresql://localhost/fp_svc_test').cursor()
c.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name IN ('document_type','service_order_ref')\")
print('foi_de_parcurs cols:', sorted(r[0] for r in c.fetchall()))
c.execute(\"SELECT to_regclass('public.fp_contract_configs')\"); print('table:', c.fetchone()[0])
"
```
Expected: `foi_de_parcurs cols: ['document_type', 'service_order_ref']` and `table: fp_contract_configs`. **Never point `DATABASE_URL` at staging/prod** (see `reference_database_init_on_import`).

- [ ] **Step 4: Commit.**
```bash
git add jarvis/migrations/domains/schema_incremental.py
git commit -m "feat(foi-parcurs): schema for Service context (document_type, pool, contract configs)"
```

---

### Task 2: List projection + `document_type` read filter

**Files:**
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` (`_LIST_COLUMNS` ~line 17-31; `get_contracts` ~line 52-99)
- Modify: `jarvis/foi_parcurs/routes/contracts.py` (`api_list_contracts` ~line 170-204)

**Interfaces:**
- Produces: `get_contracts(..., document_type=None)` adds `WHERE fp.document_type = %s` when set; `document_type` and `service_order_ref` present in every list row.

- [ ] **Step 1: Add the columns to the lean projection.** In `_LIST_COLUMNS`, append `document_type` and `service_order_ref` to the final line (currently ends `...fp.driver_contact_id, fp.event_id`):

```python
    'fp.driver_name, fp.driver_contact_id, fp.event_id, '
    'fp.document_type, fp.service_order_ref'
```

- [ ] **Step 2: Add the filter param to `get_contracts`.** Add `document_type=None` to the signature, and after the `route_type` filter block (~line 88-90) add:

```python
        if document_type:
            where_clauses.append('fp.document_type = %s')
            params.append(document_type)
```

- [ ] **Step 3: Read + pass the param in the route.** In `api_list_contracts`, after the `route_type` read (~line 177) add `document_type = (request.args.get('document_type') or '').strip() or None`, and pass `document_type=document_type` into the `_fp_repo.get_contracts(...)` call.

- [ ] **Step 4: Verify.** Run: `python3 -m py_compile jarvis/foi_parcurs/repositories/foi_parcurs_repository.py jarvis/foi_parcurs/routes/contracts.py` — Expected: exit 0. Then `python -m pytest tests/ -x -q` — Expected: green (no regressions).

- [ ] **Step 5: Commit.**
```bash
git add jarvis/foi_parcurs/repositories/foi_parcurs_repository.py jarvis/foi_parcurs/routes/contracts.py
git commit -m "feat(foi-parcurs): document_type in list projection + read filter"
```

---

### Task 3: `document_types.py` — constants + pure pool helpers (TDD)

**Files:**
- Create: `jarvis/foi_parcurs/document_types.py`
- Test: `tests/test_foi_parcurs_service_context.py`

**Interfaces:**
- Produces: `SALES='sales'`, `SERVICE='service'`, `VALID={SALES,SERVICE}`, `normalize(v)->str`, `pools_match(session_dt, vehicle_dt)->bool`.

- [ ] **Step 1: Write the failing test.** Create `tests/test_foi_parcurs_service_context.py`:

```python
"""Pure-logic units for the Foi de Parcurs Service context."""
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from foi_parcurs.document_types import SALES, SERVICE, normalize, pools_match


class TestDocumentTypes:
    def test_normalize_valid(self):
        assert normalize('service') == SERVICE
        assert normalize('sales') == SALES

    def test_normalize_unknown_defaults_to_sales(self):
        assert normalize('') == SALES
        assert normalize(None) == SALES
        assert normalize('bogus') == SALES

    def test_pools_match(self):
        assert pools_match('service', 'service') is True
        assert pools_match('sales', 'sales') is True

    def test_pools_mismatch(self):
        assert pools_match('service', 'sales') is False
        assert pools_match('sales', 'service') is False

    def test_pools_match_normalizes_blanks(self):
        # a legacy/blank vehicle pool is treated as 'sales'
        assert pools_match('sales', None) is True
        assert pools_match('service', None) is False
```

- [ ] **Step 2: Run it to verify it fails.** Run: `python -m pytest tests/test_foi_parcurs_service_context.py -q` — Expected: FAIL (`ModuleNotFoundError: foi_parcurs.document_types`).

- [ ] **Step 3: Implement.** Create `jarvis/foi_parcurs/document_types.py`:

```python
"""Document-type axis for Foi de Parcurs: Sales vs Service (courtesy car).

`document_type` rides alongside route_type/source/is_internal on foi_de_parcurs
AND on fp_vehicles. A session may only attach to a vehicle in the same pool.
Values are the internal keys; user-facing labels ("Vânzări" / "Mașini de
curtoazie") live in the frontend only.
"""

SALES = 'sales'
SERVICE = 'service'
VALID = {SALES, SERVICE}


def normalize(value) -> str:
    """Coerce any input to a valid document_type; unknown/blank -> 'sales'
    (all legacy data is Sales)."""
    v = (value or '').strip().lower() if isinstance(value, str) else (value or '')
    return v if v in VALID else SALES


def pools_match(session_document_type, vehicle_document_type) -> bool:
    """True when a session's document_type equals its vehicle's pool (after
    normalizing blanks to 'sales'). The submit-time isolation rule."""
    return normalize(session_document_type) == normalize(vehicle_document_type)
```

- [ ] **Step 4: Run the tests to verify they pass.** Run: `python -m pytest tests/test_foi_parcurs_service_context.py -q` — Expected: PASS.

- [ ] **Step 5: Commit.**
```bash
git add jarvis/foi_parcurs/document_types.py tests/test_foi_parcurs_service_context.py
git commit -m "feat(foi-parcurs): document_types constants + pool-match helper (TDD)"
```

---

### Task 4: `contract_template.py` — placeholder rendering (TDD)

**Files:**
- Create: `jarvis/foi_parcurs/services/contract_template.py`
- Test: `tests/test_foi_parcurs_service_context.py` (append)

**Interfaces:**
- Produces: `PLACEHOLDERS` (the whitelisted token set) and `render_contract_template(template: str, context: dict) -> str`. Only whitelisted `{token}`s are substituted; unknown `{tokens}` render literally; a whitelisted token missing from `context` renders as empty string.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_foi_parcurs_service_context.py`:

```python
from foi_parcurs.services.contract_template import render_contract_template, PLACEHOLDERS


class TestContractTemplate:
    def test_substitutes_known_tokens(self):
        out = render_contract_template(
            'Client {client_name}, VIN {vin}, km {km_start}.',
            {'client_name': 'Ion Pop', 'vin': 'WVW123', 'km_start': 45000},
        )
        assert out == 'Client Ion Pop, VIN WVW123, km 45000.'

    def test_unknown_token_renders_literally(self):
        out = render_contract_template('Hi {not_a_token} there', {'client_name': 'X'})
        assert out == 'Hi {not_a_token} there'

    def test_missing_known_token_is_blank(self):
        out = render_contract_template('Ref: {service_order_ref}!', {})
        assert out == 'Ref: !'

    def test_service_order_ref_is_whitelisted(self):
        assert 'service_order_ref' in PLACEHOLDERS

    def test_none_template_is_empty_string(self):
        assert render_contract_template(None, {'vin': 'X'}) == ''
```

- [ ] **Step 2: Run it to verify it fails.** Run: `python -m pytest tests/test_foi_parcurs_service_context.py::TestContractTemplate -q` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement.** Create `jarvis/foi_parcurs/services/contract_template.py`:

```python
"""Render a per-company contract body_template by substituting a whitelisted
set of {placeholders} with session data. Plain, safe string replacement — no
eval, no user SQL. Unknown {tokens} are left as-is so authors see their typos;
a whitelisted token with no value renders empty."""

# Whitelisted tokens an author may use in a contract template.
PLACEHOLDERS = (
    'client_name', 'client_phone', 'client_address',
    'company_name', 'brand', 'vin', 'registration_number',
    'km_start', 'km_end', 'distance_km',
    'departure_datetime', 'return_datetime',
    'service_order_ref', 'advisor_name', 'general_conditions',
)


def render_contract_template(template: str, context: dict) -> str:
    """Substitute only whitelisted {tokens}; leave unknown {tokens} literal."""
    if not template:
        return ''
    out = template
    ctx = context or {}
    for token in PLACEHOLDERS:
        needle = '{' + token + '}'
        if needle in out:
            value = ctx.get(token)
            out = out.replace(needle, '' if value is None else str(value))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass.** Run: `python -m pytest tests/test_foi_parcurs_service_context.py -q` — Expected: PASS (all classes).

- [ ] **Step 5: Commit.**
```bash
git add jarvis/foi_parcurs/services/contract_template.py tests/test_foi_parcurs_service_context.py
git commit -m "feat(foi-parcurs): contract template placeholder rendering (TDD)"
```

---

### Task 5: `ContractConfigRepository`

**Files:**
- Create: `jarvis/foi_parcurs/repositories/contract_config_repository.py`
- Modify: `jarvis/foi_parcurs/repositories/__init__.py` (export it, matching the existing export style)

**Interfaces:**
- Produces:
  - `list_for_company(company_id) -> list` — one row per active brand, LEFT JOIN so unconfigured brands appear blank (mirrors `DealerConfigRepository.list_for_company`).
  - `upsert(company_id, brand_id, title, body_template, general_conditions, is_active=True, document_type='service')`.
  - `get_active(company_id, brand_name, document_type='service') -> dict|None` — resolves by brand **name** (JOIN `brands`), mirroring `DealerConfigRepository.get_general_conditions`, because the runtime callers (submit, PDF) hold the vehicle's brand name, not its id.
  - `service_enabled(company_id) -> list` — brand_ids with an active service config.

- [ ] **Step 1: Implement the repository.** Create `jarvis/foi_parcurs/repositories/contract_config_repository.py`:

```python
"""Data access for fp_contract_configs (per company+brand contract template).

The existence of an active document_type='service' row is what enables the
Service context for a (company, brand). Mirrors DealerConfigRepository."""
from core.base_repository import BaseRepository


class ContractConfigRepository(BaseRepository):

    def list_for_company(self, company_id, document_type='service'):
        """Per-brand contract config for a company's active brands. LEFT JOIN so
        brands without a row appear with empty values (ready to edit)."""
        return self.query_all(
            '''SELECT b.id AS brand_id, b.name AS brand_name,
                      cc.id AS config_id, cc.title, cc.body_template,
                      cc.general_conditions,
                      COALESCE(cc.is_active, FALSE) AS is_active
               FROM company_brands cb
               JOIN brands b ON b.id = cb.brand_id
               LEFT JOIN fp_contract_configs cc
                      ON cc.company_id = cb.company_id AND cc.brand_id = cb.brand_id
                     AND cc.document_type = %s
               WHERE cb.company_id = %s AND cb.is_active = TRUE AND b.is_active = TRUE
               ORDER BY b.name''',
            (document_type, company_id),
        )

    def upsert(self, company_id, brand_id, title, body_template,
               general_conditions, is_active=True, document_type='service'):
        return self.execute(
            '''INSERT INTO fp_contract_configs
                   (company_id, brand_id, document_type, title, body_template,
                    general_conditions, is_active, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (company_id, brand_id, document_type) DO UPDATE SET
                   title = EXCLUDED.title,
                   body_template = EXCLUDED.body_template,
                   general_conditions = EXCLUDED.general_conditions,
                   is_active = EXCLUDED.is_active,
                   updated_at = NOW()''',
            (company_id, brand_id, document_type, title, body_template,
             general_conditions, is_active),
        )

    def get_active(self, company_id, brand_name, document_type='service'):
        """The active contract template for a (company, brand-name), or None.
        Resolves by brand NAME (JOIN brands) — runtime callers hold the vehicle's
        brand name, not its id — mirroring DealerConfigRepository.get_general_conditions."""
        if not company_id or not brand_name:
            return None
        return self.query_one(
            '''SELECT cc.* FROM fp_contract_configs cc
               JOIN brands b ON b.id = cc.brand_id
               WHERE cc.company_id = %s AND LOWER(b.name) = LOWER(%s)
                 AND cc.document_type = %s AND cc.is_active = TRUE''',
            (company_id, brand_name, document_type),
        )

    def service_enabled(self, company_id, document_type='service') -> list:
        """brand_ids that have an active contract config for this company."""
        rows = self.query_all(
            '''SELECT brand_id FROM fp_contract_configs
               WHERE company_id = %s AND document_type = %s AND is_active = TRUE''',
            (company_id, document_type),
        )
        return [r['brand_id'] for r in (rows or [])]
```

- [ ] **Step 2: Export it.** In `jarvis/foi_parcurs/repositories/__init__.py`, add `from .contract_config_repository import ContractConfigRepository` and include it in `__all__` if that file uses one (match the existing style in that file).

- [ ] **Step 3: Verify.** Run: `python3 -m py_compile jarvis/foi_parcurs/repositories/contract_config_repository.py jarvis/foi_parcurs/repositories/__init__.py` — Expected: exit 0.

- [ ] **Step 4: Commit.**
```bash
git add jarvis/foi_parcurs/repositories/contract_config_repository.py jarvis/foi_parcurs/repositories/__init__.py
git commit -m "feat(foi-parcurs): ContractConfigRepository (per company+brand template)"
```

---

### Task 6: Contract-config CRUD + `service-enabled` routes

**Files:**
- Create: `jarvis/foi_parcurs/routes/contract_configs.py`
- Modify: `jarvis/foi_parcurs/routes/__init__.py` (add `contract_configs` to the import list ~line 3-12)

**Interfaces:**
- Consumes: `ContractConfigRepository` (Task 5), `_shared` blueprint helpers.
- Produces (HTTP):
  - `GET /api/foi-parcurs/contract-configs/<int:company_id>` → `{success, configs:[{brand_id,brand_name,title,body_template,general_conditions,is_active}]}`
  - `PUT /api/foi-parcurs/contract-configs/<int:company_id>/<int:brand_id>` (admin) → `{success}`
  - `GET /api/foi-parcurs/service-enabled?company_id=<id>` → `{success, enabled:bool, brands:[brand_id]}`

- [ ] **Step 1: Implement the routes.** Create `jarvis/foi_parcurs/routes/contract_configs.py`:

```python
"""Routes for per-company+brand Service contract templates (fp_contract_configs).
Configuring an active Service template here is what enables the Service context
for that (company, brand)."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..repositories.contract_config_repository import ContractConfigRepository

_cc_repo = ContractConfigRepository()


def _is_admin():
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


@foi_parcurs_bp.route('/api/foi-parcurs/contract-configs/<int:company_id>', methods=['GET'])
@login_required
def api_list_contract_configs(company_id):
    """Per-brand Service contract template for a company's active brands."""
    return jsonify({'success': True, 'configs': _cc_repo.list_for_company(company_id)})


@foi_parcurs_bp.route('/api/foi-parcurs/contract-configs/<int:company_id>/<int:brand_id>', methods=['PUT'])
@login_required
def api_put_contract_config(company_id, brand_id):
    """Upsert one (company, brand) Service contract template. Admin only."""
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json(silent=True) or {}
    _cc_repo.upsert(
        company_id, brand_id,
        (data.get('title') or '').strip() or None,
        (data.get('body_template') or '').strip() or None,
        (data.get('general_conditions') or '').strip() or None,
        is_active=bool(data.get('is_active', True)),
    )
    logger.info('service contract-config upserted for company=%s brand=%s by %s',
                company_id, brand_id, getattr(current_user, 'email', '?'))
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/service-enabled', methods=['GET'])
@login_required
def api_service_enabled():
    """Which brands (if any) have an active Service contract for a company."""
    company_id = request.args.get('company_id', type=int)
    brands = _cc_repo.service_enabled(company_id) if company_id else []
    return jsonify({'success': True, 'enabled': bool(brands), 'brands': brands})
```

- [ ] **Step 2: Register the module.** In `jarvis/foi_parcurs/routes/__init__.py`, add `contract_configs` to the existing `from . import (...)` list so the routes load with the blueprint.

- [ ] **Step 3: Verify import graph.** Run: `python3 -m py_compile jarvis/app.py` — Expected: exit 0 (blueprint + new routes import cleanly).

- [ ] **Step 4: Commit.**
```bash
git add jarvis/foi_parcurs/routes/contract_configs.py jarvis/foi_parcurs/routes/__init__.py
git commit -m "feat(foi-parcurs): contract-config CRUD + service-enabled endpoints"
```

---

### Task 7: Write-path — thread `document_type`, validate pool, pick Service conditions

**Files:**
- Modify: `jarvis/foi_parcurs/routes/test_drive.py` (`api_submit_test_drive` ~line 73-262; the contract-data dict assembled before `create_from_td_form`)

**Interfaces:**
- Consumes: `document_types.normalize`/`pools_match` (Task 3), `ContractConfigRepository.get_active` (Task 5), `_vehicle_repo.get_by_vin`.
- Produces: submitted sessions persist `document_type` + `service_order_ref`; Service sessions are rejected (400) on a Sales car; Service general-conditions come from `fp_contract_configs`, not `fp_dealer_config`.

- [ ] **Step 1: Import the helpers.** At the top of `test_drive.py`, add `from ..document_types import normalize as _normalize_doctype, pools_match` and `from ..repositories.contract_config_repository import ContractConfigRepository`, and instantiate `_cc_repo = ContractConfigRepository()` next to the other module repos.

- [ ] **Step 2: Resolve + validate the pool early in `api_submit_test_drive`.** After the vehicle-lock check (~line 108) and after the vehicle brand is available, add:

```python
    document_type = _normalize_doctype(data.get('document_type'))
    if document_type != 'sales':
        _veh_pool = (_vehicle_repo.get_by_vin(data['vin']) or {}).get('document_type')
        if not pools_match(document_type, _veh_pool):
            return jsonify({'success': False,
                            'error': 'Mașina selectată nu aparține parcului pentru acest tip de document.'}), 400
```

- [ ] **Step 3: Source Service conditions from the contract config.** Where `general_conditions_text` is resolved (~line 122-130), branch on `document_type`:

```python
    if document_type == 'service':
        try:
            _veh = _vehicle_repo.get_by_vin(data['vin'])
            _cfg = _cc_repo.get_active(int(data['company_id']), (_veh or {}).get('brand'), 'service')
            general_conditions_text = ((_cfg or {}).get('general_conditions') or '')
        except Exception:
            logger.warning('service contract-config lookup failed at submit', exc_info=True)
            general_conditions_text = ''
```
(Leave the existing Sales branch untouched under an `else`.)

- [ ] **Step 4: Persist the new fields.** In the `contract_data` dict passed to `create_from_td_form`, add `'document_type': document_type` and `'service_order_ref': (data.get('service_order_ref') or None)`.

- [ ] **Step 5: Verify.** Run: `python3 -m py_compile jarvis/foi_parcurs/routes/test_drive.py` — Expected: exit 0. Then `python -m pytest tests/ -x -q` — Expected: green.

- [ ] **Step 6: Commit.**
```bash
git add jarvis/foi_parcurs/routes/test_drive.py
git commit -m "feat(foi-parcurs): submit threads document_type + pool-match + service conditions"
```

---

### Task 8: Fleet pool filter + pool on vehicle create/edit

**Files:**
- Modify: `jarvis/foi_parcurs/repositories/vehicle_repository.py` (`get_all` ~line 107-116; create/update column sets)
- Modify: `jarvis/foi_parcurs/routes/vehicles.py` (list route ~line 29-34; create/edit handlers)

**Interfaces:**
- Produces: `GET /api/foi-parcurs/vehicles?document_type=service` returns only that pool; vehicle create/edit accepts+persists `document_type`.

- [ ] **Step 1: Add the pool filter to the repo read.** In `vehicle_repository.get_all`, add an optional `document_type=None` param; when set, add `AND document_type = %s` to the WHERE clause (build params conditionally, parameterised).

- [ ] **Step 2: Read the param in the list route.** In `vehicles.py` list handler, read `document_type = (request.args.get('document_type') or '').strip() or None` and pass it to `get_all(...)`. Default `None` = all pools (management/back-compat).

- [ ] **Step 3: Accept the pool on create/edit.** In the vehicle create + update handlers, read `document_type` from the JSON body, `normalize()` it (import from `..document_types`), and include it in the insert/update column set. Default `'sales'` when absent.

- [ ] **Step 4: Verify.** Run: `python3 -m py_compile jarvis/foi_parcurs/repositories/vehicle_repository.py jarvis/foi_parcurs/routes/vehicles.py` — Expected: exit 0. `python -m pytest tests/ -x -q` — Expected: green.

- [ ] **Step 5: Commit.**
```bash
git add jarvis/foi_parcurs/repositories/vehicle_repository.py jarvis/foi_parcurs/routes/vehicles.py
git commit -m "feat(foi-parcurs): vehicle fleet pool filter + document_type on create/edit"
```

---

## Phase 2 — Setup zone (Settings tab)

### Task 9: Frontend API client methods

**Files:**
- Modify: `jarvis/frontend/src/api/foiParcurs.ts` (inside the `foiParcursApi` object ~line 100+)

**Interfaces:**
- Produces: `foiParcursApi.getContractConfigs(companyId)`, `foiParcursApi.putContractConfig(companyId, brandId, payload)`, `foiParcursApi.getServiceEnabled(companyId)`. `getContracts`/`getVehicles` gain an optional `documentType`.

- [ ] **Step 1: Add the methods.** Following the existing fetch-wrapper style in the file, add:

```ts
  getContractConfigs: (companyId: number) =>
    apiGet(`/api/foi-parcurs/contract-configs/${companyId}`),
  putContractConfig: (companyId: number, brandId: number, payload: {
    title: string; body_template: string; general_conditions: string; is_active: boolean
  }) => apiPut(`/api/foi-parcurs/contract-configs/${companyId}/${brandId}`, payload),
  getServiceEnabled: (companyId: number) =>
    apiGet(`/api/foi-parcurs/service-enabled?company_id=${companyId}`),
```
(Use whatever the file's actual helpers are named — match `getContracts`/`submitTestDrive`'s style; if it uses a raw `fetch(...)` pattern, mirror that instead of `apiGet`/`apiPut`.)

- [ ] **Step 2: Thread `documentType` into existing calls.** In `getContracts(params)` and `getVehicles(...)`, add an optional `documentType` and append `&document_type=${documentType}` (contracts) / `?document_type=${documentType}` (vehicles) when provided.

- [ ] **Step 3: Verify.** Run: `cd jarvis/frontend && npm run build` — Expected: 0 TS errors. `cd ../..`.

- [ ] **Step 4: Commit.**
```bash
git add jarvis/frontend/src/api/foiParcurs.ts
git commit -m "feat(foi-parcurs): FE API for contract-configs + service-enabled + doc_type filter"
```

---

### Task 10: Contract setup zone in Settings

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/ContractConfigSection.tsx`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` (mount the section inside `SettingsTab`)

**Interfaces:**
- Consumes: `foiParcursApi.getContractConfigs`, `putContractConfig` (Task 9).
- Produces: a `<ContractConfigSection companyId={number} />` component.

- [ ] **Step 1: Build the section.** Create `ContractConfigSection.tsx` — a shadcn card titled **"Contract Mașini de curtoazie"**, fetching `getContractConfigs(companyId)` and rendering, per brand: `title` input, `body_template` textarea, `general_conditions` textarea, an `is_active` switch, a Save button (calls `putContractConfig`), and a static placeholder cheat-sheet listing the tokens from `PLACEHOLDERS` (`{client_name} {vin} {km_start} {return_datetime} {service_order_ref} …`). Use `useQuery`/`useMutation` + `toast` consistent with the rest of the page. Disabled when `!companyId`.

- [ ] **Step 2: Mount it.** In `SettingsTab` (in `index.tsx`), render `<ContractConfigSection companyId={companyId} />` below the existing dealer-config section. Admin-gate its visibility the same way other admin-only settings are gated in that file.

- [ ] **Step 3: Verify.** Run: `cd jarvis/frontend && npm run build` — Expected: 0 TS errors. `cd ../..`.

- [ ] **Step 4: Manual smoke.** With the local stack running (backend :5001, Vite :5173 per `reference_jarvis_local_dev_against_staging`), open `/app/foi-parcurs` → Settings, pick a company, fill a brand's Service contract, Save; reload and confirm it persists; hit `GET /api/foi-parcurs/service-enabled?company_id=<id>` and confirm `enabled:true`.

- [ ] **Step 5: Commit.**
```bash
git add jarvis/frontend/src/pages/FoiParcurs/ContractConfigSection.tsx jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): Service contract setup zone in Settings tab"
```

---

## Phase 3 — Standalone toggle + Service PDF

### Task 11: `documentType.ts` helpers + `DocTypeToggle` component (TDD)

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/documentType.ts` (+ `documentType.test.ts`)
- Create: `jarvis/frontend/src/pages/FoiParcurs/DocTypeToggle.tsx` (+ `DocTypeToggle.test.tsx`)

**Interfaces:**
- Produces: `type DocType = 'sales' | 'service'`; `DOC_TYPE_LABELS` (`{sales:'Vânzări', service:'Mașini de curtoazie'}`); `contextFromSearch(search: string): DocType` (reads `?context=service`); `<DocTypeToggle value onChange />`.

- [ ] **Step 1: Write the failing helper test.** Create `documentType.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { DOC_TYPE_LABELS, contextFromSearch } from './documentType'

describe('documentType helpers', () => {
  it('labels use Romanian user-facing names', () => {
    expect(DOC_TYPE_LABELS.sales).toBe('Vânzări')
    expect(DOC_TYPE_LABELS.service).toBe('Mașini de curtoazie')
  })
  it('reads ?context=service from the query string', () => {
    expect(contextFromSearch('?context=service')).toBe('service')
  })
  it('defaults to sales for anything else', () => {
    expect(contextFromSearch('')).toBe('sales')
    expect(contextFromSearch('?context=bogus')).toBe('sales')
  })
})
```

- [ ] **Step 2: Run it to verify it fails.** Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/documentType.test.ts` — Expected: FAIL (module missing). `cd ../..`.

- [ ] **Step 3: Implement the helpers.** Create `documentType.ts`:

```ts
export type DocType = 'sales' | 'service'

export const DOC_TYPE_LABELS: Record<DocType, string> = {
  sales: 'Vânzări',
  service: 'Mașini de curtoazie',
}

/** Read the `context` query param; anything but 'service' → 'sales'. */
export function contextFromSearch(search: string): DocType {
  return new URLSearchParams(search).get('context') === 'service' ? 'service' : 'sales'
}
```

- [ ] **Step 4: Implement the toggle** `DocTypeToggle.tsx` (segmented control mirroring `DriveTypeToggle.tsx`):

```tsx
import { Tag, KeyRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DOC_TYPE_LABELS, type DocType } from './documentType'

const OPTIONS: { value: DocType; Icon: typeof Tag }[] = [
  { value: 'sales', Icon: Tag },
  { value: 'service', Icon: KeyRound },
]

/** Sales ↔ Service (Mașini de curtoazie) context switch for the standalone
 *  Foi de Parcurs header. Shown only when the company has Service enabled. */
export default function DocTypeToggle({ value, onChange }: { value: DocType; onChange: (v: DocType) => void }) {
  return (
    <div className="flex h-9 shrink-0 gap-0.5 rounded-lg bg-muted p-0.5">
      {OPTIONS.map(({ value: v, Icon }) => (
        <button
          key={v}
          type="button"
          title={DOC_TYPE_LABELS[v]}
          aria-label={DOC_TYPE_LABELS[v]}
          onClick={() => onChange(v)}
          className={cn('flex h-full items-center gap-1.5 rounded-md px-3 text-sm transition-colors',
            value === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}
        >
          <Icon className="h-4 w-4" />
          <span className="hidden sm:inline">{DOC_TYPE_LABELS[v]}</span>
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Write the toggle test** `DocTypeToggle.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DocTypeToggle from './DocTypeToggle'

describe('DocTypeToggle', () => {
  it('renders both Romanian labels and fires onChange', () => {
    const onChange = vi.fn()
    render(<DocTypeToggle value="sales" onChange={onChange} />)
    fireEvent.click(screen.getByLabelText('Mașini de curtoazie'))
    expect(onChange).toHaveBeenCalledWith('service')
  })
})
```

- [ ] **Step 6: Run tests to verify they pass.** Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/documentType.test.ts src/pages/FoiParcurs/DocTypeToggle.test.tsx` — Expected: PASS. Then `npm run build` — Expected: 0 TS errors. `cd ../..`.

- [ ] **Step 7: Commit.**
```bash
git add jarvis/frontend/src/pages/FoiParcurs/documentType.ts jarvis/frontend/src/pages/FoiParcurs/documentType.test.ts jarvis/frontend/src/pages/FoiParcurs/DocTypeToggle.tsx jarvis/frontend/src/pages/FoiParcurs/DocTypeToggle.test.tsx
git commit -m "feat(foi-parcurs): DocTypeToggle + documentType helpers (TDD)"
```

---

### Task 12: Wire the context into the standalone page

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` (header ~line 201-228; tab prop threading ~line 255-258)

**Interfaces:**
- Consumes: `DocTypeToggle`, `contextFromSearch`, `foiParcursApi.getServiceEnabled` (Tasks 9, 11).
- Produces: a `docType` state (persisted `fp.docType`, seeded from `?context=`) threaded into `SessionsTab`/`StockTab`/`CalendarTab`/list+fleet calls; toggle rendered only when the selected company is Service-enabled.

- [ ] **Step 1: Add the state + enablement query.** Near the existing `companyId`/`brand`/`driveType` state (~line 139-148), add `const [docType, setDocType] = usePersistentState<DocType>('fp.docType', contextFromSearch(window.location.search))` and a `useQuery(['fp-service-enabled', companyId], () => foiParcursApi.getServiceEnabled(companyId), { enabled: companyId > 0 })`. When the query says not enabled, force `docType='sales'`.

- [ ] **Step 2: Render the toggle.** In the header row next to the brand `Select` (~line 216-227), render `{serviceEnabled && <DocTypeToggle value={docType} onChange={setDocType} />}`.

- [ ] **Step 3: Thread the prop.** Pass `documentType={docType}` to `SessionsTab`, `StockTab`, `CalendarTab` (~line 255-258), and pass it through their list/fleet API calls (`getContracts({..., documentType})`, `getVehicles(true, docType)`). Each tab filters its rows by the active pool.

- [ ] **Step 4: Verify.** Run: `cd jarvis/frontend && npm run build` — Expected: 0 TS errors. `cd ../..`.

- [ ] **Step 5: Manual smoke.** Local stack: with a Service-enabled company, the header shows `[Vânzări | Mașini de curtoazie]`; switching to Service shows only Service-pool cars/sessions; a non-enabled company shows no toggle. Deep-link `/app/foi-parcurs?context=service` lands on Service.

- [ ] **Step 6: Commit.**
```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): standalone header context toggle + pool-scoped tabs"
```

---

### Task 13: Service fields in the session form

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx`

**Interfaces:**
- Consumes: `documentType` context (via route/query or a prop from the create flow).
- Produces: the form submits `document_type` + `service_order_ref`; when Service, it relabels and reveals the service-order field.

- [ ] **Step 1: Determine the form's context.** Read the active `document_type` the same way the form reads its other context (query param `?context=service` or nav state). Default `'sales'`.

- [ ] **Step 2: Add the Service-only field.** When `documentType === 'service'`, render a "Nr. comandă service" text input bound to `service_order_ref`; hide it for Sales. Relabel the form heading/CTA to "Predare mașină de curtoazie" for Service.

- [ ] **Step 3: Include the fields in the submit payload.** Add `document_type` and (when present) `service_order_ref` to the `submitTestDrive(...)` payload.

- [ ] **Step 4: Verify.** Run: `cd jarvis/frontend && npm run build` — Expected: 0 TS errors. `cd ../..`.

- [ ] **Step 5: Commit.**
```bash
git add jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx
git commit -m "feat(foi-parcurs): Service order field + relabel in session form"
```

---

### Task 14: Service contract PDF

**Files:**
- Modify: `jarvis/foi_parcurs/services/pdf_service.py` (add `generate_service_contract_pdf`)
- Modify: `jarvis/foi_parcurs/routes/pdf.py` (dispatch on `document_type` ~line 181)

**Interfaces:**
- Consumes: `ContractConfigRepository.get_active` (Task 5), `render_contract_template` + `PLACEHOLDERS` (Task 4).
- Produces: `generate_service_contract_pdf(contract) -> path`; the legal-PDF dispatch calls it when `contract['document_type'] == 'service'`.

- [ ] **Step 1: Implement the generator.** In `pdf_service.py`, add `generate_service_contract_pdf(contract)` that: looks up `ContractConfigRepository().get_active(contract['company_id'], contract.get('vehicle_brand'), 'service')` (the contract row from `get_contract_by_id` already carries `vehicle_brand` via `v.brand AS vehicle_brand`); builds a `context` dict from the contract row keyed by the `PLACEHOLDERS` names; calls `render_contract_template(cfg['title'], ctx)` and `render_contract_template(cfg['body_template'], ctx)`; then lays the rendered title/body/conditions out using the **existing** PDF primitives in this file, reusing the same signature/damage/km-fuel blocks `generate_legal_pdf` uses. Write to `os.path.join(_PDF_DIR, f'{cid}-service.pdf')`. If no active config, fall back to `generate_legal_pdf` (so a misconfig never 500s).

- [ ] **Step 2: Dispatch on document_type.** In `pdf.py` where `generate_legal_pdf(contract)` is chosen (~line 181), branch: `generate_service_contract_pdf(contract) if contract.get('document_type') == 'service' and pdf_type == 'legal' else (generate_legal_pdf(contract) if pdf_type == 'legal' else generate_custom_pdf(contract))`. Import the new function.

- [ ] **Step 3: Verify.** Run: `python3 -m py_compile jarvis/foi_parcurs/services/pdf_service.py jarvis/foi_parcurs/routes/pdf.py` — Expected: exit 0. `python -m pytest tests/ -x -q` — Expected: green.

- [ ] **Step 4: Manual smoke.** Create a Service session (Service-enabled company, Service car), open its legal PDF, confirm it renders the company's templated title/body with placeholders substituted and the signature/km blocks intact.

- [ ] **Step 5: Commit.**
```bash
git add jarvis/foi_parcurs/services/pdf_service.py jarvis/foi_parcurs/routes/pdf.py
git commit -m "feat(foi-parcurs): per-company templated Service contract PDF"
```

---

## Final verification (whole plan)

- [ ] **Full gate:** `cd jarvis/frontend && npm run build` (0 TS errors) · `cd ../.. && python -m pytest tests/ -x -q` (green) · `python3 -m py_compile jarvis/app.py`.
- [ ] **End-to-end manual:** configure a company's Service contract → toggle appears on `/app/foi-parcurs` → assign a car to the Service pool → create a Service session on it (Sales car is rejected) → PDF uses the per-company template → return + overdue behave exactly as a test drive.
- [ ] **Isolation check:** with `company=0` management view, Service rows are visible (badge) and never leak into a Sales-filtered list; a non-enabled company shows no toggle and all its rows stay `sales`.

## Out of scope (follow-up plans)

- **Phase 4 — Hub tile + `HubCourtesyPanel`** (`jarvis/frontend/src/pages/Hub/index.tsx` `appTiles` + a `documentType='service'` wrapper over `HubDrivingPanel`).
- **Phase 5 — Mobile** (`jarvis-mobile-2`: separate "Mașini de curtoazie" launcher icon + Service screen set over the existing mobile session endpoints; needs its own exploration first).
- Migrating the **Sales** contract into `fp_contract_configs` (today it stays on the hardcoded template).
