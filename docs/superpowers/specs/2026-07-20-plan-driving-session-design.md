# Plan a Driving Session — draft, calendar & conflict detection

**Date:** 2026-07-20
**Status:** Approved
**Scope:** New capability across JARVIS backend, web Foi de Parcurs, and jarvis-mobile-2 Sales/Driving Sessions.

## Problem / goal

Consilieri need to **plan** a test-drive session ahead of time: fill the whole form now,
save it as a **draft** (a "planned drive" when dated in the future), and finalise it with the
client's acceptance/signature when the client actually arrives. They also need a **calendar**
of all planned sessions, and a **conflict warning** when a car is already booked (planned) or
currently out, so two people don't grab the same car.

Today the TD form creates a live session immediately (`FILLED` → `driving` → `COMPLETED`),
requires the client signature up front, and has no notion of a future/scheduled draft.

## Core model

A planned session is an ordinary `foi_de_parcurs` row, `route_type='TD'`, with a **new status
`PLANNED`**:

- Full form data saved; `departure_datetime` / `return_datetime` scheduled (future or now).
- **Client signature and GDPR consent deferred** (not required to save a draft).
- No PDF generated yet (PDF is produced at activation).

### Lifecycle

```
PLANNED ──activate (client arrives → confirm + sign)──▶ FILLED ─▶ driving ─▶ COMPLETED
   └──── discard (delete) ────▶ ✗
```

`PLANNED` must be evaluated **before** `td_status` everywhere status is derived, because
`_TD_STATUS_SQL`'s ELSE branch returns `driving` for any non-COMPLETED row (it would otherwise
mislabel a plan as "driving"). This mirrors the existing `PENDING`-first guard.

Display label: **"Planificat"** (RO), muted/indigo color, distinct from the four existing
Sesiuni Driving states (Nealocat / În desfășurare / Întârziat / Finalizat).

## Permissions

Anyone with **`test_drive` access** (`P.canTestDrive` / backend `@login_required` TD routes)
can create, activate, and discard plans — same gate as creating a live TD. No creator-only
restriction.

## Phase 1 — Backend

**Status & schema**
- No new table. `foi_de_parcurs.status` gains the `'PLANNED'` value (VARCHAR, no enum change
  needed). No migration beyond documenting the value.

**Draft create** — extend `POST /api/foi-parcurs/test-drive`:
- Accept `status: 'PLANNED'` (default remains `'FILLED'` — existing callers unchanged).
- When `status == 'PLANNED'`: `client_signature` and `gdpr_consent` are **optional**;
  `departure_datetime` may be in the future; **no PDF** is generated.
- When `status` absent/`'FILLED'`: current behaviour verbatim (signature + GDPR required, PDF
  generated).

**Activate** — `PUT /api/foi-parcurs/test-drive/{id}/activate`:
- Guard: row exists, `route_type='TD'`, `status='PLANNED'`.
- Body carries the fields that may change at handover + the now-required
  `client_signature` (and GDPR consent): `odometer_start`, `fuel_gauge_start_level`,
  `departure_datetime`, `departure_damage`, `client_signature`, `advisor_signature`,
  `gdpr_consent`, plus any edited form fields.
- Recomputes fuel liters (same logic as create), sets `status='FILLED'`, generates the
  Legal/Custom PDFs (same as the current submit path), returns the updated contract.

**Discard** — new route `DELETE /api/foi-parcurs/test-drive/{id}`:
- Deletes the row **only when `status='PLANNED'`** (returns 400/409 otherwise), so any TD user
  can discard a draft without touching the existing admin-gated hard-delete
  (`DELETE /api/foi-parcurs/contracts/{id}`), which stays as-is. Confirmation lives in the UI.

**Conflicts** — `GET /api/foi-parcurs/vehicles/{vin}/conflicts?from=&to=&exclude_id=`:
- Returns TD sessions on that VIN that **overlap** `[from, to]` and are either `status='PLANNED'`
  **or** currently live (`td_status IN ('driving','incomplete')`). Overlap = existing
  `[departure_datetime, COALESCE(return_datetime, departure_datetime)]` intersects `[from, to]`.
