# Test Drive → Forms Module Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the standalone TestDriveForm page with a seeded form in the JARVIS Forms module, rendered via FormRenderer, published to Hub, with a post-submit hook that creates the `foi_de_parcurs` contract and generates PDFs.

**Architecture:** Three new field types (`fp_vehicle`, `fp_client`, `datetime`) are added to FormRenderer alongside the existing special types. A seed script creates the form definition in the `forms` table. A post-submit hook in `form_service.py` bridges the form submission to the `foi_de_parcurs` contract creation and PDF generation. The standalone TestDriveForm.tsx and its route are deleted.

**Tech Stack:** Flask/Python backend, React 19 + TypeScript + Tailwind + shadcn/ui frontend, PostgreSQL, ReportLab (PDFs).

## Global Constraints

- All development on `dev` branch
- Backend: Flask, Python, parameterized SQL (`%s` placeholders)
- Frontend: React 19, TypeScript strict, Tailwind 4, shadcn/ui components
- Backend port: 5001 (macOS), Frontend Vite: 5173
- Run `npx tsc --noEmit` after frontend changes
- Run `npm run build` before staging push
- No cross-module DB writes — Forms module writes to `forms`/`form_submissions`, hook writes to `foi_de_parcurs` via the existing FoiParcursRepository

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `jarvis/forms/services/form_service.py` | Modify | Add field types to FIELD_TYPES + FIELD_TYPES set, add `_create_test_drive_contract` hook, modify `_run_post_submit_hooks` to return hook_data |
| `jarvis/foi_parcurs/form_seed.py` | Create | Seed script with TEST_DRIVE_FORM_SCHEMA + `ensure_test_drive_form()` |
| `jarvis/migrations/init_schema.py` | Modify | Call `ensure_test_drive_form()` alongside voucher seed |
| `frontend/src/types/forms.ts` | Modify | Add 3 types to FieldType union |
| `frontend/src/components/forms/FormRenderer.tsx` | Modify | Add `FpVehicleField`, `FpClientField`, `datetime` case to switch |
| `frontend/src/pages/Forms/FormBuilder.tsx` | Modify | Add 3 types to FIELD_TYPES palette |
| `frontend/src/pages/Hub/index.tsx` | Modify | Add prefill support + hook_data PDF rendering to HubFormModal |
| `frontend/src/App.tsx` | Modify | Remove test-drive route + lazy import |
| `frontend/src/pages/FoiParcurs/index.tsx` | Modify | Remove "New Test Drive" button |
| `frontend/src/pages/FoiParcurs/TestDriveForm.tsx` | Delete | Standalone form replaced by Forms module |
| `frontend/src/api/foiParcurs.ts` | Modify | Remove `submitTestDrive`, `getTestDrive` |
| `frontend/src/types/foiParcurs.ts` | Modify | Remove `TestDriveFormPayload` |

---

### Task 1: Backend — Add Field Types + Hook Infrastructure

**Files:**
- Modify: `jarvis/forms/services/form_service.py:31-36` (FIELD_TYPES set)
- Modify: `jarvis/forms/services/form_service.py:222-223` (submit_public hook call)
- Modify: `jarvis/forms/services/form_service.py:240-244` (response data)
- Modify: `jarvis/forms/services/form_service.py:287-288` (submit_internal hook call)
- Modify: `jarvis/forms/services/form_service.py:300-307` (`_run_post_submit_hooks`)

**Interfaces:**
- Produces: `_run_post_submit_hooks()` returns `Optional[dict]`; `hook_data` key in submission response; `_create_test_drive_contract(form, submission_id, answers, user_id)` method

- [ ] **Step 1: Expand FIELD_TYPES set**

In `jarvis/forms/services/form_service.py`, replace lines 31-36:

```python
# Supported field types for validation
FIELD_TYPES = {
    'short_text', 'long_text', 'email', 'phone', 'number',
    'dropdown', 'radio', 'checkbox', 'date', 'file_upload',
    'heading', 'paragraph', 'hidden', 'signature',
}
```

With:

```python
# Supported field types for validation
FIELD_TYPES = {
    'short_text', 'long_text', 'email', 'phone', 'number',
    'dropdown', 'radio', 'checkbox', 'date', 'datetime', 'file_upload',
    'heading', 'paragraph', 'hidden', 'signature',
    'crm_client', 'service_catalog', 'company_select',
    'department_select', 'user_select',
    'fp_vehicle', 'fp_client',
}
```

