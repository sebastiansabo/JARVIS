# Foi de Parcurs — Service context ("Mașini de curtoazie") — Design

- **Date:** 2026-08-24
- **Branch:** `feature/foi-parcurs-service-context` (off `dev`)
- **Status:** Design — awaiting review, no implementation yet
- **Module:** `jarvis/foi_parcurs/` (Driving Hub) + `jarvis/frontend/src/pages/{FoiParcurs,Hub}` + `jarvis-mobile-2`

## 1. Problem

The Driving Hub (`/app/foi-parcurs`) today handles **Sales** driving: client test drives and Comodat loans, each producing a legal "foaie de parcurs" contract. A second, parallel use case exists on the **Service** side of each dealership: **courtesy / replacement cars** ("mașini de curtoazie") handed to a service customer while their car is being repaired. This is the *same operational flow* (a car is handed over, driven, and returned) but a **different contract document**, a **separate car fleet**, and it must be **set up per company**.

We want to add a Service context that:
- reuses the entire existing session engine (lifecycle, return, odometer, calendar, signatures, alerts),
- keeps Sales and Service data separated by a real partition (not just a view filter),
- lets each company (per brand) configure its own courtesy-car contract in an admin zone,
- surfaces as a **toggle** on the standalone `/app/foi-parcurs` page, but as a **separate icon + zone** on the Hub and in the mobile app.

## 2. Decisions (locked)

| Question | Decision |
|---|---|
| What is "Service"? | Courtesy/replacement car ("Mașini de curtoazie") — same drive/return engine, different contract + a service-order link |
| Switch behaviour | Per-tenant **header context toggle** on `/app/foi-parcurs`; **separate icon + zone** on Hub and mobile |
| Number of document types | Unknown — use a **generic discriminator** now, graduatable to a per-company registry with no row migration |
| Car pool | **Separate fleet** — a car belongs to exactly one pool |
| Return window | **Same as test drive** — full reuse of scheduled-return + overdue-alert |
| Contract authoring | **Editable text template** per company+brand, with `{placeholders}`, rendered by the existing PDF engine |
| Setup zone location | Driving Hub → **Settings tab** |
| Config scope | **Per company + brand** (mirrors `fp_dealer_config`) |
| Permissions | **Shared** — anyone with `can_access_carpark` sees both contexts; no new permission flag |
| User-facing label | **"Mașini de curtoazie"** (internal key `document_type='service'`); Sales = "Vânzări" |

## 3. Existing architecture (grounding)

- One table `foi_de_parcurs` already carries orthogonal type axes: `route_type` (`TD`/`Comodat`), `source` (`td_form`/`batch`/`import`/`gap-fill`), `is_internal`, `status`, `company_id`. Schema: `jarvis/migrations/domains/schema_incremental.py:1919`.
- Tenant scoping is by explicit `company_id` passed from the UI selector (`foi_parcurs_repository.py:79`); the vehicle fleet and companies list are fetched unscoped and filtered client-side (`routes/vehicles.py:29`, `index.tsx` fleet filter).
- Per-tenant config already lives in `fp_dealer_config` (per company+brand: `general_conditions`, contact, `show_in_foi_parcurs`), `fp_km_configs`, `fp_company_config`, `fp_routes`.
- The Sales contract body is **hardcoded** Romanian test-drive clauses in `services/pdf_service.py:80-299`; `generate_legal_pdf`/`generate_custom_pdf` (`routes/pdf.py:181`).
- Toggle precedents to follow: `DriveTypeToggle.tsx` (segmented control) and `SessionTypeChooser.tsx` (create-flow chooser).
- Single blueprint `foi_parcurs_bp`, all routes `/api/foi-parcurs/*` (`app.py:269`, no url_prefix).
- Web Hub is a tile registry: `appTiles` in `jarvis/frontend/src/pages/Hub/index.tsx:114`; the Driving tile (`key:'driving'`, `HubDrivingPanel`) opens an in-page panel.

