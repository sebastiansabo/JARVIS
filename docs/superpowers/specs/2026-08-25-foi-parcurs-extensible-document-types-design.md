# Foi de Parcurs — Extensible, user-defined document types + per-type contracts

**Date:** 2026-08-25
**Branch:** feature/foi-parcurs-service-impl (staging line)
**Status:** design — awaiting user review before plan
**Supersedes (partially):** the per-(company, brand) `fp_contract_configs` model
from `2026-08-24-foi-parcurs-service-courtesy-cars-design.md` and
`2026-08-24-service-courtesy-rental-contract-design.md`.

## Problem

Today `document_type` is a fixed two-value enum (`sales` | `service`) baked into
code (`foi_parcurs/document_types.py: VALID`), and contract templates are stored
**per (company, brand, document_type)** in `fp_contract_configs`. This has two
problems the user hit:

1. **Per-brand templates are redundant.** The templates are tag-based
   (`{brand}`, `{vehicle_model}`, …), so one template serves every brand. The
   Settings UI shows one editable card per franchise brand (AAP, Audi, …) — noise.
2. **Types are not extensible.** Users can only ever have Sales and Service.
   They want to define additional document types (e.g. "Comodat", a rent-a-car
   variant, …), each with its own contract, and pick any of them when adding a car.

## Goals

- Document types are **user-defined per company**, managed in Settings, each with
  its own contract template (title + body + T&C) and an active flag.
- Drop the **brand** axis from contract templates (one template per type).
- The Settings contract editor is **collapsible** (one card per type).
- The vehicle **"Parc / Tip document"** selector and the standalone page's
  **header type selector** list the company's active types dynamically.
- **`sales` remains a fixed, non-deletable default** (all legacy data is sales;
  it uses the legacy `generate_legal_pdf`, has no editable template).

## Non-goals (deferred)

- Hub "tile/zone per type" (Phase 4 today ships a single Service tile).
- Mobile (jarvis-mobile-2) per-type screens.
- Cross-company / global type sharing — types are per company.
- Reworking the €0-tariff guard (separate, still pending).

## Design

### Data model — single registry table (Approach A)

A document type *is* its contract. Retire the per-brand `fp_contract_configs`
and introduce one table:

```
fp_document_types (
  id                  SERIAL PRIMARY KEY,
  company_id          INTEGER NOT NULL,
  key                 TEXT NOT NULL,          -- stored on vehicles/sessions (slug)
  label               TEXT NOT NULL,          -- user-facing (e.g. "Mașini de curtoazie")
  title               TEXT,                   -- contract title  (NULL for sales)
  body_template       TEXT,                   -- contract body   (NULL for sales)
  general_conditions  TEXT,                   -- T&C             (NULL for sales)
  is_rental           BOOLEAN NOT NULL DEFAULT FALSE,  -- rental (rent-a-car) type: has pricing
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  is_default          BOOLEAN NOT NULL DEFAULT FALSE,  -- exactly the sales row
  sort_order          INTEGER NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, key)
)
```

- **`is_rental` separates rental from everything else (esp. Vânzări).** Only
  rental types expose the car pricing fields (`{svc_*}` tariff/garanție/franșiză/
  km) and freeze a rental pricing snapshot on a session. `sales` is **always**
  `is_rental=false` (and non-editable). A non-rental custom type may still have a
  contract template (rendered without `{svc_*}` tags) but shows no pricing UI.
- `key` is the value already stored on `fp_vehicles.document_type` and
  `foi_de_parcurs.document_type` (those columns are unchanged). For new types the
  key is a slug of the label (`slugify(label)`, deduped per company); `sales` and
  `service` keys are preserved from migration.
- The **sales** row: `key='sales'`, `is_default=true`, template columns `NULL`
  (sales uses the legacy legal PDF, not a template). Not deletable / not
  deactivatable via the API.

### Migration (idempotent; localhost → staging; NEVER prod)

Runs from `schema_incremental.py` (same path S1 used), guarded so re-runs are
no-ops and a failure is SAVEPOINT-scoped (never aborts the startup schema txn):

1. `CREATE TABLE IF NOT EXISTS fp_document_types (...)`.
2. For every `company_id` present in `companies`: `INSERT ... ON CONFLICT DO
   NOTHING` a `sales` default row (`label='Vânzări'`, `is_default=true`).
3. Collapse existing `fp_contract_configs` rows with `document_type='service'`
   into **one** `service` row per company (`label='Mașini de curtoazie'`,
   **`is_rental=true`**), taking `title/body_template/general_conditions` from any
   active brand row for that company (they are identical, tag-based). `ON CONFLICT
   (company_id, key) DO NOTHING` so re-runs are safe.
4. `fp_contract_configs` is left in place but no longer read (drop in a later
   cleanup once verified); no destructive change to shipped data.

### Backend

- `foi_parcurs/document_types.py`:
  - `normalize(value)` unchanged (blank/None → `sales`; returns the lowercased
    string otherwise). It stays pure (no DB).
  - `pools_match(a, b)` unchanged — already generic equality; needs no enum.
  - Remove reliance on the fixed `VALID` set for validation. Validity is now
    "exists as an active row for this company", enforced at the repo/route layer.
- New repository `document_type_repository.py`:
  - `list_for_company(company_id, active_only=True) -> [{key,label,is_rental,has_template,is_default,is_active,sort_order}]`
  - `get(company_id, key)` (full row incl. template)
  - `upsert(company_id, key|None, label, title, body_template, general_conditions, is_rental, is_active)`
    — insert (slug key from label) or update; guards: cannot deactivate/rename the
    default `sales`; label required.
  - `get_template(company_id, key)` used by the PDF.