- [ ] **Step 2: Make `_run_post_submit_hooks` return hook_data**

Replace the method at line 300:

```python
def _run_post_submit_hooks(self, form: dict, submission_id: int, answers: Dict, user_id: Optional[int]) -> Optional[Dict]:
    """Run form-specific hooks after submission. Returns optional hook_data for response."""
    slug = form.get('slug', '')
    try:
        if slug == 'voucher-issuance' and user_id:
            self._create_voucher_from_submission(form, submission_id, answers, user_id)
        elif slug == 'test-drive':
            return self._create_test_drive_contract(form, submission_id, answers, user_id)
    except Exception as e:
        logger.error('Post-submit hook failed for %s submission %s: %s', slug, submission_id, e)
    return None
```

- [ ] **Step 3: Wire hook_data into submit_public response**

In `submit_public` method, change the hook call at line 223 from:

```python
        self._run_post_submit_hooks(form, submission_id, answers, user_id)
```

To:

```python
        hook_data = self._run_post_submit_hooks(form, submission_id, answers, user_id)
```

Then update the return at line 240 from:

```python
        return ServiceResult(success=True, data={
            'submission_id': submission_id,
            'thank_you_message': thank_you,
            'redirect_url': redirect_url,
        }, status_code=201)
```

To:

```python
        response_data = {
            'submission_id': submission_id,
            'thank_you_message': thank_you,
            'redirect_url': redirect_url,
        }
        if hook_data:
            response_data['hook_data'] = hook_data
        return ServiceResult(success=True, data=response_data, status_code=201)
```

- [ ] **Step 4: Wire hook_data into submit_internal response**

In `submit_internal` method, change the hook call at line 288 from:

```python
        self._run_post_submit_hooks(form, submission_id, answers, user.user_id)
```

To:

```python
        hook_data = self._run_post_submit_hooks(form, submission_id, answers, user.user_id)
```

And update the return at line 296 from:

```python
        return ServiceResult(success=True, data={'submission_id': submission_id}, status_code=201)
```

To:

```python
        response_data = {'submission_id': submission_id}
        if hook_data:
            response_data['hook_data'] = hook_data
        return ServiceResult(success=True, data=response_data, status_code=201)
```

- [ ] **Step 5: Add `_create_test_drive_contract` method**

Add after `_create_voucher_from_submission` method (after line ~380):

