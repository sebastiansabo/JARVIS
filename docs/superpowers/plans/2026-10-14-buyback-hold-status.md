# Buyback "Hold" Status — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add an `ON_HOLD` buyback status with Hold/Resume actions (reason + note), returning a held request to the exact status it was held from, and notifying the issuer by email + in-app/FCM push.

**Architecture:** New lifecycle status + two dedicated service ops (`hold`/`resume`) that stamp a `hold_prior_status` (for exact resume) plus reason/note/held_at/held_by, log audit events, and fire a best-effort email + `notify_user` push to the record's creator. New `buyback.record.hold` permission. UI: a reason+note modal + Hold/Resume on the list and the detail.

**Tech Stack:** Python/Flask, psycopg2 (`%s`, `BaseRepository`), PostgreSQL; React 19 + TS + Tailwind + shadcn; Vitest; pytest (psycopg2 mocked in tests/conftest.py).

**Spec:** `docs/superpowers/specs/2026-10-14-buyback-hold-status-design.md`

## Global Constraints
- Raw SQL, `%s` params only. Repos subclass `BaseRepository`. Migrations idempotent; `schema_buyback.py`/`schema_roles.py` are PROTECTED (confirmed in design).
- Frontend targets `jarvis/frontend/src/`. API envelope wrapped (`{record: ...}`).
- `ON_HOLD` label = **"Suspendat"**. Active statuses that can be held: `PENDING_EVALUATION`, `INITIAL_OFFER`, `INSPECTION`, `FINAL_OFFER`. Resume restores `hold_prior_status`.
- Permission `buyback.record.hold` → Admin, Manager, Acquisition (Viewer denied).
- Notify the record's **creator** (`created_by`): email (reason+note) + `notify_user` in-app/FCM push. Both best-effort — never fail the hold.
- Branch `feat/buyback-hold-status` off `staging` (includes the date hotfix). Per user pref: `/code-review` before each commit; staging first → prod on double-confirm.

## Review Focus
- **Hold from a non-active status** (BOUGHT/LOST/CANCELLED/already ON_HOLD) → 409, no state change. (Task 3/4)
- **Resume a record that isn't ON_HOLD** → 409. (Task 3/4)
- **Resume restores the EXACT prior status** (e.g. held from INSPECTION → resumes to INSPECTION, not PENDING_EVALUATION). (Task 3)
- **Empty/missing reason** on hold → 400. (Task 4)
- **A raising email or notify_user does NOT fail the hold** (best-effort). (Task 4)

---

## File Structure
**Backend — modify:** `jarvis/migrations/domains/schema_buyback.py` (columns + reason seed), `schema_roles.py` (permission), `jarvis/buyback/lifecycle.py` (ON_HOLD), `jarvis/buyback/repositories/record_repository.py` (updatable cols + SELECT), `jarvis/buyback/services/buyback_service.py` (hold/resume), `jarvis/buyback/services/notifications.py` (held notification: email+push), `jarvis/buyback/routes/records.py` (+ routes or a new `routes/hold.py` + `routes/__init__.py`), `jarvis/buyback/routes/lookups.py` (hold_reasons option).
**Backend — create:** `tests/test_buyback_hold.py`.
**Frontend — modify:** `recordStatus.ts`, `types/buyback.ts`, `api/buyback.ts`, `pages/BuyBack/ActionPanel.tsx` (+ a shared `HoldDialog`), `pages/BuyBack/index.tsx`, `pages/BuyBack/BuyBackDetail.tsx`, `ActionPanel.test.tsx`.

---

## Task 1: Migration batch — hold columns + reason seed + permission
**Files:** modify `schema_buyback.py`, `schema_roles.py`.

- [ ] **Step 1 — hold columns** (in `create_schema_buyback`, after the indexes, idempotent per column):
```python
    for _col, _type in [
        ('hold_prior_status', 'VARCHAR(24)'), ('hold_reason', 'VARCHAR(100)'),
        ('hold_note', 'TEXT'), ('held_at', 'TIMESTAMPTZ'), ('held_by', 'INTEGER'),
    ]:
        cursor.execute(f'''
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='buyback_records' AND column_name='{_col}') THEN
                    ALTER TABLE buyback_records ADD COLUMN {_col} {_type};
                END IF;
            END $$;
        ''')
```
(`_col`/`_type` are code-controlled literals, not user input — safe to f-string.)

