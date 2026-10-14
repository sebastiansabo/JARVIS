# Buyback "Hold" Status — Design

**Date:** 2026-10-14
**Branch:** `feat/buyback-hold-status` (off `staging`, includes the date/equipment hotfix)
**Status:** Design approved (in-chat). Awaiting spec review → implementation plan.

---

## 1. Problem

When a buyback price request is submitted with **incomplete info** (missing photos, talon/CIV, VIN, price, contact…), the acquisition team today has no way to pause it and signal back what's missing. They can only let it sit in `PENDING_EVALUATION`, cancel it, or push it forward. There's no "waiting on the submitter to complete it" state, and the submitter is never told what's missing.

## 2. Goals / Non-goals

**Goals**
- A new **`ON_HOLD`** buyback status ("Suspendat").
- A **Hold** action (button on the list **and** the detail) available on any **active** request (`PENDING_EVALUATION`, `INITIAL_OFFER`, `INSPECTION`, `FINAL_OFFER`). Opens a modal: **pick a reason** (admin-configurable list) + **optional note**. The record goes `ON_HOLD`.
- A **Resume** action on `ON_HOLD` records that returns the record to **exactly the status it was held from**.
- On hold, notify the **issuer** (the internal advisor/creator) via **both**: an **email** (reason + note) and a **JARVIS notification** (in-app + FCM push).
- `ON_HOLD` appears in the list status badge + the status filter.
- New permission **`buyback.record.hold`** (Admin/Manager/Acquisition).

**Non-goals (deferred)**
- Notifying the external seller/client (internal advisor only, per decision).
- Auto-release / SLA timers on held records.
- A hold *history* beyond the audit-event trail + the current hold fields (one hold at a time; re-holding overwrites the current reason).
- Notifying on **resume** (resume just transitions; no email/push unless requested later).

## 3. Locked decisions

1. **Scope:** Hold from **any active status**; **Resume restores the exact held-from status** (stored on the record), not a fixed target.
2. **Motive:** a **predefined, admin-configurable reason** (dropdown) **+ optional free-text note**.
3. **Issuer notified:** the **internal advisor/creator** (`created_by` for the push target; advisor email via the existing internal-recipient resolver). Both email **and** in-app+push.
4. **Reason storage:** reason + note live on the record (current hold); every hold/resume also writes a `buyback_events` audit row.
5. `ON_HOLD` is a first-class lifecycle status with its own transitions (so `is_valid_transition`, filters, and labels all recognize it).

## 4. Data model

### 4.1 `buyback_records` — new columns (idempotent `ADD COLUMN`, `schema_buyback.py`, PROTECTED — confirm)
```sql
hold_prior_status VARCHAR(24),   -- status the record was in when held (restored on resume)
hold_reason       VARCHAR(100),  -- selected reason value (from buyback_hold_reason dropdown)
hold_note         TEXT,          -- optional free-text note
held_at           TIMESTAMPTZ,
held_by           INTEGER
```
Each guarded by a `DO $$ ... information_schema ... ADD COLUMN ...` block. Cleared (set NULL) on resume.

### 4.2 Reasons dropdown (seeded, admin-configurable)
Seed `dropdown_options` type **`buyback_hold_reason`** (idempotent, same `WHERE NOT EXISTS` pattern as the CUSTODIE source): e.g. *Poze lipsă, Talon/CIV lipsă, VIN lipsă/greșit, Preț incomplet, Date contact lipsă, Altele*. Managed via the existing Settings dropdown admin.

### 4.3 Lifecycle (`jarvis/buyback/lifecycle.py`)
- Add `ON_HOLD = 'ON_HOLD'`; `STATUS_LABELS[ON_HOLD] = 'Suspendat'`.
- `TRANSITIONS`: each active status (`PENDING_EVALUATION`, `INITIAL_OFFER`, `INSPECTION`, `FINAL_OFFER`) gains `ON_HOLD`; `ON_HOLD` → `{PENDING_EVALUATION, INITIAL_OFFER, INSPECTION, FINAL_OFFER}`. (Hold/Resume are implemented as dedicated service ops that also stamp the hold fields — not a bare transition — but the map keeps the status graph consistent for any `is_valid_transition` caller and the `/status` escape hatch.)

## 5. Backend

### 5.1 Service — `BuyBackService.hold(record, reason, note, actor)` / `.resume(record, actor)`
- `hold`: assert `record.status` ∈ active set (else ValueError→409). Stamp `hold_prior_status = record.status`, `status = ON_HOLD`, `hold_reason`, `hold_note`, `held_at`, `held_by`. Log `buyback_events` `held` with `{reason, note}`. Return updated record.
- `resume`: assert `record.status == ON_HOLD` (else ValueError→409). Set `status = hold_prior_status`, clear the 5 hold fields. Log `resumed` with `{restored_to}`. Return updated record.