```python
def _create_test_drive_contract(self, form: dict, submission_id: int, answers: Dict, user_id: Optional[int]) -> Optional[Dict]:
    """Create a foi_de_parcurs contract from a test-drive form submission."""
    import time
    import uuid
    from foi_parcurs.repositories import FoiParcursRepository, FPVehicleRepository
    from foi_parcurs.services.fuel_service import parse_fuel_level
    from foi_parcurs.services.pdf_service import generate_legal_pdf, generate_custom_pdf

    vehicle_id = answers.get('f_vehicle')
    if not vehicle_id:
        logger.warning('Test drive submission %s missing vehicle', submission_id)
        return None

    vehicle_repo = FPVehicleRepository()
    vehicle = vehicle_repo.get_by_id(int(vehicle_id))
    if not vehicle:
        logger.warning('Test drive submission %s — vehicle %s not found', submission_id, vehicle_id)
        return None

    vin = vehicle['vin']
    tank = vehicle.get('fuel_tank_capacity_liters', 50)
    fuel_start_level = answers.get('f_fuel_start', '1')
    fuel_end_level = answers.get('f_fuel_end', fuel_start_level)

    try:
        start_fraction = parse_fuel_level(str(fuel_start_level))
        end_fraction = parse_fuel_level(str(fuel_end_level))
    except ValueError:
        start_fraction, end_fraction = 1.0, 1.0

    fuel_start_liters = start_fraction * tank
    fuel_end_liters = end_fraction * tank
    fuel_consumed = max(0, fuel_start_liters - fuel_end_liters)

    contract_id = f"TD-{vin[:8]}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    # Parse company_id — company_select stores company name, look up ID
    company_id_raw = answers.get('f_company')
    company_id = None
    if company_id_raw:
        from core.base_repository import BaseRepository
        base = BaseRepository()
        row = base.query_one('SELECT id FROM companies WHERE company = %s', (str(company_id_raw),))
        if row:
            company_id = row['id']

    contract_data = {
        'contract_id': contract_id,
        'vin': vin,
        'registration_number': vehicle.get('registration_number', ''),
        'company_id': company_id or form.get('company_id'),
        'client_id': int(answers.get('f_client', 0)) or None,
        'route_type': 'TD',
        'slot_number': 0,
        'km_start': int(answers.get('f_odometer_start', 0) or 0),
        'km_end': int(answers.get('f_odometer_end', 0) or 0) or int(answers.get('f_odometer_start', 0) or 0),
        'distance_km': int(answers.get('f_estimated_km', 0) or 0),
        'fuel_tank_capacity_liters': tank,
        'fuel_gauge_start_level': str(fuel_start_level),
        'fuel_gauge_end_level': str(fuel_end_level),
        'fuel_start_liters': fuel_start_liters,
        'fuel_end_liters': fuel_end_liters,
        'fuel_consumed_liters': fuel_consumed,
        'itinerary': answers.get('f_itinerary', ''),
        'advisor_name': answers.get('f_advisor', ''),
        'signature_ai_generated': answers.get('f_advisor_sig', ''),
        'client_signature': answers.get('f_client_sig', ''),
        'departure_datetime': answers.get('f_departure'),
        'return_datetime': answers.get('f_return'),
        'gdpr_consent': bool(answers.get('f_gdpr')),
        'inspection_acceptance': bool(answers.get('f_inspection')),
        'source': 'td_form',
        'status': 'FILLED',
    }

    fp_repo = FoiParcursRepository()
    contract = fp_repo.create_from_td_form(contract_data)

    # Generate PDFs
    pdf_legal_url = None
    pdf_custom_url = None
    try:
        legal_path = generate_legal_pdf(contract)
        custom_path = generate_custom_pdf(contract)
        fp_repo.execute(
            'UPDATE foi_de_parcurs SET pdf_legal_path = %s, pdf_custom_path = %s WHERE id = %s',
            (legal_path, custom_path, contract['id']),
        )
        pdf_legal_url = f'/api/foi-parcurs/contracts/{contract["id"]}/pdf/legal'
        pdf_custom_url = f'/api/foi-parcurs/contracts/{contract["id"]}/pdf/custom'
    except Exception:
        logger.exception('PDF generation failed for TD contract %s', contract_id)

    logger.info('Test drive contract %s created from form submission %s', contract_id, submission_id)

    return {
        'contract_id': contract_id,
        'foi_de_parcurs_id': contract.get('id'),
        'pdf_legal_url': pdf_legal_url,
        'pdf_custom_url': pdf_custom_url,
    }
```

- [ ] **Step 6: Verify Python compiles**

Run: `python3 -m py_compile jarvis/forms/services/form_service.py`
Expected: no output (success)

- [ ] **Step 7: Commit**

```bash
git add jarvis/forms/services/form_service.py
git commit -m "feat(forms): add test-drive post-submit hook and new field types to validation set"
```

---

### Task 2: Seed Script + Migration Hook

**Files:**
- Create: `jarvis/foi_parcurs/form_seed.py`
- Modify: `jarvis/migrations/init_schema.py:71-76`

**Interfaces:**
- Produces: `ensure_test_drive_form()` — idempotent function that inserts the test-drive form into `forms` table

- [ ] **Step 1: Create the seed script**

Create `jarvis/foi_parcurs/form_seed.py`:

