# Test Drive Form → Forms Module Integration — Design Spec

**Date:** 2026-06-29
**Module:** Foi de Parcurs + Forms
**Status:** Draft

## Overview

Migrate the standalone TestDriveForm (`/app/foi-parcurs/test-drive`, 721 lines) into the JARVIS Forms module. The form becomes a seeded form definition (like `voucher-issuance` and `bilet-de-invoire`), rendered by FormRenderer, submitted through the Forms API, and published to the Hub. A post-submit hook creates the `foi_de_parcurs` contract and generates PDFs.

## Why

- The standalone form duplicates FormRenderer's job — field rendering, validation, submission, signatures
- No submission tracking, no CSV export, no Hub integration, no audit trail
- Client search was wired to CRM instead of `fp_clients` (just fixed)
- Advisors should access this form from the Hub like other internal forms

## Flow (After Migration)

```
Advisor opens Hub → clicks "Test Drive" form tile
  → HubFormModal opens with FormRenderer
  → Selects Company → Selects Vehicle (filtered by company)
  → Vehicle info + latest inspection displayed
  → Searches fp_client or sees "no clients" hint
  → Fills route details (datetime, odometer, itinerary)
  → Fuel gauge levels (dropdown)
  → GDPR consent + inspection acceptance (checkboxes)
  → Client signature + advisor signature (2x SignatureCanvas)
  → Submit
  → Post-submit hook fires:
    → foi_de_parcurs contract created (status: FILLED, source: td_form)
    → Legal PDF + Custom PDF generated
    → PDF URLs returned in response
  → Success screen with thank-you message + PDF download links
```

## New Field Types (3)

### 1. `fp_vehicle` — Vehicle Selector

