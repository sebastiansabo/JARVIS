# Mobile Parc Auto (Driving Park) — Design

**Date:** 2026-07-22
**Repos:** JARVIS backend (`dev`) + jarvis-mobile-2 (`main`)
**Status:** Approved

## Goal
A read-only "Parc Auto" section in the mobile Sales launcher: list the user's
company vehicles (mileage + on-TD badge) → detail (full info + view/open the
documents uploaded via the JARVIS web app: Asigurare, Talon, CIV, Doc
înmatriculare, Ofertă).

## Decisions
- **Access:** universal (all authenticated users), like Test Drive.
- **List scope:** vehicles of the logged-in user's company; searchable.
- **Documents:** preview images inline; PDFs written to cache and opened/shared
  via the OS. Read-only — uploads remain web-only.

## Backend facts (already exist)
- `fp_vehicles.odometer_km` = current mileage (auto-advanced on TD return).
- Docs are base64 data-URLs in `fp_vehicles` columns: `insurance_doc`,
  `talon_doc`, `civ_doc`, `registration_doc`, `offer_doc` (no separate table).
- Lean list `GET /vehicles` omits blobs; `GET /vehicles/<id>` returns full row.
- "On TD" isn't a column — derived from `foi_de_parcurs` `td_status`.

## Backend changes (JARVIS, dev)
1. `vehicle_repository.py` `_LIST_SELECT`: add cheap booleans
   `insurance_doc IS NOT NULL AS has_insurance` (+ talon/civ/registration/offer)
   so the app knows which docs exist without downloading blobs.
2. New `GET /api/foi-parcurs/vehicles/<int:id>/documents/<doc_type>`
   (`@login_required`), `doc_type` ∈ insurance|talon|civ|registration|offer.
   Returns `{success, type, filename, data_url}` for just that one doc.
   400 unknown type, 404 unknown vehicle or empty doc.

## Mobile changes (jarvis-mobile-2, main)
- Extend `FpVehicle` type: `brand, color, fuel_type, vignette_valid_until,
  itp_valid_until, insurance_valid_until, has_insurance, has_talon, has_civ,
  has_registration, has_offer`.
- New lazy hook `useFpVehicleDocument()` (mutation) → GET the single doc.
- `SALES_APPS` tile "Parc Auto"; routes `/sales/parc-auto`, `/sales/parc-auto/:id`.
- **List** (`Sales/ParcAuto/index.tsx`): `useFpVehicles()` filtered to the user's
  company; search by plate/mark/model; card shows mark/model, plate,
  `odometer_km`, and a badge "În TD"/"Disponibil" from `useTestDrives()`
  (`td_status` driving/incomplete → Set<vin>).
- **Detail** (`Sales/ParcAuto/Detail.tsx`): full info + validity dates (expiry
  highlight) + Documents section (only `has_*` docs), Romanian labels. Tap →
  lazy-fetch doc → image previews inline (modal `<img>`); PDF → filesystem cache
  + Share.
- Doc-open util (`Sales/ParcAuto/openDoc.ts`): decode data-URL; image → preview
  callback; PDF → `Filesystem.writeFile` (cache) → `Share.share({files:[uri]})`.
- New dependency: `@capacitor/filesystem` (`@capacitor/share` already present).

## Testing
- Backend pytest: per-document endpoint (valid → data_url; empty → 404; bad type
  → 400; unknown vehicle → 404); has_* flags present on list.
- Mobile manual: company list w/ mileage + TD badge; open an image doc and a PDF
  doc; no-docs empty state.

## Out of scope
- Editing/uploading vehicles or docs from mobile.
- The separate `pages/CarPark/` sales-inventory module (naming collision).
