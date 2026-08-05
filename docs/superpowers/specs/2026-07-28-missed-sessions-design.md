# Missed Driving Sessions — grace window, archive & reschedule

**Date:** 2026-07-28
**Status:** Approved
**Scope:** Full-stack — JARVIS backend (`foi_parcurs`) + `jarvis-mobile-2`. Web
"Sesiuni Driving" tab inherits the derived statuses for free; no dedicated web
work in this spec.

## Problem

A `PLANNED` Test Drive session whose start time (`departure_datetime`) passes but
is never activated stays `PLANNED` forever. It keeps blocking its vehicle in the
conflict check, never surfaces as a problem, and there is no way to move it to a
new time. There is no notion of a "missed" session.

## Goal

Give a planned session a real end-of-life:

1. When its **start hour is missed**, keep it **open for 8 hours** (grace window)
   so the consilier can still activate it late, reschedule it, or drop it.
2. Notify the consilier by push the **moment the start is missed**.
3. After **8 hours** with no action, **archive it as MISSED** — which also
   **frees the vehicle** for other sessions.
4. A missed session can be **revived by rescheduling** it to a new future time.

## Lifecycle & status model

`departure` = `departure_datetime`. Grace = 8h.

| Persisted `status` | Condition | Derived `td_status` | Badge (mobile/web) | List |
|---|---|---|---|---|
| `PLANNED` | `departure` in future | `planned` | Planificat (indigo) | active |
| `PLANNED` | `departure ≤ now < departure+8h` | `late` | Întârziat (amber) | active |
| `MISSED` | archived (or PLANNED past `departure+8h`, pre-job) | `missed` | Ratată (gray) | archived |
| `FILLED` | out / overdue | `driving` / `incomplete` | unchanged | active |
| `COMPLETED` | return submitted | `complete` | Complet (green) | archived |

**Transitions**

- `PLANNED(future)` → *(time passes)* → `late` (derived; row is still `PLANNED`)
- `late` → **Activate** → `FILLED` (existing activate endpoint)
- `late` → **Reschedule** → `PLANNED(new future)`
- `late` → **Discard** → deleted (existing DELETE; row is still `PLANNED`)
- `late` → *(8h elapses, no action)* → `MISSED` (scheduled job)
- `MISSED` → **Reschedule (revive)** → `PLANNED(new future)`

"PLANNED must be evaluated before `td_status`" (existing rule) becomes "missed →
late → planned must be evaluated before the FILLED-era `td_status`", applied
identically in the SQL and the mobile `deriveTdStatus`.

## Backend (JARVIS `foi_parcurs`, dev branch)

### Migration
Add to `foi_de_parcurs`:
- `missed_at TIMESTAMP NULL` — when the row was archived missed.
- `late_notified_at TIMESTAMP NULL` — dedupe for the "missed at start" push.

Introduce `MISSED` as a `status` value. `status` is a plain varchar with no CHECK
constraint (verify in planning), so no constraint change is needed.

### `_TD_STATUS_SQL` (`foi_parcurs_repository.py`)
Prepend the new branches so a planned/missed row is never mislabeled `driving`:

```sql
CASE
  WHEN fp.status = 'COMPLETED' THEN 'complete'
  WHEN fp.status = 'MISSED' THEN 'missed'
  WHEN fp.status = 'PLANNED'
       AND fp.departure_datetime + INTERVAL '8 hours' < NOW() THEN 'missed'  -- safety net pre-job
  WHEN fp.status = 'PLANNED'
       AND fp.departure_datetime < NOW() THEN 'late'
  WHEN fp.status = 'PLANNED' THEN 'planned'
  WHEN fp.return_datetime IS NOT NULL AND fp.return_datetime < NOW() THEN 'incomplete'
  ELSE 'driving'
END AS td_status
```

(The SQL now emits `planned` explicitly; the mobile derivation already tolerates
that and keeps its own fallback.)

### `find_conflicts`
A missed slot must free the vehicle. Add to the "open session" filter:

```sql
AND fp.status <> 'MISSED'
AND NOT (fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '8 hours' < NOW())
```

So `late` (grace) sessions still block the VIN — the client may yet show up — but
`missed` ones (and PLANNED-past-grace not yet archived) do not.

### Reschedule endpoint
`PUT /api/foi-parcurs/test-drive/{id}/reschedule`, `@login_required`.
Body: `{ departure_datetime, return_datetime }`.

