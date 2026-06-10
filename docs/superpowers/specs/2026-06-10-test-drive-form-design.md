# Test Drive Form + Contract Generation — Design Spec

**Date:** 2026-06-10
**Module:** Foi de Parcurs (Phase 2)
**Status:** Approved

## Overview

A Test Drive form built using JARVIS's existing forms module that serves as the primary data entry point for test drive events. On submission, it generates a `foi_de_parcurs` contract record and two PDF outputs: a legal Foaie de Parcurs (Ordin 1171/2005) and a custom branded summary.

## Flow

```
Advisor opens TD Form
  → Selects Company → Selects Vehicle (from stock, filtered by company)
  → Latest damage inspection displayed (read-only)
  → Searches CRM client or adds new client
  → Fills route details (odometer, itinerary, date/time)
  → Fuel gauge levels
  → GDPR consent + car inspection acceptance
  → Client signature + advisor signature
  → Submit
  → foi_de_parcurs record created (status: FILLED)
  → PDF 1: Legal Foaie de Parcurs generated
  → PDF 2: Custom branded summary generated
```

## Form Sections

### 1. Vehicle & Company

| Field | Type | Required | Source |
|-------|------|----------|--------|
| Company | dropdown | yes | companies table |
| Vehicle | dropdown (filtered by company) | yes | fp_vehicles (shows registration_number - mark model) |
| Latest damage inspection | read-only card | no | fp_vehicle_inspections (latest for selected VIN) |

### 2. Client

