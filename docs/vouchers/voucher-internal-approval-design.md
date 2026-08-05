# Voucher Internal Approval — Design & Implementation Plan

**Status:** DESIGN ONLY (no code changed). Branch: `dev`.
**Goal:** Move voucher issuance fully onto the **direct-create `/api/vouchers` path** + the **internal `core/approvals` engine**, with **zero dependency on the Forms module**, and add full persistence of `start_date`, `company_id` (issuer-selectable), `client_email`, `client_cif`.

---

## 0. TL;DR — the key architectural finding

**The direct-create path is ALREADY wired into `core/approvals`.** `VoucherService.create_voucher`
(`jarvis/accounting/vouchers/services/voucher_service.py:65-135`) already:

1. resolves the approver (`resolve_approver`, same file `:18-63`),
2. inserts the voucher as `pending_approval` (`VoucherRepository.create`),
3. calls `ApprovalEngine().submit(entity_type='voucher', entity_id=…, context=…, requested_by=…)` (`:104-127`),
4. writes back `approval_request_id`,
5. emails the approver (`_notify_approver`).

A **voucher-native approval handler already exists and is registered**:
`jarvis/core/approvals/handlers/entity_voucher.py` (`handle_approved` → `activate_voucher`,
`handle_rejected` → `reject_voucher`), dispatched from `event_handlers._on_approved` (`:139-140`) and
`_on_rejected` (`:223-224`). A `voucher-approval` flow (`entity_type='voucher'`, one `context_approver`
step) exists in **staging and local** DBs (verified live).

**So the "make it self-contained on core/approvals" work is mostly already done for the direct-create
path — with ONE breaking gap:** `create_voucher` builds an approval `context` that is **missing
`approver_user_id` / `stakeholder_approver_ids`** (`:108-115`). The flow's single step is
`context_approver`, whose authorization (`engine._is_authorized`, `engine.py:552-568`) and queue
visibility (`request_repo.get_pending_for_user`, `request_repo.py:150-155`) BOTH read
`context_snapshot->>'approver_user_id'`. With that key absent, **the resolved manager can never approve
via the engine** (they don't appear in `/approvals/api/my-queue`, and `POST .../decide` raises
`NotAuthorizedError`). The forms path works only because `form_service._trigger_approval`
(`form_service.py:623-638`) DOES put `approver_user_id` + `stakeholder_approver_ids` in context.

**The single most important change (Task A1): enrich the `context` dict in `create_voucher` to include
`approver_user_id`, `stakeholder_approver_ids`, `title`, `company_id`.** Everything else (handler,
flow, notifications, activate/reject) is already in place.

Secondary decisions: seed the `voucher-approval` flow idempotently in migrations (currently DB-only,
not reproducible), add the persistence columns, and retire the Forms coupling.

---

## 1. `core/approvals` architecture (read-only findings)

### 1.1 Tables (`jarvis/migrations/domains/schema_approvals.py`)
- `approval_flows` (`:70-88`): `id, name, slug UNIQUE, description, entity_type, trigger_conditions JSONB,
  is_active, priority, allow_parallel_steps, auto_approve_below NUMERIC, auto_reject_after_hours,
  requires_signature, created_by, timestamps`.
- `approval_steps` (`:92-113`): `id, flow_id FK, name, step_order, approver_type, approver_user_id,
  approver_role_name, requires_all, min_approvals, skip_conditions JSONB, timeout_hours,
  escalation_step_id, escalation_user_id, notify_on_pending, notify_on_decision, reminder_after_hours`.
- **`approval_requests` (`:116-140`)**: `id, entity_type, entity_id, flow_id FK, current_step_id FK,
  status DEFAULT 'pending', context_snapshot JSONB, requested_by FK, requested_at, resolved_at,
  resolution_note, priority, due_by, created_at, updated_at`. Status CHECK ∈
  `('pending','in_progress','approved','rejected','cancelled','expired','escalated','on_hold')`.
  Indexes on `(entity_type, entity_id)`, `status`, `(current_step_id, status)`, `requested_by`.
