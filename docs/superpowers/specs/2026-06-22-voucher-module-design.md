# Voucher Module — Design Spec

**Date:** 2026-06-22
**Status:** Draft
**Module location:** `jarvis/accounting/vouchers/`

---

## Overview

End-to-end voucher system: issuance by sales/staff, approval via the existing Approval Engine, tracking by accounting, redemption, expiry management, and monthly digest reporting. Vouchers represent post-sale benefits tied to a client, contract, and VIN.

---

## Data Model

### Table: `vouchers`

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PK |
| company_id | INT | FK → companies, NOT NULL |
| voucher_code | VARCHAR(20) | UNIQUE, NOT NULL, format: `VCH-{YYYYMM}-{6-char alphanum}` |
| client_name | VARCHAR(255) | NOT NULL |
| contract_number | VARCHAR(100) | NOT NULL |
| car_vin | VARCHAR(17) | NOT NULL, CHECK (length = 17, alphanumeric) |
| validity_months | INT | NOT NULL, CHECK (IN 1, 3, 6, 12, 24) |
| expires_at | DATE | NULL (set on approval) |
| issued_at | DATE | NULL (set on approval) |
| issued_by_user_id | INT | FK → users, NOT NULL |
| voucher_type | VARCHAR(30) | NOT NULL, CHECK (IN 'value', 'accessory_discount_code', 'accessory_percentage', 'service_items') |
| value_lei | NUMERIC(12,2) | NULL — only when voucher_type = 'value' |
| discount_code | VARCHAR(100) | NULL — only when voucher_type = 'accessory_discount_code' |
| discount_percentage | NUMERIC(5,2) | NULL — only when voucher_type = 'accessory_percentage' |
| service_items | JSONB | NULL — array of strings, only when voucher_type = 'service_items' |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending_approval', CHECK (IN 'draft', 'pending_approval', 'approved', 'active', 'rejected', 'redeemed', 'expired') |
| approval_request_id | INT | FK → approval_requests, NULL |
| approver_user_id | INT | FK → users, NULL — explicit override; NULL = org hierarchy manager |
| redeemed_at | TIMESTAMP | NULL |
| redeemed_by_user_id | INT | FK → users, NULL |
| redemption_notes | TEXT | NULL |
| notes | TEXT | NULL |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**Indexes:** `company_id`, `status`, `issued_by_user_id`, `expires_at`, `voucher_code`

**Voucher code generation:** `VCH-{YYYYMM}-{6 random alphanumeric uppercase}`. Retry on collision (unique constraint).

---

## File Structure

```
jarvis/accounting/vouchers/
├── __init__.py
├── repositories/
│   └── voucher_repository.py    # BaseRepository subclass, raw SQL via psycopg2
├── services/
│   └── voucher_service.py       # Business logic, approval engine calls, approver resolution
├── routes/
│   ├── crud.py                  # Create, read, list, my-vouchers, PDF
│   └── accounting.py            # Accounting list, redeem, export
├── schemas.py                   # Pydantic v2: VoucherCreate, VoucherRead, VoucherListItem, VoucherRedeem
├── pdf_generator.py             # ReportLab A4 voucher PDF
└── digest.py                    # Monthly digest email builder
```

---

## Backend API

### Blueprint: `/api/vouchers`

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/api/vouchers` | Create + submit for approval | `@login_required` |
| GET | `/api/vouchers` | List (company-scoped, filters) | `@login_required` |
| GET | `/api/vouchers/<id>` | Single voucher detail | `@login_required` |
| GET | `/api/vouchers/my` | Current user's issued vouchers | `@login_required` |
| GET | `/api/vouchers/accounting` | Full list for accounting team | accounting/admin role |
| PATCH | `/api/vouchers/<id>/redeem` | Mark as redeemed | accounting/admin role |
| GET | `/api/vouchers/<id>/pdf` | Generate printable PDF | `@login_required` |
| GET | `/api/vouchers/export` | CSV export of filtered view | accounting/admin role |

### Pydantic v2 Schemas

```python
class VoucherCreate(BaseModel):
    client_name: str
    contract_number: str
    car_vin: str                          # 17 alphanumeric, validated
    validity_months: int                  # 1, 3, 6, 12, 24
    voucher_type: str                     # 'value' | 'accessory_discount_code' | 'accessory_percentage' | 'service_items'
    value_lei: Optional[Decimal] = None
    discount_code: Optional[str] = None
    discount_percentage: Optional[Decimal] = None
    service_items: Optional[list[str]] = None
    approver_user_id: Optional[int] = None  # NULL = org hierarchy manager
    notes: Optional[str] = None

