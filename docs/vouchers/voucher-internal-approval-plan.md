# Voucher Internal Approval — Build Plan (consolidated)

Companion to [voucher-internal-approval-design.md](voucher-internal-approval-design.md). Build on `dev`,
verify on localhost/staging, **no staging/main deploy without explicit user confirmation**. Deploy later
via surgical cherry-pick of the code commits (docs stay on dev), per the branch-drift rule.

## Confirmed product decisions
- **Company = own company only.** The Company field is shown for parity but fixed to the issuer's company
  (`company_id = current_user.company_id`). No company-override / no cross-company authz. (Design task B4 is dropped.)
- **Full persistence.** Add `start_date`, `client_cif` columns (client_email + company_id already exist).
- **Approval via `core/approvals`** (already wired) — fix the missing-approver context bug.
- **Notifications owned by the approval engine.** Retire the duplicate service-level approver email.
- **Fail closed:** if `engine.submit` finds no flow/approver, raise → API 400 (no orphan pending voucher).
- **Forms deprecated for vouchers**, but old `entity_form.py` voucher helpers are deleted LAST, only after
  zero form-linked pending vouchers remain (deferred out of this build).
- **Romanian labels** on mobile; web keeps its English labels.

## Build slices (each independently verifiable on dev/localhost)

### Slice 1 — Approval engine fix (backend, drift-free)
Files: `accounting/vouchers/services/voucher_service.py`, `migrations/domains/schema_vouchers.py`,
`core/approvals/handlers/_shared.py`.
1. Enrich `create_voucher` approval `context` with `title`, `company_id`, `approver_user_id`,
   `stakeholder_approver_ids=[approver_id]` (design A1).
2. Fail closed: if no approver resolved OR `engine.submit` returns falsy/raises → rollback the voucher +
   raise `ValueError` so the route returns 400 (design A5, hardened).
3. Retire the duplicate `_notify_approver` service email (engine `_on_submitted` now notifies) — design A2.
4. Idempotent seed of the `voucher-approval` flow + `context_approver` step in `schema_vouchers.py` (design A4).
5. Add a `voucher` case to `_shared._entity_link` → `/app/accounting/vouchers` (design A6).
Verify: fresh localhost DB boot seeds flow (idempotent on re-boot); issue via `/api/vouchers` →
`context_snapshot->>'approver_user_id'` set + appears in approver `/approvals/api/my-queue`; approve → `active`,
reject → `rejected`; one approver email.

### Slice 2 — Full persistence (backend, drift-free)
Files: `schema_vouchers.py`, `accounting/vouchers/schemas.py`, `.../repositories/voucher_repository.py`,
`.../services/voucher_service.py`.
1. Idempotent migration: `ADD COLUMN IF NOT EXISTS start_date DATE`, `client_cif VARCHAR(20)` (+ client_email safety).
2. `VoucherCreate`: add `start_date`, `client_email`, `client_cif` (validators). (`company_id` NOT taken from
   payload — own-company-only; keep deriving from `current_user`.)
3. `VoucherRepository.create`: persist `start_date`, `client_cif` (client_email already a param).
4. `activate_voucher`: anchor `issued_at`/`expires_at` on `voucher['start_date'] or today` (keep the
   form-submission fallback until Path A removed).
5. `VoucherRead` + list surface `start_date`, `client_cif`.
Verify: unit tests for schema + repo round-trip; approve a voucher with `start_date` → issued/expires anchored.

### Slice 3a — Web Accounting Issue view → native form (frontend, drift-free files)
Files: `frontend/src/pages/Accounting/Vouchers/index.tsx` (+ `NewVoucher.tsx` reuse), `api/vouchers.ts`,
`types/vouchers.ts`. Replace the `view==='issue'` `FormRenderer`+`useVoucherSchema` block with a native voucher
form posting `/api/vouchers` (fields: Company [read-only own], Department [optional], CRM search, Client Name,
CIF, Email, Contract, VIN, Validity, Type+sub-field with service prices+total, Notes, Starting Date, Send-for-
Approval). Stop importing `useVoucherSchema`/`getFormSchema` for vouchers. Do NOT touch generic `FormRenderer`
(other forms use it).
Verify: `npm run build` clean; issuing from web posts `/api/vouchers` (no `/forms/*/submit`).

### Slice 3b — HUB Vouchers tile routes the native issue form (frontend, drift-free files)
Files: `frontend/src/pages/Hub/index.tsx`, `frontend/src/pages/Profile/VouchersPanel.tsx`. Make the dedicated
`vouchers` tile reach the native issue form (wire the existing `showIssue` trigger in `VouchersPanel`, now
rendering the native form instead of the Forms block). Gate stays `vouchers.profile.view`.
Verify: `npm run build`; from the Vouchers tile you can open the issue form and submit.

### Slice M — Mobile New.tsx full field parity (jarvis-mobile-2)
File: `jarvis-mobile-2/src/pages/Vouchers/New.tsx` (+ `useApi.ts` hooks: companies (own), departments, users
(approver), reuse `useCrmClientSearch`, `useServiceCatalogCompany`). Romanian labels. Add: Companie (read-only
own), Departament, Caută client CRM (autofill Nume/CIF/Email/VIN/Contract), CIF/CUI, Email client, Data începerii
(default today), Trimite spre aprobare (approver, default "Manager direct"), service prices + running total.
Extend `VoucherCreatePayload` + submit with `start_date`, `client_email`, `client_cif`, `approver_user_id`.
Verify: `npm run build && npx cap sync android`; vitest.

## Deferred (not in this build)
- Forms cleanup (delete `entity_form.py` voucher helpers) — after in-flight form-vouchers drain.
- Public `VoucherPortal.tsx` fate (still Forms-based).
- Removing `form-schema`/`form-id` endpoints — after web/mobile cutover verified.

## Deploy (later, per branch-drift rule; needs explicit confirmation)
Cherry-pick code commits (no docs) → staging first, verify, then main (2 confirmations). Slices ship in order 1→2→3→M.