- `approval_decisions` (`:146-162`), `approval_audit_log` (`:166-176`), `approval_delegations` (`:180-193`),
  `notifications` (`:198-211`).

### 1.2 How an approval request is created
`ApprovalEngine.submit(entity_type, entity_id, context, requested_by, priority='normal', due_by=None)`
— `jarvis/core/approvals/engine.py:57-152`:
1. `get_pending_for_entity` guard → `AlreadyPendingError` if one is open (`:67-71`).
2. `_find_matching_flow(entity_type, context)` (`:510-517`) — highest-`priority` active flow whose
   `trigger_conditions` match via `ConditionEvaluator.evaluate`; **`{}` conditions always match.**
   No flow → `NoMatchingFlowError`.
3. auto-approve check (`_check_auto_approve`, needs `context['amount']` < `auto_approve_below`; N/A for vouchers).
4. `RequestRepository.create(entity_type, entity_id, flow_id, requested_by, context_snapshot, priority, due_by)`
   (`request_repo.py:50-62`) → inserts `context_snapshot::jsonb`, returns id.
5. advance to first eligible step (`_find_next_eligible_step`), set status `pending` + `current_step_id`.
6. `hooks.fire('approval.submitted', {...})`.
Returns the full request row (`get_by_id`), i.e. a **dict with `id`** — `voucher_service` reads `approval.get('id')`.

### 1.3 Handler / event dispatch pattern (NOT a class registry — a hooks bus + hard-coded if-ladder)
- **Event bus** `jarvis/core/approvals/hooks.py`: `on(event, cb)`, `fire(event, payload)`, `clear()`; module-level
  `_registry: dict[str, list]`.
- **Registration** `jarvis/core/approvals/handlers/__init__.py::register_approval_hooks()` (`:14-29`),
  called once at startup: `app.py:363-364`. Binds `_on_submitted/_on_approved/_on_rejected/_on_returned/
  _on_step_advanced/_on_reminder` to their events.
- **Orchestrator** `jarvis/core/approvals/handlers/event_handlers.py`: each `_on_*` sends push+email, then
  **dispatches per entity_type with an explicit `if entity_type == '…'` ladder** to `entity_<type>.handle_*`.
  Voucher is already wired: `_on_approved` `:139-140`, `_on_rejected` `:223-224`. (`entity_form.py` is the
  Forms one; `entity_voucher.py`, `entity_invoice.py`, `entity_carpark.py`, `entity_marketing.py`,
  `entity_leave_permit_conversion.py` are the others.) **There is no `entity_type → handler` map to
  "register" into; you extend the if-ladder + drop an `entity_<type>.py` module.** For vouchers both already exist.
- **Voucher handler** `jarvis/core/approvals/handlers/entity_voucher.py` (whole file):
  - `handle_approved(entity_id, request_id=None, requester_id=None)` → `VoucherService().activate_voucher(entity_id)`.
  - `handle_rejected(entity_id, comment=None)` → `VoucherService().reject_voucher(entity_id, reason=comment)`.

### 1.4 How approve/reject is triggered + who is notified
- Approver hits **`POST /approvals/api/requests/<id>/decide`** (`routes.py:118-151`), body
  `{decision, comment, ...}`, guarded by `@approvals_access_required` → V2 perm `approvals.module.access`
  (`routes.py:26-37`). Calls `ApprovalEngine.decide(...)` (`engine.py:154-291`):
  - `_is_authorized` (`:544-594`): for `context_approver` reads `ctx['approver_user_id']` /
    `ctx['stakeholder_approver_ids']` (`:552-568`); also self-approval block (`:178-179`), role match,
    delegation.
  - on final `approved` → `hooks.fire('approval.approved')` → `_on_approved` → `entity_voucher.handle_approved`.
  - on `rejected` → `hooks.fire('approval.rejected')` → `_on_rejected` → `entity_voucher.handle_rejected`.
- Queue endpoints: `GET /approvals/api/my-queue` (`routes.py:216-223`) and `/my-queue/count`, both via
  `request_repo.get_pending_for_user` (`:115-180`) — context_approver visibility keyed on
  `context_snapshot->>'approver_user_id'` (`:151-153`) or `stakeholder_approver_ids @> ...` (`:154-155`).
