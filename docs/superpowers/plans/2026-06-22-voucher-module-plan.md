# Voucher Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end Voucher module: issuance, approval, tracking, redemption, expiry, PDF, monthly digest.

**Architecture:** Raw SQL + psycopg2 via BaseRepository pattern, Flask blueprints, Pydantic v2 schemas, React + TanStack Query + Radix UI + Tailwind. Integrates with existing Approval Engine (hooks), Notification Service (SMTP email), APScheduler (jobs).

**Tech Stack:** Python 3.11, Flask, psycopg2, Pydantic v2, ReportLab, APScheduler, React 19, TypeScript, Vite, TanStack Query, Zustand, Radix UI, Tailwind CSS.

## Global Constraints

- All DB queries scoped by `company_id` (not tenant_id)
- All endpoints protected with `@login_required` minimum
- Use `BaseRepository` from `core/base_repository.py` — never raw psycopg2 directly
- Use `jsonify()` for all route responses
- Use `@handle_api_errors` decorator on all routes
- Mirror exact patterns from invoices/facturare modules
- Work on `dev` branch only
- No new libraries except what's already installed
- Frontend: use existing `api` client from `src/api/client.ts`
- Frontend: use `sonner` toast for notifications, Radix UI Dialog for modals
- Frontend: lazy-load all page components in App.tsx

---

## Phase 1: Backend Core (DB + Repository + Schemas + Service)

### Task 1: Database Migration

**Files:**
- Create: `jarvis/migrations/domains/schema_vouchers.py`
- Modify: `jarvis/migrations/init_schema.py`

**Produces:** `vouchers` table in database, callable via `create_schema_vouchers(conn, cursor)`

- [ ] **Step 1: Create schema_vouchers.py**

```python
"""Voucher module schema."""
import logging

logger = logging.getLogger(__name__)


def create_schema_vouchers(conn, cursor):
    """Create vouchers table and indexes."""

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vouchers (
            id SERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES companies(id),
            voucher_code VARCHAR(20) NOT NULL UNIQUE,
            client_name VARCHAR(255) NOT NULL,
            contract_number VARCHAR(100) NOT NULL,
            car_vin VARCHAR(17) NOT NULL,
            validity_months INT NOT NULL,
            expires_at DATE,
            issued_at DATE,
            issued_by_user_id INT NOT NULL REFERENCES users(id),
            voucher_type VARCHAR(30) NOT NULL,
            value_lei NUMERIC(12,2),
            discount_code VARCHAR(100),
            discount_percentage NUMERIC(5,2),
            service_items JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending_approval',
            approval_request_id INT,
            approver_user_id INT REFERENCES users(id),
            redeemed_at TIMESTAMP,
            redeemed_by_user_id INT REFERENCES users(id),
            redemption_notes TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Check constraints
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_voucher_status'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_status
                CHECK (status IN ('draft', 'pending_approval', 'approved', 'active', 'rejected', 'redeemed', 'expired'));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_voucher_type'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_type
                CHECK (voucher_type IN ('value', 'accessory_discount_code', 'accessory_percentage', 'service_items'));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_validity_months'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_validity_months
                CHECK (validity_months IN (1, 3, 6, 12, 24));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_car_vin_length'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_car_vin_length
                CHECK (char_length(car_vin) = 17);
            END IF;
        END $$;
    ''')

    # Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_company_id ON vouchers(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_issued_by ON vouchers(issued_by_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_expires_at ON vouchers(expires_at)')

    conn.commit()
    logger.info('Vouchers schema created/updated')
```

- [ ] **Step 2: Register in init_schema.py**

Add import and call in `init_schema.py` after the last domain schema call:

```python
from migrations.domains.schema_vouchers import create_schema_vouchers
# ... in the init function, after other schema calls:
create_schema_vouchers(conn, cursor)
```

