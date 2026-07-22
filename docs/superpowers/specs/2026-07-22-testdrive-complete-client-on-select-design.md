# Test Drive — Complete Client Contact Details On Select

**Date:** 2026-07-22
**Repos:** JARVIS (backend, branch `dev`) + jarvis-mobile-2 (frontend, branch `main`)
**Status:** Approved design

## Problem

In the mobile Test Drive / Foi de Parcurs flow, a consilier searches the CRM and
selects an existing client. The backend `/api/foi-parcurs/crm-clients/search`
endpoint already returns `email` and `phone`, but:

- The mobile `CrmClient` type drops `email` entirely and treats `phone` as
  display-only.
- The only validation on the selected client is existence
  (`missing.client = !selectedClient`).

So a client with no phone (or no email) can be selected and the test drive
submitted. Contract/GDPR email and phone contact are therefore not guaranteed.

## Goal

When a client is selected and is missing **email** and/or **phone**, prompt the
consilier to fill the missing field(s) inline, immediately after selection, and
persist them to the CRM client record.

## Decisions (locked)

- **UX pattern:** inline fields under the selected-client card (not a modal).
- **Required fields:** phone required (with `07…/+40…/004…` validation), email
  optional. Mirrors the existing create-client endpoint.
- **Enforcement:** hard block — a selected client with no phone is treated as
  incomplete and blocks draft + activate, same as no client selected. Missing
  email does **not** block.
- **Trigger:** panel appears **only when a field is empty**, not for editing an
  existing (non-empty) value.

## Changes

### Backend (JARVIS, `dev`)

**New route:** `PATCH /api/foi-parcurs/crm-clients/<int:id>` in
`jarvis/foi_parcurs/routes/test_drive.py`, `@login_required` (mirrors the
existing login-gated `POST /api/foi-parcurs/crm-clients`). Rationale: consilieri
without full CRM (sales) access must be able to complete contact details.

Behaviour:
- Accepts JSON `phone` and/or `email`.
- If `phone` present: strip spaces/dashes, validate against `_PHONE_RE`
  (`07…/+40…/004…`); on failure return `400` with the existing message.
- Build a partial dict of provided fields and call
  `_crm_client_repo.update(id, data)` — both `phone` and `email` are already in
  the repo's `_EDITABLE` whitelist. Empty string → NULL (repo already maps this).
- Return `{'success': True, 'client': <updated>}`; unknown id → repo update
  returns `None` → `404`.

No repository changes required (`update()` and `_EDITABLE` already suffice).

### Frontend (jarvis-mobile-2, `main`)

1. **Type + normalizer:** add `email?: string | null` to `CrmClient`
   (`src/hooks/useApi.ts`) and carry it through `normalizeCrmClients`.

2. **Mutation hook:** `useUpdateCrmClient()` — `PATCH
   /api/foi-parcurs/crm-clients/:id` with `{ phone?, email? }`, returns the
   updated client; invalidates the `crm-client-search` query.

3. **ClientPicker (`src/pages/Sales/TestDrive/New.tsx`):**
   - After selection, when `!client.phone || !client.email`, render an inline
     "Completează datele clientului" panel under the selected card showing an
     input for each missing field plus a Save button.
   - Phone input reuses the create-path validation and error message.
   - On Save → call `useUpdateCrmClient` → on success `setSelectedClient(updated)`
     (panel collapses because the fields are now present).

4. **Gate:** change the `missing.client` computation so it is truthy when there
   is no selected client **or** the selected client has no phone. Email absence
   does not affect the gate. This flows into the existing draft (line ~306) and
   activate (line ~324) gates unchanged.

## Data flow

```
select client
  → detect missing phone/email
  → inline panel (missing inputs + Save)
  → Save → PATCH /crm-clients/:id → repo.update → returns full client
  → setSelectedClient(updated) → panel collapses, gate clears
```

## Error handling

- Invalid phone format → inline field error, no PATCH sent.
- PATCH failure (network/500) → inline error under Save; client stays
  incomplete; gate stays blocked.
- Empty email on Save → allowed (skipped / sent as null).

## Testing

- **Backend (pytest):** valid phone update; invalid phone → 400; email-only
  update; unknown id → 404; both fields update.
- **Frontend (manual via run/webapp flow):**
  - select client missing phone → blocked until saved;
  - select client missing email only → panel fillable, skippable, not blocked;
  - select complete client → no panel, gate clear.

## Out of scope

- Editing existing (non-empty) email/phone values from this panel.
- Any change to the desktop CRM client editor.
- Address/CNP completion (only email + phone).