- Notifications on submit: `_on_submitted` (`event_handlers.py:14-73`) →
  `_get_current_step_approvers(request_id)` (`_shared.py:140-186`) — for `context_approver` returns
  `stakeholder_approver_ids` else `[approver_user_id]` — then `notify_with_push` (in-app + push) +
  approver email. **Empty context ⇒ empty approver list ⇒ no engine notification.**
- Entity deep-links: `_shared._entity_link` (`:94-108`) has **no `voucher` case** → falls to `/app/approvals`;
  `_approval_deeplink` (`:111-115`) special-cases only `form_submission`.

### 1.5 `context_snapshot` usage
Frozen JSONB copy of everything the engine/notifier needs after submit: approver identity for
`context_approver` (`approver_user_id`, `stakeholder_approver_ids`), `title` (used by every notification/email
as `ctx.get('title') or '<entity_type> #<id>'`), `amount` (auto-approve + queue serialization), and any
`notify_on_*` lists (forms only). Read in `engine._is_authorized`, `engine._is_step_complete`
(`min_approvals_override`), `request_repo.get_pending_for_user`, and all `event_handlers._on_*`.

---

## 2. Current voucher ↔ approvals lifecycle (both paths)

### Path A — Forms engine (authoritative web "Issue" today)
FE `Accounting/Vouchers/index.tsx` view `issue` (`:280-303`) → `FormRenderer` + `useVoucherSchema`
(`hooks/useVoucherSchema.ts`) → `formsApi.submitInternal(formId, answers)` (`api/forms.ts:66-69` → `POST
/forms/api/forms/{id}/submit`) → forms engine → `form_service._trigger_approval`
(`form_service.py:594-658`, `entity_type='form_submission'`, flow id 7).
- submit: `_on_submitted` → `entity_form.handle_submitted` → `SubmissionRepository.update_status('pending_approval')`
  **+ `_create_voucher_on_submit`** (`entity_form.py:196-241`) creates the voucher `pending_approval`,
  linking `form_submission_id`, copying `approver_user_id` from the request context.
- approve: `_on_approved` → `entity_form.handle_approved` → `_activate_voucher_from_submission`
  (`entity_form.py:253-289`) → `VoucherService.activate_voucher`.
- reject: `_on_rejected` → `entity_form.handle_rejected` → `_reject_voucher_from_submission` (`:292-308`).
- Approver identity works because context has `approver_user_id`+`stakeholder_approver_ids`
  (`form_service.py:631-632`). Approver notified by the engine hooks.

### Path B — Direct-create `/api/vouchers` (legacy, to become the ONLY path)
FE `NewVoucher.tsx` (routed at `/app/accounting/vouchers/new`, `App.tsx:185`) → `vouchersApi.create` →
`POST /api/vouchers` (`routes/crud.py:59-88`) → `VoucherService.create_voucher`.
- **create_voucher ALREADY**: resolve approver → `repo.create` (`pending_approval`, `approver_user_id` set)
  → `engine.submit(entity_type='voucher', flow id 6)` → write `approval_request_id` → `_notify_approver`.
- approve: engine `approval.approved` → `_on_approved` → `entity_voucher.handle_approved` →
  `activate_voucher` (issued_at from `f_start_date` **only if `form_submission_id` present**, else today;
  `expires_at = start + validity_months`, `voucher_service.py:137-164`).
- reject: `approval.rejected` → `_on_rejected` → `entity_voucher.handle_rejected` → `reject_voucher` (`:169-178`).
- **BROKEN today:** context lacks `approver_user_id`/`stakeholder_approver_ids` (`:108-115`) → resolved
  manager not authorized and not in queue; only the out-of-band `_notify_approver` email fires. The
  request sits `pending` forever (until timeout auto-approve if the flow had `timeout_hours`, which it does not).

### What populates `vouchers.approval_request_id` / `approver_user_id`
- `approval_request_id`: Path B `voucher_service.py:123-127` (`repo.update_status(..., approval_request_id=…)`).
  Path A: not set on the voucher row (the link is `form_submission_id` → submission → its `approval_request_id`).
