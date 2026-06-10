# Test Drive Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Test Drive form that creates foi_de_parcurs contracts and generates legal + branded PDFs.

**Architecture:** Custom React page using existing JARVIS components (SignatureCanvas, DateField, SearchInput, CRM client search). Backend Flask routes in the foi_parcurs module. PDF generation via ReportLab. DB schema extended with new columns and inspection table.

**Tech Stack:** React 19 + TypeScript + Tailwind + shadcn/ui, Flask/Python, PostgreSQL, ReportLab (PDF), existing SignatureCanvas component.

---

## File Structure

**Backend (new/modified):**
- Modify: `jarvis/migrations/domains/schema_incremental.py` — add columns + inspections table
- Create: `jarvis/foi_parcurs/routes/test_drive.py` — TD form submit + retrieval endpoints
- Create: `jarvis/foi_parcurs/routes/inspections.py` — vehicle inspection CRUD
- Create: `jarvis/foi_parcurs/services/pdf_service.py` — legal + custom PDF generation
- Modify: `jarvis/foi_parcurs/routes/__init__.py` — register new route modules
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` — new query methods
- Create: `jarvis/foi_parcurs/repositories/inspection_repository.py` — inspection CRUD
- Modify: `jarvis/foi_parcurs/repositories/vehicle_repository.py` — registration_number support

**Frontend (new/modified):**
- Create: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx` — TD form page
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — add TD Form tab/button, inspection UI in Stock
- Modify: `jarvis/frontend/src/api/foiParcurs.ts` — new API methods
- Modify: `jarvis/frontend/src/types/foiParcurs.ts` — new types

---

