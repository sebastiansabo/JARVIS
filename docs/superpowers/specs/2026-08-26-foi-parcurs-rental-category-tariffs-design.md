# Foi de Parcurs — Category-based, duration-tiered rental tariffs

**Date:** 2026-08-26
**Depends on:** [[project_foi_parcurs_document_types]] + Service context (rental pricing) — both now on PROD.
**Source data:** `Tarife Coporate - Sharetoo Rent Octombrie 2025.pdf` (SHARETOO RENT corporate tariffs, EUR ex-VAT).

## Problem

Today a courtesy car's rental price is a **per-car flat** `svc_tariff_eur_day` (<30 days)
/ `svc_tariff_eur_month` (≥30 days), resolved car-value-first then a single company
default. Real corporate pricing is **category-based and duration-tiered**: a car
belongs to a **category** (ECONOMY … LUXURY), and the daily rate steps down as the
rental gets longer across **intervals** (1-8 / 9-30 / 31-90 / 91-180 / 181+ days).
Franchise and extra-km are per category. The current model can't express any of this.

## Goals

- **Categories** (per company) with a **duration-interval × €/day price matrix**.
- **User-defined intervals** (global per company; edit the day boundaries in Settings).
- Each courtesy car **assigned to a category**; its rental price derives from the
  category × the interval that matches the rental's day-count.
- Per-category **franchise** (€/event) and **extra-km** (€/km).
- Settings UI to manage intervals + the category price grid (mirrors the PDF).
- Seed the full **Sharetoo scheme** for Autoworld PREMIUM (co11) as a starting point.

## Decisions (locked with user)

1. **Transmission is NOT a pricing dimension** — one €/day per (category, interval);
   transmission is only a label (not stored/priced in v1).
2. **Daily-interval pricing only** — total = `eur_per_day(category, interval(days)) ×
   days`. The monthly-estimate columns (1-3 / 3-6 / >6 months) are reference only and
   are **deferred** (not built in v1).
3. **Intervals are global + user-defined per company** — one interval set applied to
   all that company's categories.
4. **Categories are per-company.**

## Non-goals (v1 / deferred)

- Monthly-subscription pricing mode + the estimated-monthly display columns.
- Transmission as stored data / a pricing axis.
- Per-car price override (category is the sole source; old `svc_tariff_eur_*` columns
  are kept for back-compat but no longer drive price).
- Auto-classifying existing cars into categories (user assigns; a best-effort seed
  mapping for the 3 known cars is a nice-to-have, not required).

## Data model (new, per company)

```
fp_rental_intervals (
  id SERIAL PK, company_id BIGINT NOT NULL,
  label TEXT NOT NULL,            -- "1-8 zile"
  min_days INT NOT NULL,          -- inclusive
  max_days INT,                   -- inclusive; NULL = open-ended (181+)
  sort_order INT NOT NULL DEFAULT 0,
  UNIQUE (company_id, min_days)
)

fp_rental_categories (
  id SERIAL PK, company_id BIGINT NOT NULL,
  name TEXT NOT NULL,             -- "SUV+"
  models_note TEXT,               -- "Skoda Karoq, VW T-Roc, Cupra Formentor" (display)
  franchise_eur NUMERIC(10,2),    -- damage franchise / event
  extra_km_eur  NUMERIC(10,2),    -- € per extra km
  sort_order INT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (company_id, name)
)

fp_rental_category_prices (
  id SERIAL PK, company_id BIGINT NOT NULL,
  category_id BIGINT NOT NULL,    -- FK fp_rental_categories
  interval_id BIGINT NOT NULL,    -- FK fp_rental_intervals
  eur_per_day NUMERIC(10,2),
  UNIQUE (company_id, category_id, interval_id)
)
```
- `fp_vehicles.rental_category_id BIGINT` (nullable FK) — the car's category.
- Existing `svc_*` columns on `fp_vehicles` / `foi_de_parcurs` are **unchanged**; the
  frozen snapshot still uses the `svc_*` fields (see mapping below), so the contract
  PDF + tokens keep working. The price *source* changes from per-car tariff → category.

### Interval matching
`days = rental_days(departure, return)` (existing helper: ceil(hours/24), floor 1).
Pick the interval where `min_days ≤ days AND (max_days IS NULL OR days ≤ max_days)`,
ordered by `min_days`. If no interval matches (misconfig) → price 0 + a logged warning
(never 500). Open-ended top band (`max_days NULL`) catches long rentals.

## Migration + seed (idempotent; localhost → staging → prod)

In `schema_incremental.py` (same discipline as prior seeds: `IF NOT EXISTS`, `ON
CONFLICT DO NOTHING`, SAVEPOINT-gated):
1. Create the 3 tables + add `fp_vehicles.rental_category_id` (DO-block guard).
2. Seed, **for co11 only** (Autoworld PREMIUM), the Sharetoo scheme:
   - 5 intervals: `1-8 (1..8)`, `9-30 (9..30)`, `31-90 (31..90)`, `91-180 (91..180)`,
     `181+ (181..NULL)`.
   - 18 categories with `models_note`, `franchise_eur`, `extra_km_eur`.
   - the full `category × interval → eur_per_day` matrix.
   - **Seed values are transcribed from the PDF**; at implementation time extract them
     precisely (`pdftotext`), don't eyeball — a wrong cell is wrong money on a contract.
3. Seed is co11-only + `ON CONFLICT DO NOTHING` so re-runs and other companies are
   untouched; admins can edit afterwards.