- `approver_user_id`: Path B `repo.create(approver_user_id=approver['id'])` (`:100`). Path A
  `_create_voucher_on_submit` (`entity_form.py:207-216, 235`) reads it from the request `context_snapshot`.
- **A dedicated voucher approve/reject handler outside `entity_form.py` already exists**: `entity_voucher.py`.

---

## 3. Forms coupling to vouchers — inventory + disposition

| # | Coupling | File / lines | Disposition when Forms is gone |
|---|----------|--------------|-------------------------------|
| 1 | `VOUCHER_FORM_SCHEMA`, `VOUCHER_FORM_SLUG`, `ensure_voucher_form()` | `accounting/vouchers/form_seed.py` (whole) | RETIRE seeding (stop calling `ensure_voucher_form` at startup). Keep the field list only if reused to build the native form UI; otherwise delete. `VOUCHER_FORM_SLUG` is imported by `routes/crud.py:5` and `entity_form.py:184` — remove those importers first. |
| 2 | `GET /api/vouchers/form-id`, `GET /api/vouchers/form-schema` | `routes/crud.py:24-56` | RETIRE once FE stops fetching the form schema. Return 410/remove after FE cutover. |
| 3 | Voucher creation/activation via form submission | `entity_form.py:115-345` (`_create_voucher_on_submit`, `_activate_voucher_from_submission`, `_reject_voucher_from_submission`, `_is_voucher_submission`, `_parse_voucher_fields`, `_resolve_voucher_company`, `_find_voucher_by_submission`, `_create_voucher_from_submission_legacy`) | RETIRE after existing form-created pending vouchers drain (see §6 risk). These are only reachable for `entity_type='form_submission'` on the voucher form. Leaving them is harmless once no new voucher form submissions occur; delete in a later cleanup. |
| 4 | Generic approval trigger (used by voucher form) | `form_service._trigger_approval` (`:594-658`) | KEEP as-is (generic to all forms). Voucher no longer routes through it. No change. |
| 5 | FE authoritative Issue via Forms | `Accounting/Vouchers/index.tsx:251-303`, `hooks/useVoucherSchema.ts`, `components/forms/FormRenderer.tsx`, `api/forms.ts submitInternal`, public `Public/VoucherPortal.tsx` | REPLACE the `issue` view's submit with a native voucher form posting `/api/vouchers`. `FormRenderer`/`submitInternal` stay (used by real forms); just stop using them for vouchers. Decide public `VoucherPortal` fate (see open questions). |
| 6 | `activate_voucher` reads `f_start_date` from submission answers | `voucher_service.py:145-155` | REPLACE with `voucher['start_date']` column (Task B). Keep the submission fallback branch until Path A is fully removed. |
| 7 | `vouchers.form_submission_id` column + index | `schema_vouchers.py:92-99` | KEEP the column (nullable; historical link). New direct-create vouchers leave it NULL. |

**Must be preserved regardless:** `resolve_approver` (`voucher_service.py:18-63`), the whole redeem flow
(`redeem_voucher` + `/api/vouchers/redeem*`, `RedeemScan.tsx`, `VoucherPortal` redemption), the service-catalog
endpoints (`routes/crud.py:200-500`), PDF/send (`routes/crud.py:137-197`), digest (`digest.py`) and cleanup
(`tasks/cleanup.py`) — none of these import Forms.

---

## 4. `resolve_approver` (independent of Forms — confirmed)

`VoucherService.resolve_approver(user_id, company_id, explicit_approver_id=None)`
— `voucher_service.py:18-63`:
- **Explicit override:** if `explicit_approver_id` → `SELECT id,name,email FROM users WHERE id=%s` and return
  (`:29-33`). This is how the "Send for Approval to" selection wins.
- **Direct manager:** user's `org_unit_id` → parent `structure_nodes.responsable_user_id` → that user
  (`:35-50`). *(Note: reads `structure_nodes`, not the Sincron organigram — consistent with accounting scope,
  see MEMORY. Out of scope here.)*
