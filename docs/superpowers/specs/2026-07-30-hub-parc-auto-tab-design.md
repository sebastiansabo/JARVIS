# Parc Auto tab in Hub Driving Sessions — Design

**Date:** 2026-07-30
**Status:** Approved (design), pending implementation plan
**Branch:** dev (localhost-first; no staging/prod during build)

## Goal

Add a **"Parc Auto"** tab to the Hub's **Driving Sessions** panel (next to `Sesiuni` and
`Calendar`). The tab replicates the existing web **"Driving Park"** view at
`/app/foi-parcurs` (the `StockTab` fleet table over `fp_vehicles`) with full parity:
list + add / edit / lock-unlock / archive-restore + document uploads + odometer history.

On top of replication, the archive workflow is upgraded:

1. The header's "Arată arhivate" checkbox becomes a **segmented `Active | Arhivate`
   toggle** that fully isolates active vehicles from archived ones (never mixed).
2. Archiving a vehicle captures a **reason** (category + optional note) and a **date**
   (defaults to today, backdate allowed).
3. The Arhivate view surfaces the reason + archive date per vehicle and offers Restore.

## Decisions (confirmed with user)

- **Code approach:** Extract & share — pull `StockTab` into a new exported component,
  used by BOTH the full page and the Hub tab. Single source of truth, no drift.
- **Edit scope:** Full parity (add/edit/lock/archive/restore + docs + odometer history).
- **Archive view:** Segmented `Active | Arhivate` toggle isolating the two sets.
- **Archive reason:** Category dropdown + optional free-text note.
- **Archive date:** Date picker defaulting to today, editable (backdating allowed).

## Non-goals

- No responsive redesign of the table — it replicates the desktop table and
  horizontal-scrolls on phones inside the Hub, exactly as it does on the page today.
- No new per-action permission gating. The Driving tile is already gated by
  `can_access_carpark`; Drive Park has no per-action gates today and keeps that behavior
  (full parity). Flagged below as an accepted consequence.
- No change to the CarPark rental module (`/api/carpark`, `pages/CarPark/*`) — a
  separate domain. This work is entirely within Foi de Parcurs (`fp_vehicles`).

## Architecture

Extract the currently-private `StockTab` (in the 2950-line
`jarvis/frontend/src/pages/FoiParcurs/index.tsx`, lines ~1947–2376) into a new
**exported** component. Verified extraction boundary: every helper `StockTab` needs
(`VehicleFormFields`, `DocUpload`, `STOCK_COLUMNS`/`StockColumnKey`, `VehicleFormValue`,
`emptyVehicleForm`, `vehicleToForm`, `fmtValidity`, `validityCls`, `fileToDataUrl`,
`downscaleImage`, `fileToDoc`, `openDoc`) is used **only** by `StockTab` and its own
subcomponents. The only cross-tab dependency is `naiveDate`, already an external import
(`@/lib/naiveDate`). So the block moves cleanly with no impact on the other tabs.

The new archive UX lives inside the shared component, so it appears identically on the
full page and in the Hub tab.

## Data flow

No blob changes to the list endpoint. The component uses existing endpoints plus two new
archive/restore endpoints. React Query keys (`fp-vehicles`, `fp-companies`, `fp-brands`)
are shared, so the Hub tab and the full page share one cache.

## Components / files

### New

**`jarvis/frontend/src/pages/FoiParcurs/DrivePark.tsx`**
Wholesale move of `StockTab` + its ~12 private helpers out of `index.tsx`.
`export default function DrivePark({ companyId, brand }: { companyId: number; brand: string })`.
Imports: `foiParcursApi`, `FpVehicle` + fuel helpers + `LOCKOUT_LABELS` + `ARCHIVE_LABELS`
from types, `LockVehicleDialog`, `ArchiveVehicleDialog` (new), `VehicleOdometerHistory`,
shared `EmptyState`/`TableSkeleton`, shadcn ui, lucide icons, `useQuery`/`useQueryClient`,
`naiveDate`.

Header change:
- Replace the `Arată arhivate` checkbox with a **segmented toggle** (`mode: 'active' |
  'archived'`, shadcn `Tabs`/`ToggleGroup`) in the same header spot. Columns button stays.
- Active mode query: `getVehicles(true)` (server returns active only).
- Archived mode query: `getVehicles(false)` then client-filter `!v.is_active`
  (dataset is small; avoids a new list-endpoint param). Distinct query key per mode.

Active mode:
- Row actions: **Edit** / **Lock-Unlock** / **Archive** (Archive now opens the dialog,
  not a bare `confirm()`).
- "Add Vehicle" button shows only in active mode.
- No "Arhivat" badge needed (archived rows are isolated into the other view). The
  "🔒 Blocat" lockout badge stays.

Archived mode:
- Two extra read-only columns: **Motiv** (`ARCHIVE_LABELS[archive_category]` + note if
  present) and **Data arhivării** (`archived_at`, `ro-RO` formatted).
- Only action: **Restaurează** → `restoreVehicle(id)`.
- No add/edit/lock in this mode.

**`jarvis/frontend/src/pages/FoiParcurs/ArchiveVehicleDialog.tsx`**
Mirrors `LockVehicleDialog.tsx`. Fields: category `<Select>` (Vândut / Returnat leasing /
Casat / Sfârșit contract / Altele), optional note `<Textarea>`, date `<Input type=date>`
pre-filled with today. Confirm → calls back with `{ category, note, archived_at }`.

### Edited — frontend