**Frontend (FormRenderer):**
- Select dropdown populated from `GET /api/foi-parcurs/vehicles?active_only=true`
- Filtered by company via `config.companyField` (watches another field's answer, same pattern as `department_select`)
- On selection: shows vehicle info card below (VIN, registration number, make, model, fuel type, tank capacity)
- Fetches latest inspection via `GET /api/foi-parcurs/vehicles/{id}/inspections/latest` — displays if exists
- Answer value: vehicle ID (integer)

**Backend (form_service.py):**
- Add `'fp_vehicle'` to `FIELD_TYPES` set
- Validation: check value is a non-empty integer

### 2. `fp_client` — FP Client Search

**Frontend (FormRenderer):**
- Text input with debounced autocomplete (300ms)
- Searches `GET /api/foi-parcurs/clients/search?q=...&limit=10`
- Dropdown shows name + phone for each match
- On selection: shows client badge with name, option to clear/change
- Answer value: client ID (integer)

**Backend (form_service.py):**
- Add `'fp_client'` to `FIELD_TYPES` set
- Validation: check value is a non-empty integer

### 3. `datetime` — DateTime Input

**Frontend (FormRenderer):**
- `<Input type="datetime-local" />` (same pattern as existing `date` case)
- Answer value: ISO datetime string

**Backend (form_service.py):**
- Add `'datetime'` to `FIELD_TYPES` set
- Validation: check value is a valid datetime string

## Form Schema (Seeded)

Slug: `test-drive`

| Order | Field ID | Type | Label | Required | Config |
|-------|----------|------|-------|----------|--------|
| 1 | `f_td_heading` | `heading` | Formular Test Drive | - | - |
| 2 | `f_company` | `company_select` | Companie | Yes | - |
| 3 | `f_vehicle` | `fp_vehicle` | Vehicul | Yes | `{companyField: 'f_company'}` |
| 4 | `f_client` | `fp_client` | Client | Yes | - |
| 5 | `f_departure` | `datetime` | Data si ora plecarii | Yes | - |
| 6 | `f_return` | `datetime` | Data si ora intoarcerii | No | - |
| 7 | `f_odometer_start` | `number` | KM plecare | Yes | - |
| 8 | `f_odometer_end` | `number` | KM sosire | No | - |
| 9 | `f_estimated_km` | `number` | KM estimat | Yes | - |
| 10 | `f_itinerary` | `long_text` | Traseu / Itinerariu | Yes | `{placeholder: 'Descrieti traseul...'}` |
| 11 | `f_fuel_start` | `dropdown` | Nivel combustibil plecare | Yes | - |
| 12 | `f_fuel_end` | `dropdown` | Nivel combustibil sosire | No | - |
| 13 | `f_gdpr` | `checkbox` | Consimtamant GDPR | Yes | - |
| 14 | `f_inspection` | `checkbox` | Acceptare inspectie vehicul | Yes | - |
| 15 | `f_advisor` | `short_text` | Nume consilier | Yes | - |
| 16 | `f_client_sig` | `signature` | Semnatura client | Yes | - |
| 17 | `f_advisor_sig` | `signature` | Semnatura consilier | Yes | - |

**Dropdown options for fuel fields:** `["1", "3/4", "2/3", "1/2", "1/4"]`

**Checkbox options:**
- `f_gdpr`: `["Accept procesarea datelor personale conform GDPR"]`
- `f_inspection`: `["Accept starea vehiculului conform ultimei inspectii"]`

**Form settings:**
```json
{
  "thank_you_message": "Test Drive inregistrat cu succes!",
  "prefill": {
    "f_advisor": "user.name"
  }
}
```

The `prefill` map tells HubFormModal to populate `f_advisor` from the current user's name before rendering.

## Seed Script

File: `jarvis/foi_parcurs/form_seed.py`

Pattern: identical to `accounting/vouchers/form_seed.py`
- `TEST_DRIVE_FORM_SLUG = 'test-drive'`
- `TEST_DRIVE_FORM_SCHEMA = [...]` (the 17 fields above)
- `ensure_test_drive_form()` — idempotent insert into `forms` table
- Called from `init_schema.py` alongside `ensure_voucher_form()`
- Form created as `status='published'`, `published_to_hub=True`, `requires_approval=False`

## Post-Submit Hook

In `forms/services/form_service.py`, extend `_run_post_submit_hooks()`:

```python
def _run_post_submit_hooks(self, form, submission_id, answers, user_id):
    slug = form.get('slug', '')
    try:
        if slug == 'voucher-issuance' and user_id:
            self._create_voucher_from_submission(form, submission_id, answers, user_id)
        elif slug == 'test-drive':
            self._create_test_drive_contract(form, submission_id, answers, user_id)
    except Exception as e:
        logger.error(...)
```

### `_create_test_drive_contract()` logic:

1. **Look up vehicle** — `fp_vehicles` by ID from `f_vehicle` answer → get VIN, registration_number, fuel_tank_capacity_liters
2. **Get fuel liters** — convert gauge level strings to liters using `fuel_service.gauge_to_liters(level, tank_capacity)`
3. **Generate contract_id** — `TD-{VIN[:8]}-{unix_timestamp}-{uuid_hex[:4]}`
4. **Insert into `foi_de_parcurs`:**
   - `contract_id`, `vin`, `company_id` (from `f_company`), `client_id` (from `f_client`)
   - `route_type = 'TD'`, `status = 'FILLED'`, `source = 'td_form'`
   - `km_start`, `km_end` (if provided), `distance_km = f_estimated_km`
   - `fuel_tank_capacity_liters`, `fuel_gauge_start_level`, `fuel_gauge_end_level`
   - `fuel_start_liters`, `fuel_end_liters`, `fuel_consumed_liters`
   - `itinerary`, `advisor_name`, `registration_number`
   - `departure_datetime`, `return_datetime`
   - `client_signature` (from `f_client_sig`), `gdpr_consent`, `inspection_acceptance`
5. **Generate PDFs** — call `pdf_service.generate_legal_pdf(contract)` and `generate_custom_pdf(contract)`
6. **Update contract** with `pdf_legal_path` and `pdf_custom_path`
7. **Return** `{contract_id, pdf_legal_url, pdf_custom_url}` — included in submission response as `hook_data`

### Response enhancement

`_run_post_submit_hooks` currently returns nothing. Change signature to return optional `dict`:
- If hook returns data, merge it into the submission response under `hook_data`
- HubFormModal / PublicForm success screen renders `hook_data.pdf_legal_url` and `hook_data.pdf_custom_url` as download links if present

## FormBuilder Palette

Add the 3 new types to `FIELD_TYPES` in FormBuilder.tsx:

```typescript
{ value: 'fp_vehicle', label: 'FP Vehicle', group: 'Special' },
{ value: 'fp_client', label: 'FP Client', group: 'Special' },
{ value: 'datetime', label: 'Date & Time', group: 'Input' },
```

This makes them available for admins editing the test-drive form or creating new forms.

## Backend Validation Updates

In `forms/services/form_service.py`:

```python
FIELD_TYPES = {
    'short_text', 'long_text', 'email', 'phone', 'number',
    'dropdown', 'radio', 'checkbox', 'date', 'file_upload',
    'heading', 'paragraph', 'hidden', 'signature',
    # Special types (used by seeded forms)
    'crm_client', 'service_catalog', 'company_select',
    'department_select', 'user_select',
    # New types
    'fp_vehicle', 'fp_client', 'datetime',
}
```

Note: `crm_client`, `service_catalog`, `company_select`, `department_select`, `user_select` are also missing from the backend set today. Adding all of them prevents validation failures if these field types appear in form schemas saved via FormBuilder.

## TypeScript Type Update

In `types/forms.ts`, add to `FieldType` union:

```typescript
| 'fp_vehicle'
| 'fp_client'
| 'datetime'
```

## Cleanup (Remove)

1. **Delete** `frontend/src/pages/FoiParcurs/TestDriveForm.tsx` (721 lines)
2. **Remove** route `/app/foi-parcurs/test-drive` from `App.tsx`
3. **Remove** the lazy import of `TestDriveForm` from `App.tsx`
4. **Remove** the "New Test Drive" button from `FoiParcurs/index.tsx` header (or replace with a link to Hub)
5. **Remove** `submitTestDrive` and `getTestDrive` from `api/foiParcurs.ts` (now handled by Forms API)
6. **Remove** `TestDriveFormPayload` type from `types/foiParcurs.ts`
7. **Keep** the backend endpoint `POST /api/foi-parcurs/test-drive` for backward compatibility (mobile app may use it) — mark as deprecated

## Hub Integration

The seeded form has `published_to_hub = True`. It appears on the Hub page alongside other published forms (e.g., Voucher Issuance, Bilet de Invoire).

HubFormModal already renders any published form via FormRenderer. The only enhancement needed:
1. Read `settings.prefill` map and construct `defaultValues` from user context before passing to FormRenderer
2. After successful submission, if response contains `hook_data` with PDF URLs, render download links in success screen

## Migration Considerations

- **All FP tables are empty in production** — no data migration needed
- The form seed script is idempotent (checks for existing slug before insert)
- The new field types are additive — no existing forms are affected
- The standalone route removal is a clean delete — no redirects needed since the module was never used in production

## Files Changed (Summary)

| File | Action |
|------|--------|
| `forms/services/form_service.py` | Add field types + post-submit hook |
| `frontend/src/components/forms/FormRenderer.tsx` | Add FpVehicleField, FpClientField, datetime case |
| `frontend/src/types/forms.ts` | Add 3 types to FieldType union |
| `frontend/src/pages/Forms/FormBuilder.tsx` | Add 3 types to FIELD_TYPES palette |
| `foi_parcurs/form_seed.py` | **New** — seed script |
| `migrations/init_schema.py` | Call `ensure_test_drive_form()` |
| `frontend/src/pages/FoiParcurs/TestDriveForm.tsx` | **Delete** |
| `frontend/src/pages/FoiParcurs/index.tsx` | Remove "New Test Drive" button |
| `frontend/src/App.tsx` | Remove test-drive route |
| `frontend/src/api/foiParcurs.ts` | Remove submitTestDrive, getTestDrive |
| `frontend/src/types/foiParcurs.ts` | Remove TestDriveFormPayload |
| `frontend/src/pages/Hub/HubFormModal.tsx` (or similar) | Add prefill + hook_data PDF rendering |