4. Best-effort: set `rental_category_id` on the 3 known prod courtesy cars
   (VW T-Roc → SUV+, Audi Q3 → PREMIUM SUV) — only if still NULL.

## Backend

- **Repository** `rental_category_repository.py`:
  - `list_intervals(company_id)`, `upsert_interval(...)`, `delete_interval(...)`
  - `list_categories(company_id, active_only=False)` (with their per-interval prices)
  - `upsert_category(...)`, `delete_category(...)` (guard: refuse delete if cars use it)
  - `set_price(company_id, category_id, interval_id, eur_per_day)`
  - `price_for(company_id, category_id, days) -> {eur_per_day, interval, franchise, extra_km}`
- **Routes** (admin writes; `/api/foi-parcurs/rental-tariffs/*`):
  - `GET  …/intervals?company_id` / `PUT …/intervals` / `DELETE …/intervals`
  - `GET  …/categories?company_id` (grid: categories + prices) / `PUT`/`POST`/`DELETE`
  - `PUT  …/prices` (set one cell)
  - `GET  …/categories?company_id&active=1` — lean list for the car-form dropdown.
- **`rental_pricing.py`** — new `compute_category_pricing(company_id, category_id,
  departure, return_dt, repo)`: resolve interval by day-count → `eur_per_day` → total.
  `compute_service_pricing` (existing per-car path) stays as a fallback when a car has
  **no** `rental_category_id` (back-compat), so nothing breaks pre-assignment.
- **`_resolve_service_pricing`** (test_drive submit/activate) picks category pricing
  when the vehicle has `rental_category_id`, else the legacy per-car path. Advisor
  overrides in the payload still win (unchanged).

### Snapshot / token mapping (unchanged token surface)
`compute_service_pricing` today emits exactly these keys (verified in
`rental_pricing.py:77-86`): `svc_rate_basis`, `svc_tariff_eur`, `svc_units`,
`svc_total_eur`, `svc_km_included_day`, `svc_extra_km_eur`, `svc_garantie_eur`
(= the resolved **deposit**), `svc_fransiza_eur` (= the resolved **franchise**). The
category path populates the same keys:
- `svc_rate_basis = 'day'`, `svc_tariff_eur = eur_per_day` (of the matched interval),
  `svc_units = days`, `svc_total_eur = round(eur_per_day × days, 2)`.
- `svc_fransiza_eur = category.franchise_eur`, `svc_extra_km_eur = category.extra_km_eur`.
- `svc_garantie_eur` (**deposit** — the PDF has no per-category deposit) and
  `svc_km_included_day` stay resolved from the existing car/company policy
  (`resolve_policy`), so category pricing supplies rate+franchise+extra-km and the
  deposit/km-included defaults are unchanged.

So the contract PDF + all `{svc_*}` tokens work with **zero** template changes.
**Note:** the PDF "franchise" column is a damage *franchise* → `svc_fransiza_eur`, NOT
the deposit (`svc_garantie_eur`); don't cross them.

## Frontend

- **Settings — new "Tarife închiriere" block** in the Mașini de curtoazie context:
  - **Intervale** editor: rows of `label / min_days / max_days(∞)`; add/edit/delete.
  - **Categorii** grid: rows = categories, columns = the intervals, cells = €/day
    (editable); plus `models_note`, `franchise`, `extra-km`; add/edit/delete category.
    This *is* the PDF table, editable. Uses the header company.
- **Car form** (`VehicleFormFields`, service context): the "Preț & politică" section's
  per-car tariff inputs → a **Categorie** `<Select>` (active categories for the car's
  company). Show the resolved franchise/km read-only from the chosen category. Blank
  category ⇒ legacy per-car fields still available (back-compat).
- **API client**: `getRentalIntervals/putRentalInterval/deleteRentalInterval`,
  `getRentalCategories/putRentalCategory/addRentalCategory/deleteRentalCategory/setRentalPrice`.

## Edge cases
- Car with no category → legacy per-car pricing (or €0 if none) — no crash.
- days beyond all intervals → the open-ended top band; if none open → 0 + warn.
- Deleting a category/interval in use → refused (400) with a clear message.
- Changing a category's prices later never rewrites an already-frozen contract snapshot.
- Rental spanning a boundary uses the single interval matching total day-count (not a
  blended/pro-rated rate) — matches the PDF's per-interval flat daily rate.

## Testing (TDD)
- Pure `rental_pricing.compute_category_pricing` + interval-matching (boundaries: 8/9,
  30/31, 180/181, open-ended, no-match) — unit tests.
- `rental_category_repository` (list/upsert/price_for/delete-guard) — pytest.
- Migration idempotency (apply twice; co11 seeded once; other companies untouched).
- Frontend: Settings grid renders + edits a cell; car-form category dropdown; snapshot
  maps to `svc_*`. Keep existing rental/service tests green.
- Full: build 0 TS + vitest + backend pytest.

## Rollout
localhost (seed + click-through) → staging (FF) → prod (cherry-pick/squash per the
established main workflow; prod DB migration runs the new tables + co11 seed, idempotent).

## Risks
- **Seed accuracy** — a mis-transcribed price = wrong contract money; extract from the
  PDF precisely + spot-check against the PDF before prod.
- **Back-compat** — the legacy per-car path stays as fallback so un-categorized cars
  and the current 3 courtesy cars keep working until assigned.
- **Prod DB migration** — additive (new tables + nullable column + co11-only seed);
  idempotent; no change to existing rows.
