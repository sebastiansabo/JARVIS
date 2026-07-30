# Voucher Module — Slice 3a (Accounting Issue view) + Slice 3b (HUB Vouchers tile)

Status: **Done.** Both slices are built on the reusable native `VoucherIssueForm`
component, posting directly to `POST /api/vouchers` (the same path `NewVoucher.tsx`
already used). No Forms-engine plumbing remains in either consumer.

## Goal recap

Move web voucher **issuing** off the Forms engine (`FormRenderer` +
`useVoucherSchema` + `formsApi.submitInternal`) onto the native direct-create
path, using one reusable form component embedded in both:
- Accounting → Vouchers → "Issue" view (`Accounting/Vouchers/index.tsx`)
- HUB → Vouchers tile (`Profile/VouchersPanel.tsx`)

The backend (`VoucherCreate` schema, `POST /api/vouchers`, `core/approvals`
routing) already supported `start_date`, `client_email`, `client_cif`,
`approver_user_id` on this branch — no backend changes were needed.

## Files created

- `jarvis/frontend/src/pages/Accounting/Vouchers/VoucherIssueForm.tsx` — new,
  self-contained, embeddable form. Props: `{ onSuccess?: () => void }`.

## Files changed

- `jarvis/frontend/src/types/vouchers.ts` — `VoucherCreatePayload` gained
  optional `start_date?`, `client_email?`, `client_cif?` (matches the
  `VoucherCreate` Pydantic schema in `accounting/vouchers/schemas.py`;
  `approver_user_id` already existed).
- `jarvis/frontend/src/pages/Accounting/Vouchers/index.tsx` — the `view ===
  'issue'` branch now renders `<VoucherIssueForm onSuccess={...} />` instead of
  `FormRenderer` + `useVoucherSchema`. Removed imports: `FormRenderer`,
  `useVoucherSchema`, `formsApi`, `api` (all were only used by the removed
  `formData` query / `submitFormMutation`). `onSuccess` switches `view` back to
  `'tracking'` and invalidates `['vouchers-accounting']`.
- `jarvis/frontend/src/pages/Profile/VouchersPanel.tsx` — added a visible
  "Issue Voucher" button (previously `setShowIssue(true)` was dead code — no
  UI ever called it). The `showIssue` branch now renders
  `<VoucherIssueForm onSuccess={...} />` instead of the Forms block. Removed
  imports: `FormRenderer`, `useVoucherSchema`, `formsApi`, `api`,
  `useMutation` (all only used by the removed `formData`/`issueSchema`/
  `submitMutation`). Kept `toast` import (still used by `InlineRedeem`, a
  separate component in the same file, for the existing public redeem flow).
  `onSuccess` closes the issue panel and invalidates `['my-vouchers']`. The
  HUB tile registration itself (`pages/Hub/index.tsx`) and the
  `vouchers.profile.view` gate (in `Hub/index.tsx` / `Profile/index.tsx`,
  external to `VouchersPanel`) were **not** touched.

`FormRenderer.tsx`, `useVoucherSchema.ts`, and `useVoucherSchema`'s other
consumer (`pages/Hub/index.tsx`'s generic form-preview renderer at ~line 1908,
unrelated to vouchers) were left untouched, as were `Public/VoucherPortal.tsx`
and `Public/PublicForm.tsx` (out of scope — public-facing forms, not part of
this task).

## VoucherIssueForm — field order & wiring

1. **Company** — read-only `<Input disabled value={user.company} />`. Not
   sent in the payload; the backend derives `company_id` from
   `current_user.company_id` in `create_voucher()` (confirmed in
   `accounting/vouchers/routes/crud.py`).
2. **Department** — optional `<Select>` populated from
   `organizationApi.getDepartments(userCompany)`, defaulting to
   `user.department`. Informational only — **not sent** in the payload. The
   `VoucherCreate` schema has no department field, so persisting it isn't
   currently possible without a backend change; kept as UI-only context,
   matching the task's instruction to omit it if unsupported.