```python
"""Seed the Test Drive form definition in the JARVIS Forms engine."""
import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.form_seed')

TEST_DRIVE_FORM_SLUG = 'test-drive'

TEST_DRIVE_FORM_SCHEMA = [
    {
        'id': 'f_td_heading',
        'type': 'heading',
        'label': 'Formular Test Drive',
        'order': 1,
    },
    {
        'id': 'f_company',
        'type': 'company_select',
        'label': 'Companie',
        'required': True,
        'order': 2,
    },
    {
        'id': 'f_vehicle',
        'type': 'fp_vehicle',
        'label': 'Vehicul',
        'required': True,
        'order': 3,
        'config': {'companyField': 'f_company'},
    },
    {
        'id': 'f_client',
        'type': 'fp_client',
        'label': 'Client',
        'required': True,
        'order': 4,
    },
    {
        'id': 'f_departure',
        'type': 'datetime',
        'label': 'Data si ora plecarii',
        'required': True,
        'order': 5,
    },
    {
        'id': 'f_return',
        'type': 'datetime',
        'label': 'Data si ora intoarcerii',
        'required': False,
        'order': 6,
    },
    {
        'id': 'f_odometer_start',
        'type': 'number',
        'label': 'KM plecare',
        'required': True,
        'placeholder': 'Kilometraj la plecare',
        'order': 7,
    },
    {
        'id': 'f_odometer_end',
        'type': 'number',
        'label': 'KM sosire',
        'required': False,
        'placeholder': 'Kilometraj la sosire',
        'order': 8,
    },
    {
        'id': 'f_estimated_km',
        'type': 'number',
        'label': 'KM estimat',
        'required': True,
        'placeholder': 'Distanta estimata',
        'order': 9,
    },
    {
        'id': 'f_itinerary',
        'type': 'long_text',
        'label': 'Traseu / Itinerariu',
        'required': True,
        'placeholder': 'Descrieti traseul...',
        'order': 10,
    },
    {
        'id': 'f_fuel_start',
        'type': 'dropdown',
        'label': 'Nivel combustibil plecare',
        'required': True,
        'options': ['1', '3/4', '2/3', '1/2', '1/4'],
        'order': 11,
    },
    {
        'id': 'f_fuel_end',
        'type': 'dropdown',
        'label': 'Nivel combustibil sosire',
        'required': False,
        'options': ['1', '3/4', '2/3', '1/2', '1/4'],
        'order': 12,
    },
    {
        'id': 'f_gdpr',
        'type': 'checkbox',
        'label': 'Consimtamant GDPR',
        'required': True,
        'options': ['Accept procesarea datelor personale conform GDPR'],
        'order': 13,
    },
    {
        'id': 'f_inspection',
        'type': 'checkbox',
        'label': 'Acceptare inspectie vehicul',
        'required': True,
        'options': ['Accept starea vehiculului conform ultimei inspectii'],
        'order': 14,
    },
    {
        'id': 'f_advisor',
        'type': 'short_text',
        'label': 'Nume consilier',
        'required': True,
        'placeholder': 'Numele consilierului',
        'order': 15,
    },
    {
        'id': 'f_client_sig',
        'type': 'signature',
        'label': 'Semnatura client',
        'required': True,
        'order': 16,
    },
    {
        'id': 'f_advisor_sig',
        'type': 'signature',
        'label': 'Semnatura consilier',
        'required': True,
        'order': 17,
    },
]


def ensure_test_drive_form():
    """Ensure the Test Drive form exists. Idempotent."""
    base = BaseRepository()

    existing = base.query_one(
        "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL",
        (TEST_DRIVE_FORM_SLUG,)
    )
    if existing:
        logger.debug('Test Drive form already exists (id=%s)', existing['id'])
        return existing['id']

    company = base.query_one('SELECT id FROM companies ORDER BY id LIMIT 1')
    admin = base.query_one("SELECT id FROM users WHERE role_id = 1 ORDER BY id LIMIT 1")
    if not company or not admin:
        logger.warning('Cannot seed test drive form — no company or admin user found')
        return None

    form_id = base.execute('''
        INSERT INTO forms
            (name, slug, description, company_id, owner_id, created_by,
             schema, published_schema, settings, utm_config, branding,
             requires_approval, published_to_hub, status, version, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'published', 1, CURRENT_TIMESTAMP)
        RETURNING id
    ''', (
        'Test Drive',
        TEST_DRIVE_FORM_SLUG,
        'Formular intern pentru inregistrarea test drive-urilor.',
        company['id'],
        admin['id'],
        admin['id'],
        json.dumps(TEST_DRIVE_FORM_SCHEMA),
        json.dumps(TEST_DRIVE_FORM_SCHEMA),
        json.dumps({
            'thank_you_message': 'Test Drive inregistrat cu succes!',
            'prefill': {'f_advisor': 'user.name'},
        }),
        json.dumps({}),
        json.dumps({}),
        False,
        True,
    ), returning=True)

    logger.info('Seeded Test Drive form (id=%s)', form_id['id'])
    return form_id['id']
```

- [ ] **Step 2: Add seed call to init_schema.py**

In `jarvis/migrations/init_schema.py`, after the voucher seed block (after line ~76), add:

```python
    # Seed test drive form (idempotent, needs forms table to exist)
    try:
        from foi_parcurs.form_seed import ensure_test_drive_form
        ensure_test_drive_form()
    except Exception:
        pass  # May fail during initial import chain; app.py will retry
```

- [ ] **Step 3: Verify Python compiles**

Run: `python3 -m py_compile jarvis/foi_parcurs/form_seed.py`
Expected: no output (success)

