# export_pontaje — Design Spec

**Date:** 2026-07-08
**Status:** Approved (brainstorm)
**Author:** Sebastian Sabo + Claude

## 1. Goal

A fresh, simple export that dumps **Pontaje** data — exactly the information shown on the
`/hr/pontaje` page — as an XLSX, **one row per employee-contract per calendar day**, for a
**user-selected period**, including the **exact Sincron activity code** so that absence days
are explained (e.g. `CO` = concediu odihnă = on holiday, not a no-show).

This is a **new** feature named `export_pontaje`. The existing client-side export dropdown in
`PontajeTab.tsx` (`downloadXlsx`) is **left untouched**.

## 2. Non-goals

- No change to `_sync_biostar_schedules` (the combined SUM/MIN/MAX cache stays; it still serves
  the collapsed single-row page view and single-contract auto-adjust).
- No change to the existing `downloadXlsx` export or the `/api/export` Events-bonuses route.
- No refactor of `PontajeTab.tsx` beyond adding the new period controls + button.

## 3. Data model — where everything comes from

| Column | Source | Notes |
|---|---|---|
| Date, Weekday | generated from the period loop | every calendar day in `[start, end]` |
| Name | `users.name` (mapped) / `biostar_employees.name` | |
| Group | `biostar_employees.user_group_name` | per contract |
| Company | `biostar_employees.company_id → companies.company` | paired to the group via `company_aliases` (source='biostar') |
| Checked In / Out | `adjusted_first/last_punch ?? first/last_punch` | adjusted overrides raw; "Not exited" when `total_punches==1` and no adjustment |
| Actual In / Out | raw `first_punch` / `last_punch` | |
| **Lunch** | **per-contract Sincron**: `COALESCE(program_break, static_lunch)` | verbatim; `0` kept; **NULL → NULL** (no 60 fallback) |
| Duration | `net = gross − COALESCE(lunch, 0)` | gross = adjusted span if both adjusted else `duration_seconds`; blank when absent or single-punch-no-adjustment |
| **Schedule** | **per-contract Sincron**: `COALESCE(program_in, static_start)`–`COALESCE(program_out, static_end)` | that contract's own hours |
| **Sincron** | `sincron_repo.get_day_codes_for_users` | **exact `short_code`** verbatim (`OZ`/`OS`/`CO`/`CM`/`ZLS`/`X`/blank). No relabeling. |
| Status | page logic | leave label if leave code, else Present / Absent |

### Key correctness rule (per-contract, never summed)
For multi-company people, Schedule and Lunch must reflect **that specific contract**, not the
summed `biostar_employees` value. Source them from the **un-collapsed** `day_schedules` CTE in
`sincron_repository.get_full_day_schedule_by_jarvis_user` (currently collapsed to the primary
contract via `LIMIT 1` — the export needs all contracts, keyed by `(jarvis_user, company, day)`).

Example (split shift, same day):

| Date | Name | Company | Schedule | Lunch | Duration |
|---|---|---|---|---|---|
| 07-01 | Dan P. | AW INTERNATIONAL | 09:00–12:00 | 3 min | 3:00 |
| 07-01 | Dan P. | AW ONE | 13:00–17:00 | 30 min | 3:36 |

## 4. Architecture

### 4.1 Endpoint
- `GET /api/attendance/export?start=YYYY-MM-DD&end=YYYY-MM-DD`
- View function `export_pontaje` in `jarvis/core/connectors/biostar/routes.py`.
- Auth: `@api_login_required`.
- Scope: `jarvis_user_ids = _resolve_manager_filter()` — identical visibility to the page.
  A manager exports only their managed employees; L0 exports the whole company.

### 4.2 Assembly (server-side)
1. **Roster** — active `biostar_employees` in scope, each with `user_group_name` +
   `company_id → companies.company` (the authoritative group↔company pair). One roster entry
   per contract → drives per-company rows.
2. **Punches per contract per day** — aggregate `biostar_punch_logs` per `biostar_user_id` per
   day (reuse the `get_daily_summary` dedup: `DISTINCT ON (user, date_trunc('minute', ...))`),
   LEFT-joined onto the roster so **absent days appear** (null punches). Join
   `biostar_daily_adjustments` for adjusted times.