| Field | Type | Required | Source |
|-------|------|----------|--------|
| Client search | autocomplete | yes | CRM clients (crmApi.getClients) |
| — OR Add New — | | | |
| Name | text | yes | manual |
| Phone | text | yes | manual |
| Email | email | no | manual |
| Company (client's) | text | no | manual |
| Date of Birth | date picker | yes | manual |
| Driver License | text | yes | manual |
| Driver License Photo | file upload / camera | yes | manual |
| Address | text | no | manual |

When adding a new client, the client is created in `crm_clients` table.

### 3. Route

| Field | Type | Required | Source |
|-------|------|----------|--------|
| Date of departure | datetime | yes | manual |
| Date of return | datetime | no | filled after return |
| Odometer start | number | yes | manual |
| Odometer end | number | no | filled after return |
| Estimated KM | number | yes | manual |
| Itinerary | textarea + auto-fill | yes | AI-generated from company config or manual |

### 4. Fuel

| Field | Type | Required | Source |
|-------|------|----------|--------|
| Fuel gauge start level | dropdown (1, 1/2, 2/3, 1/4) | yes | manual |
| Fuel gauge end level | dropdown | no | filled after return |

### 5. Compliance

| Field | Type | Required | Source |
|-------|------|----------|--------|
| GDPR consent | checkbox | yes | client checks |
| GDPR consent text | read-only paragraph | — | configured per company |
| Car inspection acceptance | checkbox | yes | client confirms vehicle condition |
| Inspection note | read-only text | — | latest inspection summary |
| Advisor name | text (pre-filled) | yes | logged-in user |

### 6. Signatures

| Field | Type | Required | Source |
|-------|------|----------|--------|
| Client signature | signature pad (touch/draw) | yes | client draws on screen |
| Advisor signature | signature pad or AI-generated | yes | advisor |

## Database Changes

### fp_vehicles — add registration_number

```sql
ALTER TABLE fp_vehicles ADD COLUMN registration_number VARCHAR(20);
```

Managed in the Stock tab. Displayed on vehicle selection dropdown and on PDF contracts.

### fp_vehicle_inspections — new table

```sql
CREATE TABLE fp_vehicle_inspections (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id BIGINT NOT NULL REFERENCES fp_vehicles(id),
    vin VARCHAR(50) NOT NULL,
    inspection_date DATE NOT NULL,
    condition_notes TEXT,
    photos JSONB DEFAULT '[]',
    inspector_name VARCHAR(255),
    inspector_signature TEXT,
    created_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_fp_inspections_vehicle ON fp_vehicle_inspections(vehicle_id);
CREATE INDEX idx_fp_inspections_date ON fp_vehicle_inspections(inspection_date DESC);
```

### foi_de_parcurs — add fields

```sql
ALTER TABLE foi_de_parcurs ADD COLUMN registration_number VARCHAR(20);
ALTER TABLE foi_de_parcurs ADD COLUMN departure_datetime TIMESTAMP WITH TIME ZONE;
ALTER TABLE foi_de_parcurs ADD COLUMN return_datetime TIMESTAMP WITH TIME ZONE;
ALTER TABLE foi_de_parcurs ADD COLUMN client_signature TEXT;
ALTER TABLE foi_de_parcurs ADD COLUMN gdpr_consent BOOLEAN DEFAULT FALSE;
ALTER TABLE foi_de_parcurs ADD COLUMN inspection_acceptance BOOLEAN DEFAULT FALSE;
ALTER TABLE foi_de_parcurs ADD COLUMN inspection_id BIGINT;
ALTER TABLE foi_de_parcurs ADD COLUMN pdf_legal_path TEXT;
ALTER TABLE foi_de_parcurs ADD COLUMN pdf_custom_path TEXT;
ALTER TABLE foi_de_parcurs ADD COLUMN source VARCHAR(20) DEFAULT 'batch';
-- source: 'batch' (from batch generation) or 'td_form' (from test drive form)
```

## PDF Generation

### PDF 1: Legal Foaie de Parcurs (Ordin 1171/2005)

Standard Romanian format with mandated fields:
- Header: company name, CUI, registered address
- Vehicle: mark, model, registration number, VIN
- Driver/Client: name, driver license number, date of birth
- Route: departure point, destination, return point, itinerary
- Odometer: start, end, total KM
- Fuel: gauge start, gauge end, consumption
- Dates: departure date/time, return date/time
- Signatures: advisor + client (embedded from signature pad)

### PDF 2: Custom Branded Summary

Autoworld-branded document:
- Company logo + branding
- Test drive summary (vehicle, client, route)
- GDPR consent record
- Car condition acceptance
- Both signatures
- QR code linking to digital record in JARVIS

## Backend Endpoints

### Test Drive Form
- `POST /api/foi-parcurs/test-drive` — Submit TD form, creates contract + generates PDFs
- `GET /api/foi-parcurs/test-drive/:id` — Get TD form data for a contract

### Vehicle Inspections
- `GET /api/foi-parcurs/vehicles/:id/inspections` — List inspections for a vehicle
- `POST /api/foi-parcurs/vehicles/:id/inspections` — Create inspection
- `GET /api/foi-parcurs/vehicles/:id/inspections/latest` — Latest inspection

### PDF
- `GET /api/foi-parcurs/contracts/:id/pdf/legal` — Download legal PDF
- `GET /api/foi-parcurs/contracts/:id/pdf/custom` — Download custom PDF

## Frontend

### Test Drive Form Page
- New route: `/app/foi-parcurs/test-drive` (or dialog from Parcurs tab)
- Uses JARVIS FormRenderer patterns but as a custom page (not dynamic form builder)
- Pre-fills vehicle data when opened from a specific contract
- Signature pad component for client + advisor signatures

### Stock Tab Additions
- `registration_number` field in vehicle add/edit forms and table
- New "Inspections" sub-section per vehicle (or expandable row)
- Add inspection: date, notes, photos (multi-upload), inspector name + signature

### Parcurs Tab Addition
- "TD Form" button on PENDING contracts (opens the Test Drive form pre-filled)
- "Download PDF" buttons on FILLED contracts (legal + custom)

## Integration with Existing Forms Module

The TD form uses the existing forms infrastructure for:
- Signature field type (`signature` in FormRenderer)
- File upload field type (`file_upload` for license photo + inspection photos)
- Validation patterns from FormRenderer

But it is a **custom page** (not a dynamic form from the form builder) because:
- It needs live vehicle/client search dropdowns tied to specific tables
- It generates foi_de_parcurs records on submit
- It triggers PDF generation
- The field layout is fixed, not user-configurable

## Out of Scope (Phase 3+)
- Comodat form (similar but for longer-term vehicle loans)
- Digital signing with qualified electronic signature
- SMS/email sending of PDF to client
- Mobile-optimized TD form for tablet use at dealership