- [ ] **Step 4: Test seed script locally**

Run:
```bash
cd jarvis/jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python3 -c "from foi_parcurs.form_seed import ensure_test_drive_form; print(ensure_test_drive_form())"
```

Expected: prints the form ID (integer) or None if tables don't exist yet.

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/form_seed.py jarvis/migrations/init_schema.py
git commit -m "feat(foi-parcurs): add test-drive form seed script and migration hook"
```

---

### Task 3: Frontend — TypeScript Types + `datetime` Field + FormBuilder Palette

**Files:**
- Modify: `jarvis/frontend/src/types/forms.ts:5-24` (FieldType union)
- Modify: `jarvis/frontend/src/components/forms/FormRenderer.tsx:498-509` (add datetime case)
- Modify: `jarvis/frontend/src/pages/Forms/FormBuilder.tsx:27-43` (FIELD_TYPES palette)

**Interfaces:**
- Produces: `FieldType` union includes `'fp_vehicle' | 'fp_client' | 'datetime'`; FormRenderer renders `datetime` input; FormBuilder palette includes 3 new types

- [ ] **Step 1: Add types to FieldType union**

In `jarvis/frontend/src/types/forms.ts`, replace the FieldType definition (lines 5-24):

```typescript
export type FieldType =
  | 'short_text'
  | 'long_text'
  | 'email'
  | 'phone'
  | 'number'
  | 'dropdown'
  | 'radio'
  | 'checkbox'
  | 'date'
  | 'datetime'
  | 'file_upload'
  | 'heading'
  | 'paragraph'
  | 'hidden'
  | 'signature'
  | 'crm_client'
  | 'service_catalog'
  | 'company_select'
  | 'department_select'
  | 'user_select'
  | 'fp_vehicle'
  | 'fp_client'
```

- [ ] **Step 2: Add datetime case to FormRenderer**

In `jarvis/frontend/src/components/forms/FormRenderer.tsx`, after the `case 'date':` block (after line 509), add:

```typescript
    case 'datetime':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="datetime-local"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )
```

- [ ] **Step 3: Add 3 types to FormBuilder palette**

In `jarvis/frontend/src/pages/Forms/FormBuilder.tsx`, replace lines 27-43 (the FIELD_TYPES array):

```typescript
const FIELD_TYPES: { value: FieldType; label: string; group: string }[] = [
  { value: 'short_text', label: 'Short Text', group: 'Input' },
  { value: 'long_text', label: 'Long Text', group: 'Input' },
  { value: 'email', label: 'Email', group: 'Input' },
  { value: 'phone', label: 'Phone', group: 'Input' },
  { value: 'number', label: 'Number', group: 'Input' },
  { value: 'date', label: 'Date', group: 'Input' },
  { value: 'datetime', label: 'Date & Time', group: 'Input' },
  { value: 'dropdown', label: 'Dropdown', group: 'Selection' },
  { value: 'radio', label: 'Radio', group: 'Selection' },
  { value: 'checkbox', label: 'Checkbox', group: 'Selection' },
  { value: 'file_upload', label: 'File Upload', group: 'Special' },
  { value: 'signature', label: 'Signature', group: 'Special' },
  { value: 'heading', label: 'Heading', group: 'Display' },
  { value: 'paragraph', label: 'Paragraph', group: 'Display' },
  { value: 'hidden', label: 'Hidden Field', group: 'Special' },
  { value: 'crm_client', label: 'CRM Client', group: 'Special' },
  { value: 'fp_vehicle', label: 'FP Vehicle', group: 'Special' },
  { value: 'fp_client', label: 'FP Client', group: 'Special' },
]
```

- [ ] **Step 4: TypeScript check**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/types/forms.ts jarvis/frontend/src/components/forms/FormRenderer.tsx jarvis/frontend/src/pages/Forms/FormBuilder.tsx
git commit -m "feat(forms): add datetime field type + fp_vehicle/fp_client to types and FormBuilder palette"
```

---

### Task 4: Frontend — FpVehicleField Component

**Files:**
- Modify: `jarvis/frontend/src/components/forms/FormRenderer.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.getVehicles()`, `foiParcursApi.getLatestInspection()` from `@/api/foiParcurs`
- Produces: `FpVehicleField` component rendered for `case 'fp_vehicle'`; answer value is vehicle ID as string

- [ ] **Step 1: Add the foiParcursApi import**

