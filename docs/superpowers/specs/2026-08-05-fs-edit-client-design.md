# Field Sales — Edit Client Details (Phase 2, Slice 3)

**Date:** 2026-08-05
**Branch:** `fs-edit-client` (off `dev` 787699eec) → ff-merge to `dev` at finish.
**Type:** Small feature. Third slice of Phase 2 (`add-info-during-visit`).

## Problem
A KAM can view a client's details in the Field Sales Client 360 card but cannot correct them (a stale phone, a wrong contact person, a missing address). The only client-edit path today is the CRM endpoint `PUT /api/crm/clients/:id`, which requires `@crm_required` + `can_edit_crm` — permissions a KAM typically lacks — and applies no tenant scoping. This slice adds an in-context edit for the correction-worthy identity/contact fields.

## Decisions (user)
- **Editable fields:** `display_name, contact_person, phone, email, street, city, region, country, company_name, nr_reg` (all already in `crm.ClientRepository._EDITABLE`). `cui` is excluded (owned by the ANAF/fiscal enrich flow).
- **Access:** any Field Sales user may edit any client they can open — **no tenant/ownership gate**. Because `crm_clients` is a shared master record, an edit is global; this is intentional (a corrected phone benefits every tenant).

## Data model
No schema change. Two existing tables: `crm_clients` (shared master — the editable fields live here) and `client_profiles` (per-tenant overlay). The write reuses `crm.repositories.client_repository.ClientRepository.update(client_id, data)` — it whitelists via `_EDITABLE`, converts `''`→NULL, keeps `name_normalized` in sync when `display_name` changes, JSONB-wraps dict/list values, and returns the fresh row. It is already covered by `jarvis/tests/foi_parcurs/test_crm_client_update.py`.

The `GET /clients/:id/360` endpoint already returns the full `crm_clients` row under `result['client']` (`ClientFsRepository.get_360` → `SELECT * FROM crm_clients`), but the frontend `getClient360` normalizer currently **drops** it — so this slice must expose it for the edit form's prefill.

## Design

### Backend — new endpoint (reuse the CRM writer, add FS access)
`PUT /api/field-sales/clients/<int:client_id>` in `jarvis/field_sales/routes/clients.py`, decorated `@jwt_or_login_required` + `@field_sales_required`. Steps:
1. `data = request.get_json(silent=True) or {}`.
2. Filter `data` to the FS-editable subset `FS_EDITABLE = {display_name, contact_person, phone, email, street, city, region, country, company_name, nr_reg}` (a module constant). Dropping any other key (e.g. `is_blacklisted`, `client_type`, `cui`, `eurofib_konto_debit`, `driver_license_number`) — even though `ClientRepository._EDITABLE` would accept some of them, the FS surface must not.
3. If the filtered dict is empty → 400 "Niciun câmp editabil".
4. `client = ClientRepository().update(client_id, filtered)` (import from `crm.repositories.client_repository`). If `None` → 404 "Client negăsit sau niciun câmp editabil".
5. Return `{'success': True, 'client': client}`.
Docstring states explicitly: any FS user may edit; no tenant gate; edit is global on the shared `crm_clients` record (deliberate, not an oversight).

### Frontend
- **Expose the raw client row.** Add an `FSClientRaw` interface (the editable subset + `id`, `cui` for display) and a `client: FSClientRaw | null` field to `FSClient360` (`api/fieldSales.ts`). In `getClient360`'s normalizer, map `res.client` → `FSClientRaw` (it's already in the backend response, just currently discarded).
- **API wrapper.** `updateClient(clientId: number, data: Partial<FSClientRaw>)` → `api.put('/api/field-sales/clients/${clientId}', data)` returning `{ success: boolean; client: FSClientRaw }`.
- **`ClientCard360` edit mode.** An "Editează" button toggles an edit form (local `useState` for the 10 fields, prefilled from `client360.client`) with a "Salvează"/"Anulează" pair. "Salvează" runs a `useMutation(updateClient)` whose `onSuccess` invalidates `['field-sales-client360', clientId]` (the card refetches with the fresh values) and exits edit mode; "Anulează" discards local edits and exits. Save button disabled while the mutation is pending. Keep the existing read-only sections (fiscal, fleet, purchases, visit history) unchanged; the edit form covers only the `crm_clients` identity/contact fields. iOS-sized inputs, Romanian labels.

### Data flow
Edit → `updateClient` → `PUT` → `ClientRepository.update` (whitelisted crm_clients write) → 360 query invalidated → card shows fresh values. `name_normalized` stays consistent automatically.

## Tenant-awareness
None, by user decision. The endpoint requires only `@field_sales_required`; there is no `company_id`/ownership check. `crm_clients` is a shared master table, so the edit is global. Documented in the endpoint docstring so a future reviewer doesn't read the absence as a bug.

## Error handling
- 400 when no editable field is supplied; 404 when the client doesn't exist. Frontend surfaces a toast on error and keeps the form open with the user's edits intact.

## Testing
- **Backend:** `python3 -c "import ast; ast.parse(...)"` on `clients.py`. A Flask test-client registration/auth test (mirroring `tests/test_field_sales_quick_note.py`): the route exists and rejects an unauthenticated `PUT` (401/302). The write itself is already covered by `test_crm_client_update.py` (the shared `ClientRepository.update`). The FS field-filter is small and deterministic; a focused unit test of the filter constant may be added if cheap.
- **Frontend (vitest, primary):** (a) `getClient360` now surfaces `client` (raw crm_clients subset) from a mocked response; (b) `ClientCard360` — "Editează" reveals the form prefilled from `client360.client` (e.g. the existing phone shows in the input); "Salvează" calls `updateClient(clientId, {...})` and invalidates `['field-sales-client360', clientId]`; "Anulează" restores read-only; save disabled while pending.
- **Gates:** `npx tsc --noEmit` clean; full `npx vitest run` pristine; backend `ast.parse`; `npm run build` then revert artifacts. Commit source only. Ignore the post-commit hook's pre-existing failures.

## Out of scope
- Editing `cui`/fiscal fields (ANAF-owned); editing `client_profiles` fields (revenue/priority/etc. — those have `update_profile`).
- A tenant/ownership gate (declined).
- CRM-admin fields (`is_blacklisted`, `client_type`, `eurofib_konto_debit`, `driver_license_number`).
- Fleet add/edit (Slice 4).

## Self-review
Decisions (contact+address set, any-FS-user) are encoded in `FS_EDITABLE` and the `@field_sales_required`-only gate. Reuses the tested `ClientRepository.update` for one source of write truth; the FS route only adds access + a narrower field filter. The one non-obvious dependency — the 360 normalizer must expose the already-returned `client` row for prefill — is called out explicitly. Testing centers on the frontend contract + a backend registration/auth guard, matching Slice 2's proven shape. Scope is one slice / one plan.