- [ ] **Step 2 — reason dropdown seed** (idempotent, mirror the CUSTODIE `WHERE NOT EXISTS` pattern), one INSERT per value for `dropdown_type='buyback_hold_reason'`: `Poze lipsă`, `Talon/CIV lipsă`, `VIN lipsă/greșit`, `Preț incomplet`, `Date contact lipsă`, `Altele`.

- [ ] **Step 3 — permission** in `_seed_buyback_permissions_v2`: add tuple `('record','Buyback Records','hold','Hold','Pune o solicitare în așteptare (info lipsă)', True, 9)` to `perms`; extend the Acquisition grant loop to include `('record','hold')`. (Admin/Manager + Viewer-deny auto via `all_entities_actions`.)

- [ ] **Step 4:** `python3 -m py_compile` both files. Do NOT run psql/init_db (shared localhost DB). Verify by re-reading the SQL vs this brief.
- [ ] **Step 5:** `/code-review`, then commit `feat(buyback): hold columns + buyback_hold_reason seed + buyback.record.hold permission`.

## Task 2: lifecycle ON_HOLD + repo whitelist/SELECT
**Files:** modify `lifecycle.py`, `record_repository.py`.

- [ ] **Step 1:** `lifecycle.py` — add `ON_HOLD = 'ON_HOLD'`; `STATUS_LABELS[ON_HOLD] = 'Suspendat'`; in `TRANSITIONS` add `ON_HOLD` to each of the 4 active statuses' sets, and add `ON_HOLD: {PENDING_EVALUATION, INITIAL_OFFER, INSPECTION, FINAL_OFFER}`.
- [ ] **Step 2 (failing test first):** add `tests/test_buyback_hold.py` asserting `lifecycle.is_valid_transition('PENDING_EVALUATION','ON_HOLD')` and `is_valid_transition('ON_HOLD','INSPECTION')` are True, and `STATUS_LABELS['ON_HOLD']=='Suspendat'`. Run → it passes only after Step 1 (if writing strictly TDD, write test, see it fail on the missing constant, then add Step 1).
- [ ] **Step 3:** `record_repository.py` — add the 5 hold columns to `_UPDATABLE_COLUMNS`, and add `r.hold_prior_status, r.hold_reason, r.hold_note, r.held_at, r.held_by` to the `_SELECT` field list (so GET returns them).
- [ ] **Step 4:** run the lifecycle test (green). **Step 5:** `/code-review`, commit `feat(buyback): ON_HOLD lifecycle status + hold fields on record repo`.

## Task 3: `BuyBackService.hold` / `.resume` + tests
**Files:** modify `buyback_service.py`; test `tests/test_buyback_hold.py`.
**Interfaces produced:** `hold(record, reason, note, actor) -> dict`, `resume(record, actor) -> dict`.