At the top of `FormRenderer.tsx` (after the existing api imports at line 17), add:

```typescript
import { foiParcursApi } from '@/api/foiParcurs'
```

- [ ] **Step 2: Add FpVehicleField component**

Add before the `FieldComponent` function (before line 440):

```typescript
function FpVehicleField({ field, value, error, onChange, allAnswers }: FieldProps) {
  const companyFieldId = (field.config as Record<string, unknown> | undefined)?.companyField as string || 'f_company'
  const companyName = (allAnswers?.[companyFieldId] as string) || ''

  const { data: vehicleData } = useQuery({
    queryKey: ['fp-vehicles-active'],
    queryFn: () => foiParcursApi.getVehicles(true),
    staleTime: 60_000,
  })

  const allVehicles = vehicleData?.vehicles ?? []
  const filtered = companyName
    ? allVehicles.filter((v: { company_name?: string }) => v.company_name === companyName)
    : allVehicles

  const selectedId = value ? String(value) : ''
  const selectedVehicle = allVehicles.find((v: { id: number }) => String(v.id) === selectedId) as Record<string, unknown> | undefined

  const { data: inspectionData } = useQuery({
    queryKey: ['fp-inspection', selectedId],
    queryFn: () => foiParcursApi.getLatestInspection(Number(selectedId)),
    enabled: !!selectedId,
  })
  const latestInspection = inspectionData?.inspection ?? null

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
        <Select value={selectedId} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder={companyName ? 'Selectati vehiculul...' : 'Selectati compania intai'} />
          </SelectTrigger>
          <SelectContent>
            {filtered.map((v: { id: number; mark: string; model: string; vin: string; registration_number?: string }) => (
              <SelectItem key={v.id} value={String(v.id)}>
                {v.mark} {v.model} — {v.registration_number || v.vin}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
      {selectedVehicle && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3 text-sm space-y-1">
          <p><span className="text-muted-foreground">VIN:</span> {String(selectedVehicle.vin)}</p>
          <p><span className="text-muted-foreground">Nr. inmatriculare:</span> {String(selectedVehicle.registration_number || '—')}</p>
          <p><span className="text-muted-foreground">Combustibil:</span> {String(selectedVehicle.fuel_type)} — {String(selectedVehicle.fuel_tank_capacity_liters)}L</p>
        </div>
      )}
      {latestInspection && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3 text-sm">
          <p className="font-medium text-xs text-amber-700 dark:text-amber-400">Ultima inspectie: {String((latestInspection as Record<string, unknown>).inspection_date)}</p>
          {(latestInspection as Record<string, unknown>).condition_notes && (
            <p className="text-muted-foreground mt-1">{String((latestInspection as Record<string, unknown>).condition_notes)}</p>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Add case to FieldComponent switch**

In the `FieldComponent` switch (around line 451, after the `crm_client` case), add:

```typescript
    case 'fp_vehicle':
      return <FpVehicleField field={field} value={value} error={error} onChange={onChange} allAnswers={allAnswers} />
```

- [ ] **Step 4: TypeScript check**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/components/forms/FormRenderer.tsx
git commit -m "feat(forms): add FpVehicleField component to FormRenderer"
```

---

### Task 5: Frontend — FpClientField Component

**Files:**
- Modify: `jarvis/frontend/src/components/forms/FormRenderer.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.searchClients()` from `@/api/foiParcurs`
- Produces: `FpClientField` component rendered for `case 'fp_client'`; answer value is client ID as string

- [ ] **Step 1: Add FpClientField component**

Add after `FpVehicleField` in `FormRenderer.tsx`:

