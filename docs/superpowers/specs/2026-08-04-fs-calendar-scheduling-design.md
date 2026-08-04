# Design — Outlook-style calendar scheduling for Field Sales

**Date:** 2026-08-04
**Status:** Approved (design)
**Scope:** JARVIS web frontend + ONE additive backend column (`kam_visit_plans.planned_end_time`).
**Branch:** `dev`

## Problem
The Hub Field Sales calendar (`FieldSalesCalendar`) is month-only and read-oriented: it shows visits as dots and lists a selected day's visits. Users want to schedule visits directly on the calendar, Outlook-style — click a day to add, and in a Day/Week time-grid drag to create/move/resize a meeting with a real start and end time.

## Decisions (from brainstorming)
- **Both** month click-to-add **and** a Day/Week hourly time-grid.
- Meetings have **start + end** → add `planned_end_time` to `kam_visit_plans` (start stays `planned_time`).
- **Full drag**: drag-to-create, drag-to-move, drag-to-resize; each persists via the existing `PUT /visits/:id`.
- Grid hours **07:00–21:00**, **30-minute snap**, default new-meeting duration **1h**.

## Data model
`ALTER TABLE kam_visit_plans ADD COLUMN IF NOT EXISTS planned_end_time TIME` — added in `jarvis/migrations/domains/schema_field_sales.py` (idempotent; runs on startup). Nullable. Semantics: block height = `planned_end_time - planned_time`; start-but-no-end → default 1h; no `planned_time` → "Fără oră" untimed strip.

## Backend (no new endpoints)
- `VisitRepository.create()` — add `planned_end_time` to the INSERT.
- `VisitRepository.update_visit()` — add `'planned_end_time'` to the editable-field list (already handles `planned_date`/`planned_time`/`visit_type`/`goals`/`status`/`outcome`/`contact_person`).
- `get_by_kam_and_date` / `get_team_visits` select `v.*`, so `planned_end_time` flows through automatically.
- `POST /api/field-sales/visits` — accept + validate `planned_end_time` (TIME `HH:MM`, optional) and pass to `create`.
- `PUT /api/field-sales/visits/:id` — accept + validate `planned_end_time`. **Move** = PUT `{planned_date, planned_time, planned_end_time}`; **resize** = PUT `{planned_end_time}` (and `planned_time` if top-edge). Reuse `fieldSalesApi.updateVisit`.

## Web API types (`api/fieldSales.ts`)
Add `planned_end_time?: string` to `FSVisit`, `CreateVisitPayload`; add `'planned_end_time'` to the `VisitUpdatePayload` Pick.

## Frontend

### AddVisitForm (in `HubFieldSalesPanel.tsx`)
New **Sfârșit** (end-time) field, default = start + 1h; new optional props `initialDate` / `initialTime` / `initialEndTime`. Submit includes `planned_end_time`. The panel's `add` overlay kind becomes `{ kind: 'add'; date?; time?; endTime? }`; `onAdd` opens it prefilled.

### FieldSalesCalendar
- View switcher **Lună / Săptămână / Zi**, persisted `usePersistedState('hub-fs-cal-view','month')`.
- **Lună** = current month grid, unchanged, **plus** click-a-day-to-add: each cell hover `+` and the selected-day section "+ Adaugă vizită" → `onAdd(dayKey)`.
- **Săptămână / Zi** = time-grid: columns = day(s) (Mon-start week via existing `startOfWeek`), rows = hours 07:00–21:00 with 30-min sub-slots; a "Fără oră" strip per day column for untimed visits. Blocks positioned/sized from `planned_time`→`planned_end_time`, colored via `STATUS_CONFIG.dot`/bg.
- Data via `getMyVisits` over the visible range (day / week 7-day / month grid), keyed `['field-sales-cal', viewKey, rangeStartKey]`.
- New prop `onAdd(date: string, time?: string, endTime?: string)`; keeps `onOpen(visitId)`.

### Drag interactions (pointer events)
Grid geometry: fixed px-per-hour (e.g. 48px), snap to 30 min. A shared `useState` drag model tracks `{mode:'create'|'move'|'resize', ...}`.
- **Empty-grid drag** → create: track start/end from pointer y (and day from x); on pointerup if moved → `onAdd(day, start, end)`; a plain click → `onAdd(day, hour, hour+1h)`.
- **Block-body drag** → move: new day (x) + new start (y), duration preserved; live preview; on drop → `updateVisit({planned_date, planned_time, planned_end_time})`.
- **Block bottom-edge drag** → resize: new end (y, min 30 min after start); on drop → `updateVisit({planned_end_time})`.
- **Persistence**: optimistic (React Query `onMutate` writes the moved/resized block into the cached list so it doesn't jump; rollback on error), then invalidate `['field-sales-visits']`, `['field-sales-mine']`, `['field-sales-cal']` on settle. Errors surface via `err?.data?.error`.
- Clicking a block (no drag) → `onOpen(visitId)`.

## Error handling
All mutations surface `err?.data?.error`; failed move/resize rolls back the optimistic cache write and shows an inline message.

## Testing (Vitest, pristine)
- Backend field flows through: `create`/`update_visit` include `planned_end_time` (repo unit or via API wrapper tests where practical).
- `fieldSalesApi` types: create/update payloads carry `planned_end_time`.
- AddVisitForm: honors `initialDate/initialTime/initialEndTime`; submit sends `planned_end_time`; end defaults to start+1h.
- Calendar: view toggle month↔week↔day; block height ∝ duration; untimed strip; a plain slot click fires `onAdd(date, "HH:00", "HH+1:00")`; a block click fires `onOpen`.
- Drag (pointer events with mocked `getBoundingClientRect`): drag-create fires `onAdd` with snapped start/end; drag-move calls `updateVisit({planned_date, planned_time, planned_end_time})`; drag-resize calls `updateVisit({planned_end_time})`.

## Out of scope
Recurring meetings; overlap/conflict detection; cross-KAM scheduling; all-day events; time-zone handling beyond the app's existing local dates.

## Files
- `jarvis/migrations/domains/schema_field_sales.py` (column)
- `jarvis/field_sales/repositories/visit_repository.py` (create/update)
- `jarvis/field_sales/routes/visits.py` (POST/PUT validation)
- `jarvis/frontend/src/api/fieldSales.ts` (types)
- `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx` (AddVisitForm end field + `add` overlay + onAdd wiring)
- `jarvis/frontend/src/pages/Hub/FieldSalesCalendar.tsx` (views + time-grid + drag)
- + test files per component

## Rollout
Dev only for build + verification (tsc, vitest, build) + localhost DB gets the column applied for testing. Deploy later (user-gated): the `ADD COLUMN IF NOT EXISTS` runs safely on staging/main; cherry-pick the source commits per the branch-drift rule.