class VoucherRead(BaseModel):
    id: int
    company_id: int
    voucher_code: str
    client_name: str
    contract_number: str
    car_vin: str
    validity_months: int
    expires_at: Optional[date]
    issued_at: Optional[date]
    issued_by_user_id: int
    issued_by_name: str                   # joined from users table
    voucher_type: str
    value_lei: Optional[Decimal]
    discount_code: Optional[str]
    discount_percentage: Optional[Decimal]
    service_items: Optional[list[str]]
    status: str
    approver_user_id: Optional[int]
    approver_name: Optional[str]          # joined from users table
    redeemed_at: Optional[datetime]
    redeemed_by_user_id: Optional[int]
    redeemed_by_name: Optional[str]
    redemption_notes: Optional[str]
    notes: Optional[str]
    days_remaining: Optional[int]         # computed in query or service
    created_at: datetime
    updated_at: datetime

class VoucherListItem(BaseModel):
    id: int
    voucher_code: str
    client_name: str
    contract_number: str
    car_vin: str
    voucher_type: str
    benefit_display: str                  # formatted: "500 LEI" / "10%" / "CODE-XYZ" / "3 service items"
    issued_at: Optional[date]
    expires_at: Optional[date]
    days_remaining: Optional[int]
    status: str
    issued_by_name: str

class VoucherRedeem(BaseModel):
    redemption_notes: Optional[str] = None
```

### Validation Rules

- `car_vin`: exactly 17 alphanumeric characters (uppercase enforced)
- Exactly one type-specific field must be populated, matching `voucher_type`:
  - `value` → `value_lei` required, others null
  - `accessory_discount_code` → `discount_code` required, others null
  - `accessory_percentage` → `discount_percentage` required (0-100), others null
  - `service_items` → `service_items` required (non-empty list), others null
- Redeem only if `status == 'active'` AND `expires_at >= today`
- Redeem requires accounting role or admin
- Issuer must have a resolvable manager (org hierarchy) if `approver_user_id` not provided; otherwise return 400: "Your account has no configured superior. Contact admin."

---

## Approval Engine Integration

### Flow Registration

Insert into `approval_flows`:
- `entity_type = 'voucher'`
- `name = 'Voucher Approval'`
- Single-step flow: approver resolved dynamically at submission time

### Create Flow

1. Insert voucher row with `status='pending_approval'`
2. Resolve approver:
   - If `approver_user_id` is set → use that user
   - Else → look up issuer's manager from org structure:
     - Check `structure_nodes` for issuer's `org_unit_id` → find responsable at parent level
     - Fallback to `company_responsables` (L0) for the issuer's `company_id`
   - If no manager found → abort, return 400
3. Call `ApprovalEngine.submit(entity_type='voucher', entity_id=voucher.id, context={voucher snapshot}, requested_by=current_user.id)`
4. Store `approval_request_id` on voucher row

### Approval Hooks (registered in voucher service, listening via `hooks.py`)

- **`approval.approved`** where `entity_type='voucher'`:
  - Set `status='active'`, `issued_at=today`, `expires_at = issued_at + validity_months`
  - Notify issuer: "Voucher VCH-XXXX approved and active"

- **`approval.rejected`** where `entity_type='voucher'`:
  - Set `status='rejected'`
  - Notify issuer: "Voucher VCH-XXXX rejected — [reason]"

---

## Notification Integration

All notifications via existing `send_email()` from `core/services/notification_service.py`.

| Event | Recipient | Message |
|-------|-----------|---------|
| Voucher created | Approver | "Voucher VCH-XXXX awaiting your approval" |
| Approval granted | Issuer | "Voucher VCH-XXXX approved and active" |
| Approval rejected | Issuer | "Voucher VCH-XXXX rejected — [reason]" |
| 7 days before expiry | Issuer | "Voucher VCH-XXXX expires in 7 days" |
| Redeemed | Issuer | "Voucher VCH-XXXX was redeemed by accounting" |
| Monthly digest | All users | Per-user voucher summary + company-wide totals |

---

## Scheduled Jobs

Added to existing `tasks/cleanup.py` scheduler:

| Job | Schedule | Logic |
|-----|----------|-------|
| `expire_vouchers` | Daily (midnight) | `status='active'` WHERE `expires_at < today` → set `status='expired'` |
| `voucher_expiry_warning` | Daily (9 AM) | `status='active'` WHERE `expires_at = today + 7` → email issuer |
| `voucher_monthly_digest` | 1st business day of month (9 AM) | Build and send digest email to all users |

### Monthly Digest Content

Per-user section:
- Their issued vouchers: count by status, total active value
- List of vouchers expiring in the coming month

Company-wide summary:
- Active count + total value
- Redeemed last month (count + value)
- Expired last month (count)
- Expiring this month (count)
- New vouchers issued last month

---

## Frontend

### 1. Voucher Issuance Form — `/app/accounting/vouchers/new`

Standard React form component (pattern: AddInvoice):
- Fields: client_name, contract_number, car_vin (17-char input with validation), validity_months (dropdown: 1/3/6/12/24), voucher_type (radio group)
- Conditional fields toggle based on voucher_type:
  - `value` → value_lei numeric input
  - `accessory_discount_code` → discount_code text input
  - `accessory_percentage` → discount_percentage numeric 0-100
  - `service_items` → multi-tag input
- approver_user_id — optional user picker dropdown, placeholder: "Leave empty for direct manager"
- notes — textarea
- Submit → POST `/api/vouchers` → toast: "Voucher VCH-XXXX created — pending approval from [approver name]"

### 2. My Vouchers Tab — User Profile

Embedded tab in existing profile page (mirror existing tab pattern):

| Column | Notes |
|--------|-------|
| Voucher Code | |
| Client | |
| Contract | |
| VIN | |
| Type | |
| Benefit | Formatted display (e.g. "500 LEI", "10%") |
| Issued | Date |
| Expires | Date |
| Days Left | Computed |
| Status | Color-coded badge |

- Status badges: pending=yellow, active=green, expiring ≤30d=orange, expired/rejected=red, redeemed=gray
- Row click → modal with full detail + Download PDF button
- Read-only after submission

### 3. Accounting Voucher Tracking — `/app/accounting/vouchers`

New page under accounting:
- **Summary bar:** Active (count) | Expiring Soon ≤30d (count) | Redeemed this month | Expired | Total active value (LEI)
- **Filters:** status (multi-select), voucher_type (multi-select), date range (issued_at), expiring within N days
- **Table:** Code | Issuer | Client | Contract | VIN | Type | Benefit | Issued | Expires | Status | Actions
- **Actions:** "Mark Redeemed" button → confirm modal with optional note
- **Export CSV** button — current filtered view
- **Auth guard:** `can_access_accounting` + V2 permission `accounting.vouchers.manage`

### Routing (App.tsx)

```typescript
const VoucherTracking = lazy(() => import('./pages/Accounting/Vouchers'))
const VoucherNew = lazy(() => import('./pages/Accounting/Vouchers/NewVoucher'))