```typescript
function FpClientField({ field, value, error, onChange }: FieldProps) {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)
  const [selectedName, setSelectedName] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleSearchChange = (val: string) => {
    setSearch(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(val)
      if (val.length >= 2) setShowDropdown(true)
    }, 300)
  }

  const { data: clientData, isFetching } = useQuery({
    queryKey: ['fp-clients-search', debouncedSearch],
    queryFn: () => foiParcursApi.searchClients(debouncedSearch, 10),
    enabled: debouncedSearch.length >= 2 && !value,
    staleTime: 10_000,
  })
  const clients = clientData?.clients ?? []

  const clearSelection = () => {
    onChange('')
    setSelectedName('')
    setSearch('')
    setDebouncedSearch('')
  }

  return (
    <div className="space-y-1">
      <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
      {value && selectedName ? (
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-md border px-3 py-1.5 text-sm font-medium">
            {selectedName}
          </span>
          <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={clearSelection}>
            Schimba
          </button>
        </div>
      ) : (
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Cauta dupa nume sau telefon..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            onFocus={() => { if (debouncedSearch.length >= 2) setShowDropdown(true) }}
          />
          {isFetching && (
            <div className="absolute right-2.5 top-2.5 h-4 w-4 border-2 border-muted-foreground border-t-transparent rounded-full animate-spin" />
          )}
          {showDropdown && debouncedSearch.length >= 2 && (
            <div className="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md max-h-48 overflow-y-auto">
              {clients.length === 0 && !isFetching ? (
                <div className="p-3 text-sm text-muted-foreground text-center">Niciun client gasit</div>
              ) : (
                clients.map((c: { id: number; name: string; phone: string }) => (
                  <button
                    key={c.id}
                    type="button"
                    className="w-full text-left px-3 py-2 hover:bg-accent text-sm"
                    onClick={() => {
                      onChange(String(c.id))
                      setSelectedName(c.name)
                      setShowDropdown(false)
                      setSearch('')
                    }}
                  >
                    <span className="font-medium">{c.name}</span>
                    {c.phone && <span className="text-muted-foreground ml-2">{c.phone}</span>}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Add case to FieldComponent switch**

After the `fp_vehicle` case, add:

```typescript
    case 'fp_client':
      return <FpClientField field={field} value={value} error={error} onChange={onChange} />
```

- [ ] **Step 3: TypeScript check**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/components/forms/FormRenderer.tsx
git commit -m "feat(forms): add FpClientField component to FormRenderer"
```

---

