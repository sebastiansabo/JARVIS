# Pontaje Export — Filter Modal (design)

**Date:** 2026-07-08
**Status:** Approved (pending spec review)
**Area:** HR / BioStar Pontaje export

## Problem

The Pontaje XLSX export currently uses an inline start/end date picker in `PontajeTab`
and exports everyone in the caller's permission scope. Users want to click **Export**,
get a modal, and narrow the export by **period (year/month)** and by **group** or
**employee** before downloading.

## Goals

- Clicking **Export** opens a modal (replaces the inline period pickers).
- Period chosen as **Year + Month** → exports that whole calendar month.
- One filter at a time: **All** (scope) · **By Group** (single) · **By Employee** (multi-select).
- Filtering never widens visibility: the requested filter is always **intersected with the
  caller's permission scope** (`_resolve_manager_filter()`).

## Non-Goals (YAGNI)

- No combined group + employee filter (mutually exclusive by design).
- No arbitrary cross-month date ranges (month granularity only).
- No saved filter presets.

## User Flow

1. User clicks **Export** in PontajeTab → `PontajeExportModal` opens.
2. Modal fields:
   - **Year** dropdown — current year and the two prior years.
   - **Month** dropdown — Jan–Dec, defaults to the current month.
   - **Filter mode** radio:
     - **All** (default) — everyone in the caller's scope.
     - **By Group** — single-select, options from `biostarApi.getGroups()`.
     - **By Employee** — multi-select searchable list, options from `biostarApi.getEmployees()`.
   - **Export** button (spinner while running) + **Cancel**.
3. On submit the client computes `start = YYYY-MM-01`, `end =` last day of that month, adds the
   mode-specific parameter, and calls the export endpoint (blob download, cookie auth — unchanged).

## Backend

Extend `GET /biostar/api/attendance/export` (in `biostar/routes.py`).

### New optional query params

- `group` — a `user_group_name` string.
- `employee_ids` — comma-separated JARVIS user ids (e.g. `12,45,88`).

`start` / `end` remain required and keep the existing validation (ISO format, `start <= end`,
max 366 days).

### Resolution (permission-safe)

```
allowed = _resolve_manager_filter()          # None = all | [ids] | [-1] deny | [self]

final = _resolve_export_ids(allowed, group_ids, employee_ids)
  where:
    employee_ids present -> intersect(requested_ids, allowed)
    elif group present   -> intersect(ids_in_group, allowed)
    else                 -> allowed           # unchanged current behaviour

generate(start, end, final)
```

`_resolve_export_ids(allowed, group_ids, employee_ids)` is a **pure helper** (module-level,
no DB/request access) so the security-critical intersection logic is unit-testable.

Intersection semantics:
- `allowed is None` (see-all): result = the requested list as-is (no narrowing by scope).
- `allowed == [-1]` (deny): result = `[-1]` regardless of request (stays denied).
- otherwise: `result = [id for id in requested if id in allowed]`.
- If a filter is requested but resolves to an empty intersection → return HTTP 400
  `{'success': False, 'error': 'no employees match the selected filter'}` (avoids an
  all-employees export when the user intended a narrow one).

### New repository method

`BioStarRepository.get_jarvis_ids_for_group(group_name)`:

```sql
SELECT DISTINCT mapped_jarvis_user_id
FROM biostar_employees
WHERE user_group_name = %s
  AND mapped_jarvis_user_id IS NOT NULL
```

Returns a list of ints. Group→employee mapping uses `biostar_employees.user_group_name`
(single group per employee row).

`generate()` and the row-building service are unchanged — they already accept a
`jarvis_user_ids` list (and `None` = all).

## Frontend

- New component `PontajeExportModal.tsx` under `pages/Hr/` (keeps PontajeTab from growing further).
- Reuse existing API: `biostarApi.getGroups()`, `biostarApi.getEmployees(activeOnly=true)`.
- Extend `biostarApi.exportPontaje` to accept optional `{ group?, employeeIds?: number[] }`
  and append them to the query string.
- PontajeTab: replace the inline `exportStart`/`exportEnd` UI with an **Export** button that
  opens the modal. Existing `exporting` spinner state is reused.

## Error Handling

- Client: toast on failure (existing pattern); disable Export while a request is in flight.
- Server: 400 on empty filter intersection; 400 on the existing date validation; blob otherwise.
- Group/employee list fetch failure in the modal → show an inline message, still allow **All**.

## Testing

Unit tests (pytest, pure logic — no DB):

- `_resolve_export_ids`:
  - `allowed=None`, employee_ids → returns requested list unchanged.
  - `allowed=[1,2,3]`, employee_ids=[2,9] → returns `[2]` (9 stripped, outside scope).
  - `allowed=[-1]` (deny), any request → returns `[-1]`.
  - group path: `allowed=[1,2,3]`, group_ids=[2,3,7] → `[2,3]`.
  - no filter: `allowed=[1,2]`, nothing requested → `[1,2]`.
  - empty intersection is detectable by the caller (returns `[]`).

Manual/E2E:
- Modal opens on Export click; Year/Month default to current; mode toggles reveal the right control.
- Export by group and by multi-employee produce correctly scoped XLSX for a chosen month.

## Files Touched

- `jarvis/core/connectors/biostar/routes.py` — params + `_resolve_export_ids` + wiring.
- `jarvis/core/connectors/biostar/repositories/biostar_repository.py` — `get_jarvis_ids_for_group`.
- `jarvis/tests/biostar/test_pontaje_export.py` (or a new route test) — `_resolve_export_ids` tests.
- `jarvis/frontend/src/pages/Hr/PontajeExportModal.tsx` — new modal.
- `jarvis/frontend/src/pages/Hr/PontajeTab.tsx` — Export button opens modal; drop inline pickers.
- `jarvis/frontend/src/api/biostar.ts` — `exportPontaje` gains optional filter args.