### 5.2 Routes (`jarvis/buyback/routes/`)
- `POST /records/<id>/hold` — `@v2_permission_required('buyback','record','hold')`, `_guard_company`, body `{reason, note?}`; validate `reason` is a non-empty string (and optionally a known `buyback_hold_reason` value); call `service.hold(...)`; then best-effort **notify** (5.3). Returns `{success, record}`.
- `POST /records/<id>/resume` — same perm + guard; `service.resume(...)`. Returns `{success, record}`.

### 5.3 Notify the issuer (best-effort, never blocks the hold)
- **Email**: reuse `buyback.services.notifications` / `email.py` `_resolve_internal_recipient(record, ...)` + `send_email` with a "Request on hold" template carrying the reason + note.
- **In-app + push**: `from core.notifications.notify import notify_user`; `notify_user(record['created_by'], title='Solicitare BuyBack suspendată', message=f'{reason} — {note}', link=f'/app/buyback/{record_id}', entity_type='buyback_record', entity_id=record_id, category='buyback')`. Wrap in try/except (swallow), mirroring the other buyback notifications.

### 5.4 Permission
Add `('record','Buyback Records','hold','Hold','Put a request on hold pending missing info', True, 9)` to `_seed_buyback_permissions_v2`; grant to Admin/Manager (auto via `all_entities_actions`) + Acquisition; Viewer deny (auto).

## 6. Frontend

### 6.1 Status plumbing
- `recordStatus.ts`: add `ON_HOLD` → key `on_hold`, label **"Suspendat"**, a badge class (e.g. amber/orange), row class; add to `STATUS_FILTER_OPTIONS`.
- `types/buyback.ts`: `BuybackStatus` gains `'ON_HOLD'`; `BuybackRecord` gains `hold_prior_status`, `hold_reason`, `hold_note`, `held_at`, `held_by`.
- `api/buyback.ts`: `hold(id, {reason, note?})` and `resume(id)`.

### 6.2 List (`pages/BuyBack/index.tsx`)
- A **Hold** button on rows whose status is active + `can('buyback.record.hold')` → opens the reason+note modal.
- A **Resume** button on `ON_HOLD` rows.
- `ON_HOLD` shows in the status column + filter (via recordStatus).

### 6.3 Detail / ActionPanel (`pages/BuyBack/ActionPanel.tsx`)
- A **Hold** button (active statuses + perm) opening the same modal; a **Resume** button on `ON_HOLD`.
- Detail shows the current hold reason/note + held_at/by when `status==='ON_HOLD'`.

### 6.4 Hold modal (shared component)
Reason `Select` (options from the `buyback_hold_reason` dropdown via the existing lookups) + optional note `Textarea` + confirm. Submit disabled until a reason is chosen.

## 7. Testing

**Backend**
- `service.hold` from each active status → `ON_HOLD`, prior stored, fields stamped, event logged; from a non-active status → ValueError.
- `service.resume` from `ON_HOLD` → restores `hold_prior_status`, clears fields; from non-`ON_HOLD` → ValueError.
- Route guards: no-perm 403, cross-company 403, non-active hold 409, non-hold resume 409, missing/empty reason 400.
- Notify is best-effort: a raising email/`notify_user` does NOT fail the hold (patch them to raise, assert 200 + hold persisted).
- Permission seed: `buyback.record.hold` present + granted to Admin/Manager/Acquisition, Viewer denied.

**Frontend**
- recordStatus renders `ON_HOLD`; filter includes it.
- List + ActionPanel button visibility matrix (active+perm → Hold; ON_HOLD → Resume; no perm → hidden).
- Modal requires a reason before submit.

## 8. Rollout
- Own branch off `staging`. Idempotent migration (ADD COLUMNs + reason seed + permission grant). Protected `schema_buyback.py`/`schema_roles.py` — confirmed in design.
- Pre-push: `npm run build`, `pytest`, `py_compile app.py`. Staging first → prod on double confirmation.

## 9. Open questions (resolve in planning, non-blocking)
1. Should `resume` also notify the advisor ("your request is back in evaluation")? (Default: no.)
2. Exact `held_by`/push target: `created_by` vs `advisor_id` if they differ — default `created_by` for the push (it's a real user id); advisor email via the resolver.
3. Reason as a hard enum (reject unknown values server-side) vs free-form-but-seeded. Default: accept any non-empty string but seed the common list (mirrors other buyback dropdowns).