3. **Sincron schedule + lunch per contract** — new un-collapsed variant of
   `get_full_day_schedule_by_jarvis_user`, keyed `(jarvis_user, company, day)`.
4. **Sincron exact code** — `get_day_codes_for_users(ids, year, month)` per spanned month,
   merged to `{jarvis_user_id: {day: short_code}}`.
5. Emit one row per roster-entry × calendar day; join (2)(3)(4) by their keys.
6. Stream XLSX via `openpyxl` (styled header + auto-width, like `routes/export.py`).

### 4.3 New/changed backend code
- `biostar_repository`: new method for per-(biostar_user_id, day) attendance across a date range
  with the full-roster LEFT JOIN (absent days included) + adjustments. Working name
  `get_pontaje_rows(start, end, jarvis_user_ids)`. Alternatively loop days calling a new
  `get_daily_overview_by_company(date, jarvis_user_ids)`. (Plan decides; per-day loop is simplest.)
- `sincron_repository`: new `get_all_day_schedules_for_users(jarvis_user_ids, date)` returning
  every contract's `(jarvis_user_id, company_name, schedule_start, schedule_end,
  lunch_break_minutes)` — the `day_schedules` CTE without the primary-only `LIMIT 1`.
- Reuse `sincron_repository.get_day_codes_for_users` unchanged.
- `routes.py`: `export_pontaje` view assembling + streaming the workbook.

### 4.4 Frontend
- `PontajeTab.tsx`: add two `DateField`s (From / To, default = current month) to the toolbar,
  and an **"Export Pontaje"** button.
- `api/biostar.ts`: `exportPontaje(start, end)` — `fetch` the endpoint, read the blob, trigger a
  download; surface non-200 as a toast (so 401/400 don't silently fail).
- Filename: `pontaje_{start}_{end}.xlsx`.
- The existing export dropdown stays exactly as-is.

## 5. Columns (final, 15)

`Date · Weekday · Name · Group · Company · Checked In · Checked Out · Actual In · Actual Out ·
Lunch · Duration · Punches · Schedule · Sincron · Status`

## 6. Computation rules (ported from PontajeTab helpers)

- **Checked In** = `adjusted_first_punch ?? first_punch`; **Checked Out** =
  `adjusted_last_punch ?? last_punch`. When `total_punches == 1` and no adjustment → Checked Out
  and Duration blank, Status = `Not exited`.
- **Actual In/Out** = raw `first_punch` / `last_punch`.
- **Duration**: `gross = (adjusted_first && adjusted_last) ? span(adjusted) : duration_seconds`;
  `net = gross − COALESCE(lunch, 0)`; blank if `net <= 0` or absent.
- **Lunch**: per-contract `COALESCE(program_break, static_lunch)`, printed verbatim; `0` → `0 min`;
  **NULL → blank** (no fallback). Same value feeds the Duration deduction.
- **Status**: `sincron_leave_code ? LEAVE_LABEL : (present || hasAdjustment ? 'Present' : 'Absent')`.
- **Sincron column**: exact `short_code` from `get_day_codes_for_users`, no labeling.
- **Times** rendered `HH:MM` by string slice (timestamps are Romania-local naive — no tz conversion).

## 7. Scope & rows

- **Every calendar day** in `[start, end]` (weekends + holidays included; mostly Absent rows).
- **All manager-scoped employees**, including absentees (page parity).
- Export **ignores** the on-screen group/status/search filters — always the full scoped set.

## 8. Guardrails

- Validate `start` and `end` present and `start <= end` → `400` otherwise.
- Cap range at **366 days** (one punch-query per day) → `400` if exceeded.
- Empty result → `400` "No pontaje data for this period".

## 9. Out-of-scope inconsistencies (noted, not fixed here)

From the earlier 360 analysis of `downloadXlsx` — left alone by request:
- 30-vs-60 lunch default divergence, `raw`-ignored fallback branch, duplicated row builders,
  manager-scope bypass in the old export. `export_pontaje` avoids all of these by construction
  (server-side, manager-scoped, single row-builder, per-contract lunch, null-safe).