- New routes (admin-gated for writes, mirroring the existing contract-config
  routes; **no SQL in routes** per the architecture hook):
  - `GET  /api/foi-parcurs/document-types?company_id=` → active types (used by the
    header selector + the vehicle "Parc / Tip document" selector).
  - `PUT  /api/foi-parcurs/document-types` (body: company_id, key, label, title,
    body_template, general_conditions, is_rental, is_active) → upsert.
  - `POST /api/foi-parcurs/document-types` → add (label ⇒ slug key).
  - These replace `GET /service-enabled` and the per-brand `GET/PUT
    /contract-configs`. `service-enabled` semantics fold into "is `service` (or any
    non-sales type) active for this company".
- PDF: `sales` → `generate_legal_pdf` (unchanged). **Any other type with a
  template** → `generate_service_contract_pdf`, resolving the template by
  `(company_id, document_type)` from `fp_document_types` (was brand-based); it
  renders whatever tags the template uses, so a non-rental type simply omits
  `{svc_*}`. The self-resolving company-legal + client cui/ci fallbacks stay. The
  rental pricing **snapshot** (svc_* on the session, submit/activate) is written
  only when the type `is_rental`.
- Enablement: a company "has non-sales types" iff `list_for_company` returns any
  active non-default row. The standalone page shows the type selector whenever
  there is more than one active type.

### Frontend (scope: Settings + car selector + header selector)

- **`documentType.ts`**: `DocType` becomes `string` (was `'sales' | 'service'`).
  `DOC_TYPE_LABELS` stays as a *fallback* map for `sales`/`service`; live labels
  come from the API. `contextFromSearch` unchanged (`?context=` still carries a key).
- **New API client methods** in `api/foiParcurs.ts`: `getDocumentTypes(companyId)`,
  `putDocumentType(...)`, `addDocumentType(...)`. Keep `getVehicles`/`getContracts`
  `document_type` params as-is (already generic strings).
- **Settings → Contracte (`ContractConfigSection` → rewritten as
  `DocumentTypesSection`)**: a list of **collapsible** cards, one per type for the
  header company: label, title, body_template, general_conditions, an
  **"Închiriere (rent-a-car)" toggle (`is_rental`)**, an active toggle,
  plus **"+ Adaugă tip document"** (prompts for a label, creates the row, expands
  it). The token cheat-sheet (all 38 placeholders) stays, shown once above the
  list. `sales` renders read-only (default; no template, `is_rental` forced off).
  Uses the header company (as shipped in JAR-1319).
- **Header selector (`DocTypeToggle` → `DocTypeSelect`)**: a dropdown of the
  company's active types (label→key). Selecting sets `docType`. When only `sales`
  is active it can hide (parity with today's "no toggle unless service enabled").
  The `serviceEnabled` gate generalizes to `documentTypes.length > 1`.
- **Add Vehicle "Parc / Tip document"** (`VehicleFormFields`): options come from
  `getDocumentTypes(companyId)` (dynamic), not a hardcoded two-item list. Still
  `lockDocType` in the Add form (bound to the header type). Edit stays editable
  (choose among active types).
- **Rental pricing (separated from Vânzări):** the car's "Preț & politică
  (Mașini de curtoazie)" block + the rental pricing snapshot show **only when the
  selected type `is_rental`** (was `=== 'service'`). `sales` is never rental, so
  Vânzări never shows pricing. A non-rental custom type may still have a contract
  template but no pricing UI. To resolve `is_rental` in the car form, the vehicle
  type options carry the flag (`getDocumentTypes` returns `{key,label,is_rental}`).
- Everything else already keys off `documentType` as an opaque string
  (SessionsTab/StockTab/CalendarTab/ContractsTab/HubDrivingPanel filtering,
  pools_match) — **no change**.

### Edge cases

- **Deleting/deactivating a type that cars still use:** deactivation hides it from
  the selectors but existing cars/sessions keep their `document_type` key and
  still render (label falls back to the key if the row is inactive). Cannot
  deactivate `sales`.
- **Slug collisions:** `slugify(label)` deduped per company (`-2`, `-3`).
- **A car on an inactive/removed type:** its list still shows it (filter is by
  key equality); the header selector just won't offer that key.
- **Company with no `service` history:** migration seeds only `sales`; the type
  selector is hidden until the user adds a type.
- **`normalize` default:** any unknown/blank key → `sales`, preserving legacy rows.

### Testing (TDD)

- Backend: `document_type_repository` (list/upsert/slug/guard-sales) unit tests;
  migration idempotency (apply twice, assert one sales row per company + collapsed
  service). PDF resolves by (company, type); sales → legal PDF.
- Frontend: `DocumentTypesSection` renders a collapsible card per type + add flow;
  `DocTypeSelect` lists active types; `VehicleFormFields` options come from the API
  and lock in Add; rental block shows for a non-sales type. Keep the existing
  isolation tests green (they use opaque string keys already).
- Full: `npm run build` 0 TS + full vitest; backend pytest for the new repo/routes.

### Rollout

- Build 0 TS + tests green → FF to **staging only** (never main without 2
  confirmations). Migration runs on staging deploy (idempotent). Prod untouched.

## Risks

- **Sales regression** — mitigated: `sales` is the default, keeps the legacy PDF,
  and all generic filtering is unchanged.
- **Migration on staging** — idempotent + SAVEPOINT-gated; `fp_contract_configs`
  is not dropped (read-path switched, data preserved for rollback).
- **`DocType` widening to `string`** — a compile-time ripple; the build surfaces
  every site. Labels now come from the API, with the static map as fallback.