- **L0 fallback:** `company_responsables` for `company_id` (`:52-61`).
- Returns `{'id','name','email'}` or `None`. Called from `create_voucher:78-81` with
  `explicit_approver_id=data.get('approver_user_id')`. **No Forms dependency.** (`form_service._resolve_form_approver`
  merely delegates to it — the dependency is Forms→Voucher, not Voucher→Forms.)

---

## 5. `vouchers` table + migration mechanism

### 5.1 Current columns (verified live on staging + local)
`schema_vouchers.py:10-36` defines the base table; incremental `ALTER … ADD COLUMN IF NOT EXISTS` blocks add
`form_submission_id` (`:92-99`), `deleted_at` (`:102-108`), `service_items_value` (`:248-259`).
`client_email` and `redeemer_signature` were added elsewhere and **already exist** (live check). `company_id`
already exists (`INT NOT NULL REFERENCES companies(id)`). **Missing: `start_date`, `client_cif`** (confirmed
absent on staging).

### 5.2 How migrations run at deploy
`jarvis/migrations/init_schema.py` imports each `create_schema_*` and calls them in a fixed order
(`:43-69`). `create_schema_vouchers` runs at `:67`, then `create_schema_incremental` **last** at `:69`. This
runs on every boot (idempotent). Constraint (MEMORY): **all migrations must be additive + idempotent**
(`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `DO $$ … IF NOT EXISTS`), and on
`schema_incremental.py` merge conflicts "keep BOTH table blocks". New voucher columns + the flow seed belong in
`schema_vouchers.py` (co-located, already idempotent) — that is the recommendation below.

---

## 6. DESIGN — target state

### A. Direct-create → `core/approvals` (no Forms)

**A1 (the load-bearing fix). Enrich the approval context in `create_voucher`.**
File `jarvis/accounting/vouchers/services/voucher_service.py`, replace the `context` dict (`:108-115`) so it
carries approver identity + a human title (the engine/notifier both depend on these):

```python
context = {
    'title': f"Voucher {voucher['voucher_code']} — {voucher['client_name']}",
    'voucher_code': voucher['voucher_code'],
    'client_name': voucher['client_name'],
    'voucher_type': voucher['voucher_type'],
    'value_lei': str(voucher.get('value_lei') or ''),
    'discount_code': voucher.get('discount_code') or '',
    'discount_percentage': str(voucher.get('discount_percentage') or ''),
    'company_id': company_id,
    'approver_user_id': approver['id'],                 # ← authorizes context_approver step
    'stakeholder_approver_ids': [approver['id']],       # ← queue visibility + push/email fan-out
}
```

This makes: (a) `engine._is_authorized` authorize the resolved manager, (b) the request appear in
`/approvals/api/my-queue`, (c) `_on_submitted` push/email the approver via the engine.

**A2. Remove the duplicate out-of-band email.** With A1, `_on_submitted` now emails+pushes the approver.
Delete or gate the `self._notify_approver(voucher, approver)` call (`voucher_service.py:132`) and its method
(`:202-221`) to avoid a double email. (Keep `_notify_issuer_approved/_rejected/_redeemed` — those are the
engine's `_on_approved`/`_on_rejected` requester emails are ALSO sent, so also consider deduping issuer emails;
see open question OQ4.)

**A3. Handler + registration — NO NEW CODE NEEDED.** `entity_voucher.py` already implements
`handle_approved`/`handle_rejected` and is already dispatched from `event_handlers._on_approved:139-140` /
`_on_rejected:223-224`. Approve → `activate_voucher`, reject → `reject_voucher`. Confirmed reused.

**A4. Seed the `voucher-approval` flow idempotently (currently DB-only, not in code).**
Add to `schema_vouchers.py` (after the table, mirroring `schema_carpark.py:709-719`):

```sql
INSERT INTO approval_flows (name, slug, entity_type, is_active, priority, created_by)
SELECT 'Voucher Approval', 'voucher-approval', 'voucher', TRUE, 1, 1
WHERE NOT EXISTS (SELECT 1 FROM approval_flows WHERE slug = 'voucher-approval');

INSERT INTO approval_steps (flow_id, name, step_order, approver_type, notify_on_pending, notify_on_decision)
SELECT f.id, 'Manager Approval', 1, 'context_approver', TRUE, TRUE
FROM approval_flows f
WHERE f.slug = 'voucher-approval'
  AND NOT EXISTS (SELECT 1 FROM approval_steps s WHERE s.flow_id = f.id);
```

Rationale: staging/prod already have this flow (created via admin UI), but a **fresh DB has none** → `submit`
would raise `NoMatchingFlowError`. The `WHERE NOT EXISTS` guards make it a no-op where it already exists.
(The existing `UPDATE approval_steps SET approver_type='context_approver'` block at `schema_vouchers.py:120-124`
stays and remains harmless.)

**A5. Robust `create_voucher` failure handling.** Today `engine.submit` is wrapped in a bare
`except Exception: logger.exception(...)` (`:128-129`), so a missing flow silently leaves an orphan
`pending_approval` voucher with no request. Decide policy (OQ2): either surface the error (raise `ValueError`
so the API returns 400) or keep best-effort. Minimum: log at ERROR (already does) and ensure A4 removes the
common cause.

**A6. Voucher entity deep-links (polish, optional but recommended).** Add a `voucher` case to
`_shared._entity_link` (`:94-108`) → `/app/accounting/vouchers` (or `/app/accounting/vouchers?id={id}`), so
approver/issuer notifications link to the voucher instead of the generic `/app/approvals`.

**Resulting lifecycle (Path B only):**
`POST /api/vouchers` → `repo.create` (`pending_approval`, approver_user_id) → `engine.submit('voucher', …,
context WITH approver)` → request `pending`, step `context_approver` → `approval.submitted` push+email to
approver → approver `POST /approvals/api/requests/<id>/decide {approved}` → `approval.approved` →
`entity_voucher.handle_approved` → `activate_voucher` (issued_at = start_date or today; expires = start +
validity) → issuer notified. Reject symmetric → `reject_voucher` → status `rejected`.

### B. Full persistence

**B1. Migration (idempotent, additive) — append to `schema_vouchers.py` before final `conn.commit()`:**

```sql
ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS client_cif VARCHAR(20);
-- client_email already exists (added earlier); include IF NOT EXISTS for fresh DBs / safety:
ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS client_email VARCHAR(255);
```

`company_id` already exists (NOT NULL) — no migration; issuer selection is handled in the service (B4).
Wrap each in the repo's standard idempotent style; `ADD COLUMN IF NOT EXISTS` is itself idempotent so a plain
statement is sufficient (matches `schema_forms.py:35-40`).

**B2. `VoucherCreate` schema additions** (`accounting/vouchers/schemas.py:12-73`):
```python
start_date: Optional[date] = None          # activation anchor; default today at activation
company_id: Optional[int] = None           # issuer override; default current_user.company_id
client_email: Optional[str] = None
client_cif: Optional[str] = None
```
Add light validators: `client_email` format (or reuse an EmailStr), `client_cif` strip/upper, `start_date` not
absurdly past (optional). `date` is already imported (`schemas.py:5`).

**B3. `VoucherRepository.create` changes** (`repositories/voucher_repository.py:47-80`): add params
`start_date=None, client_cif=None` (client_email already a param `:53`); extend the INSERT column list + VALUES
+ tuple to persist `start_date`, `client_cif` (and keep `client_email`). Nullable, so existing callers
(including `entity_form.py`) remain valid.

**B4. `create_voucher` wiring** (`voucher_service.py:65-135`):
- Resolve effective company: `company_id = data.get('company_id') or company_id` (issuer override; validate the
  user may issue for it — OQ3).
- Pass `start_date=data.get('start_date')`, `client_email=data.get('client_email')`,
  `client_cif=data.get('client_cif')` to `repo.create`.

**B5. Activation uses `start_date`** (`voucher_service.activate_voucher:137-164`): change the anchor to
```python
start = voucher.get('start_date') or date.today()
# (keep the form_submission f_start_date branch ONLY while Path A still exists; remove with §3 item 6)
expires = start + relativedelta(months=voucher['validity_months'])
```
Preserves existing behavior when `start_date` is NULL.

**B6. Read models / list** — add `start_date`, `client_cif` to `VoucherRead` (`schemas.py:76-104`); `client_email`
already implicitly in `repo` rows. Surface in `get_by_id`/`get_all` via `v.*` (already `SELECT v.*`).

### C. Forms decoupling

Order matters (retire consumers before producers):
1. **FE cutover (Task C1):** replace `Accounting/Vouchers/index.tsx` `issue` view submit to build a native
   voucher payload and call `vouchersApi.create` (`/api/vouchers`), adding fields for company (select),
   start_date, client_email, client_cif, approver ("Send for Approval to"). Reuse/extend `NewVoucher.tsx`
   (already posts `/api/vouchers`) rather than `FormRenderer`. Remove `useVoucherSchema` +
   `getFormSchema/getFormId` usage for vouchers.
2. **Backend endpoints (Task C2):** after FE no longer calls them, remove/410 `GET /api/vouchers/form-id` +
   `/api/vouchers/form-schema` (`routes/crud.py:24-56`) and drop the `VOUCHER_FORM_SLUG` import (`crud.py:5`).
3. **Stop seeding the form (Task C3):** remove the `ensure_voucher_form()` startup call (find via
   `grep -rn ensure_voucher_form jarvis/`); leave the existing `forms` row in place (harmless) or disable it.
4. **Handler cleanup (Task C4, LAST):** once no pending voucher form submissions remain (see risk), delete the
   voucher helpers in `entity_form.py:115-345` and their references in `event_handlers` (they only run for
   `entity_type='form_submission'`, so they are inert for the new path even before deletion).

**Preserve:** `resolve_approver`, redeem flow, service-catalog endpoints, PDF/send, digest, cleanup,
`vouchers.form_submission_id` column, and `form_service._trigger_approval` (generic).

**Risky — existing pending vouchers created via the Forms path:** vouchers with `status='pending_approval'`
and a non-NULL `form_submission_id` are tied to a `form_submission` approval request (flow 7). If you disable
the Forms module / stop registering `entity_form` dispatch, **those in-flight requests can no longer
activate/reject** through hooks. Mitigation: (a) keep `entity_form.py` + the form-submission handler dispatch
alive until a live query shows zero open form-linked pending vouchers
(`SELECT COUNT(*) FROM vouchers WHERE status='pending_approval' AND form_submission_id IS NOT NULL`), or
(b) one-time backfill/migrate those to the voucher-approval flow. Do **not** delete `entity_form` voucher code
in the same release that cuts the FE over.

---

## 7. Task-by-task plan (each independently testable)

| Task | Files | Test |
|------|-------|------|
| **A4** Seed `voucher-approval` flow idempotently | `migrations/domains/schema_vouchers.py` | Fresh localhost DB → boot → `SELECT * FROM approval_flows WHERE slug='voucher-approval'` returns 1 row + 1 `context_approver` step; re-run boot → still 1 (idempotent). |
| **A1** Add `approver_user_id`/`stakeholder_approver_ids`/`title`/`company_id` to context | `services/voucher_service.py` | Create voucher via `/api/vouchers`; assert `approval_requests.context_snapshot->>'approver_user_id'` = approver; approver sees it in `GET /approvals/api/my-queue`. |
| **A2/A6** Dedupe approver email; add voucher deep-link | `voucher_service.py`, `handlers/_shared.py` | One approver email (not two); notification link → `/app/accounting/vouchers`. |
| **A-e2e** Approve → active / reject → rejected | (no code) | `POST /approvals/api/requests/<id>/decide {approved}` → voucher `active`, `issued_at`/`expires_at` set; `{rejected}` → `rejected`. |
| **B1** Migration: `start_date`, `client_cif` (+`client_email` safety) | `schema_vouchers.py` | Boot → columns exist (staging currently lacks them); re-run idempotent. |
| **B2** `VoucherCreate` fields + validators | `schemas.py` | Unit: valid payload with new fields parses; bad email/cif rejected. |
| **B3** `repo.create` persists new columns | `voucher_repository.py` | Insert with all fields → row round-trips. |
| **B4** `create_voucher` company override + field pass-through | `voucher_service.py` | Issue with `company_id` != caller's → stored company_id honored (subject to OQ3 authz). |
| **B5** Activation from `start_date` | `voucher_service.py` | Voucher with `start_date=2026-09-01`, validity 12 → on approve `issued_at=2026-09-01`, `expires_at=2027-09-01`. |
| **C1** FE native issue form → `/api/vouchers` | `frontend/.../Vouchers/index.tsx`, `NewVoucher.tsx`, `api/vouchers.ts`, `types/vouchers` | Issue from web submits `/api/vouchers`; no `/forms/*/submit` call (network tab). |
| **C2** Remove form-schema/form-id endpoints | `routes/crud.py` | Endpoints gone/410; app boots; catalog endpoints unaffected. |
| **C3** Stop seeding voucher form | startup wiring | Boot without creating a new `voucher-issuance` form. |
| **C4** Delete `entity_form` voucher helpers (LAST, gated) | `handlers/entity_form.py`, `event_handlers.py` | Only after zero open form-linked pending vouchers; regression: normal (non-voucher) forms still approve. |

Suggested deploy slices (surgical, per MEMORY branch-drift rule — cherry-pick code commits, no docs to
staging/main): Slice 1 = A4+A1+A2+A6 (fixes the engine path). Slice 2 = B1..B6 (persistence). Slice 3 = C1..C3
(Forms cutover). Slice 4 = C4 (cleanup, after drain).

---

## 8. Open questions / risks (top first)

1. **Flows are data, not code (HIGH).** `voucher-approval` (id 6) + `form-submission-approval` (id 7) exist in
   staging & local but are seeded by **no migration** (admin-UI created). A fresh/rebuilt DB has neither →
   `submit('voucher')` raises `NoMatchingFlowError`, silently swallowed → orphan pending voucher. **Task A4
   fixes this**; verify prod actually has flow 6 before shipping so the idempotent seed is a true no-op there.
2. **Missing approver in context is the current prod bug (HIGH).** Any voucher issued via `/api/vouchers`
   today cannot be approved through the engine (approver not authorized / not in queue). Confirm whether prod
   issuance currently even uses Path B (FE issue view uses Path A/Forms) — if all real issuance is via Forms,
   Path B may be effectively unused today, and A1 is what makes the cutover safe.
3. **Company-override authorization (MED).** Letting the issuer pick any `company_id` needs a guard (which
   companies may a user issue for?). Options: restrict to `company_responsables`/visible companies, or allow
   all for privileged roles. Needs a product decision before B4.
4. **Double requester/approver emails (MED).** `voucher_service` sends its own approver/issuer emails
   (`_notify_approver`, `_notify_issuer_*`) AND the engine hooks (`_on_submitted`, `_on_approved/_on_rejected`)
   send approver/requester emails. Post-A1 these overlap — decide which layer owns notifications (recommend the
   engine hooks; retire the service-level approver email in A2, consider retiring issuer ones too).
5. **Draining Forms-path pending vouchers (MED).** Do not delete `entity_form` voucher code until
   `SELECT COUNT(*) FROM vouchers WHERE status='pending_approval' AND form_submission_id IS NOT NULL` = 0, or
   migrate those requests to flow 6. Sequence C4 last.
6. **Public `VoucherPortal.tsx` (LOW/MED).** It renders the voucher form publicly via `useVoucherSchema` +
   `FormRenderer` (Forms-based). Decide: drop public issuance, or build a public `/api/vouchers`-backed variant.
   Out of scope for the internal-approval change but part of full Forms removal.
7. **Staging staleness (LOW).** MEMORY: staging DB is a ~6-month stale snapshot and not auto-refreshed;
   validate the migration + flow seed on a **fresh localhost DB**, not just staging.
8. **`approvals.module.access` permission (LOW).** Approvers must hold V2 `approvals.module.access` to hit
   `/decide` and see `/my-queue`. Confirm the manager roles that approve vouchers already have it (they do for
   the Forms path, so unchanged).
```