### Task 6: Frontend — HubFormModal Prefill + Hook Data PDF Links

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/index.tsx:1506-1564`

**Interfaces:**
- Consumes: `form.settings.prefill` map, `submitMutation` response `hook_data`
- Produces: HubFormModal passes prefilled `defaultValues` and renders PDF download links on success

- [ ] **Step 1: Add auth store import**

At the top of `Hub/index.tsx`, check if `useAuthStore` is already imported. If not, add:

```typescript
import { useAuthStore } from '@/stores/authStore'
```

- [ ] **Step 2: Rewrite HubFormModal with prefill + success state**

Replace the `HubFormModal` function (lines 1506-1564) with:

```typescript
function HubFormModal({ slug, name, onClose, onSubmitted }: { slug: string; name: string; onClose: () => void; onSubmitted: () => void }) {
  const user = useAuthStore((s) => s.user)
  const [successData, setSuccessData] = useState<{ thank_you_message?: string; hook_data?: Record<string, string> } | null>(null)

  const { data: form, isLoading } = useQuery({
    queryKey: ['public-form', slug],
    queryFn: () => import('@/api/forms').then(m => m.formsApi.getPublicForm(slug)),
  })

  const { schema, defaultValues: voucherDefaults, submitLabel, needsSignatureSave } =
    useVoucherSchema(form?.schema ?? [], slug)

  // Build prefill defaults from form settings
  const prefillDefaults = useMemo(() => {
    const prefill = form?.settings?.prefill as Record<string, string> | undefined
    if (!prefill || !user) return {}
    const defaults: Record<string, unknown> = {}
    for (const [fieldId, source] of Object.entries(prefill)) {
      if (source === 'user.name') defaults[fieldId] = user.name || ''
      else if (source === 'user.email') defaults[fieldId] = user.email || ''
    }
    return defaults
  }, [form?.settings, user])

  const mergedDefaults = useMemo(
    () => ({ ...prefillDefaults, ...voucherDefaults }),
    [prefillDefaults, voucherDefaults],
  )

  const submitMutation = useMutation({
    mutationFn: async (answers: Record<string, unknown>) => {
      if (needsSignatureSave && answers.f_signature && typeof answers.f_signature === 'string') {
        await api.put('/profile/api/signature', { signature: answers.f_signature })
      }
      const { f_signature: _, ...formAnswers } = answers
      return import('@/api/forms').then(m => m.formsApi.submitPublicForm(slug, { answers: formAnswers }))
    },
    onSuccess: (data) => {
      setSuccessData({
        thank_you_message: data?.thank_you_message,
        hook_data: data?.hook_data,
      })
      onSubmitted()
    },
    onError: () => toast.error('Failed to submit form'),
  })

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col animate-in slide-in-from-right duration-200">
      {/* Top nav bar */}
      <div className="shrink-0 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center h-12 px-4">
          <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-xs" onClick={onClose}>
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          <h2 className="flex-1 text-center text-sm font-semibold truncate px-2">{name}</h2>
          <div className="w-16" />
        </div>
      </div>
      {/* Form body */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-lg px-5 py-6">
          {successData ? (
            <div className="text-center space-y-4 py-8">
              <div className="mx-auto w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <Check className="h-6 w-6 text-green-600" />
              </div>
              <p className="text-sm text-muted-foreground">{successData.thank_you_message || 'Submitted successfully!'}</p>
              {successData.hook_data?.pdf_legal_url && (
                <div className="flex flex-col gap-2 pt-2">
                  <a href={successData.hook_data.pdf_legal_url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent">
                    Download Legal PDF
                  </a>
                  {successData.hook_data.pdf_custom_url && (
                    <a href={successData.hook_data.pdf_custom_url} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent">
                      Download Custom PDF
                    </a>
                  )}
                </div>
              )}
              <Button variant="outline" size="sm" onClick={onClose}>Inchide</Button>
            </div>
          ) : isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : schema.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">This form has no fields.</p>
          ) : (
            <Suspense fallback={<Skeleton className="h-48 w-full" />}>
              <FormRendererLazy
                schema={schema}
                onSubmit={(answers) => submitMutation.mutate(answers)}
                submitting={submitMutation.isPending}
                submitLabel={submitLabel}
                defaultValues={mergedDefaults}
              />
            </Suspense>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Ensure required imports at top of Hub/index.tsx**

Verify these are imported (add any that are missing):

```typescript
import { useMemo } from 'react'  // likely already there
```

The `Check` icon from lucide-react should already be imported in Hub. If not, add it to the existing lucide import.

- [ ] **Step 4: TypeScript check**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/index.tsx
git commit -m "feat(hub): add prefill support and PDF download links to HubFormModal"
```

---

### Task 7: Frontend Cleanup — Remove Standalone TestDriveForm

**Files:**
- Delete: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx`
- Modify: `jarvis/frontend/src/App.tsx:59,241`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx:98-101`
- Modify: `jarvis/frontend/src/api/foiParcurs.ts:120-124` (remove submitTestDrive, getTestDrive)
- Modify: `jarvis/frontend/src/types/foiParcurs.ts:221+` (remove TestDriveFormPayload)

**Interfaces:**
- Consumes: nothing new
- Produces: clean removal of all standalone TestDriveForm references

- [ ] **Step 1: Delete TestDriveForm.tsx**

```bash
rm jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx
```

- [ ] **Step 2: Remove route and lazy import from App.tsx**

In `jarvis/frontend/src/App.tsx`, remove line 59:

```typescript
const TestDriveForm = lazy(() => import('./pages/FoiParcurs/TestDriveForm'))
```

Remove line 241:

```typescript
        <Route path="foi-parcurs/test-drive" element={<Guard flag="can_access_carpark"><SuspensePage><TestDriveForm /></SuspensePage></Guard>} />
```

- [ ] **Step 3: Remove "New Test Drive" button from FoiParcurs/index.tsx**

In `jarvis/frontend/src/pages/FoiParcurs/index.tsx`, remove lines 98-101:

```typescript
          <Button variant="outline" onClick={() => navigate('/app/foi-parcurs/test-drive')}>
            <FileText className="mr-1.5 h-4 w-4" />
            New Test Drive
          </Button>
```

Also remove the `navigate` import if it's only used for this button (check other usages first).

- [ ] **Step 4: Remove submitTestDrive and getTestDrive from API client**

In `jarvis/frontend/src/api/foiParcurs.ts`, remove:

```typescript
  submitTestDrive: (data: TestDriveFormPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  getTestDrive: (id: number) =>
    api.get<{ success: boolean; contract: FoiContract; inspection: FpVehicleInspection | null }>(`${BASE}/test-drive/${id}`),
```

Also remove `TestDriveFormPayload` from the import at the top.

- [ ] **Step 5: Remove TestDriveFormPayload from types**

In `jarvis/frontend/src/types/foiParcurs.ts`, remove the `TestDriveFormPayload` interface (starts at line 221).

- [ ] **Step 6: TypeScript check**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 7: Build check**

Run: `cd jarvis/frontend && npm run build`
Expected: clean build, zero errors

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(foi-parcurs): remove standalone TestDriveForm, now handled by Forms module"
```