- Allowed only when current `status ∈ {PLANNED, MISSED}`; else 409.
- Rejects a past `departure_datetime` (mirror the plan form's date-in-past guard).
- Sets the new datetimes, `status='PLANNED'`, `missed_at=NULL`,
  `late_notified_at=NULL`.
- Runs the same VIN soft-conflict check as plan/activate (returns conflicts; the
  client decides whether to proceed — matching the existing soft-block sheet).

Repository: `reschedule_session(id, departure, return_dt)` guarded by
`WHERE status IN ('PLANNED','MISSED')`.

### Scheduled job (`tasks/`)
New `tasks/foi_parcurs_sessions.py`, registered in `tasks/cleanup.py`
`start_scheduler()` as an interval job (**every 10 min**), mirroring
`archive_pending_invoices`. Two idempotent passes:

1. **Notify** — for each `PLANNED` row with
   `departure < now ≤ departure+8h` and `late_notified_at IS NULL`:
   resolve advisor → user (extend `_consilier_contact` to also return `users.id`),
   `notify_with_push([uid], "Sesiune ratată la start",
   "{client} — {vehicul} la {HH:MM}. Reprogramează sau activează.",
   link="/sales/test-drive/{id}", entity_type="foi_parcurs_td", entity_id=id)`,
   then stamp `late_notified_at = NOW()`.
2. **Archive** — `UPDATE foi_de_parcurs SET status='MISSED', missed_at=NOW()
   WHERE route_type='TD' AND status='PLANNED'
   AND departure_datetime + INTERVAL '8 hours' < NOW()`.

Both passes are safe to run repeatedly; the dedup column + WHERE clauses make them
convergent. Push is best-effort (unresolved advisor → skip, never raise).

## Mobile (`jarvis-mobile-2`)

- `TdStatus` gains `'late' | 'missed'`. `deriveTdStatus` checks `MISSED` / grace
  math **before** returning `planned`, prefers backend `td_status` when it is
  `late`/`missed`, and keeps the device-clock fallback (as today's `incomplete`
  fallback does).
- `tdStatusBadge`: `late` → amber "Întârziat"; `missed` → gray "Ratată".
- List (`index.tsx`): archived view = `complete || missed`; active view = the rest
  (`planned` / `late` / `driving` / `incomplete`).
- **`RescheduleSheet.tsx`** — new `BottomSheet`: two `datetime-local` inputs
  (departure default `now+1h`, return default `departure+1h`), reuses the VIN
  soft-block sheet, calls `useRescheduleTestDrive` → `PUT …/reschedule`. Opened
  from a `late` row, a `missed` row, and from Detail.
- `Detail.tsx`: `late` → Activate + Reschedule + Discard; `missed` → Reschedule
  (revive) + read-only session data.
- Push tap deep-links to `/sales/test-drive/{id}` via the existing
  `appUrlOpen`/push-tap routing (the Approvals deep-link pattern, `57c7bfb`).

## Units & interfaces

- **Status derivation** (SQL `_TD_STATUS_SQL` + mobile `deriveTdStatus`) — one
  rule set, two implementations that must agree; boundary-tested on both sides.
- **Reschedule** (endpoint + repo method + `useRescheduleTestDrive` +
  `RescheduleSheet`) — self-contained; only touches datetimes + status.
- **Sweeper job** (`foi_parcurs_sessions.py`) — pure background transition, no
  request context; testable with a frozen clock.
- **Conflict filter** — a localized change to one WHERE clause.

## Edge cases

- **Push targeting** relies on `advisor_name → users` (the mapping the auto-email
  already uses). Name collisions → best-effort; unresolved → skip. A proper
  `created_by` user id on the row is the future fix (out of scope).
- **Grace boundary** uses server time in SQL (authoritative). The mobile fallback
  uses the device clock — acceptable, and only used before backend `td_status`
  is present.
- **Reschedule of a live/completed row** → 409 (endpoint guard).
- **Reschedule into the past** → rejected client- and server-side.
- **Job cadence** — a session becomes archived/notified within ≤10 min of its
  boundary, not exactly on it; the `_TD_STATUS_SQL` safety net keeps the *display*
  and *conflict-freeing* correct in the gap before the job runs.

## Testing

**Backend**
- `_TD_STATUS_SQL` derivation at the `departure` and `departure+8h` boundaries
  (planned / late / missed).
- `find_conflicts` excludes MISSED + PLANNED-past-grace; still includes `late`.
- Reschedule endpoint: PLANNED→ ok, MISSED→revive ok, FILLED/COMPLETED→409,
  past-departure→400, clears `missed_at`/`late_notified_at`.
- Sweeper (frozen clock): notify pass stamps once (idempotent); archive pass flips
  PLANNED-past-grace to MISSED.

**Mobile**
- `deriveTdStatus` boundaries (late/missed/planned) + backend-`td_status`
  precedence.
- `tdStatusBadge` labels/classes.
- List filtering (active vs archived) includes `late` in active and `missed` in
  archived.
- `RescheduleSheet` validation (return-before-departure, past-departure).

## Sequencing

Coordinated backend + mobile release. **Hold mobile `2.0.35`** and ship the
backend (JARVIS dev → staging → main) together with the mobile build that carries
this feature **plus** the already-completed license-optional-when-planning fix.
This design doc stays on `dev` and is dropped before any staging/main merge.