<Route path="accounting/vouchers" element={
  <Guard flag="can_access_accounting">
    <SuspensePage><VoucherTracking /></SuspensePage>
  </Guard>
} />
<Route path="accounting/vouchers/new" element={
  <SuspensePage><VoucherNew /></SuspensePage>
} />
```

Profile tab is embedded — no separate route.

### PDF (ReportLab)

A4 page containing:
- Company logo placeholder (top-left)
- "VOUCHER" title + voucher_code in large font
- Client name, contract number, VIN
- Voucher type + benefit description
- Validity: issued_at → expires_at
- Issuer name
- Approval stamp placeholder
- Generated date footer

---

## Permission Setup

- New V2 permission key: `accounting.vouchers.manage` — required for accounting endpoints (redeem, export, full list)
- Issuance form: any authenticated user (`@login_required`)
- Profile tab: any authenticated user viewing their own vouchers

---

## Deliverables Checklist

- [ ] Database migration (CREATE TABLE vouchers + indexes)
- [ ] Approval flow seed (INSERT into approval_flows)
- [ ] Repository (voucher_repository.py — BaseRepository, raw SQL)
- [ ] Pydantic v2 schemas (schemas.py)
- [ ] Service layer (voucher_service.py — create, approve/reject hooks, redeem, approver resolution)
- [ ] Routes — CRUD (crud.py)
- [ ] Routes — Accounting (accounting.py)
- [ ] PDF generator (pdf_generator.py — ReportLab)
- [ ] Scheduled jobs — expiry, 7-day warning, monthly digest
- [ ] Digest email builder (digest.py)
- [ ] Approval hooks registration
- [ ] Notification hooks (create, approve, reject, expiry warning, redeem)
- [ ] Frontend: Issuance form component
- [ ] Frontend: My Vouchers profile tab
- [ ] Frontend: Accounting tracking page (summary + table + filters + export)
- [ ] Frontend: routing + guards in App.tsx
- [ ] V2 permission key registration
