# Bulk Session Import — Design

**Date:** 2026-07-22
**Module:** `jarvis/foi_parcurs`
**Status:** Approved (brainstorm)

## Goal

Import historical driving sessions from an Excel file, **tenant-scoped** (per
company), keyed by **VIN**. Unknown VINs auto-create the car. Re-importable
(skips duplicates). Feeds the monthly Foaie de Parcurs.

## UX

An **"Importă sesiuni"** button on the *Foi de Parcurs* tab opens a modal:
1. **Company** selector (tenant) — defaults to the header company.
2. **Descarcă template** → `.xlsx` pre-scoped to that company.
3. **Upload** the filled file → result report:
   `Inserted: N · Skipped (dup): N · Cars created: N · Errors: N`
   with a per-row error list (row number + reason).

## Template (`.xlsx`)

**Sheet 1 "Sesiuni"** — one row per session:

| Col | Required | Notes |
|---|---|---|
| VIN | yes | links the row to a car (key) |
| Marcă | new car only | make (e.g. Audi); required when VIN is new |
| Model | new car only | required when VIN is new |
| Nr. înmatriculare | no | shown on the sheet |
| Combustibil | no | default `Diesel` |
| Capacitate rezervor (L) | no | default `50` |
| Brand | no | defaults to Marcă; drives header brand filter |
| Plecare | yes | departure date+time; `dd.mm.yyyy HH:MM` or ISO |
| Sosire | no | arrival date+time |
| KM start | yes | integer |
| KM end | yes | integer > KM start |
| Șofer | no | driver name → `client_name` |

Car-identity columns are used **only when the VIN is new**; ignored if it exists.

**Sheet 2 "Mașini"** — reference list of the selected company's cars (Model, VIN).
A header row is included with one example row on Sheet 1.

## Backend

New `foi_parcurs/services/session_import_service.py` + routes in
`foi_parcurs/routes/` (registered via `routes/__init__.py`):

- `GET /api/foi-parcurs/sessions/import-template?company_id=` →
  `.xlsx` (headers + example + "Mașini" sheet). `@login_required`.
- `POST /api/foi-parcurs/sessions/import` (multipart: `file`, `company_id`) →
  parse → validate → insert → `{success, inserted, skipped, cars_created,
  errors:[{row, message}]}`. `@login_required`.

### Row processing (per data row)

1. **Resolve VIN** in `fp_vehicles`:
   - exists & `company_id == selected` → use it;
   - exists & different company → **reject** (tenant violation);
   - not found → **create** `fp_vehicles` (vin, mark=Marcă, model=Model,
     registration_number, fuel_type|Diesel, fuel_tank_capacity_liters|50,
     brand|Marcă, company_id=selected, is_active=TRUE) → count `cars_created`.
     Requires Marcă+Model, else row error.
2. **Build session** → insert into `foi_de_parcurs`:
   - `vin`, `company_id`(selected), `departure_datetime`=Plecare,
     `return_datetime`=Sosire, `km_start`, `km_end`,
     `distance_km`=end−start, `client_name`=Șofer,
     `year`/`month` from Plecare, `status='COMPLETED'`, `source='import'`.
   - `route_type`: `TD` if distance ≤ company `fp_km_configs.td_km_max` (def 50)
     else `Comodat`.
   - Fuel/gauge defaults: tank from vehicle|50, gauge `'1'/'1'`, liters `0/0/0`.
   - `registration_number` from the vehicle.
   - `contract_id` = `IMPORT_{safe_vin}_{yyyymmdd}_{km_start}_{km_end}` (encodes
     VIN+date+km → idempotent).
3. **Insert** with `ON CONFLICT (contract_id) DO NOTHING` → conflicts counted as
   **skipped** (dedup). New-car creation likewise idempotent (`ON CONFLICT (vin)`).

### Validation (partial import — valid rows import, invalid reported)

Row errors (non-fatal): missing VIN; VIN in another company; new VIN without
Marcă/Model; unparseable Plecare; `KM end ≤ KM start`; Sosire before Plecare.
The whole import runs in one transaction per row batch; a row error skips that
row only.

## Tenant scoping

"Tenant based" = the import is bound to the **selected company**. Every session
and any auto-created car attach to it; a VIN owned by another company is
rejected. (Data-level scoping — independent of the auth/IDOR discussion.)

## Out of scope (YAGNI)

- Editing/deleting imported sessions in bulk (use existing per-session tools).
- CSV format (Excel only).
- Column mapping UI (fixed template).