### Task 1: Database Schema — Add Columns + Inspections Table

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py`

- [ ] **Step 1: Add new columns to foi_de_parcurs and fp_vehicles**

At the end of `_create_schema_incremental_continued()`, after the existing FP migration blocks, add:

```python
    # ── Foi de Parcurs Phase 2 — TD form fields ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='registration_number') THEN
                ALTER TABLE fp_vehicles ADD COLUMN registration_number VARCHAR(20);
            END IF;
        END $$;
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='registration_number') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN registration_number VARCHAR(20);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='departure_datetime') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN departure_datetime TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='return_datetime') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN return_datetime TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='client_signature') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN client_signature TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='gdpr_consent') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN gdpr_consent BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='inspection_acceptance') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN inspection_acceptance BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='inspection_id') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN inspection_id BIGINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='pdf_legal_path') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN pdf_legal_path TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='pdf_custom_path') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN pdf_custom_path TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='source') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN source VARCHAR(20) DEFAULT 'batch';
            END IF;
        END $$;
    ''')
```

- [ ] **Step 2: Create fp_vehicle_inspections table**

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_vehicle_inspections (
            id BIGSERIAL PRIMARY KEY,
            vehicle_id BIGINT NOT NULL,
            vin VARCHAR(50) NOT NULL,
            inspection_date DATE NOT NULL,
            condition_notes TEXT,
            photos JSONB DEFAULT '[]',
            inspector_name VARCHAR(255),
            inspector_signature TEXT,
            created_by INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_inspections_vehicle ON fp_vehicle_inspections(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_inspections_date ON fp_vehicle_inspections(inspection_date DESC)')
```

- [ ] **Step 3: Restart backend to apply migration**

```bash
kill $(lsof -ti:5001) 2>/dev/null; sleep 1
cd jarvis && DATABASE_URL="postgresql://localhost/defaultdb" python -c "from app import create_app; app = create_app(); app.run(port=5001, debug=False)" &
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/migrations/domains/schema_incremental.py
git commit -m "feat(foi-parcurs): add TD form columns + vehicle inspections table"
```

---

### Task 2: Backend — Inspection Repository + Routes

**Files:**
- Create: `jarvis/foi_parcurs/repositories/inspection_repository.py`
- Create: `jarvis/foi_parcurs/routes/inspections.py`
- Modify: `jarvis/foi_parcurs/routes/__init__.py`
- Modify: `jarvis/foi_parcurs/routes/_shared.py`

- [ ] **Step 1: Create inspection_repository.py**

```python
"""Data access for fp_vehicle_inspections table."""
from core.base_repository import BaseRepository


class InspectionRepository(BaseRepository):

    def create(self, data: dict) -> dict:
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO fp_vehicle_inspections ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def get_by_vehicle(self, vehicle_id: int) -> list:
        return self.query_all(
            'SELECT * FROM fp_vehicle_inspections WHERE vehicle_id = %s ORDER BY inspection_date DESC',
            (vehicle_id,),
        ) or []

    def get_latest(self, vehicle_id: int) -> dict | None:
        return self.query_one(
            'SELECT * FROM fp_vehicle_inspections WHERE vehicle_id = %s ORDER BY inspection_date DESC LIMIT 1',
            (vehicle_id,),
        )

    def delete(self, inspection_id: int):
        self.execute('DELETE FROM fp_vehicle_inspections WHERE id = %s', (inspection_id,))
```

- [ ] **Step 2: Update _shared.py to export InspectionRepository**

Add to `_shared.py`:
```python
from ..repositories.inspection_repository import InspectionRepository
_inspection_repo = InspectionRepository()
```

And update `__all__` to include `InspectionRepository`, `_inspection_repo`.

- [ ] **Step 3: Create inspections.py routes**

```python
"""Routes for vehicle damage inspections."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger, _inspection_repo


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>/inspections', methods=['GET'])
@login_required
def api_get_inspections(vehicle_id):
    rows = _inspection_repo.get_by_vehicle(vehicle_id)
    return jsonify({'inspections': rows})


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>/inspections', methods=['POST'])
@login_required
def api_create_inspection(vehicle_id):
    data = request.get_json(silent=True) or {}
    from ..repositories.vehicle_repository import FPVehicleRepository
    vehicle = FPVehicleRepository().get_by_id(vehicle_id)
    if not vehicle:
        return jsonify({'success': False, 'error': 'Vehicle not found'}), 404

    row = _inspection_repo.create({
        'vehicle_id': vehicle_id,
        'vin': vehicle.get('vin', ''),
        'inspection_date': data.get('inspection_date'),
        'condition_notes': data.get('condition_notes', ''),
        'photos': data.get('photos', []),
        'inspector_name': data.get('inspector_name', ''),
        'inspector_signature': data.get('inspector_signature', ''),
        'created_by': current_user.id if current_user else None,
    })
    return jsonify({'success': True, 'inspection': row})


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>/inspections/latest', methods=['GET'])
@login_required
def api_latest_inspection(vehicle_id):
    row = _inspection_repo.get_latest(vehicle_id)
    return jsonify({'inspection': row})


@foi_parcurs_bp.route('/api/foi-parcurs/inspections/<int:id>', methods=['DELETE'])
@login_required
def api_delete_inspection(id):
    _inspection_repo.delete(id)
    return jsonify({'success': True})
```

- [ ] **Step 4: Register inspections routes in __init__.py**

Add: `from . import inspections  # noqa: F401`

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/repositories/inspection_repository.py \
        jarvis/foi_parcurs/routes/inspections.py \
        jarvis/foi_parcurs/routes/__init__.py \
        jarvis/foi_parcurs/routes/_shared.py
git commit -m "feat(foi-parcurs): vehicle inspection CRUD backend"
```

---

### Task 3: Backend — Test Drive Submit Route

**Files:**
- Create: `jarvis/foi_parcurs/routes/test_drive.py`
- Modify: `jarvis/foi_parcurs/routes/__init__.py`
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py`

- [ ] **Step 1: Add create_from_td_form method to foi_parcurs_repository.py**

Add method to `FoiParcursRepository`:

```python
    def create_from_td_form(self, data: dict) -> dict:
        """Create a FILLED contract from test drive form data."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs ({col_names}) VALUES ({placeholders}) RETURNING *'
        row = self.execute(sql, tuple(data[c] for c in cols), returning=True)
        # Re-fetch with JOINs for client/company names
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row
```

- [ ] **Step 2: Create test_drive.py routes**

```python
"""Routes for Test Drive form submission."""
import time
import uuid
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user,
    logger, _fp_repo, _inspection_repo,
)


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive', methods=['POST'])
@login_required
def api_submit_test_drive():
    """Submit test drive form — creates FILLED contract + triggers PDF generation."""
    data = request.get_json(silent=True) or {}

    required = ['company_id', 'vin', 'client_id', 'odometer_start', 'estimated_km',
                'fuel_gauge_start_level', 'departure_datetime', 'itinerary',
                'advisor_name', 'client_signature', 'gdpr_consent']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'success': False, 'error': f'Missing: {", ".join(missing)}'}), 400

    if not data.get('gdpr_consent'):
        return jsonify({'success': False, 'error': 'GDPR consent is required'}), 400

    contract_id = f"TD-{data['vin'][:8]}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    try:
        contract_data = {
            'contract_id': contract_id,
            'vin': data['vin'],
            'registration_number': data.get('registration_number', ''),
            'company_id': int(data['company_id']),
            'client_id': int(data['client_id']),
            'route_type': 'TD',
            'slot_number': 0,
            'km_start': int(data['odometer_start']),
            'km_end': int(data.get('odometer_end', 0)) or int(data['odometer_start']),
            'distance_km': int(data.get('estimated_km', 0)),
            'fuel_tank_capacity_liters': int(data.get('fuel_tank_capacity_liters', 0)),
            'fuel_gauge_start_level': data['fuel_gauge_start_level'],
            'fuel_gauge_end_level': data.get('fuel_gauge_end_level', data['fuel_gauge_start_level']),
            'fuel_start_liters': float(data.get('fuel_start_liters', 0)),
            'fuel_end_liters': float(data.get('fuel_end_liters', 0)),
            'fuel_consumed_liters': float(data.get('fuel_consumed_liters', 0)),
            'itinerary': data.get('itinerary', ''),
            'advisor_name': data['advisor_name'],
            'signature_ai_generated': data.get('advisor_signature', ''),
            'client_signature': data['client_signature'],
            'departure_datetime': data['departure_datetime'],
            'return_datetime': data.get('return_datetime'),
            'gdpr_consent': True,
            'inspection_acceptance': bool(data.get('inspection_acceptance')),
            'inspection_id': data.get('inspection_id'),
            'source': 'td_form',
            'status': 'FILLED',
        }

        contract = _fp_repo.create_from_td_form(contract_data)

        # PDF generation will be added in Task 5
        # For now, return the contract
        return jsonify({'success': True, 'contract': contract})

    except Exception as e:
        logger.exception('Failed to submit test drive form')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>', methods=['GET'])
@login_required
def api_get_test_drive(id):
    """Get test drive form data for a contract."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    # Get latest inspection for the vehicle
    from ..repositories.vehicle_repository import FPVehicleRepository
    vehicle_repo = FPVehicleRepository()
    vehicles = vehicle_repo.get_all(active_only=False)
    vehicle = next((v for v in (vehicles or []) if v.get('vin') == contract.get('vin')), None)
    inspection = None
    if vehicle:
        inspection = _inspection_repo.get_latest(vehicle['id'])

    return jsonify({
        'success': True,
        'contract': contract,
        'vehicle': vehicle,
        'inspection': inspection,
    })
```

- [ ] **Step 3: Register test_drive routes in __init__.py**

Add: `from . import test_drive  # noqa: F401`

- [ ] **Step 4: Commit**

```bash
git add jarvis/foi_parcurs/routes/test_drive.py \
        jarvis/foi_parcurs/routes/__init__.py \
        jarvis/foi_parcurs/repositories/foi_parcurs_repository.py
git commit -m "feat(foi-parcurs): test drive form submit endpoint"
```

---

### Task 4: Frontend — API + Types + Stock Tab Updates

**Files:**
- Modify: `jarvis/frontend/src/api/foiParcurs.ts`
- Modify: `jarvis/frontend/src/types/foiParcurs.ts`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` (Stock tab — registration_number + inspections)

- [ ] **Step 1: Add types for inspections and TD form**

In `types/foiParcurs.ts`, add:

```typescript
export interface FpVehicleInspection {
  id: number
  vehicle_id: number
  vin: string
  inspection_date: string
  condition_notes: string
  photos: string[]
  inspector_name: string
  inspector_signature: string
  created_by: number | null
  created_at: string
}

export interface TestDriveFormPayload {
  company_id: number
  vin: string
  registration_number: string
  client_id: number
  odometer_start: number
  odometer_end?: number
  estimated_km: number
  fuel_tank_capacity_liters: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level?: FuelGaugeLevel
  fuel_start_liters?: number
  fuel_end_liters?: number
  fuel_consumed_liters?: number
  itinerary: string
  departure_datetime: string
  return_datetime?: string
  advisor_name: string
  advisor_signature: string
  client_signature: string
  gdpr_consent: boolean
  inspection_acceptance: boolean
  inspection_id?: number
}
```

Update `FpVehicle` to include `registration_number?: string`.

- [ ] **Step 2: Add API methods**

In `api/foiParcurs.ts`, add:

```typescript
  // ── Test Drive Form ──
  submitTestDrive: (data: TestDriveFormPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  getTestDrive: (id: number) =>
    api.get<{ success: boolean; contract: FoiContract; vehicle: FpVehicle; inspection: FpVehicleInspection | null }>(`${BASE}/test-drive/${id}`),

  // ── Vehicle Inspections ──
  getInspections: (vehicleId: number) =>
    api.get<{ inspections: FpVehicleInspection[] }>(`${BASE}/vehicles/${vehicleId}/inspections`),

  createInspection: (vehicleId: number, data: Partial<FpVehicleInspection>) =>
    api.post<{ success: boolean; inspection: FpVehicleInspection }>(`${BASE}/vehicles/${vehicleId}/inspections`, data),

  getLatestInspection: (vehicleId: number) =>
    api.get<{ inspection: FpVehicleInspection | null }>(`${BASE}/vehicles/${vehicleId}/inspections/latest`),

  deleteInspection: (inspectionId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/inspections/${inspectionId}`),

  // ── PDF Downloads ──
  getContractPdfUrl: (contractId: number, type: 'legal' | 'custom') =>
    `${BASE}/contracts/${contractId}/pdf/${type}`,
```

- [ ] **Step 3: Add registration_number to Stock tab**

In the `StockTab` component in `index.tsx`:
- Add `registration_number` to `STOCK_COLUMNS` array
- Add the field to the "Add Vehicle" form
- Add the field to the inline edit row
- Display in the table

- [ ] **Step 4: Add Inspections section to Stock tab**

Below the vehicles table, add an expandable "Inspections" panel per vehicle:
- When a vehicle row is expanded, show its inspections list
- "Add Inspection" button opens a form: date (DateField), condition notes (Textarea), inspector name, inspector signature (SignatureCanvas)
- Each inspection shows date, notes, inspector, with delete button

- [ ] **Step 5: Build and verify**

```bash
cd jarvis/frontend && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/api/foiParcurs.ts \
        jarvis/frontend/src/types/foiParcurs.ts \
        jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): registration number + inspections in Stock tab"
```

---

### Task 5: Frontend — Test Drive Form Page

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — add TD Form tab
- Modify: `jarvis/frontend/src/App.tsx` — add route

- [ ] **Step 1: Create TestDriveForm.tsx**

Build a form page with these sections in order:

**Section 1 — Vehicle & Company:**
- Company dropdown (from `foiParcursApi.getCompanies()`)
- Vehicle dropdown (filtered by company, shows `registration_number - mark model`)
- Latest inspection card (auto-fetched when vehicle selected, read-only)

**Section 2 — Client:**
- CRM client search (using `crmApi.getClients({ q })`)
- Selected client badge with "Change" button
- "Add New Client" placeholder (links to CRM)

**Section 3 — Route:**
- Departure datetime (DateField)
- Return datetime (DateField, optional)
- Odometer start (number input)
- Odometer end (number input, optional)
- Estimated KM (number input)
- Itinerary (ItineraryField component with auto-fill)

**Section 4 — Fuel:**
- Fuel gauge start level (select)
- Fuel gauge end level (select, optional)

**Section 5 — Compliance:**
- GDPR consent text (read-only paragraph)
- GDPR consent checkbox
- Car inspection acceptance checkbox
- Advisor name (pre-filled from logged-in user)

**Section 6 — Signatures:**
- Client signature (SignatureCanvas component)
- Advisor signature (SignatureCanvas component)

**Submit button** calls `foiParcursApi.submitTestDrive()`.

On success: show confirmation with contract details + PDF download buttons.

Use existing components:
- `SignatureCanvas` from `@/components/shared/SignatureCanvas`
- `DateField` from `@/components/ui/date-field`
- `SearchInput` from `@/components/shared/SearchInput`
- `Card`, `Label`, `Input`, `Select`, `Checkbox`, `Button` from shadcn/ui
- `ItineraryField` from the existing FoiParcurs page

- [ ] **Step 2: Add route in App.tsx**

```tsx
const TestDriveForm = lazy(() => import('./pages/FoiParcurs/TestDriveForm'))

// In routes:
<Route path="foi-parcurs/test-drive" element={<Guard flag="can_access_carpark"><SuspensePage><TestDriveForm /></SuspensePage></Guard>} />
```

- [ ] **Step 3: Add "New Test Drive" button to Contracts tab and Parcurs tab**

In `index.tsx`, add a button at the top that links to `/app/foi-parcurs/test-drive`:

```tsx
<Button onClick={() => navigate('/app/foi-parcurs/test-drive')}>
  <FileText className="mr-1.5 h-4 w-4" />
  New Test Drive
</Button>
```

In Parcurs tab, add "TD Form" button on PENDING contracts that navigates to `/app/foi-parcurs/test-drive?contract_id=X`.

- [ ] **Step 4: Build and verify**

```bash
cd jarvis/frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx \
        jarvis/frontend/src/pages/FoiParcurs/index.tsx \
        jarvis/frontend/src/App.tsx \
        jarvis/static/react/
git commit -m "feat(foi-parcurs): Test Drive form page with signatures and compliance"
```

---

### Task 6: Backend — PDF Generation Service

**Files:**
- Create: `jarvis/foi_parcurs/services/pdf_service.py`
- Create: `jarvis/foi_parcurs/routes/pdf.py`
- Modify: `jarvis/foi_parcurs/routes/__init__.py`
- Modify: `jarvis/foi_parcurs/routes/test_drive.py` — wire PDF after submit

- [ ] **Step 1: Install ReportLab if needed**

```bash
pip install reportlab qrcode[pil]
```

- [ ] **Step 2: Create pdf_service.py**

Two functions:

`generate_legal_pdf(contract, vehicle, client, company)` — Standard Foaie de Parcurs format:
- A4 landscape, company header (name, CUI, address)
- Vehicle block: mark, model, registration number, VIN
- Client block: name, driver license, DOB
- Route block: itinerary, departure/return dates
- Odometer: start, end, distance
- Fuel: start level, end level, consumption
- Signature blocks: advisor + client (embed base64 SVG/PNG)
- Returns file path

`generate_custom_pdf(contract, vehicle, client, company)` — Autoworld branded:
- A4 portrait, company logo
- Test drive summary card
- GDPR consent record
- Car condition acceptance
- Both signatures
- QR code linking to `/app/foi-parcurs/test-drive/{id}`
- Returns file path

Both save to `jarvis/static/pdfs/foi-parcurs/` directory.

- [ ] **Step 3: Create pdf.py routes**

```python
"""PDF download routes for foi de parcurs contracts."""
import os
from flask import send_file
from ._shared import foi_parcurs_bp, jsonify, login_required, logger, _fp_repo
from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/pdf/<pdf_type>', methods=['GET'])
@login_required
def api_download_pdf(id, pdf_type):
    if pdf_type not in ('legal', 'custom'):
        return jsonify({'success': False, 'error': 'Invalid PDF type'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    path_field = f'pdf_{pdf_type}_path'
    pdf_path = contract.get(path_field)

    # Generate if not yet generated
    if not pdf_path or not os.path.exists(pdf_path):
        try:
            if pdf_type == 'legal':
                pdf_path = generate_legal_pdf(contract)
            else:
                pdf_path = generate_custom_pdf(contract)
            # Save path back to DB
            _fp_repo.execute(
                f'UPDATE foi_de_parcurs SET {path_field} = %s WHERE id = %s',
                (pdf_path, id),
            )
        except Exception as e:
            logger.exception('Failed to generate PDF for contract %s', id)
            return jsonify({'success': False, 'error': str(e)[:200]}), 500

    return send_file(pdf_path, as_attachment=True,
                     download_name=f'foaie-parcurs-{contract["contract_id"]}-{pdf_type}.pdf')
```

- [ ] **Step 4: Register pdf routes**

Add to `__init__.py`: `from . import pdf  # noqa: F401`

- [ ] **Step 5: Wire PDF generation into test_drive.py submit**

After `contract = _fp_repo.create_from_td_form(contract_data)`, add:

```python
        # Generate PDFs
        try:
            from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf
            legal_path = generate_legal_pdf(contract)
            custom_path = generate_custom_pdf(contract)
            _fp_repo.execute(
                'UPDATE foi_de_parcurs SET pdf_legal_path = %s, pdf_custom_path = %s WHERE id = %s',
                (legal_path, custom_path, contract['id']),
            )
            contract['pdf_legal_path'] = legal_path
            contract['pdf_custom_path'] = custom_path
        except Exception:
            logger.exception('PDF generation failed for contract %s', contract.get('contract_id'))
```

- [ ] **Step 6: Commit**

```bash
git add jarvis/foi_parcurs/services/pdf_service.py \
        jarvis/foi_parcurs/routes/pdf.py \
        jarvis/foi_parcurs/routes/__init__.py \
        jarvis/foi_parcurs/routes/test_drive.py
git commit -m "feat(foi-parcurs): PDF generation — legal Foaie de Parcurs + custom branded"
```

---

### Task 7: Frontend — PDF Download Buttons + Parcurs Tab Integration

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — PDF buttons in Parcurs tab
- Modify: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx` — success screen with PDF links

- [ ] **Step 1: Add PDF download buttons in Parcurs tab expanded row**

In the expanded row detail panel, for FILLED contracts that have `source === 'td_form'`, add:

```tsx
<div className="flex gap-2 mt-2">
  <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank">
    <Button variant="outline" size="sm">
      <FileText className="mr-1 h-3.5 w-3.5" /> Legal PDF
    </Button>
  </a>
  <a href={foiParcursApi.getContractPdfUrl(c.id, 'custom')} target="_blank">
    <Button variant="outline" size="sm">
      <FileText className="mr-1 h-3.5 w-3.5" /> Custom PDF
    </Button>
  </a>
</div>
```

- [ ] **Step 2: Add success screen to TestDriveForm.tsx**

After successful submission, show:
- Green checkmark + "Test Drive contract created"
- Contract ID, vehicle, client summary
- Two PDF download buttons (legal + custom)
- "New Test Drive" button to reset form
- "Back to Parcurs" link

- [ ] **Step 3: Build and verify**

```bash
cd jarvis/frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx \
        jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx \
        jarvis/static/react/
git commit -m "feat(foi-parcurs): PDF download buttons in Parcurs tab + TD form success screen"
```

---

### Task 8: Final — Restart Backend, Build Frontend, Test End-to-End

- [ ] **Step 1: Restart backend**

```bash
kill $(lsof -ti:5001) 2>/dev/null; sleep 1
cd jarvis && DATABASE_URL="postgresql://localhost/defaultdb" python -c "from app import create_app; app = create_app(); app.run(port=5001, debug=False)" &
```

- [ ] **Step 2: Build frontend**

```bash
cd jarvis/frontend && npm run build
```

- [ ] **Step 3: Test end-to-end flow**

1. Stock tab: Add a vehicle with registration number, create an inspection
2. Open Test Drive form: select company, vehicle, verify inspection shows
3. Search and select CRM client
4. Fill route details, fuel levels
5. Check GDPR consent, car inspection acceptance
6. Draw client + advisor signatures
7. Submit — verify contract created in Parcurs tab
8. Download both PDFs — verify content

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(foi-parcurs): Test Drive form complete — form, inspections, PDFs"
```