3. **Search CRM Client** — a self-contained search box (not a reuse of
   `FormRenderer`'s `CrmClientField`, but the same API pattern): debounced-on-
   Enter/click search via `crmApi.getClients({ q, limit: '10' })`, rendering a
   dropdown of matches. Selecting a result calls `crmApi.getClient(id)` and
   autofills:
   - Client Name + CIF from the search result (`display_name`, `nr_reg`)
   - CIF from `detail.profile.cui` (overrides `nr_reg` if present, same
     precedence as `CrmClientField`)
   - Client Email from `detail.client.email`
   - Car VIN + Contract Number from `detail.deals[0]` (`vin`,
     `dossier_number`) when a deal exists
4. **Client Name*** (required), **CIF/CUI**, **Client Email** (validated for
   `@` when non-empty), **Contract Number*** (required), **Car VIN*** (17-char
   alphanumeric regex, same as `NewVoucher.tsx`).
5. **Validity*** (1/3/6/12/24 months select) and **Voucher Type*** (radio:
   Value / Discount Code / Percentage / Service Items) with the matching
   conditional sub-field. For **Service Items**: checkboxes populated from
   `vouchersApi.getServiceCatalogCompany()`, each row showing `{price}
   {currency}`, with a running **Total** in LEI (mirrors
   `ServiceCatalogField`). Locally the selection is held as
   `{id, name, price, currency}[]` (needed to compute the total), but on
   submit it is mapped to `service_items: selectedServices.map(s => s.name)`
   — a flat `string[]` — because the backend schema
   (`accounting/vouchers/schemas.py: service_items: Optional[list[str]]`)
   and `pdf_generator.py` both expect plain names, exactly the shape
   `NewVoucher.tsx` already sends (comma-split strings). This was verified
   against the Pydantic schema before implementing, since the Forms-engine
   `ServiceCatalogField` stores richer `{id,name,price}` objects that would
   NOT match the backend's `list[str]` contract.
6. **Notes** (optional textarea).
7. **Starting Date** — `<input type="date">` defaulting to today's date
   (`toISOString().slice(0,10)`) → payload `start_date`.
8. **Send for Approval to** — Popover + search combobox (same interaction
   pattern as `FormRenderer`'s `UserSelectField`, reimplemented locally so
   `FormRenderer` itself is not imported) over `usersApi.getUsers()`. First
   entry "Direct manager" clears the selection (no `approver_user_id` sent);
   picking a user sets `approver_user_id`.

Submit button: "Issue Voucher". On success: toast
`` `Voucher ${voucher_code} created — pending approval from ${approver_name}` ``
(identical message/format to `NewVoucher.tsx`), the form resets its internal
state, and `onSuccess?.()` fires (each host wires this to close its
inline view + invalidate its list query).

## Verification

- `cd jarvis/frontend && npm run build` → **zero errors.** The build script is
  `tsc -b && vite build`, so this is a full type-check + bundle, not just
  bundling. Output only shows the pre-existing "chunk larger than 500 kB"
  advisory (unrelated, pre-existing large chunks like `ProjectDetail`,
  `xlsx`, `ScatterChart`).
- Grep-confirmed: neither `Accounting/Vouchers/index.tsx` nor
  `Profile/VouchersPanel.tsx` reference `useVoucherSchema`, `FormRenderer`,
  `submitInternal`, or `formsApi` anymore.
- Confirmed via `git grep` that `FormRenderer`/`useVoucherSchema` still have
  other live consumers (`Public/VoucherPortal.tsx`, `Public/PublicForm.tsx`,
  `Forms/FormBuilder.tsx`, `Hub/index.tsx`'s unrelated generic-form-preview
  code, `InvoireForm.tsx`) — neither shared file was modified, so those are
  unaffected.

## Left informational / not persisted

- **Department** (Task A field 2) — selectable in the UI (defaults to the
  user's own department, scoped to their company via
  `organizationApi.getDepartments`), but **not included** in the
  `POST /api/vouchers` payload. Reason: `VoucherCreate` / `vouchers` table
  have no department column; there is nowhere on the backend for it to land
  without a schema change, which was out of scope for this slice.

## Commits (on `feat/voucher-web-hub`, not pushed)

1. `feat(vouchers): native VoucherIssueForm + web Accounting Issue view off Forms engine`
   — adds `VoucherIssueForm.tsx`, extends `VoucherCreatePayload`, rewires
   `Accounting/Vouchers/index.tsx`.
2. `feat(vouchers): route native issue form on the HUB Vouchers tile`
   — rewires `Profile/VouchersPanel.tsx` + adds the "Issue Voucher" button.