- [ ] **Step 3: Test — run migration locally**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python -c "
from migrations.domains.schema_vouchers import create_schema_vouchers
from core.database import get_db, release_db, get_cursor
conn = get_db()
try:
    cursor = get_cursor(conn)
    create_schema_vouchers(conn, cursor)
    cursor.execute(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'vouchers' ORDER BY ordinal_position\")
    for row in cursor.fetchall():
        print(f'  {row[0]:30s} {row[1]}')
    print('Migration OK')
finally:
    release_db(conn)
"
```

Expected: Table created with all columns listed.

- [ ] **Step 4: Commit**

```bash
git add jarvis/migrations/domains/schema_vouchers.py jarvis/migrations/init_schema.py
git commit -m "feat(vouchers): add vouchers table migration"
```

---

### Task 2: Pydantic v2 Schemas

**Files:**
- Create: `jarvis/accounting/vouchers/schemas.py`

**Produces:** `VoucherCreate`, `VoucherRead`, `VoucherListItem`, `VoucherRedeem` classes

- [ ] **Step 1: Create schemas.py**

```python
"""Pydantic v2 schemas for the Voucher module."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class VoucherCreate(BaseModel):
    client_name: str
    contract_number: str
    car_vin: str
    validity_months: int
    voucher_type: str
    value_lei: Optional[Decimal] = None
    discount_code: Optional[str] = None
    discount_percentage: Optional[Decimal] = None
    service_items: Optional[list[str]] = None
    approver_user_id: Optional[int] = None
    notes: Optional[str] = None

    @field_validator('car_vin')
    @classmethod
    def validate_vin(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{17}', v):
            raise ValueError('VIN must be exactly 17 alphanumeric characters')
        return v

    @field_validator('validity_months')
    @classmethod
    def validate_validity(cls, v: int) -> int:
        if v not in (1, 3, 6, 12, 24):
            raise ValueError('validity_months must be 1, 3, 6, 12, or 24')
        return v

    @field_validator('voucher_type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = ('value', 'accessory_discount_code', 'accessory_percentage', 'service_items')
        if v not in allowed:
            raise ValueError(f'voucher_type must be one of {allowed}')
        return v

    @field_validator('discount_percentage')
    @classmethod
    def validate_percentage(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError('discount_percentage must be between 0 and 100')
        return v

    @model_validator(mode='after')
    def validate_type_fields(self):
        """Ensure exactly one type-specific field is populated, matching voucher_type."""
        vt = self.voucher_type
        fields_map = {
            'value': ('value_lei', self.value_lei),
            'accessory_discount_code': ('discount_code', self.discount_code),
            'accessory_percentage': ('discount_percentage', self.discount_percentage),
            'service_items': ('service_items', self.service_items),
        }
        field_name, field_val = fields_map[vt]
        if field_val is None or (isinstance(field_val, list) and len(field_val) == 0):
            raise ValueError(f'{field_name} is required when voucher_type is {vt}')

        # Ensure other type fields are null
        for other_type, (other_name, other_val) in fields_map.items():
            if other_type != vt and other_val is not None:
                raise ValueError(f'{other_name} must be null when voucher_type is {vt}')

        return self


class VoucherRead(BaseModel):
    id: int
    company_id: int
    voucher_code: str
    client_name: str
    contract_number: str
    car_vin: str
    validity_months: int
    expires_at: Optional[date] = None
    issued_at: Optional[date] = None
    issued_by_user_id: int
    issued_by_name: Optional[str] = None
    voucher_type: str
    value_lei: Optional[Decimal] = None
    discount_code: Optional[str] = None
    discount_percentage: Optional[Decimal] = None
    service_items: Optional[list[str]] = None
    status: str
    approver_user_id: Optional[int] = None
    approver_name: Optional[str] = None
    approval_request_id: Optional[int] = None
    redeemed_at: Optional[datetime] = None
    redeemed_by_user_id: Optional[int] = None
    redeemed_by_name: Optional[str] = None
    redemption_notes: Optional[str] = None
    notes: Optional[str] = None
    days_remaining: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VoucherListItem(BaseModel):
    id: int
    voucher_code: str
    client_name: str
    contract_number: str
    car_vin: str
    voucher_type: str
    benefit_display: str
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    days_remaining: Optional[int] = None
    status: str
    issued_by_name: Optional[str] = None


class VoucherRedeem(BaseModel):
    redemption_notes: Optional[str] = None
```

- [ ] **Step 2: Test schemas locally**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python -c "
from accounting.vouchers.schemas import VoucherCreate, VoucherRead, VoucherRedeem
# Valid create
v = VoucherCreate(client_name='Test', contract_number='C001', car_vin='WVWZZZ3CZWE123456', validity_months=12, voucher_type='value', value_lei=500)
print(f'Valid create: {v.voucher_code if hasattr(v, \"voucher_code\") else \"OK\"}')

# Invalid VIN
try:
    VoucherCreate(client_name='Test', contract_number='C001', car_vin='SHORT', validity_months=12, voucher_type='value', value_lei=500)
    print('ERROR: should have raised')
except Exception as e:
    print(f'VIN validation: {e}')

# Wrong type field
try:
    VoucherCreate(client_name='Test', contract_number='C001', car_vin='WVWZZZ3CZWE123456', validity_months=12, voucher_type='value', discount_code='ABC')
    print('ERROR: should have raised')
except Exception as e:
    print(f'Type mismatch validation: {e}')

print('Schema tests passed')
"
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/accounting/vouchers/schemas.py
git commit -m "feat(vouchers): add Pydantic v2 schemas with validation"
```

---

### Task 3: Repository

**Files:**
- Create: `jarvis/accounting/vouchers/__init__.py`
- Create: `jarvis/accounting/vouchers/repositories/__init__.py`
- Create: `jarvis/accounting/vouchers/repositories/voucher_repository.py`

**Consumes:** `BaseRepository` from `core/base_repository.py`
**Produces:** `VoucherRepository` class with methods: `create()`, `get_by_id()`, `get_all()`, `get_by_user()`, `get_for_accounting()`, `update_status()`, `redeem()`, `get_expiring()`, `get_expired_active()`, `get_summary_counts()`, `get_digest_data()`

- [ ] **Step 1: Create directory structure and __init__ files**

Create `jarvis/accounting/vouchers/__init__.py`:
```python
"""Voucher module — issuance, approval, tracking, redemption."""
```

Create `jarvis/accounting/vouchers/repositories/__init__.py`:
```python
from .voucher_repository import VoucherRepository

__all__ = ['VoucherRepository']
```

- [ ] **Step 2: Create voucher_repository.py**

```python
"""Data access layer for vouchers."""
import json
import logging
import random
import string
from datetime import date, timedelta

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.vouchers.repository')


def _generate_voucher_code() -> str:
    """Generate VCH-YYYYMM-XXXXXX code."""
    today = date.today()
    prefix = f"VCH-{today.strftime('%Y%m')}-"
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return prefix + suffix


def _benefit_display(row: dict) -> str:
    """Format benefit for display based on voucher_type."""
    vt = row.get('voucher_type', '')
    if vt == 'value':
        val = row.get('value_lei')
        return f"{val} LEI" if val is not None else ''
    elif vt == 'accessory_discount_code':
        return row.get('discount_code') or ''
    elif vt == 'accessory_percentage':
        pct = row.get('discount_percentage')
        return f"{pct}%" if pct is not None else ''
    elif vt == 'service_items':
        items = row.get('service_items')
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except (json.JSONDecodeError, TypeError):
                items = []
        if items:
            return f"{len(items)} service item{'s' if len(items) != 1 else ''}"
        return ''
    return ''


class VoucherRepository(BaseRepository):

    def create(self, company_id: int, issued_by_user_id: int,
               client_name: str, contract_number: str, car_vin: str,
               validity_months: int, voucher_type: str,
               value_lei=None, discount_code=None,
               discount_percentage=None, service_items=None,
               approver_user_id=None, notes=None) -> dict:
        """Insert a new voucher. Retries on code collision. Returns full row."""
        for attempt in range(5):
            code = _generate_voucher_code()
            try:
                row = self.execute('''
                    INSERT INTO vouchers
                        (company_id, voucher_code, client_name, contract_number,
                         car_vin, validity_months, issued_by_user_id, voucher_type,
                         value_lei, discount_code, discount_percentage, service_items,
                         status, approver_user_id, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'pending_approval', %s, %s)
                    RETURNING *
                ''', (
                    company_id, code, client_name, contract_number,
                    car_vin, validity_months, issued_by_user_id, voucher_type,
                    value_lei, discount_code, discount_percentage,
                    json.dumps(service_items) if service_items else None,
                    approver_user_id, notes,
                ), returning=True)
                return row
            except Exception as e:
                if 'unique' in str(e).lower() and 'voucher_code' in str(e).lower():
                    if attempt < 4:
                        continue
                raise
        raise RuntimeError('Failed to generate unique voucher code after 5 attempts')

    def get_by_id(self, voucher_id: int) -> dict | None:
        """Get a single voucher with joined user names."""
        return self.query_one('''
            SELECT v.*,
                   u_issued.name  AS issued_by_name,
                   u_approver.name AS approver_name,
                   u_redeemed.name AS redeemed_by_name,
                   CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                        THEN (v.expires_at - CURRENT_DATE)
                        ELSE NULL END AS days_remaining
            FROM vouchers v
            LEFT JOIN users u_issued   ON u_issued.id = v.issued_by_user_id
            LEFT JOIN users u_approver ON u_approver.id = v.approver_user_id
            LEFT JOIN users u_redeemed ON u_redeemed.id = v.redeemed_by_user_id
            WHERE v.id = %s
        ''', (voucher_id,))

    def get_all(self, company_id: int, status=None, voucher_type=None,
                issued_by_user_id=None, expiring_soon=False,
                date_from=None, date_to=None, expiring_within_days=None,
                limit=200, offset=0) -> list[dict]:
        """List vouchers with filters, company-scoped."""
        conditions = ['v.company_id = %s']
        params = [company_id]

        if status:
            if isinstance(status, list):
                placeholders = ','.join(['%s'] * len(status))
                conditions.append(f'v.status IN ({placeholders})')
                params.extend(status)
            else:
                conditions.append('v.status = %s')
                params.append(status)

        if voucher_type:
            if isinstance(voucher_type, list):
                placeholders = ','.join(['%s'] * len(voucher_type))
                conditions.append(f'v.voucher_type IN ({placeholders})')
                params.extend(voucher_type)
            else:
                conditions.append('v.voucher_type = %s')
                params.append(voucher_type)

        if issued_by_user_id:
            conditions.append('v.issued_by_user_id = %s')
            params.append(issued_by_user_id)

        if expiring_soon:
            conditions.append("v.status = 'active'")
            conditions.append('v.expires_at <= CURRENT_DATE + INTERVAL \'30 days\'')
            conditions.append('v.expires_at >= CURRENT_DATE')

        if expiring_within_days is not None:
            conditions.append("v.status = 'active'")
            conditions.append('v.expires_at <= CURRENT_DATE + %s * INTERVAL \'1 day\'')
            conditions.append('v.expires_at >= CURRENT_DATE')
            params.append(expiring_within_days)

        if date_from:
            conditions.append('v.issued_at >= %s')
            params.append(date_from)

        if date_to:
            conditions.append('v.issued_at <= %s')
            params.append(date_to)

        where = ' AND '.join(conditions)
        params.extend([limit, offset])

        rows = self.query_all(f'''
            SELECT v.*,
                   u_issued.name AS issued_by_name,
                   CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                        THEN (v.expires_at - CURRENT_DATE)
                        ELSE NULL END AS days_remaining
            FROM vouchers v
            LEFT JOIN users u_issued ON u_issued.id = v.issued_by_user_id
            WHERE {where}
            ORDER BY v.created_at DESC
            LIMIT %s OFFSET %s
        ''', tuple(params))

        for row in rows:
            row['benefit_display'] = _benefit_display(row)
        return rows

    def get_by_user(self, user_id: int, limit=100, offset=0) -> list[dict]:
        """Get vouchers issued by a specific user (for profile tab)."""
        rows = self.query_all('''
            SELECT v.*,
                   u_issued.name AS issued_by_name,
                   CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                        THEN (v.expires_at - CURRENT_DATE)
                        ELSE NULL END AS days_remaining
            FROM vouchers v
            LEFT JOIN users u_issued ON u_issued.id = v.issued_by_user_id
            WHERE v.issued_by_user_id = %s
            ORDER BY v.created_at DESC
            LIMIT %s OFFSET %s
        ''', (user_id, limit, offset))

        for row in rows:
            row['benefit_display'] = _benefit_display(row)
        return rows

    def update_status(self, voucher_id: int, status: str,
                      issued_at=None, expires_at=None,
                      approval_request_id=None) -> dict | None:
        """Update voucher status and optional fields. Returns updated row."""
        sets = ['status = %s', 'updated_at = CURRENT_TIMESTAMP']
        params = [status]

        if issued_at is not None:
            sets.append('issued_at = %s')
            params.append(issued_at)
        if expires_at is not None:
            sets.append('expires_at = %s')
            params.append(expires_at)
        if approval_request_id is not None:
            sets.append('approval_request_id = %s')
            params.append(approval_request_id)

        params.append(voucher_id)
        return self.execute(
            f"UPDATE vouchers SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def redeem(self, voucher_id: int, redeemed_by_user_id: int,
               redemption_notes: str = None) -> dict | None:
        """Mark voucher as redeemed. Returns updated row."""
        return self.execute('''
            UPDATE vouchers
            SET status = 'redeemed',
                redeemed_at = CURRENT_TIMESTAMP,
                redeemed_by_user_id = %s,
                redemption_notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'active' AND expires_at >= CURRENT_DATE
            RETURNING *
        ''', (redeemed_by_user_id, redemption_notes, voucher_id), returning=True)

    def expire_active(self) -> int:
        """Set status='expired' for active vouchers past expiry. Returns count."""
        return self.execute('''
            UPDATE vouchers
            SET status = 'expired', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'active' AND expires_at < CURRENT_DATE
        ''')

    def get_expiring_on(self, target_date: date) -> list[dict]:
        """Get active vouchers expiring on a specific date."""
        return self.query_all('''
            SELECT v.*, u.name AS issued_by_name, u.email AS issued_by_email
            FROM vouchers v
            JOIN users u ON u.id = v.issued_by_user_id
            WHERE v.status = 'active' AND v.expires_at = %s
        ''', (target_date,))

    def get_summary_counts(self, company_id: int) -> dict:
        """Get status counts and total active value for summary bar."""
        row = self.query_one('''
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'active' AND expires_at <= CURRENT_DATE + INTERVAL '30 days' AND expires_at >= CURRENT_DATE) AS expiring_soon_count,
                COUNT(*) FILTER (WHERE status = 'redeemed' AND date_trunc('month', redeemed_at) = date_trunc('month', CURRENT_DATE)) AS redeemed_this_month,
                COUNT(*) FILTER (WHERE status = 'expired') AS expired_count,
                COALESCE(SUM(value_lei) FILTER (WHERE status = 'active' AND voucher_type = 'value'), 0) AS total_active_value
            FROM vouchers
            WHERE company_id = %s
        ''', (company_id,))
        return row or {}

    def get_digest_data(self, company_id: int, ref_date: date) -> dict:
        """Get data for monthly digest email."""
        first_of_month = ref_date.replace(day=1)
        prev_month_start = (first_of_month - timedelta(days=1)).replace(day=1)
        prev_month_end = first_of_month - timedelta(days=1)
        next_month_end = (first_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        summary = self.query_one('''
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COALESCE(SUM(value_lei) FILTER (WHERE status = 'active' AND voucher_type = 'value'), 0) AS active_total_value,
                COUNT(*) FILTER (WHERE status = 'redeemed' AND redeemed_at >= %s AND redeemed_at < %s) AS redeemed_last_month,
                COALESCE(SUM(value_lei) FILTER (WHERE status = 'redeemed' AND voucher_type = 'value' AND redeemed_at >= %s AND redeemed_at < %s), 0) AS redeemed_last_month_value,
                COUNT(*) FILTER (WHERE status = 'expired' AND updated_at >= %s AND updated_at < %s) AS expired_last_month,
                COUNT(*) FILTER (WHERE status = 'active' AND expires_at >= %s AND expires_at <= %s) AS expiring_this_month,
                COUNT(*) FILTER (WHERE created_at >= %s AND created_at < %s) AS new_last_month
            FROM vouchers
            WHERE company_id = %s
        ''', (
            prev_month_start, first_of_month,
            prev_month_start, first_of_month,
            prev_month_start, first_of_month,
            first_of_month, next_month_end,
            prev_month_start, first_of_month,
            company_id,
        ))

        per_user = self.query_all('''
            SELECT
                v.issued_by_user_id,
                u.name AS user_name,
                u.email AS user_email,
                COUNT(*) FILTER (WHERE v.status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE v.status = 'redeemed') AS redeemed_count,
                COUNT(*) FILTER (WHERE v.status = 'expired') AS expired_count,
                COUNT(*) FILTER (WHERE v.status = 'pending_approval') AS pending_count,
                COALESCE(SUM(v.value_lei) FILTER (WHERE v.status = 'active' AND v.voucher_type = 'value'), 0) AS active_value,
                COUNT(*) FILTER (WHERE v.status = 'active' AND v.expires_at >= %s AND v.expires_at <= %s) AS expiring_this_month
            FROM vouchers v
            JOIN users u ON u.id = v.issued_by_user_id
            WHERE v.company_id = %s
            GROUP BY v.issued_by_user_id, u.name, u.email
            ORDER BY u.name
        ''', (first_of_month, next_month_end, company_id))

        return {
            'summary': summary or {},
            'per_user': per_user,
        }
```

- [ ] **Step 3: Test repository locally**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python -c "
from accounting.vouchers.repositories import VoucherRepository
repo = VoucherRepository()
# Test get_summary_counts (should return zeros for a company with no vouchers)
counts = repo.get_summary_counts(16)
print(f'Summary counts: {counts}')
# Test get_all with no data
rows = repo.get_all(company_id=16)
print(f'All vouchers: {len(rows)} rows')
print('Repository tests passed')
"
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/vouchers/__init__.py jarvis/accounting/vouchers/repositories/
git commit -m "feat(vouchers): add VoucherRepository with BaseRepository pattern"
```

---

### Task 4: Service Layer + Approval Integration

**Files:**
- Create: `jarvis/accounting/vouchers/services/__init__.py`
- Create: `jarvis/accounting/vouchers/services/voucher_service.py`
- Create: `jarvis/core/approvals/handlers/entity_voucher.py`
- Modify: `jarvis/core/approvals/handlers/event_handlers.py` — add voucher case to `_on_approved` and `_on_rejected`

**Consumes:** `VoucherRepository`, `ApprovalEngine.submit()`, `hooks.on()`, `send_email()`, org structure tables
**Produces:** `VoucherService` class with `create_voucher()`, `redeem_voucher()`, `resolve_approver()`; approval hooks for voucher entity type

- [ ] **Step 1: Create services/__init__.py**

```python
from .voucher_service import VoucherService

__all__ = ['VoucherService']
```

- [ ] **Step 2: Create voucher_service.py**

```python
"""Business logic for voucher operations."""
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from accounting.vouchers.repositories import VoucherRepository
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.vouchers.service')


class VoucherService:

    def __init__(self):
        self.repo = VoucherRepository()
        self._base = BaseRepository()

    def resolve_approver(self, user_id: int, company_id: int,
                         explicit_approver_id: int = None) -> dict | None:
        """Resolve the approver for a voucher.

        If explicit_approver_id is given, return that user.
        Otherwise, look up the user's manager from org structure:
          1. Find user's org_unit_id → parent structure_node → responsable
          2. Fallback to company_responsables (L0)

        Returns dict with 'id', 'name', 'email' or None if not found.
        """
        if explicit_approver_id:
            return self._base.query_one(
                'SELECT id, name, email FROM users WHERE id = %s',
                (explicit_approver_id,)
            )

        # Try structure_nodes: find user's node, then parent's responsable
        user_row = self._base.query_one(
            'SELECT org_unit_id FROM users WHERE id = %s', (user_id,)
        )
        if user_row and user_row.get('org_unit_id'):
            node = self._base.query_one('''
                SELECT sn_parent.responsable_user_id
                FROM structure_nodes sn
                JOIN structure_nodes sn_parent ON sn_parent.id = sn.parent_id
                WHERE sn.id = %s AND sn_parent.responsable_user_id IS NOT NULL
            ''', (user_row['org_unit_id'],))
            if node and node.get('responsable_user_id'):
                return self._base.query_one(
                    'SELECT id, name, email FROM users WHERE id = %s',
                    (node['responsable_user_id'],)
                )

        # Fallback: company_responsables (L0)
        resp = self._base.query_one('''
            SELECT cr.user_id, u.name, u.email
            FROM company_responsables cr
            JOIN users u ON u.id = cr.user_id
            WHERE cr.company_id = %s
            LIMIT 1
        ''', (company_id,))
        if resp:
            return {'id': resp['user_id'], 'name': resp['name'], 'email': resp['email']}

        return None

    def create_voucher(self, data: dict, user_id: int, company_id: int) -> dict:
        """Create a voucher and submit for approval.

        Args:
            data: Validated VoucherCreate dict
            user_id: Current user ID
            company_id: Current user's company ID

        Returns: Created voucher dict with approver info

        Raises: ValueError if no approver can be resolved
        """
        # Resolve approver
        approver = self.resolve_approver(
            user_id, company_id,
            explicit_approver_id=data.get('approver_user_id')
        )
        if not approver:
            raise ValueError(
                'Your account has no configured superior. Contact admin.'
            )

        # Create voucher
        voucher = self.repo.create(
            company_id=company_id,
            issued_by_user_id=user_id,
            client_name=data['client_name'],
            contract_number=data['contract_number'],
            car_vin=data['car_vin'],
            validity_months=data['validity_months'],
            voucher_type=data['voucher_type'],
            value_lei=data.get('value_lei'),
            discount_code=data.get('discount_code'),
            discount_percentage=data.get('discount_percentage'),
            service_items=data.get('service_items'),
            approver_user_id=approver['id'],
            notes=data.get('notes'),
        )

        # Submit to approval engine
        try:
            from core.approvals.engine import ApprovalEngine
            engine = ApprovalEngine()
            context = {
                'voucher_code': voucher['voucher_code'],
                'client_name': voucher['client_name'],
                'voucher_type': voucher['voucher_type'],
                'value_lei': str(voucher.get('value_lei') or ''),
                'discount_code': voucher.get('discount_code') or '',
                'discount_percentage': str(voucher.get('discount_percentage') or ''),
            }
            approval = engine.submit(
                entity_type='voucher',
                entity_id=voucher['id'],
                context=context,
                requested_by=user_id,
            )
            if approval:
                self.repo.update_status(
                    voucher['id'],
                    status='pending_approval',
                    approval_request_id=approval.get('id'),
                )
        except Exception:
            logger.exception('Failed to submit voucher %s for approval', voucher['voucher_code'])

        # Notify approver
        self._notify_approver(voucher, approver)

        voucher['approver_name'] = approver['name']
        return voucher

    def activate_voucher(self, voucher_id: int):
        """Called by approval hook when voucher is approved."""
        voucher = self.repo.get_by_id(voucher_id)
        if not voucher:
            logger.warning('Voucher %s not found for activation', voucher_id)
            return

        today = date.today()
        expires = today + relativedelta(months=voucher['validity_months'])
        self.repo.update_status(
            voucher_id,
            status='active',
            issued_at=today,
            expires_at=expires,
        )
        logger.info('Voucher %s activated, expires %s', voucher['voucher_code'], expires)

        # Notify issuer
        self._notify_issuer_approved(voucher)

    def reject_voucher(self, voucher_id: int, reason: str = None):
        """Called by approval hook when voucher is rejected."""
        voucher = self.repo.get_by_id(voucher_id)
        if not voucher:
            return

        self.repo.update_status(voucher_id, status='rejected')
        logger.info('Voucher %s rejected', voucher['voucher_code'])

        self._notify_issuer_rejected(voucher, reason)

    def redeem_voucher(self, voucher_id: int, redeemed_by_user_id: int,
                       notes: str = None) -> dict | None:
        """Mark voucher as redeemed. Returns updated row or None."""
        voucher = self.repo.get_by_id(voucher_id)
        if not voucher:
            return None
        if voucher['status'] != 'active':
            raise ValueError(f"Cannot redeem voucher with status '{voucher['status']}'")
        if voucher.get('expires_at') and voucher['expires_at'] < date.today():
            raise ValueError('Cannot redeem expired voucher')

        result = self.repo.redeem(voucher_id, redeemed_by_user_id, notes)
        if result:
            self._notify_issuer_redeemed(voucher, redeemed_by_user_id)
        return result

    # ── Notifications ───────────────────────────────────

    def _notify_approver(self, voucher: dict, approver: dict):
        try:
            from core.services.notification_service import send_email
            send_email(
                to_email=approver['email'],
                subject=f"Voucher {voucher['voucher_code']} awaiting your approval",
                html_body=f"""
                <p>A new voucher requires your approval:</p>
                <ul>
                    <li><strong>Code:</strong> {voucher['voucher_code']}</li>
                    <li><strong>Client:</strong> {voucher['client_name']}</li>
                    <li><strong>Contract:</strong> {voucher['contract_number']}</li>
                    <li><strong>VIN:</strong> {voucher['car_vin']}</li>
                    <li><strong>Type:</strong> {voucher['voucher_type']}</li>
                </ul>
                <p>Please review and approve or reject in JARVIS.</p>
                """,
            )
        except Exception:
            logger.exception('Failed to notify approver for voucher %s', voucher['voucher_code'])

    def _notify_issuer_approved(self, voucher: dict):
        try:
            from core.services.notification_service import send_email
            issuer = self._base.query_one(
                'SELECT email FROM users WHERE id = %s', (voucher['issued_by_user_id'],)
            )
            if issuer:
                send_email(
                    to_email=issuer['email'],
                    subject=f"Voucher {voucher['voucher_code']} approved and active",
                    html_body=f"<p>Your voucher <strong>{voucher['voucher_code']}</strong> for client {voucher['client_name']} has been approved and is now active.</p>",
                )
        except Exception:
            logger.exception('Failed to notify issuer for voucher %s', voucher['voucher_code'])

    def _notify_issuer_rejected(self, voucher: dict, reason: str = None):
        try:
            from core.services.notification_service import send_email
            issuer = self._base.query_one(
                'SELECT email FROM users WHERE id = %s', (voucher['issued_by_user_id'],)
            )
            if issuer:
                reason_text = f" Reason: {reason}" if reason else ""
                send_email(
                    to_email=issuer['email'],
                    subject=f"Voucher {voucher['voucher_code']} rejected",
                    html_body=f"<p>Your voucher <strong>{voucher['voucher_code']}</strong> has been rejected.{reason_text}</p>",
                )
        except Exception:
            logger.exception('Failed to notify issuer for voucher %s', voucher['voucher_code'])

    def _notify_issuer_redeemed(self, voucher: dict, redeemed_by_user_id: int):
        try:
            from core.services.notification_service import send_email
            issuer = self._base.query_one(
                'SELECT email FROM users WHERE id = %s', (voucher['issued_by_user_id'],)
            )
            redeemer = self._base.query_one(
                'SELECT name FROM users WHERE id = %s', (redeemed_by_user_id,)
            )
            if issuer:
                redeemer_name = redeemer['name'] if redeemer else 'accounting'
                send_email(
                    to_email=issuer['email'],
                    subject=f"Voucher {voucher['voucher_code']} was redeemed",
                    html_body=f"<p>Your voucher <strong>{voucher['voucher_code']}</strong> was redeemed by {redeemer_name}.</p>",
                )
        except Exception:
            logger.exception('Failed to notify issuer for voucher %s', voucher['voucher_code'])
```

- [ ] **Step 3: Create entity_voucher.py approval handler**

Create `jarvis/core/approvals/handlers/entity_voucher.py`:

```python
"""Approval hook handler for voucher entities."""
import logging

logger = logging.getLogger('jarvis.approvals.handlers.voucher')


def handle_approved(entity_id, request_id=None, requester_id=None):
    """Called when a voucher approval request is approved."""
    try:
        from accounting.vouchers.services import VoucherService
        VoucherService().activate_voucher(entity_id)
        logger.info('Voucher #%s activated via approval hook', entity_id)
    except Exception as e:
        logger.error('Failed to activate voucher #%s: %s', entity_id, e, exc_info=True)


def handle_rejected(entity_id, comment=None):
    """Called when a voucher approval request is rejected."""
    try:
        from accounting.vouchers.services import VoucherService
        VoucherService().reject_voucher(entity_id, reason=comment)
        logger.info('Voucher #%s rejected via approval hook', entity_id)
    except Exception as e:
        logger.error('Failed to reject voucher #%s: %s', entity_id, e, exc_info=True)
```

- [ ] **Step 4: Wire voucher hooks into event_handlers.py**

In `jarvis/core/approvals/handlers/event_handlers.py`, add to the `_on_approved` function after existing entity checks:

```python
from core.approvals.handlers import entity_voucher

# In _on_approved():
if entity_type == 'voucher' and entity_id:
    entity_voucher.handle_approved(entity_id, request_id, requester_id)

# In _on_rejected():
if entity_type == 'voucher' and entity_id:
    entity_voucher.handle_rejected(entity_id, comment=comment)
```

- [ ] **Step 5: Test service instantiation**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python -c "
from accounting.vouchers.services import VoucherService
svc = VoucherService()
print('VoucherService instantiated OK')
print(f'resolve_approver method exists: {hasattr(svc, \"resolve_approver\")}')
print(f'create_voucher method exists: {hasattr(svc, \"create_voucher\")}')
print(f'redeem_voucher method exists: {hasattr(svc, \"redeem_voucher\")}')
"
```

- [ ] **Step 6: Commit**

```bash
git add jarvis/accounting/vouchers/services/ jarvis/core/approvals/handlers/entity_voucher.py jarvis/core/approvals/handlers/event_handlers.py
git commit -m "feat(vouchers): add VoucherService with approval hooks and notifications"
```

---

## Phase 1 Test Gate

**Run after completing Tasks 1-4:**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python -c "
# 1. Migration
from migrations.domains.schema_vouchers import create_schema_vouchers
print('1. Migration module imports OK')

# 2. Schemas
from accounting.vouchers.schemas import VoucherCreate, VoucherRead, VoucherListItem, VoucherRedeem
v = VoucherCreate(client_name='Test', contract_number='C001', car_vin='WVWZZZ3CZWE123456', validity_months=12, voucher_type='value', value_lei=500)
print(f'2. Schemas OK — VIN: {v.car_vin}')

# 3. Repository
from accounting.vouchers.repositories import VoucherRepository
repo = VoucherRepository()
counts = repo.get_summary_counts(16)
print(f'3. Repository OK — summary: {counts}')

# 4. Service
from accounting.vouchers.services import VoucherService
svc = VoucherService()
print('4. Service OK')

print('\\n=== Phase 1 PASSED ===')
"
```

---

## Phase 2: Backend API (Routes + Blueprint + PDF)

### Task 5: Routes — CRUD

**Files:**
- Create: `jarvis/accounting/vouchers/routes/__init__.py`
- Create: `jarvis/accounting/vouchers/routes/_shared.py`
- Create: `jarvis/accounting/vouchers/routes/crud.py`

**Consumes:** `VoucherRepository`, `VoucherService`, `VoucherCreate`, `VoucherRedeem`
**Produces:** POST/GET voucher endpoints on the `vouchers_bp` blueprint

- [ ] **Step 1: Create routes/__init__.py**

```python
"""Voucher routes package."""
```

- [ ] **Step 2: Update accounting/vouchers/__init__.py with blueprint**

```python
"""Voucher module — issuance, approval, tracking, redemption."""
from flask import Blueprint

vouchers_bp = Blueprint('vouchers', __name__)

from .routes import crud, accounting as accounting_routes  # noqa: E402, F401
```

- [ ] **Step 3: Create _shared.py**

```python
"""Shared imports and singletons for voucher routes."""
import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from accounting.vouchers import vouchers_bp
from accounting.vouchers.repositories import VoucherRepository
from accounting.vouchers.services import VoucherService
from accounting.vouchers.schemas import VoucherCreate, VoucherRead, VoucherListItem, VoucherRedeem
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

__all__ = [
    'logging', 'jsonify', 'request', 'login_required', 'current_user',
    'vouchers_bp',
    'VoucherRepository', 'VoucherService',
    'VoucherCreate', 'VoucherRead', 'VoucherListItem', 'VoucherRedeem',
    'error_response', 'handle_api_errors', 'PermissionRepository',
    'logger', '_repo', '_service', '_perm_repo', '_check_accounting_role',
]

logger = logging.getLogger('jarvis.vouchers.routes')
_repo = VoucherRepository()
_service = VoucherService()
_perm_repo = PermissionRepository()


def _check_accounting_role() -> bool:
    """Check if current user has accounting/admin access."""
    if current_user.role_name in ('admin', 'superadmin'):
        return True
    if getattr(current_user, 'can_access_accounting', False):
        return _perm_repo.check_permission_v2(
            current_user.role_id, 'accounting', 'vouchers', 'manage'
        )
    return False
```

- [ ] **Step 4: Create crud.py**

```python
"""CRUD routes for vouchers."""
from ._shared import *  # noqa: F401, F403
from pydantic import ValidationError


@vouchers_bp.route('/api/vouchers', methods=['POST'])
@login_required
@handle_api_errors
def create_voucher():
    """Create a new voucher and submit for approval."""
    data = request.get_json(silent=True) or {}

    try:
        validated = VoucherCreate(**data)
    except ValidationError as e:
        return jsonify({'success': False, 'errors': e.errors()}), 400

    try:
        voucher = _service.create_voucher(
            data=validated.model_dump(),
            user_id=current_user.id,
            company_id=current_user.company_id,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({
        'success': True,
        'voucher': {
            'id': voucher['id'],
            'voucher_code': voucher['voucher_code'],
            'status': voucher['status'],
            'approver_name': voucher.get('approver_name', ''),
        },
    }), 201


@vouchers_bp.route('/api/vouchers', methods=['GET'])
@login_required
@handle_api_errors
def list_vouchers():
    """List vouchers (company-scoped)."""
    status = request.args.get('status')
    voucher_type = request.args.get('voucher_type')
    expiring_soon = request.args.get('expiring_soon', '').lower() == 'true'
    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))

    status_list = status.split(',') if status else None

    rows = _repo.get_all(
        company_id=current_user.company_id,
        status=status_list,
        voucher_type=voucher_type,
        expiring_soon=expiring_soon,
        limit=limit,
        offset=offset,
    )
    return jsonify(rows)


@vouchers_bp.route('/api/vouchers/my', methods=['GET'])
@login_required
@handle_api_errors
def my_vouchers():
    """List current user's issued vouchers."""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    rows = _repo.get_by_user(current_user.id, limit=limit, offset=offset)
    return jsonify(rows)


@vouchers_bp.route('/api/vouchers/<int:voucher_id>', methods=['GET'])
@login_required
@handle_api_errors
def get_voucher(voucher_id):
    """Get a single voucher by ID."""
    voucher = _repo.get_by_id(voucher_id)
    if not voucher:
        return error_response('Voucher not found', 404)
    return jsonify(voucher)
```

- [ ] **Step 5: Commit**

```bash
git add jarvis/accounting/vouchers/routes/ jarvis/accounting/vouchers/__init__.py
git commit -m "feat(vouchers): add CRUD routes with blueprint"
```

---

### Task 6: Routes — Accounting + Export

**Files:**
- Create: `jarvis/accounting/vouchers/routes/accounting.py`

**Consumes:** `_repo`, `_service`, `_check_accounting_role`
**Produces:** Accounting list, redeem, export, summary endpoints

- [ ] **Step 1: Create accounting.py**

```python
"""Accounting-specific voucher routes: tracking, redeem, export."""
import csv
import io
from ._shared import *  # noqa: F401, F403
from flask import Response
from pydantic import ValidationError


@vouchers_bp.route('/api/vouchers/accounting', methods=['GET'])
@login_required
@handle_api_errors
def accounting_list():
    """Full voucher list for accounting team with filters and summary."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    status = request.args.get('status')
    voucher_type = request.args.get('voucher_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    expiring_within = request.args.get('expiring_within_days', type=int)
    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))

    status_list = status.split(',') if status else None
    type_list = voucher_type.split(',') if voucher_type else None

    rows = _repo.get_all(
        company_id=current_user.company_id,
        status=status_list,
        voucher_type=type_list,
        date_from=date_from,
        date_to=date_to,
        expiring_within_days=expiring_within,
        limit=limit,
        offset=offset,
    )

    summary = _repo.get_summary_counts(current_user.company_id)

    return jsonify({
        'vouchers': rows,
        'summary': summary,
    })


@vouchers_bp.route('/api/vouchers/<int:voucher_id>/redeem', methods=['PATCH'])
@login_required
@handle_api_errors
def redeem_voucher(voucher_id):
    """Mark a voucher as redeemed (accounting/admin only)."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}

    try:
        validated = VoucherRedeem(**data)
    except ValidationError as e:
        return jsonify({'success': False, 'errors': e.errors()}), 400

    try:
        result = _service.redeem_voucher(
            voucher_id=voucher_id,
            redeemed_by_user_id=current_user.id,
            notes=validated.redemption_notes,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result:
        return error_response('Voucher not found or cannot be redeemed', 404)

    return jsonify({'success': True, 'voucher': result})


@vouchers_bp.route('/api/vouchers/export', methods=['GET'])
@login_required
@handle_api_errors
def export_vouchers():
    """CSV export of vouchers for accounting."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    status = request.args.get('status')
    voucher_type = request.args.get('voucher_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    status_list = status.split(',') if status else None
    type_list = voucher_type.split(',') if voucher_type else None

    rows = _repo.get_all(
        company_id=current_user.company_id,
        status=status_list,
        voucher_type=type_list,
        date_from=date_from,
        date_to=date_to,
        limit=10000,
        offset=0,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Voucher Code', 'Client', 'Contract', 'VIN', 'Type',
        'Benefit', 'Issued', 'Expires', 'Status', 'Issued By',
    ])
    for r in rows:
        writer.writerow([
            r.get('voucher_code', ''),
            r.get('client_name', ''),
            r.get('contract_number', ''),
            r.get('car_vin', ''),
            r.get('voucher_type', ''),
            r.get('benefit_display', ''),
            r.get('issued_at', ''),
            r.get('expires_at', ''),
            r.get('status', ''),
            r.get('issued_by_name', ''),
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=vouchers.csv'},
    )
```

- [ ] **Step 2: Commit**

```bash
git add jarvis/accounting/vouchers/routes/accounting.py
git commit -m "feat(vouchers): add accounting routes — list, redeem, CSV export"
```

---

### Task 7: Blueprint Registration + PDF Generator

**Files:**
- Modify: `jarvis/app.py` — register `vouchers_bp`
- Create: `jarvis/accounting/vouchers/pdf_generator.py`
- Modify: `jarvis/accounting/vouchers/routes/crud.py` — add PDF endpoint

**Consumes:** `vouchers_bp`, `VoucherRepository`, ReportLab
**Produces:** Registered blueprint, `/api/vouchers/<id>/pdf` endpoint

- [ ] **Step 1: Register blueprint in app.py**

In `jarvis/app.py`, inside `_register_blueprints()`, add after the existing accounting blueprints:

```python
from accounting.vouchers import vouchers_bp
flask_app.register_blueprint(vouchers_bp)
```

- [ ] **Step 2: Create pdf_generator.py**

```python
"""Voucher PDF generation using ReportLab."""
import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


def generate_voucher_pdf(voucher: dict) -> bytes:
    """Generate a printable A4 voucher PDF. Returns PDF bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Colors
    primary = HexColor('#1a365d')
    accent = HexColor('#2b6cb0')
    light_gray = HexColor('#f7fafc')

    # Background header band
    c.setFillColor(primary)
    c.rect(0, h - 80 * mm, w, 80 * mm, fill=1, stroke=0)

    # Title
    c.setFillColor(HexColor('#ffffff'))
    c.setFont('Helvetica-Bold', 28)
    c.drawString(30 * mm, h - 25 * mm, 'VOUCHER')

    # Voucher code
    c.setFont('Helvetica-Bold', 20)
    c.drawString(30 * mm, h - 40 * mm, voucher.get('voucher_code', ''))

    # Company placeholder
    c.setFont('Helvetica', 10)
    c.drawRightString(w - 20 * mm, h - 15 * mm, 'AUTOWORLD GROUP')
    c.drawRightString(w - 20 * mm, h - 20 * mm, 'www.autoworld.ro')

    # Status badge
    status = voucher.get('status', 'unknown').upper()
    c.setFont('Helvetica-Bold', 12)
    c.drawRightString(w - 20 * mm, h - 40 * mm, f'Status: {status}')

    # Content area
    y = h - 95 * mm
    c.setFillColor(HexColor('#000000'))

    def _label_value(label, value, y_pos):
        c.setFont('Helvetica', 10)
        c.setFillColor(HexColor('#718096'))
        c.drawString(30 * mm, y_pos, label)
        c.setFont('Helvetica-Bold', 12)
        c.setFillColor(HexColor('#1a202c'))
        c.drawString(80 * mm, y_pos, str(value or ''))
        return y_pos - 10 * mm

    y = _label_value('Client:', voucher.get('client_name', ''), y)
    y = _label_value('Contract:', voucher.get('contract_number', ''), y)
    y = _label_value('VIN:', voucher.get('car_vin', ''), y)

    # Benefit
    vt = voucher.get('voucher_type', '')
    benefit = ''
    if vt == 'value':
        benefit = f"{voucher.get('value_lei', '')} LEI"
    elif vt == 'accessory_discount_code':
        benefit = f"Discount Code: {voucher.get('discount_code', '')}"
    elif vt == 'accessory_percentage':
        benefit = f"{voucher.get('discount_percentage', '')}% Discount"
    elif vt == 'service_items':
        items = voucher.get('service_items') or []
        if isinstance(items, list):
            benefit = ', '.join(items)
        else:
            benefit = str(items)

    y = _label_value('Type:', vt.replace('_', ' ').title(), y)
    y = _label_value('Benefit:', benefit, y)

    # Validity
    issued = voucher.get('issued_at', '')
    expires = voucher.get('expires_at', '')
    validity = f"{voucher.get('validity_months', '')} months"
    y = _label_value('Validity:', validity, y)
    y = _label_value('Issued:', str(issued), y)
    y = _label_value('Expires:', str(expires), y)

    # Separator line
    y -= 5 * mm
    c.setStrokeColor(HexColor('#e2e8f0'))
    c.setLineWidth(0.5)
    c.line(30 * mm, y, w - 30 * mm, y)
    y -= 10 * mm

    # Issuer
    y = _label_value('Issued by:', voucher.get('issued_by_name', ''), y)

    # Approval placeholder
    y -= 15 * mm
    c.setFont('Helvetica', 9)
    c.setFillColor(HexColor('#a0aec0'))
    c.drawString(30 * mm, y, 'Approval stamp:')
    c.rect(30 * mm, y - 25 * mm, 60 * mm, 25 * mm, fill=0, stroke=1)

    # Footer
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#a0aec0'))
    c.drawString(30 * mm, 15 * mm, f'Generated: {date.today().isoformat()}')
    c.drawRightString(w - 20 * mm, 15 * mm, f'JARVIS — Voucher Module')

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
```

- [ ] **Step 3: Add PDF endpoint to crud.py**

Append to `jarvis/accounting/vouchers/routes/crud.py`:

```python
from flask import send_file
import io


@vouchers_bp.route('/api/vouchers/<int:voucher_id>/pdf', methods=['GET'])
@login_required
@handle_api_errors
def voucher_pdf(voucher_id):
    """Generate and return a printable voucher PDF."""
    voucher = _repo.get_by_id(voucher_id)
    if not voucher:
        return error_response('Voucher not found', 404)

    from accounting.vouchers.pdf_generator import generate_voucher_pdf
    pdf_bytes = generate_voucher_pdf(voucher)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"voucher-{voucher['voucher_code']}.pdf",
    )
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/app.py jarvis/accounting/vouchers/pdf_generator.py jarvis/accounting/vouchers/routes/crud.py
git commit -m "feat(vouchers): register blueprint, add PDF generator and endpoint"
```

---

### Task 8: Scheduled Jobs (Expiry + Warning + Digest)

**Files:**
- Create: `jarvis/accounting/vouchers/digest.py`
- Modify: `jarvis/tasks/cleanup.py` — add 3 voucher jobs

**Consumes:** `VoucherRepository`, `send_email()`
**Produces:** 3 APScheduler jobs: daily expiry, daily 7-day warning, monthly digest

- [ ] **Step 1: Create digest.py**

```python
"""Monthly voucher digest email builder."""
import logging
from datetime import date

logger = logging.getLogger('jarvis.vouchers.digest')


def build_digest_html(digest_data: dict, company_name: str, ref_date: date) -> str:
    """Build HTML for the monthly voucher digest email."""
    s = digest_data.get('summary', {})
    per_user = digest_data.get('per_user', [])
    month_label = ref_date.strftime('%B %Y')

    html = f"""
    <h2>Voucher Monthly Digest — {month_label}</h2>
    <p>Company: <strong>{company_name}</strong></p>

    <h3>Company Summary</h3>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
        <tr><td>Active Vouchers</td><td><strong>{s.get('active_count', 0)}</strong></td></tr>
        <tr><td>Active Total Value (LEI)</td><td><strong>{s.get('active_total_value', 0)}</strong></td></tr>
        <tr><td>Redeemed Last Month</td><td>{s.get('redeemed_last_month', 0)} (Value: {s.get('redeemed_last_month_value', 0)} LEI)</td></tr>
        <tr><td>Expired Last Month</td><td>{s.get('expired_last_month', 0)}</td></tr>
        <tr><td>Expiring This Month</td><td>{s.get('expiring_this_month', 0)}</td></tr>
        <tr><td>New Last Month</td><td>{s.get('new_last_month', 0)}</td></tr>
    </table>

    <h3>Per-User Breakdown</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
        <tr style="background:#f0f0f0;">
            <th>User</th><th>Active</th><th>Active Value</th>
            <th>Redeemed</th><th>Expired</th><th>Pending</th><th>Expiring This Month</th>
        </tr>
    """

    for u in per_user:
        html += f"""
        <tr>
            <td>{u.get('user_name', '')}</td>
            <td>{u.get('active_count', 0)}</td>
            <td>{u.get('active_value', 0)} LEI</td>
            <td>{u.get('redeemed_count', 0)}</td>
            <td>{u.get('expired_count', 0)}</td>
            <td>{u.get('pending_count', 0)}</td>
            <td>{u.get('expiring_this_month', 0)}</td>
        </tr>
        """

    html += """
    </table>
    <p style="color:#888;font-size:12px;">Generated by JARVIS Voucher Module</p>
    """
    return html


def send_monthly_digest():
    """Send monthly voucher digest to all users. Called by scheduler."""
    try:
        from accounting.vouchers.repositories import VoucherRepository
        from core.base_repository import BaseRepository
        from core.services.notification_service import send_email

        repo = VoucherRepository()
        base = BaseRepository()

        # Get all companies that have vouchers
        companies = base.query_all('''
            SELECT DISTINCT c.id, c.name
            FROM companies c
            JOIN vouchers v ON v.company_id = c.id
        ''')

        for company in companies:
            digest_data = repo.get_digest_data(company['id'], date.today())
            if not digest_data.get('per_user'):
                continue

            html = build_digest_html(digest_data, company['name'], date.today())

            # Send to each user who has vouchers
            for u in digest_data['per_user']:
                email = u.get('user_email')
                if email:
                    try:
                        send_email(
                            to_email=email,
                            subject=f"Voucher Monthly Digest — {date.today().strftime('%B %Y')}",
                            html_body=html,
                        )
                    except Exception:
                        logger.exception('Failed to send digest to %s', email)

        logger.info('Monthly voucher digest sent')
    except Exception:
        logger.exception('Failed to run monthly voucher digest')
```

- [ ] **Step 2: Add scheduled jobs to cleanup.py**

In `jarvis/tasks/cleanup.py`, add the following job registrations inside `start_scheduler()`, after existing jobs:

```python
# ── Voucher jobs ──────────────────────────────────

def _expire_vouchers():
    """Daily: expire active vouchers past their expiry date."""
    try:
        from accounting.vouchers.repositories import VoucherRepository
        count = VoucherRepository().expire_active()
        if count:
            logger.info('Expired %d voucher(s)', count)
    except Exception:
        logger.exception('Failed to run voucher expiry job')

def _voucher_expiry_warnings():
    """Daily: send 7-day expiry warnings to voucher issuers."""
    try:
        from datetime import date, timedelta
        from accounting.vouchers.repositories import VoucherRepository
        from core.services.notification_service import send_email

        target = date.today() + timedelta(days=7)
        vouchers = VoucherRepository().get_expiring_on(target)
        for v in vouchers:
            try:
                send_email(
                    to_email=v['issued_by_email'],
                    subject=f"Voucher {v['voucher_code']} expires in 7 days",
                    html_body=f"<p>Your voucher <strong>{v['voucher_code']}</strong> for client {v['client_name']} expires on {v['expires_at']}.</p>",
                )
            except Exception:
                logger.exception('Failed to send expiry warning for %s', v['voucher_code'])
        if vouchers:
            logger.info('Sent %d voucher expiry warning(s)', len(vouchers))
    except Exception:
        logger.exception('Failed to run voucher expiry warning job')

def _voucher_monthly_digest():
    """1st business day: send monthly voucher digest."""
    from datetime import date
    today = date.today()
    # Only run on first 3 days of month (covers weekends)
    if today.day > 3:
        return
    # Only run on weekdays
    if today.weekday() >= 5:
        return
    try:
        from accounting.vouchers.digest import send_monthly_digest
        send_monthly_digest()
    except Exception:
        logger.exception('Failed to run monthly voucher digest')

scheduler.add_job(
    _expire_vouchers,
    'cron',
    hour=0, minute=30,
    id='expire_vouchers',
    replace_existing=True,
    misfire_grace_time=300,
    coalesce=True,
)

scheduler.add_job(
    _voucher_expiry_warnings,
    'cron',
    hour=9, minute=0,
    id='voucher_expiry_warnings',
    replace_existing=True,
    misfire_grace_time=300,
    coalesce=True,
)

scheduler.add_job(
    _voucher_monthly_digest,
    'cron',
    hour=9, minute=15,
    day=1,
    id='voucher_monthly_digest',
    replace_existing=True,
    misfire_grace_time=3600,
    coalesce=True,
)
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/accounting/vouchers/digest.py jarvis/tasks/cleanup.py
git commit -m "feat(vouchers): add scheduled jobs — expiry, warnings, monthly digest"
```

---

## Phase 2 Test Gate

**Run the Flask dev server and test endpoints via curl:**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python app.py &
sleep 3

# Test: list vouchers (should return empty list)
curl -s -b cookies.txt http://localhost:5001/api/vouchers/my | python -m json.tool

# Test: accounting summary (should return zeros)
curl -s -b cookies.txt http://localhost:5001/api/vouchers/accounting | python -m json.tool

# Test: create voucher (need auth — will test after login)
# Test: PDF generation import
python -c "
from accounting.vouchers.pdf_generator import generate_voucher_pdf
pdf = generate_voucher_pdf({'voucher_code': 'VCH-202606-TEST01', 'client_name': 'Test', 'contract_number': 'C001', 'car_vin': 'WVWZZZ3CZWE123456', 'voucher_type': 'value', 'value_lei': 500, 'status': 'active', 'validity_months': 12, 'issued_at': '2026-06-22', 'expires_at': '2027-06-22', 'issued_by_name': 'Test User'})
print(f'PDF generated: {len(pdf)} bytes')
"

echo "Phase 2 PASSED"
```

---

## Phase 3: Frontend

### Task 9: Frontend Types + API Client

**Files:**
- Create: `jarvis/frontend/src/types/vouchers.ts`
- Create: `jarvis/frontend/src/api/vouchers.ts`

**Produces:** TypeScript types and API client for voucher endpoints

- [ ] **Step 1: Create types/vouchers.ts**

```typescript
export interface Voucher {
  id: number
  company_id: number
  voucher_code: string
  client_name: string
  contract_number: string
  car_vin: string
  validity_months: number
  expires_at: string | null
  issued_at: string | null
  issued_by_user_id: number
  issued_by_name: string | null
  voucher_type: 'value' | 'accessory_discount_code' | 'accessory_percentage' | 'service_items'
  value_lei: number | null
  discount_code: string | null
  discount_percentage: number | null
  service_items: string[] | null
  status: 'draft' | 'pending_approval' | 'approved' | 'active' | 'rejected' | 'redeemed' | 'expired'
  approver_user_id: number | null
  approver_name: string | null
  approval_request_id: number | null
  redeemed_at: string | null
  redeemed_by_user_id: number | null
  redeemed_by_name: string | null
  redemption_notes: string | null
  notes: string | null
  days_remaining: number | null
  benefit_display: string
  created_at: string
  updated_at: string
}

export interface VoucherCreatePayload {
  client_name: string
  contract_number: string
  car_vin: string
  validity_months: number
  voucher_type: string
  value_lei?: number | null
  discount_code?: string | null
  discount_percentage?: number | null
  service_items?: string[] | null
  approver_user_id?: number | null
  notes?: string | null
}

export interface VoucherSummary {
  active_count: number
  expiring_soon_count: number
  redeemed_this_month: number
  expired_count: number
  total_active_value: number
}

export interface AccountingListResponse {
  vouchers: Voucher[]
  summary: VoucherSummary
}
```

- [ ] **Step 2: Create api/vouchers.ts**

```typescript
import { api } from './client'
import type { Voucher, VoucherCreatePayload, AccountingListResponse } from '@/types/vouchers'

export const vouchersApi = {
  create: (data: VoucherCreatePayload) =>
    api.post<{ success: boolean; voucher: { id: number; voucher_code: string; status: string; approver_name: string } }>('/api/vouchers', data),

  list: (params?: Record<string, string>) =>
    api.get<Voucher[]>('/api/vouchers', params),

  getById: (id: number) =>
    api.get<Voucher>(`/api/vouchers/${id}`),

  myVouchers: (params?: Record<string, string>) =>
    api.get<Voucher[]>('/api/vouchers/my', params),

  accountingList: (params?: Record<string, string>) =>
    api.get<AccountingListResponse>('/api/vouchers/accounting', params),

  redeem: (id: number, notes?: string) =>
    api.patch<{ success: boolean; voucher: Voucher }>(`/api/vouchers/${id}/redeem`, { redemption_notes: notes }),

  pdfUrl: (id: number) => `/api/vouchers/${id}/pdf`,

  exportUrl: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return `/api/vouchers/export${qs}`
  },
}
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/types/vouchers.ts jarvis/frontend/src/api/vouchers.ts
git commit -m "feat(vouchers): add frontend TypeScript types and API client"
```

---

### Task 10: Voucher Issuance Form

**Files:**
- Create: `jarvis/frontend/src/pages/Accounting/Vouchers/NewVoucher.tsx`

**Consumes:** `vouchersApi.create()`, `useAuthStore`, Radix UI form components, `sonner` toast
**Produces:** Issuance form page component at `/app/accounting/vouchers/new`

- [ ] **Step 1: Create NewVoucher.tsx**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { vouchersApi } from '@/api/vouchers'
import { api } from '@/api/client'
import type { VoucherCreatePayload } from '@/types/vouchers'

const VALIDITY_OPTIONS = [
  { value: '1', label: '1 month' },
  { value: '3', label: '3 months' },
  { value: '6', label: '6 months' },
  { value: '12', label: '12 months' },
  { value: '24', label: '24 months' },
]

const TYPE_OPTIONS = [
  { value: 'value', label: 'Value (LEI)' },
  { value: 'accessory_discount_code', label: 'Accessory Discount Code' },
  { value: 'accessory_percentage', label: 'Accessory Percentage' },
  { value: 'service_items', label: 'Service Items' },
]

export default function NewVoucher() {
  const navigate = useNavigate()

  const [clientName, setClientName] = useState('')
  const [contractNumber, setContractNumber] = useState('')
  const [carVin, setCarVin] = useState('')
  const [validityMonths, setValidityMonths] = useState('12')
  const [voucherType, setVoucherType] = useState('value')
  const [valueLei, setValueLei] = useState('')
  const [discountCode, setDiscountCode] = useState('')
  const [discountPercentage, setDiscountPercentage] = useState('')
  const [serviceItems, setServiceItems] = useState('')
  const [approverUserId, setApproverUserId] = useState('')
  const [notes, setNotes] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => api.get<{ id: number; name: string }[]>('/api/users/list'),
    staleTime: 10 * 60_000,
  })

  const submitMutation = useMutation({
    mutationFn: (payload: VoucherCreatePayload) => vouchersApi.create(payload),
    onSuccess: (result) => {
      toast.success(
        `Voucher ${result.voucher.voucher_code} created — pending approval from ${result.voucher.approver_name}`
      )
      navigate('/app/accounting/vouchers')
    },
    onError: (error: unknown) => {
      const msg = error instanceof Error ? error.message : 'Failed to create voucher'
      toast.error(msg)
    },
  })

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!clientName.trim()) errs.clientName = 'Required'
    if (!contractNumber.trim()) errs.contractNumber = 'Required'
    const vin = carVin.trim().toUpperCase()
    if (!/^[A-Z0-9]{17}$/.test(vin)) errs.carVin = 'VIN must be exactly 17 alphanumeric characters'

    if (voucherType === 'value' && (!valueLei || parseFloat(valueLei) <= 0))
      errs.valueLei = 'Value must be greater than 0'
    if (voucherType === 'accessory_discount_code' && !discountCode.trim())
      errs.discountCode = 'Discount code is required'
    if (voucherType === 'accessory_percentage') {
      const pct = parseFloat(discountPercentage)
      if (isNaN(pct) || pct <= 0 || pct > 100)
        errs.discountPercentage = 'Must be between 0 and 100'
    }
    if (voucherType === 'service_items' && !serviceItems.trim())
      errs.serviceItems = 'At least one service item is required'

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return

    const payload: VoucherCreatePayload = {
      client_name: clientName.trim(),
      contract_number: contractNumber.trim(),
      car_vin: carVin.trim().toUpperCase(),
      validity_months: parseInt(validityMonths),
      voucher_type: voucherType,
    }

    if (voucherType === 'value') payload.value_lei = parseFloat(valueLei)
    if (voucherType === 'accessory_discount_code') payload.discount_code = discountCode.trim()
    if (voucherType === 'accessory_percentage') payload.discount_percentage = parseFloat(discountPercentage)
    if (voucherType === 'service_items')
      payload.service_items = serviceItems.split(',').map((s) => s.trim()).filter(Boolean)

    if (approverUserId) payload.approver_user_id = parseInt(approverUserId)
    if (notes.trim()) payload.notes = notes.trim()

    submitMutation.mutate(payload)
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">Issue Voucher</h1>
      </div>

      <div className="space-y-4 rounded-lg border p-6">
        {/* Client Name */}
        <div className="grid gap-1.5">
          <Label htmlFor="clientName">Client Name *</Label>
          <Input id="clientName" value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="Client name" />
          {errors.clientName && <p className="text-sm text-red-500">{errors.clientName}</p>}
        </div>

        {/* Contract Number */}
        <div className="grid gap-1.5">
          <Label htmlFor="contractNumber">Contract Number *</Label>
          <Input id="contractNumber" value={contractNumber} onChange={(e) => setContractNumber(e.target.value)} placeholder="Contract number" />
          {errors.contractNumber && <p className="text-sm text-red-500">{errors.contractNumber}</p>}
        </div>

        {/* Car VIN */}
        <div className="grid gap-1.5">
          <Label htmlFor="carVin">Car VIN *</Label>
          <Input id="carVin" value={carVin} onChange={(e) => setCarVin(e.target.value.toUpperCase())} placeholder="17-character VIN" maxLength={17} />
          {errors.carVin && <p className="text-sm text-red-500">{errors.carVin}</p>}
        </div>

        {/* Validity */}
        <div className="grid gap-1.5">
          <Label>Validity *</Label>
          <Select value={validityMonths} onValueChange={setValidityMonths}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {VALIDITY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Voucher Type */}
        <div className="grid gap-1.5">
          <Label>Voucher Type *</Label>
          <RadioGroup value={voucherType} onValueChange={setVoucherType} className="grid grid-cols-2 gap-2">
            {TYPE_OPTIONS.map((o) => (
              <div key={o.value} className="flex items-center space-x-2">
                <RadioGroupItem value={o.value} id={`type-${o.value}`} />
                <Label htmlFor={`type-${o.value}`} className="font-normal">{o.label}</Label>
              </div>
            ))}
          </RadioGroup>
        </div>

        {/* Conditional Fields */}
        {voucherType === 'value' && (
          <div className="grid gap-1.5">
            <Label htmlFor="valueLei">Value (LEI) *</Label>
            <Input id="valueLei" type="number" min="0" step="0.01" value={valueLei} onChange={(e) => setValueLei(e.target.value)} placeholder="0.00" />
            {errors.valueLei && <p className="text-sm text-red-500">{errors.valueLei}</p>}
          </div>
        )}

        {voucherType === 'accessory_discount_code' && (
          <div className="grid gap-1.5">
            <Label htmlFor="discountCode">Discount Code *</Label>
            <Input id="discountCode" value={discountCode} onChange={(e) => setDiscountCode(e.target.value)} placeholder="e.g. SUMMER2026" />
            {errors.discountCode && <p className="text-sm text-red-500">{errors.discountCode}</p>}
          </div>
        )}

        {voucherType === 'accessory_percentage' && (
          <div className="grid gap-1.5">
            <Label htmlFor="discountPercentage">Discount Percentage *</Label>
            <Input id="discountPercentage" type="number" min="0" max="100" step="0.01" value={discountPercentage} onChange={(e) => setDiscountPercentage(e.target.value)} placeholder="0 - 100" />
            {errors.discountPercentage && <p className="text-sm text-red-500">{errors.discountPercentage}</p>}
          </div>
        )}

        {voucherType === 'service_items' && (
          <div className="grid gap-1.5">
            <Label htmlFor="serviceItems">Service Items * (comma-separated)</Label>
            <Input id="serviceItems" value={serviceItems} onChange={(e) => setServiceItems(e.target.value)} placeholder="Oil change, Tire rotation, Brake inspection" />
            {errors.serviceItems && <p className="text-sm text-red-500">{errors.serviceItems}</p>}
          </div>
        )}

        {/* Approver Override */}
        <div className="grid gap-1.5">
          <Label>Approver (optional — leave empty for direct manager)</Label>
          <Select value={approverUserId} onValueChange={setApproverUserId}>
            <SelectTrigger><SelectValue placeholder="Direct manager" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="">Direct manager</SelectItem>
              {users.map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>{u.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Notes */}
        <div className="grid gap-1.5">
          <Label htmlFor="notes">Notes</Label>
          <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" />
        </div>

        {/* Submit */}
        <Button onClick={handleSubmit} disabled={submitMutation.isPending} className="w-full">
          {submitMutation.isPending ? 'Creating...' : 'Issue Voucher'}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/Vouchers/NewVoucher.tsx
git commit -m "feat(vouchers): add voucher issuance form component"
```

---

### Task 11: Accounting Voucher Tracking Page

**Files:**
- Create: `jarvis/frontend/src/pages/Accounting/Vouchers/index.tsx`

**Consumes:** `vouchersApi`, Radix UI table/dialog/select components
**Produces:** Accounting tracking page with summary, filters, table, redeem modal, CSV export

- [ ] **Step 1: Create Vouchers/index.tsx**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Download, FileText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { vouchersApi } from '@/api/vouchers'
import type { Voucher, VoucherSummary } from '@/types/vouchers'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  pending_approval: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  active: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={STATUS_COLORS[status] || ''}>
      {status.replace('_', ' ')}
    </Badge>
  )
}

function SummaryBar({ summary }: { summary: VoucherSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-green-600">{summary.active_count}</div>
        <div className="text-xs text-muted-foreground">Active</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-orange-500">{summary.expiring_soon_count}</div>
        <div className="text-xs text-muted-foreground">Expiring Soon</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-blue-600">{summary.redeemed_this_month}</div>
        <div className="text-xs text-muted-foreground">Redeemed (month)</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-red-500">{summary.expired_count}</div>
        <div className="text-xs text-muted-foreground">Expired</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold">{Number(summary.total_active_value).toLocaleString()} LEI</div>
        <div className="text-xs text-muted-foreground">Active Value</div>
      </div>
    </div>
  )
}

export default function Vouchers() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [statusFilter, setStatusFilter] = useState('__all__')
  const [typeFilter, setTypeFilter] = useState('__all__')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [redeemVoucher, setRedeemVoucher] = useState<Voucher | null>(null)
  const [redeemNotes, setRedeemNotes] = useState('')

  const [detailVoucher, setDetailVoucher] = useState<Voucher | null>(null)

  const buildParams = () => {
    const p: Record<string, string> = {}
    if (statusFilter !== '__all__') p.status = statusFilter
    if (typeFilter !== '__all__') p.voucher_type = typeFilter
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    return p
  }

  const { data, isLoading } = useQuery({
    queryKey: ['vouchers-accounting', statusFilter, typeFilter, dateFrom, dateTo],
    queryFn: () => vouchersApi.accountingList(buildParams()),
  })

  const vouchers = data?.vouchers ?? []
  const summary = data?.summary ?? { active_count: 0, expiring_soon_count: 0, redeemed_this_month: 0, expired_count: 0, total_active_value: 0 }

  const redeemMutation = useMutation({
    mutationFn: ({ id, notes }: { id: number; notes?: string }) => vouchersApi.redeem(id, notes),
    onSuccess: () => {
      toast.success('Voucher redeemed')
      setRedeemVoucher(null)
      setRedeemNotes('')
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to redeem')
    },
  })

  const getDaysLabel = (v: Voucher) => {
    if (v.days_remaining === null || v.days_remaining === undefined) return ''
    if (v.days_remaining <= 0) return 'Expired'
    return `${v.days_remaining}d`
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Voucher Tracking</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <a href={vouchersApi.exportUrl(buildParams())} download>
              <Download className="mr-1 h-4 w-4" />Export CSV
            </a>
          </Button>
          <Button size="sm" onClick={() => navigate('/app/accounting/vouchers/new')}>
            <Plus className="mr-1 h-4 w-4" />Issue Voucher
          </Button>
        </div>
      </div>

      <SummaryBar summary={summary} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="pending_approval">Pending</SelectItem>
            <SelectItem value="redeemed">Redeemed</SelectItem>
            <SelectItem value="expired">Expired</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Types</SelectItem>
            <SelectItem value="value">Value (LEI)</SelectItem>
            <SelectItem value="accessory_discount_code">Discount Code</SelectItem>
            <SelectItem value="accessory_percentage">Percentage</SelectItem>
            <SelectItem value="service_items">Service Items</SelectItem>
          </SelectContent>
        </Select>
        <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" placeholder="From" />
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" placeholder="To" />
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Issuer</TableHead>
              <TableHead>Client</TableHead>
              <TableHead>Contract</TableHead>
              <TableHead>VIN</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Benefit</TableHead>
              <TableHead>Issued</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={11} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : vouchers.length === 0 ? (
              <TableRow><TableCell colSpan={11} className="text-center py-8 text-muted-foreground">No vouchers found</TableCell></TableRow>
            ) : (
              vouchers.map((v) => (
                <TableRow key={v.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setDetailVoucher(v)}>
                  <TableCell className="font-mono text-xs">{v.voucher_code}</TableCell>
                  <TableCell>{v.issued_by_name}</TableCell>
                  <TableCell>{v.client_name}</TableCell>
                  <TableCell>{v.contract_number}</TableCell>
                  <TableCell className="font-mono text-xs">{v.car_vin}</TableCell>
                  <TableCell>{v.voucher_type.replace(/_/g, ' ')}</TableCell>
                  <TableCell>{v.benefit_display}</TableCell>
                  <TableCell>{v.issued_at || '—'}</TableCell>
                  <TableCell>
                    {v.expires_at || '—'}
                    {v.days_remaining !== null && v.days_remaining !== undefined && v.days_remaining <= 30 && v.days_remaining > 0 && (
                      <span className="ml-1 text-xs text-orange-500">({getDaysLabel(v)})</span>
                    )}
                  </TableCell>
                  <TableCell><StatusBadge status={v.status} /></TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {v.status === 'active' && (
                      <Button size="sm" variant="outline" onClick={() => { setRedeemVoucher(v); setRedeemNotes('') }}>
                        Redeem
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Redeem Modal */}
      <Dialog open={!!redeemVoucher} onOpenChange={() => setRedeemVoucher(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm Redemption</DialogTitle>
            <DialogDescription>
              Mark voucher <strong>{redeemVoucher?.voucher_code}</strong> as redeemed?
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-sm">
              <div>Client: <strong>{redeemVoucher?.client_name}</strong></div>
              <div>Benefit: <strong>{redeemVoucher?.benefit_display}</strong></div>
            </div>
            <div className="grid gap-1.5">
              <Label>Notes (optional)</Label>
              <Textarea value={redeemNotes} onChange={(e) => setRedeemNotes(e.target.value)} placeholder="Redemption notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRedeemVoucher(null)}>Cancel</Button>
            <Button onClick={() => redeemVoucher && redeemMutation.mutate({ id: redeemVoucher.id, notes: redeemNotes })} disabled={redeemMutation.isPending}>
              {redeemMutation.isPending ? 'Redeeming...' : 'Confirm Redeem'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Modal */}
      <Dialog open={!!detailVoucher} onOpenChange={() => setDetailVoucher(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Voucher Detail — {detailVoucher?.voucher_code}</DialogTitle>
          </DialogHeader>
          {detailVoucher && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Client:</span> {detailVoucher.client_name}</div>
                <div><span className="text-muted-foreground">Contract:</span> {detailVoucher.contract_number}</div>
                <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{detailVoucher.car_vin}</span></div>
                <div><span className="text-muted-foreground">Type:</span> {detailVoucher.voucher_type.replace(/_/g, ' ')}</div>
                <div><span className="text-muted-foreground">Benefit:</span> {detailVoucher.benefit_display}</div>
                <div><span className="text-muted-foreground">Validity:</span> {detailVoucher.validity_months} months</div>
                <div><span className="text-muted-foreground">Issued:</span> {detailVoucher.issued_at || '—'}</div>
                <div><span className="text-muted-foreground">Expires:</span> {detailVoucher.expires_at || '—'}</div>
                <div><span className="text-muted-foreground">Status:</span> <StatusBadge status={detailVoucher.status} /></div>
                <div><span className="text-muted-foreground">Issued by:</span> {detailVoucher.issued_by_name}</div>
                {detailVoucher.approver_name && <div><span className="text-muted-foreground">Approver:</span> {detailVoucher.approver_name}</div>}
                {detailVoucher.redeemed_by_name && <div><span className="text-muted-foreground">Redeemed by:</span> {detailVoucher.redeemed_by_name}</div>}
                {detailVoucher.redeemed_at && <div><span className="text-muted-foreground">Redeemed at:</span> {detailVoucher.redeemed_at}</div>}
              </div>
              {detailVoucher.notes && <div><span className="text-muted-foreground">Notes:</span> {detailVoucher.notes}</div>}
              {detailVoucher.redemption_notes && <div><span className="text-muted-foreground">Redemption notes:</span> {detailVoucher.redemption_notes}</div>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" asChild>
              <a href={vouchersApi.pdfUrl(detailVoucher?.id ?? 0)} download target="_blank" rel="noopener">
                <FileText className="mr-1 h-4 w-4" />Download PDF
              </a>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/Vouchers/index.tsx
git commit -m "feat(vouchers): add accounting voucher tracking page"
```

---

### Task 12: Profile — My Vouchers Tab

**Files:**
- Create: `jarvis/frontend/src/pages/Profile/VouchersPanel.tsx`
- Modify: `jarvis/frontend/src/pages/Profile/index.tsx` — add tab

**Consumes:** `vouchersApi.myVouchers()`, `vouchersApi.pdfUrl()`
**Produces:** "Vouchers" tab in user profile page

- [ ] **Step 1: Create VouchersPanel.tsx**

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { vouchersApi } from '@/api/vouchers'
import type { Voucher } from '@/types/vouchers'

const STATUS_COLORS: Record<string, string> = {
  pending_approval: 'bg-yellow-100 text-yellow-800',
  active: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
}

function expiringClass(v: Voucher): string {
  if (v.status !== 'active') return ''
  if (v.days_remaining !== null && v.days_remaining !== undefined && v.days_remaining <= 30)
    return 'bg-orange-50'
  return ''
}

export default function VouchersPanel() {
  const [selected, setSelected] = useState<Voucher | null>(null)

  const { data: vouchers = [], isLoading } = useQuery({
    queryKey: ['my-vouchers'],
    queryFn: () => vouchersApi.myVouchers(),
  })

  if (isLoading) return <div className="py-8 text-center text-muted-foreground">Loading...</div>
  if (vouchers.length === 0) return <div className="py-8 text-center text-muted-foreground">No vouchers issued yet.</div>

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Client</TableHead>
              <TableHead>Contract</TableHead>
              <TableHead>VIN</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Benefit</TableHead>
              <TableHead>Issued</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Days Left</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {vouchers.map((v) => (
              <TableRow key={v.id} className={`cursor-pointer hover:bg-muted/50 ${expiringClass(v)}`} onClick={() => setSelected(v)}>
                <TableCell className="font-mono text-xs">{v.voucher_code}</TableCell>
                <TableCell>{v.client_name}</TableCell>
                <TableCell>{v.contract_number}</TableCell>
                <TableCell className="font-mono text-xs">{v.car_vin}</TableCell>
                <TableCell>{v.voucher_type.replace(/_/g, ' ')}</TableCell>
                <TableCell>{v.benefit_display}</TableCell>
                <TableCell>{v.issued_at || '—'}</TableCell>
                <TableCell>{v.expires_at || '—'}</TableCell>
                <TableCell>
                  {v.days_remaining !== null && v.days_remaining !== undefined ? (
                    <span className={v.days_remaining <= 30 ? 'text-orange-500 font-medium' : ''}>{v.days_remaining}d</span>
                  ) : '—'}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={STATUS_COLORS[v.status] || ''}>{v.status.replace('_', ' ')}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{selected?.voucher_code}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Client:</span> {selected.client_name}</div>
                <div><span className="text-muted-foreground">Contract:</span> {selected.contract_number}</div>
                <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{selected.car_vin}</span></div>
                <div><span className="text-muted-foreground">Type:</span> {selected.voucher_type.replace(/_/g, ' ')}</div>
                <div><span className="text-muted-foreground">Benefit:</span> {selected.benefit_display}</div>
                <div><span className="text-muted-foreground">Validity:</span> {selected.validity_months} months</div>
                <div><span className="text-muted-foreground">Issued:</span> {selected.issued_at || '—'}</div>
                <div><span className="text-muted-foreground">Expires:</span> {selected.expires_at || '—'}</div>
                <div><span className="text-muted-foreground">Status:</span> <Badge variant="outline" className={STATUS_COLORS[selected.status] || ''}>{selected.status.replace('_', ' ')}</Badge></div>
              </div>
              {selected.notes && <div><span className="text-muted-foreground">Notes:</span> {selected.notes}</div>}
              {selected.redemption_notes && <div><span className="text-muted-foreground">Redemption notes:</span> {selected.redemption_notes}</div>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" asChild>
              <a href={vouchersApi.pdfUrl(selected?.id ?? 0)} download target="_blank" rel="noopener">
                <FileText className="mr-1 h-4 w-4" />Download PDF
              </a>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
```

- [ ] **Step 2: Add "Vouchers" tab to Profile/index.tsx**

Add to the Tab type union:
```typescript
type Tab = 'invoices' | 'hr-events' | 'pontaje' | 'team-pontaje' | 'sincron' | 'leave-permits' | 'activity' | 'vouchers'
```

Add to the tabs array (use `Ticket` icon from lucide-react):
```typescript
{ key: 'vouchers', label: 'Vouchers', icon: Ticket },
```

Add import at top:
```typescript
import { Ticket } from 'lucide-react'
```

Add lazy import for VouchersPanel:
```typescript
const VouchersPanel = lazy(() => import('./VouchersPanel'))
```

Add content rendering alongside other tab conditions:
```typescript
{activeTab === 'vouchers' && <Suspense fallback={<PageLoader />}><VouchersPanel /></Suspense>}
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/pages/Profile/VouchersPanel.tsx jarvis/frontend/src/pages/Profile/index.tsx
git commit -m "feat(vouchers): add My Vouchers tab to user profile"
```

---

### Task 13: App.tsx Routing

**Files:**
- Modify: `jarvis/frontend/src/App.tsx` — add lazy imports + routes

**Consumes:** `NewVoucher`, `Vouchers` page components
**Produces:** Routes at `/app/accounting/vouchers` and `/app/accounting/vouchers/new`

- [ ] **Step 1: Add lazy imports in App.tsx**

After existing accounting lazy imports:
```typescript
const VoucherTracking = lazy(() => import('./pages/Accounting/Vouchers'))
const VoucherNew = lazy(() => import('./pages/Accounting/Vouchers/NewVoucher'))
```

- [ ] **Step 2: Add routes in the accounting section**

After existing accounting routes (e.g., after the `accounting/controlling` routes):
```tsx
<Route path="accounting/vouchers" element={
  <Guard flag="can_access_accounting">
    <SuspensePage><VoucherTracking /></SuspensePage>
  </Guard>
} />
<Route path="accounting/vouchers/new" element={
  <SuspensePage><VoucherNew /></SuspensePage>
} />
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/App.tsx
git commit -m "feat(vouchers): add frontend routes in App.tsx"
```

---

## Phase 3 Test Gate

**Build frontend and verify no TypeScript/compile errors:**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis/frontend
npm run build
```

Expected: Build succeeds with no errors.

---

## Phase 4: Integration Test

### Task 14: Full Local Integration Test

**Test the complete flow locally:**

- [ ] **Step 1: Start local Flask server**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python app.py
```

- [ ] **Step 2: Test migration ran (table exists)**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis
python -c "
from core.database import get_db, release_db, get_cursor
conn = get_db()
cursor = get_cursor(conn)
cursor.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='vouchers' ORDER BY ordinal_position\")
cols = [r[0] for r in cursor.fetchall()]
print(f'Vouchers table columns ({len(cols)}):', cols)
release_db(conn)
"
```

- [ ] **Step 3: Test schema validation**

```bash
python -c "
from accounting.vouchers.schemas import VoucherCreate
# Happy path
v = VoucherCreate(client_name='Ion Popescu', contract_number='AW-2026-001', car_vin='WVWZZZ3CZWE123456', validity_months=12, voucher_type='value', value_lei=500)
print('OK:', v.model_dump())

# Sad paths
import sys
tests = [
    ('bad VIN', dict(client_name='X', contract_number='C', car_vin='SHORT', validity_months=12, voucher_type='value', value_lei=100)),
    ('wrong field', dict(client_name='X', contract_number='C', car_vin='WVWZZZ3CZWE123456', validity_months=12, voucher_type='value', discount_code='ABC')),
    ('missing value', dict(client_name='X', contract_number='C', car_vin='WVWZZZ3CZWE123456', validity_months=12, voucher_type='value')),
]
for name, data in tests:
    try:
        VoucherCreate(**data)
        print(f'FAIL: {name} should have raised')
        sys.exit(1)
    except Exception as e:
        print(f'OK ({name}): caught validation error')
print('All schema validations passed')
"
```

- [ ] **Step 4: Test PDF generation**

```bash
python -c "
from accounting.vouchers.pdf_generator import generate_voucher_pdf
pdf = generate_voucher_pdf({
    'voucher_code': 'VCH-202606-TESTPD',
    'client_name': 'Ion Popescu',
    'contract_number': 'AW-2026-001',
    'car_vin': 'WVWZZZ3CZWE123456',
    'voucher_type': 'value',
    'value_lei': 500,
    'status': 'active',
    'validity_months': 12,
    'issued_at': '2026-06-22',
    'expires_at': '2027-06-22',
    'issued_by_name': 'Sebastian Sabo',
})
with open('/tmp/test_voucher.pdf', 'wb') as f:
    f.write(pdf)
print(f'PDF generated: {len(pdf)} bytes → /tmp/test_voucher.pdf')
"
```

- [ ] **Step 5: Test digest builder**

```bash
python -c "
from accounting.vouchers.digest import build_digest_html
from datetime import date
html = build_digest_html(
    {'summary': {'active_count': 5, 'active_total_value': 2500, 'redeemed_last_month': 2, 'redeemed_last_month_value': 800, 'expired_last_month': 1, 'expiring_this_month': 3, 'new_last_month': 4}, 'per_user': [{'user_name': 'Test User', 'active_count': 3, 'active_value': 1500, 'redeemed_count': 1, 'expired_count': 0, 'pending_count': 1, 'expiring_this_month': 2}]},
    'AUTOWORLD S.R.L.',
    date.today()
)
print(f'Digest HTML generated: {len(html)} chars')
print('Contains table:', '<table' in html)
"
```

- [ ] **Step 6: Frontend build check**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis/frontend
npm run build
echo "Frontend build: $?"
```

- [ ] **Step 7: Final commit with all verified**

```bash
git add -A
git status
# If clean, no commit needed. If stragglers, commit them.
```