## 4. Data model

All DDL is idempotent (`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`) in `jarvis/migrations/domains/schema_incremental.py`, mirroring the `is_internal` block (line ~1983).

**4.1 Session discriminator** — on `foi_de_parcurs`:
```sql
ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS document_type VARCHAR(16) NOT NULL DEFAULT 'sales';
ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS service_order_ref VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_foi_parcurs_doctype ON foi_de_parcurs(company_id, document_type);
```
- Values: `'sales'` | `'service'`. **Orthogonal to `route_type`** — a Service session carries `document_type='service'` with `route_type='Comodat'` (a loaner is legally a bailment), so every existing `WHERE route_type='TD'` query is untouched.
- Add `document_type` and `service_order_ref` to the lean list projection `_LIST_COLUMNS` (`foi_parcurs_repository.py:17`).

**4.2 Fleet pool** — on `fp_vehicles`:
```sql
ALTER TABLE fp_vehicles ADD COLUMN IF NOT EXISTS document_type VARCHAR(16) NOT NULL DEFAULT 'sales';
```
- A car belongs to exactly **one** pool. (If a car ever needs both pools, graduate to a `fp_vehicle_pools` join table — no data migration of existing rows.)

**4.3 Per-company+brand contract config** — new table:
```sql
CREATE TABLE IF NOT EXISTS fp_contract_configs (
    id            BIGSERIAL PRIMARY KEY,
    company_id    BIGINT NOT NULL,
    brand_id      BIGINT NOT NULL,
    document_type VARCHAR(16) NOT NULL DEFAULT 'service',
    title         VARCHAR(255),
    body_template TEXT,               -- clauses with {placeholders}
    general_conditions TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (company_id, brand_id, document_type)
);
```
- This is the **registry, scoped to Service first**. Sales keeps its hardcoded template until/unless a `document_type='sales'` row exists (future migration path — out of scope now).

## 5. Enablement (derived — no separate flag)

A `(company, brand)` **has Service** iff it has an active `fp_contract_configs` row with `document_type='service'`. Consequences:
- The header toggle / Hub tile / mobile icon appear for a company only when at least one of its brands is configured.
- Setting up the contract in the Settings zone **is** the enablement action — nothing else to flip.
- New endpoint `GET /api/foi-parcurs/service-enabled?company_id=…` → `{ enabled: bool, brands: [brand_id…] }` for the UIs to gate on. (Cheap `EXISTS` query.)

## 6. Backend changes

**6.1 Write path** (`routes/test_drive.py:73` `api_submit_test_drive` → `create_from_td_form`):
- Accept `document_type` (default `'sales'`) and `service_order_ref` in the body; thread them into the insert next to `is_internal`.
- **Pool-match validation:** reject with 400 if `document_type != vehicle.document_type` (a Service session may only start on a Service car, and vice versa).
- When `document_type='service'`, resolve `general_conditions`/template from `fp_contract_configs` for `(company_id, vehicle.brand_id, 'service')` instead of `fp_dealer_config`.

**6.2 Read/filter path** (`repositories/foi_parcurs_repository.py:52` `get_contracts` + `routes/contracts.py:170`):
- Add a `document_type` filter param, mirroring the existing `route_type` filter (`WHERE fp.document_type = %s`). Default omitted = all (management view).

