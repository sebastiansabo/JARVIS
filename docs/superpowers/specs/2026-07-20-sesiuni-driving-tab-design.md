# Sesiuni Driving — Foi de Parcurs tab reframe

**Date:** 2026-07-20
**Status:** Approved
**Scope:** Frontend-only reframe of the "Parcurs" tab in the Foi de Parcurs module.

## Problem

The "Parcurs" tab was built for the original `PENDING → FILLED` contract lifecycle and
never updated when the Test Drive flow added `driving` and `COMPLETED` statuses. As a
result:

- `COMPLETED` sessions render with the `destructive` (red) badge — every finished test
  drive looks like an error.
- The Status filter only offers `PENDING`/`FILLED`, so completed/overdue sessions can't
  be filtered.
- Summary badges count only pending + filled, undercounting real data.
- PDF download buttons are gated on `status === 'FILLED'`, so a completed session exposes
  **no** Legal/Custom PDF.
- The Actions column re-prints the client name (green ✓), duplicating the Client column.
- Default sort is `slot_number`, which is `0` for every TD row, so `#` shows "—" and sort
  is a no-op.
- The tab shows generic contract fields (`#`, `Type`, `Itinerary`) that are meaningless
  for a TD session, and hides the fields that matter (departure/return timestamps,
  vehicle identity).

The backend **already** derives a richer session status (`td_status`) that the mobile app
uses but the web tab ignores. Comodat is dead; the module is TD-only going forward.

## Goal

Reframe the tab as **"Sesiuni Driving"** — a historical record of test-drive sessions,
showing all TD contracts, with a correct session status model and session-relevant
columns. No backend changes.

## Status model

Display status is derived on the frontend from `status` + the existing `td_status`
(`_TD_STATUS_SQL` in `foi_parcurs_repository.py`), which `get_contracts` already returns:

| Display (RO) | Derived from | Color | Meaning |
|---|---|---|---|
| Nealocat | `status === 'PENDING'` | gray/muted | Batch slot, no client yet |
| În desfășurare | `td_status === 'driving'` | blue | Car is out, not yet due |
| Întârziat | `td_status === 'incomplete'` | red | Return time passed, no return recorded |
| Finalizat | `td_status === 'complete'` | green | Returned & done |

Derivation order (frontend helper):
1. `status === 'PENDING'` → Nealocat
2. else `td_status === 'complete'` → Finalizat
3. else `td_status === 'incomplete'` → Întârziat
4. else → În desfășurare

`td_status`'s ELSE branch returns `driving` even for PENDING rows, so the `PENDING` check
must come first.

## Columns

Current: `# · Status · Company · VIN · Type · Distance · KM · Client · Itinerary · Advisor · Actions`

New: `Date · Status · Company · Vehicle · Client · Consilier · KM · Return · Actions`

- **Date** — `departure_datetime` (fallback `created_at`); **default sort DESC**.
- **Status** — 4-state session badge (above).
- **Company** — unchanged (`company_name`).
- **Vehicle** — `brand model` + plate (`vehicle_registration_number` / `registration_number`);
  raw VIN moves to the expanded row.
- **Client** — unchanged.
- **Consilier** — `advisor_name` (renamed header from "Advisor").
- **KM** — `km_start – km_end` (+ `distance_km`), unchanged content.
- **Return** — `return_datetime` formatted, or "—" when still driving / not returned.
- **Actions** — quick PDF link + admin Reset + admin Delete. Remove the redundant green ✓
  client-name.

Dropped: `#` (slot_number, always 0), `Type` (always TD), `Itinerary` (TD form dropped it),
standalone `Distance` column (folded into KM). Headers stay in **English** to match the rest
of the table; the tab label and status badges are Romanian.

## Filters, sort, summary

- **Status filter**: All / Nealocat / În desfășurare / Întârziat / Finalizat — filters on the
  derived display status (client-side; all rows are already fetched with `per_page: 1000`).
- Vehicle / Month / Year / Search filters and the Export dialog are unchanged.
- **Summary badges** recount by display status (e.g. "142 finalizate · 2 în desfășurare ·
  1 întârziat · 3 nealocate"). Zero-count states are hidden.
- `STATUS_ROW_BG` maps the 4 states to left-border tints; `Întârziat` tinted red so overdue
  rows stand out even in a history list.

## Actions & PDF

- PDF buttons (expanded row) show whenever the session has generated PDFs — i.e. any
  non-`PENDING` row — instead of `status === 'FILLED'` only. Use the existing
  `getContractPdfUrl(c.id, 'legal' | 'custom')`.
- Add a compact PDF quick-link in the Actions column for non-PENDING rows.
- Admin Reset stays (visible for `td_status` driving/complete on TD rows). Admin Delete stays.
- Expanded row gains: departure/return timestamps, full VIN. Keeps fuel, client, route,
  contract/batch/period/created blocks.

## Scope & non-goals

- **Frontend-only.** All edits in `ParcursTab` within
  `jarvis/frontend/src/pages/FoiParcurs/index.tsx`. No routes / repository / schema changes.
- Tab **label** "Parcurs" → **"Sesiuni Driving"**. Internal `TabsTrigger` value and
  `activeTab` key stay `parcurs` to avoid breaking saved state/links. Component renamed
  `ParcursTab` → `SessionsTab`.
- Comodat rows hidden via `route_type === 'TD'` filter (Comodat is dead; historical Comodat
  rows are simply not shown here).
- **Non-goals:** removing the Comodat batch-generation flow elsewhere (Contracts/Settings
  tabs), any backend status refactor, localization of the whole table to Romanian.

## Testing

- No backend logic changes → no new Python tests; existing `jarvis/tests/foi_parcurs/`
  suite (21 tests) must stay green.
- Manual verification against staging data: completed sessions render green; an overdue
  session (return_datetime in the past, not returned) renders red "Întârziat"; PDF buttons
  appear on completed sessions; status filter returns the right rows; default sort is newest
  session first.