- [ ] **Step 1 — failing tests** (mock `self.records`/`self.events`): hold from each active status sets status ON_HOLD, `hold_prior_status=old`, stamps reason/note/held_at/held_by, logs `held` event; hold from BOUGHT/LOST/ON_HOLD raises ValueError. resume from ON_HOLD calls set_status(hold_prior_status) + clears the 5 fields + logs `resumed`; resume from non-ON_HOLD raises ValueError. Assert resume restores the EXACT prior status (held from INSPECTION → INSPECTION).
```python
# shape (patch service.records / service.events with MagicMock)
svc = BuyBackService()
svc.records = MagicMock(); svc.events = MagicMock()
rec = {'id': 1, 'status': 'INSPECTION'}
svc.records.set_status.return_value = {**rec, 'status': 'ON_HOLD'}
svc.records.update.return_value = {**rec, 'status': 'ON_HOLD'}
svc.hold(rec, 'Poze lipsă', 'lipsesc 3 poze', actor=9)
assert svc.records.set_status.call_args.args[:2] == (1, 'ON_HOLD')
upd = svc.records.update.call_args.args[1]
assert upd['hold_prior_status']=='INSPECTION' and upd['hold_reason']=='Poze lipsă'
```
- [ ] **Step 2:** implement (mirror `force_status`'s set_status+update+log shape; do NOT call `transition`):
```python
_HOLDABLE = (lifecycle.PENDING_EVALUATION, lifecycle.INITIAL_OFFER,
             lifecycle.INSPECTION, lifecycle.FINAL_OFFER)

def hold(self, record, reason, note, actor) -> dict:
    if record['status'] not in _HOLDABLE:
        raise ValueError(f"Cannot hold a record in status {record['status']!r}")
    self.records.set_status(record['id'], lifecycle.ON_HOLD, actor)
    updated = self.records.update(record['id'], {
        'hold_prior_status': record['status'], 'hold_reason': reason,
        'hold_note': (note or '').strip()[:1000] or None,
        'held_at': datetime.now(timezone.utc), 'held_by': actor,
    })
    self.events.log(record['id'], 'held', actor, {'reason': reason, 'note': note})
    return updated

def resume(self, record, actor) -> dict:
    if record['status'] != lifecycle.ON_HOLD:
        raise ValueError(f"Record {record['id']} is not on hold")
    prior = record.get('hold_prior_status') or lifecycle.PENDING_EVALUATION
    self.records.set_status(record['id'], prior, actor)
    updated = self.records.update(record['id'], {
        'hold_prior_status': None, 'hold_reason': None, 'hold_note': None,
        'held_at': None, 'held_by': None,
    })
    self.events.log(record['id'], 'resumed', actor, {'restored_to': prior})
    return updated
```
- [ ] **Step 3:** tests green. **Step 4:** `/code-review`, commit `feat(buyback): BuyBackService.hold/resume`.

## Task 4: routes `/hold` + `/resume` + notify + register
**Files:** create `jarvis/buyback/routes/hold.py`; modify `routes/__init__.py`, `services/notifications.py`; test `tests/test_buyback_hold.py`.

- [ ] **Step 1 — notify helper** in `services/notifications.py`: `notify_held(record, reason, note, actor)` — best-effort email to the advisor/creator (reuse `_resolve_internal_recipient` + `send_email`) AND `from core.notifications.notify import notify_user; notify_user(record['created_by'], 'Solicitare BuyBack suspendată', message=f'{reason}' + (f' — {note}' if note else ''), link=f"/app/buyback/{record['id']}", entity_type='buyback_record', entity_id=record['id'], category='buyback')`. Wrap each in try/except (log+swallow).
- [ ] **Step 2 — routes** (`hold.py`), both `@v2_permission_required('buyback','record','hold')` + `_guard_company`:
  - `POST /records/<id>/hold`: body `{reason, note?}`; `reason` must be a non-empty string else 400; status must be holdable (service raises ValueError→409); call `service.hold`, then best-effort `notify_held`; return `{success, record}`.
  - `POST /records/<id>/resume`: `service.resume` (ValueError→409); return `{success, record}`.
  Add `from . import hold` to `routes/__init__.py`.
- [ ] **Step 3 — tests** (patch `_shared` repos + the service, triple current_user patch as in the custody route tests): hold happy path (200, service.hold called, notify called); non-active→409; empty reason→400; no-perm→403; cross-company→403; resume happy (200); resume non-hold→409; AND a best-effort test: patch `notify_held` (or the inner email/notify_user) to raise → assert the hold still returns 200.
- [ ] **Step 4:** tests green + `py_compile app.py`. **Step 5:** `/code-review`, commit `feat(buyback): POST /records/:id/hold + /resume with issuer email+push`.

## Task 5: frontend status plumbing (recordStatus + types + api)
**Files:** modify `recordStatus.ts`, `types/buyback.ts`, `api/buyback.ts`.
- [ ] `recordStatus.ts`: add `ON_HOLD` case → key `on_hold`, label `'Suspendat'`, badgeClass (amber, e.g. `'bg-amber-600 text-white'`), rowClass; add `{ value: 'ON_HOLD', label: 'Suspendat' }` to `STATUS_FILTER_OPTIONS`.
- [ ] `types/buyback.ts`: `BuybackStatus` += `'ON_HOLD'`; `BuybackRecord` += `hold_prior_status: string|null; hold_reason: string|null; hold_note: string|null; held_at: string|null; held_by: number|null`.
- [ ] `api/buyback.ts`: `hold: (id, data: {reason: string; note?: string}) => api.post(...'/hold')`; `resume: (id) => api.post(...'/resume')`. (Reasons come from the existing `getLookupOptions()` — add `hold_reasons` there in lookups.py: `'hold_reasons': _dropdown_or_static('buyback_hold_reason', _STATIC_HOLD_REASONS)` with a static fallback list.)
- [ ] Verify `npm run build` 0 errors. `/code-review`, commit `feat(buyback-ui): ON_HOLD status plumbing + hold/resume api`.

## Task 6: HoldDialog + ActionPanel Hold/Resume + tests
**Files:** modify `ActionPanel.tsx`, `ActionPanel.test.tsx` (+ inline `HoldDialog` or a small component).
- [ ] Show flags: `showHold = ['PENDING_EVALUATION','INITIAL_OFFER','INSPECTION','FINAL_OFFER'].includes(status) && can('buyback.record.hold')`; `showResume = status==='ON_HOLD' && can('buyback.record.hold')`.
- [ ] `holdMutation` → `buybackApi.hold(record.id, {reason, note})`; `resumeMutation` → `buybackApi.resume(record.id)`; success → toast + invalidate; error → `toast.error(errMsg(...))`.
- [ ] Hold button (showHold) opens a dialog: reason `Select` (options from `getLookupOptions().hold_reasons`) + optional note `Textarea`; "Suspendă" disabled until a reason is chosen. Resume button (showResume) → `resumeMutation`.
- [ ] Tests (add `hold`/`resume` to the `vi.mock('@/api/buyback')` block): active+perm shows Hold; ON_HOLD+perm shows Resume (not Hold); no perm hides both; non-active non-hold shows neither; modal "Suspendă" disabled with no reason.
- [ ] `npx vitest run ActionPanel.test.tsx` + `npm run build`. `/code-review`, commit `feat(buyback-ui): Hold/Resume actions + reason dialog in ActionPanel`.

## Task 7: list Hold/Resume + detail hold info
**Files:** modify `pages/BuyBack/index.tsx`, `BuyBackDetail.tsx`.
- [ ] `index.tsx`: in the per-row `DropdownMenu` actions, add **Suspendă** (active statuses + `can('buyback.record.hold')`) opening the shared HoldDialog, and **Reia** (ON_HOLD). Wire `holdMutation`/`resumeMutation` mirroring the existing `reopenMutation`/`deleteMutation`. `ON_HOLD` already flows into the status badge + filter via Task 5.
- [ ] `BuyBackDetail.tsx`: when `status==='ON_HOLD'`, show a small "Suspendat" info block — reason, note, held_at (fmtDate) — near the status.
- [ ] `npm run build` 0 errors. `/code-review`, commit `feat(buyback-ui): Hold/Resume on the list + hold info on detail`.

## Final verification (before integration)
- [ ] `cd jarvis/frontend && npm run build` 0 TS errors; `pytest tests/test_buyback_hold.py -q` green + full suite no NEW failures; `py_compile app.py`.
- [ ] Then integrate with custody + deploy (handled outside this plan).

## Self-Review (plan author)
- **Spec coverage:** status+transitions+label → T1/T2; columns+reason seed+permission → T1; repo whitelist/SELECT → T2; hold/resume service → T3; routes+notify(email+push) → T4; frontend status/types/api → T5; dialog+ActionPanel → T6; list+detail → T7. All spec sections mapped.
- **Placeholder scan:** concrete code for the novel backend (migration/service/routes); frontend tasks name exact files + the just-shipped custody patterns they mirror. No TBD.
- **Type consistency:** `hold(record,reason,note,actor)`/`resume(record,actor)`; route bodies `{reason,note?}`; `buybackApi.hold/resume`; `ON_HOLD`/`'Suspendat'`; the 5 hold fields identical across DB/repo/types. 
- **Review Focus:** all five (non-active hold, non-hold resume, exact-prior-restore, empty reason, best-effort notify) have tests in T3/T4.