**6.3 Fleet partition** (`routes/vehicles.py:29` `GET /api/foi-parcurs/vehicles`, `vehicle_repository.py:107`):
- Add an optional `document_type` query param → `WHERE document_type = %s`, so the Driving Park and the car picker load only the active pool at the query (upgrade from today's client-side-only filtering).
- Vehicle create/edit accepts `document_type` (pool selector in the add/edit UI).

**6.4 Contract config CRUD** — new routes on `foi_parcurs_bp`:
- `GET  /api/foi-parcurs/contract-configs/<int:company_id>` → per-brand list (LEFT JOIN `company_brands`, mirroring `dealer_config_repository.list_for_company`).
- `PUT  /api/foi-parcurs/contract-configs/<int:company_id>/<int:brand_id>` → upsert `{title, body_template, general_conditions, is_active}` for `document_type='service'`.
- New `ContractConfigRepository` (mirrors `DealerConfigRepository`).
- Admin-gated for writes (`role_name in ('admin','superadmin')`, per the existing pattern in `contracts.py`).

## 7. Contract PDF

- Add a new `generate_service_contract_pdf(contract, config)` in `pdf_service.py`, dispatched from the same point that today calls `generate_legal_pdf` (`routes/pdf.py:181`), selected when `contract.document_type == 'service'`. It:
  1. loads `fp_contract_configs` for `(company_id, vehicle.brand_id, 'service')`,
  2. substitutes `{placeholders}` in `title`/`body_template`/`general_conditions` with session data,
  3. renders through the **existing** `pdf_service` layout primitives + the existing signature / damage / km-fuel blocks.
- **Placeholder tokens (initial set):** `{client_name} {client_phone} {client_address} {company_name} {brand} {vin} {registration_number} {km_start} {km_end} {distance_km} {departure_datetime} {return_datetime} {service_order_ref} {advisor_name} {general_conditions}`. Unknown tokens render literally (documented in the zone's help text). Substitution is plain string replace of a whitelisted token map — no eval, no user SQL.
- Sales PDF path unchanged.

## 8. Surfaces & navigation

The same `document_type` axis drives three surfaces. A shared **context** (`sales`/`service`) is expressed as a URL/nav param and persisted (`fp.docType`).

**8.1 `/app/foi-parcurs` (standalone web) — TOGGLE.**
- New `DocTypeToggle` component (near-copy of `DriveTypeToggle.tsx`): `[Vânzări | Mașini de curtoazie]`, rendered in the header row next to the company/brand selectors (`FoiParcurs/index.tsx:201-228`), **shown only when the selected company has Service enabled**.
- Value persisted to `fp.docType`; passed as a prop through every tab (like `brand`/`driveType`); becomes the `document_type` param on the vehicle + contract list calls and on new sessions.
- Reads an initial `?context=service` query param (so Hub/mobile deep-links land pre-set).

**8.2 Web Hub — SEPARATE TILE + ZONE.**
- Add an `appTiles` entry (`Hub/index.tsx:114`): `{ key: 'courtesy', label: 'Mașini de curtoazie', shortLabel: 'Curtoazie', icon: <CarFront/KeyRound>, bg: 'bg-indigo-600', fg: 'text-white' }`, distinct from the existing `driving` tile.
- Gated in `visibleTiles` (`Hub/index.tsx:241`) on the same access as `driving` **AND** on Service being enabled for the user's company(ies).
- Opens a dedicated **`HubCourtesyPanel`** — a thin wrapper that renders the existing `HubDrivingPanel` with a new `documentType='service'` prop, so it's a separate zone with zero logic duplication. The existing Driving panel stays Sales-only (`documentType='sales'`, the default).

**8.3 Mobile (`jarvis-mobile-2`) — SEPARATE ICON + ZONE.** *(own phase; needs a short jarvis-mobile-2 exploration before build)*
- A separate launcher icon "Mașini de curtoazie" on the mobile home, distinct from the existing Driving / Test Drive entry.
- Its screens reuse the mobile session flow with `document_type='service'` passed through the mobile session endpoints (`/api/mobile/…` JWT-twin). Backend reuse is automatic once §6 accepts the param; the mobile work is the icon + a Service-scoped screen set + contract preview.
- Follow the standing mobile rules: `npm run build && npx cap sync android`; update `src/data/changelog.ts`; CI APK → promote staging→main.

## 9. Setup zone (Driving Hub → Settings tab)

- New section in `SettingsTab` (inside `FoiParcurs/index.tsx`), admin-gated, scoped to the selected company.
- Per brand: edit `title`, `body_template` (multi-line, with a `{placeholder}` cheat-sheet), `general_conditions`, and an `is_active` toggle; **Save** upserts via §6.4.
- Live "used placeholders / unknown placeholders" hint; a "Preview PDF" action rendering a sample contract with dummy session data.

## 10. Isolation model

- **Real data partition, not just a view filter:** every session and every vehicle carries `document_type`; the submit-time pool-match rule (§6.1) means Service sessions cannot attach to Sales cars. Lists/fleet endpoints filter by `document_type` server-side.
- **Not a permission boundary:** per the locked decision, access is shared (`can_access_carpark`); the toggle/zone are UX + data separation, not a security wall. If a hard permission split is needed later, add a `document_type`-scoped access flag and gate the endpoints (explicitly out of scope now).

## 11. Scope

**Reused unchanged:** PLANNED→FILLED→COMPLETED/MISSED lifecycle, activation/return, odometer continuity + single-open-session rule, calendar, signatures, damage, overdue-return alert, session history/audit, export.

**New work:** 1 migration (§4); `document_type`/`service_order_ref` threading (§6.1–6.2); fleet `document_type` param + vehicle pool selector (§6.3); `fp_contract_configs` + `ContractConfigRepository` + CRUD (§6.4); service-enabled endpoint (§5); Service PDF (§7); `DocTypeToggle` + standalone wiring (§8.1); Hub `courtesy` tile + `HubCourtesyPanel` (§8.2); mobile icon + Service screens (§8.3); Settings setup zone (§9).

## 12. Phasing

1. **Phase 1 — Data + backend:** migration, write/read/fleet threading, pool-match validation, `fp_contract_configs` + CRUD, service-enabled endpoint. (No UI-visible change beyond Settings API.)
2. **Phase 2 — Contract setup zone:** Settings section (author + preview). Turning on the first company validates end-to-end.
3. **Phase 3 — Standalone toggle:** `DocTypeToggle`, context param, fleet/list wiring, Service PDF on submit.
4. **Phase 4 — Hub tile + zone:** `courtesy` tile, `HubCourtesyPanel`, gating.
5. **Phase 5 — Mobile:** icon + Service screens in `jarvis-mobile-2` (own exploration).

Each phase is independently shippable; Phases 1–2 gate the rest.

## 13. Testing

- **Backend (pytest):** migration idempotency; pool-match validation (Service session on Sales car → 400 and vice versa); `get_contracts` document_type filter; contract-config upsert per (company,brand); service-enabled EXISTS logic; placeholder substitution (all tokens + unknown-token literal render); Service PDF generation smoke test.
- **Frontend (vitest):** `DocTypeToggle` render/persist; toggle hidden when Service disabled; `?context=service` deep-link presets context; Hub tile visibility gating; Settings zone save round-trip.
- **Manual/e2e:** set up a company's courtesy contract → toggle appears → create a Service session on a Service car → generated PDF uses the per-company template → return flow + overdue alert behave as test drive.

## 14. Open items / risks

- **Existing rows** default to `document_type='sales'` and `fp_vehicles.document_type='sales'` — correct (all current data is Sales). No backfill needed.
- **Company=0 (all-companies management view):** toggle hidden; Service rows shown with a small badge so management still sees everything without leaking contexts. (Confirm desired.)
- **Mobile (Phase 5)** needs its own jarvis-mobile-2 exploration (launcher registry + session screens + `/api/mobile` params) before estimation.
- **`route_sheet`/batch/monthly** flows are Sales-only for now (they generate retroactive TD/Comodat logs); Service is live-session-only. Confirm Service never needs the monthly batch generator.
- **Odometer/single-open-session** are global per VIN and remain so — a car in one pool can't be double-booked, which is correct.