**`jarvis/frontend/src/pages/FoiParcurs/index.tsx`**
Delete the moved block (helpers + `StockTab`); `import DrivePark from './DrivePark'`;
render `<DrivePark companyId={companyId} brand={brand} />` where `<StockTab .../>` was.
Net: file shrinks ~730 lines; the "Driving Park" tab looks and behaves identically.

**`jarvis/frontend/src/pages/Hub/HubDrivingPanel.tsx`**
- `type PanelTab = 'sessions' | 'calendar' | 'parcauto'`.
- Add `<TabsTrigger value="parcauto">Parc Auto</TabsTrigger>` after Calendar.
- Render `{companyId > 0 && tab === 'parcauto' && <DrivePark companyId={companyId} brand={brand} />}`.
- Hide the top "Driving Session nou" button when `tab === 'parcauto'` (it's a sessions
  action; the tab has its own "Add Vehicle").
- The panel already owns company/brand selectors + persisted state
  (`hub-driving-company`, `hub-driving-brand`, `hub-driving-tab`), which `DrivePark`
  consumes exactly like Sessions/Calendar — brand/company filtering and tab persistence
  work with no extra wiring.

**`jarvis/frontend/src/types/foiParcurs.ts`**
- `FpVehicle` gains `archive_category?: ArchiveCategory | null`, `archive_note?: string | null`,
  `archived_at?: string | null`.
- Add `type ArchiveCategory = 'sold' | 'leasing_return' | 'scrapped' | 'contract_end' | 'other'`
  and `ARCHIVE_LABELS` map:
  `sold→"Vândut"`, `leasing_return→"Returnat leasing"`, `scrapped→"Casat"`,
  `contract_end→"Sfârșit contract"`, `other→"Altele"`.

**`jarvis/frontend/src/api/foiParcurs.ts`**
- `archiveVehicle(id, { category, note, archived_at })` → `POST /api/foi-parcurs/vehicles/{id}/archive`.
- `restoreVehicle(id)` → `POST /api/foi-parcurs/vehicles/{id}/restore`.

### Edited — backend

**`jarvis/migrations/domains/schema_incremental.py`** (after the lockout ALTER block, ~line 1980)
Idempotent `ALTER TABLE fp_vehicles ADD COLUMN IF NOT EXISTS`:
```
archive_category VARCHAR(20),
archive_note     TEXT,
archived_at      DATE,
archived_by      BIGINT
```

**`jarvis/foi_parcurs/repositories/vehicle_repository.py`**
- Add `v.archive_category, v.archive_note, v.archived_at` to `_LIST_SELECT`.
- `archive(vehicle_id, category, note, archived_at, user_id)` →
  `UPDATE fp_vehicles SET is_active=FALSE, archive_category=%s, archive_note=%s,
   archived_at=%s, archived_by=%s, updated_at=NOW() WHERE id=%s RETURNING *`.
- `restore(vehicle_id)` →
  `UPDATE fp_vehicles SET is_active=TRUE, archive_category=NULL, archive_note=NULL,
   archived_at=NULL, archived_by=NULL, updated_at=NOW() WHERE id=%s RETURNING *`.

**`jarvis/foi_parcurs/routes/vehicles.py`** (mirror `lock`/`unlock`)
- `POST /api/foi-parcurs/vehicles/<int:id>/archive` — read JSON `{category, note,
  archived_at}`, validate category ∈ allowed set, default `archived_at` to today if
  missing, pass current user id → `_vehicle_repo.archive(...)`.
- `POST /api/foi-parcurs/vehicles/<int:id>/restore` → `_vehicle_repo.restore(id)`.
- The existing `DELETE /vehicles/<id>` stays for backward-compat but the UI no longer
  calls it.

## Permissions

Gated by the existing `can_access_carpark` on the Driving tile — same gate as
Sessions/Calendar. Matching the current page, Drive Park has no per-action gating, so full
parity means edit/archive/restore is available to anyone who can open the Driving panel.
Accepted consequence of the "full parity" decision; no new gate added.

## Testing

Frontend:
- `ArchiveVehicleDialog` submits `{ category, note, archived_at }` with today's date
  prefilled and category required.
- `DrivePark` segmented toggle switches active↔archived querying; archived rows render
  Motiv + Data arhivării columns and only a Restore action; active rows render
  Edit/Lock/Archive.
- `HubDrivingPanel` renders a "Parc Auto" tab trigger and shows the vehicle list on click;
  hides "Driving Session nou" in that tab.

Backend:
- `archive()` sets `is_active=FALSE` + all archive_* fields; `restore()` flips
  `is_active=TRUE` and NULLs archive_* fields.
- `/archive` route rejects an unknown category and defaults missing `archived_at` to today.

Guardrails: the extraction is behavior-preserving; `tsc` catches any missed helper/import,
and the existing `DrivingSessionsList.test.tsx` suite plus the new tests cover the wiring.

## Risks

- **Extraction leaves a helper behind** → compile error, caught immediately by typecheck.
  Low risk (boundary verified).
- **DELETE-with-body vs new POST routes** — avoided by using dedicated
  `POST /archive` + `POST /restore` (consistent with lock/unlock), no CORS/body issues.
- **Migration** applies on app startup via `schema_incremental.py`; idempotent ADD COLUMN
  IF NOT EXISTS is safe to re-run. Apply to localhost first.

## Rollout

- Build and verify on localhost against the local DB.
- Deploy via surgical cherry-pick of the feature commits (code only, no docs) per the
  established JARVIS deploy workflow (staging first, main last, 2 confirmations for main).
  Deployment is out of scope for this spec.