- `exclude_id` omits the row being edited/activated.
- Response: `{ conflicts: [{ id, contract_id, client_name, advisor_name, departure_datetime,
  return_datetime, status, td_status }] }`. Empty array = clear.

**Calendar range** — reuse `GET /api/foi-parcurs/contracts` with the existing `date_from` /
`date_to` filters (they already filter on `COALESCE(departure_datetime, created_at)`); add
`status`/`route_type='TD'` filtering client- or server-side. No new endpoint required unless a
lighter payload is wanted later.

**Repository**
- `record_activation(id, data)` in `FoiParcursRepository` (mirrors `record_return`): sets the
  handover fields + `status='FILLED'`, `RETURNING *`.
- `find_conflicts(vin, frm, to, exclude_id)` — the overlap query above.
- `_TD_STATUS_SQL` unchanged (PLANNED handled in the app layer, not the SQL alias).

**Tests** (`jarvis/tests/foi_parcurs/`): draft-create omits signature/PDF; activate requires
signature and flips to FILLED + PDF; discard removes only PLANNED; conflict overlap true/false
cases (planned-vs-planned, planned-vs-live, non-overlapping window, excluded id).

## Phase 2 — Web (Foi de Parcurs)

**Sesiuni Driving status** — extend the `sessionStatus` helper to 5 states by adding
`planificat` (checked first, `status === 'PLANNED'`). Add it to the status filter dropdown,
the summary counts, and the row tint map. (Same file/pattern as the tab we just shipped.)

**Draft / activate / discard actions**
- The TD create form gets a **"Planifică (draft)"** action next to submit → posts with
  `status: 'PLANNED'`.
- A `PLANNED` row's actions: **Începe sesiunea** (opens the prefilled form → confirm/adjust →
  capture client signature → `PUT …/activate`), **Editează**, **Discard** (confirm → delete).

**Calendar tab** — a new tab in Foi de Parcurs beside Sesiuni Driving:
- Month/week grid keyed on `departure_datetime`; events show car (brand·model·plate) · client ·
  time · consilier, colored by status. Click → session detail / activate.
- Data from the contracts list with a date-range filter.

**Conflict soft-block** — on planning or starting a TD, call the conflicts endpoint for the
chosen VIN + window; if non-empty, show a dialog listing the conflicting session(s) (client,
advisor, time, status) with **"Continuă oricum"** to override and Cancel to back out. Soft only —
never hard-blocks.

## Phase 3 — Mobile (jarvis-mobile-2)

**Draft** — `New.tsx` gains a **"Salvează ca draft / Planifică"** button beside "Trimite";
drafts relax the client-signature/GDPR requirement and allow a future `departure_datetime`.

**Activate** — a `PLANNED` session's detail page shows **"Începe sesiunea"** → reopens the form
prefilled → capture client signature → `PUT …/activate`.

**Discard** — a `PLANNED` session can be discarded from its detail/list row (confirm → delete).

**Status badge** — `deriveTdStatus` / `tdStatusBadge` in `useApi.ts` gain a **"Planificat"**
state for `status === 'PLANNED'` (checked before the td_status mapping).

**Calendar** — a calendar/agenda screen in the Driving Sessions app (list-grouped-by-day is the
simplest mobile form) showing planned + live sessions from the range query.

**Conflict soft-block** — before submitting a plan or a live TD, call the conflicts endpoint;
on overlap show a confirm sheet ("mașina e deja rezervată/plecată… Continuă oricum?").

Mobile deploy per its rule: `npm run build && npx cap sync android` after each committed change.

## Non-goals

- Recurring/repeating plans, multi-day reservations.
- Notifications / reminders for upcoming plans.
- Hard blocking (soft warning only).
- Country persistence, or any change to the existing live TD/return flow beyond adding the
  `PLANNED` branch.

## Rollout

Phase 1 (backend) ships first and is exercised by its own tests. Phase 2 (web) and Phase 3
(mobile) each consume the Phase-1 API and ship independently. Each phase gets its own
implementation plan. Docs stay on `dev` per repo policy; code merges dev → staging → main with
the usual confirmations.
