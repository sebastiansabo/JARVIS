# Reports Module — Implementation Plan

**Date**: 2026-03-22
**Author**: Claude Code Analysis
**Status**: Planning document — no implementation until approved

---

## 1. Executive Summary

The Reports module will be a **read-only, cross-module reporting layer** that aggregates data from existing tables (invoices, allocations, CRM deals, marketing projects, HR events, approval requests) into unified API endpoints. It creates **zero new database tables** — all queries run against existing schemas.

Permissions already exist in `permissions_v2`:
- `accounting.reports.view` (scope-based)
- `accounting.reports.export` (non-scope-based)
- `marketing.report.view` (scope-based)

---

## 2. Prerequisites Confirmed

### 2.1 Files Read (Step 1 Compliance)

| # | File | Status | Key Takeaways |
|---|------|--------|---------------|
| 1 | `docs/CLAUDE.md` | ✅ Read | Golden rules, module boundaries, branch workflow, DB safety |
| 2 | `jarvis/migrations/domains/schema_*.py` | ✅ Read all 11 | Full DDL for every table; no `schema.sql` file exists |
| 3 | `jarvis/marketing/routes/projects.py` | ✅ Read | Blueprint pattern: `@marketing_bp.route`, `@mkt_permission_required`, `@handle_api_errors` |
| 4 | `jarvis/database.py` | ✅ Read (235 lines) | `get_db()`, `release_db()`, `get_db_connection()`, `get_cursor()`, `transaction()`, `dict_from_row()` |
| 5 | `jarvis/core/utils/api_helpers.py` | ✅ Read (177 lines) | `@v2_permission_required`, `@api_login_required`, `@handle_api_errors`, `error_response()`, `safe_error_response()` |
| 6 | `jarvis/marketing/__init__.py` + `jarvis/dms/__init__.py` | ✅ Read | Multi-file route pattern with `routes/` subdirectory |

### 2.2 Database Tables Confirmed (Step 2)

> **Note**: No `DATABASE_URL` available in this environment. All column names below are confirmed from the DDL in `jarvis/migrations/domains/schema_*.py` migration files.

#### Invoices & Allocations (from `schema_core.py`)
- **`invoices`** — id, supplier, invoice_number, invoice_date, invoice_value, currency, exchange_rate, value_ron, value_eur, vat_rate, net_value, subtract_vat, vat_rate_id, status, payment_status, company, brand, department, subdepartment, category, description, notes, created_by, created_at, updated_at, deleted_at
- **`allocations`** — id, invoice_id, org_unit_id, company, brand, department, subdepartment, allocation_percent, allocation_value, responsable, category, notes, created_at

#### Approval Requests (from `schema_approvals.py`)
```
approval_requests:
  id              SERIAL PRIMARY KEY
  entity_type     TEXT NOT NULL
  entity_id       INTEGER NOT NULL
  flow_id         INTEGER NOT NULL (FK → approval_flows)
  current_step_id INTEGER (FK → approval_steps)
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK IN ('pending','in_progress','approved','rejected',
                            'cancelled','expired','escalated','on_hold')
  context_snapshot JSONB DEFAULT '{}'
  requested_by    INTEGER NOT NULL (FK → users)
  requested_at    TIMESTAMP
  resolved_at     TIMESTAMP
  resolution_note TEXT
  priority        TEXT DEFAULT 'normal'
                  CHECK IN ('low','normal','high','urgent')
  due_by          TIMESTAMP
  created_at      TIMESTAMP
  updated_at      TIMESTAMP
```

#### Marketing Projects (from `schema_marketing.py`)
```
mkt_projects:
  id, name, slug, description, company_id (FK→companies), company_ids,
  brand_id (FK→brands), brand_ids, department_structure_id, department_ids,
  project_type (campaign|always_on|event|launch|branding|research),
  channel_mix, status (draft|pending_approval|approved|active|paused|
  completed|archived|cancelled), start_date, end_date, total_budget,
  currency, owner_id (FK→users), created_by (FK→users), objective,
  target_audience, brief, external_ref, metadata, created_at, updated_at,
  deleted_at

mkt_budget_lines:
  id, project_id, channel, description, department_structure_id, agency_name,
  planned_amount, approved_amount, spent_amount, currency, period_type,
  period_start, period_end, status, notes, metadata, created_at, updated_at

mkt_project_kpis:
  id, project_id, kpi_definition_id, channel, target_value, current_value,
  weight, threshold_warning, threshold_critical, currency, status
  (no_data|on_track|at_risk|behind|exceeded), last_synced_at, notes,
  show_on_overview, aggregation, created_at, updated_at
```

#### CRM (from `schema_crm.py`)
```
crm_deals:
  id, client_id, source (VARCHAR 5), dealer_code, dealer_name, branch,
  dossier_number, order_number, contract_date, order_date, delivery_date,
  invoice_date, registration_date, entry_date, brand, model_name, model_code,
  model_year, order_year, body_code, vin, engine_code, fuel_type, color,
  color_code, door_count, vehicle_type, list_price, purchase_price_net,
  sale_price_net, gross_profit, discount_value, other_costs, gw_gross_value,
  dossier_status, order_status, contract_status, sales_person, buyer_name,
  buyer_address, owner_name, owner_address, customer_group,
  registration_number, vehicle_specs, import_batch_id, source_row_hash,
  created_at, updated_at

crm_clients:
  id, display_name, name_normalized, client_type, phone, phone_raw, email,
  street, city, region, country, company_name, responsible, nr_reg,
  is_blacklisted, source_flags, merged_into_id, created_at, updated_at

crm_leads:
  id, client_id, contact_name, person_type, phone, email, lead_group,
  lead_text, lead_added_by, added_date, responsible, first_contact_date,
  responsible_assigned_date, lead_score, lead_status, status_reason,
  status_notes, status_date, next_contact, last_activity, sales_advisor,
  model, model_of_interest, utm_source, utm_medium, utm_campaign,
  utm_term, utm_content, form_type, form_data, import_batch_id,
  source_row_hash, created_at, updated_at
```

#### HR Events (from `schema_hr.py`)
```
hr.events:
  id, name, start_date, end_date, company, brand, company_id (FK→companies),
  description, created_by

hr.event_bonuses:
  id, user_id (FK→users), event_id (FK), year, month, participation_start,
  participation_end, bonus_days, hours_free, bonus_net, bonus_type_id (FK),
  details, allocation_month, created_by, created_at, updated_at
```

**No `vehicles`, `inventory`, or `listings` tables exist.** Vehicle/inventory data is stored in `crm_deals` (each deal = one vehicle sale).

---

## 3. Architecture Decisions

### 3.1 No New Tables Required

The Reports module is a **read-only aggregation layer**. All data already exists in:
- `invoices` + `allocations` → Accounting reports
- `mkt_projects` + `mkt_budget_lines` + `mkt_project_kpis` → Marketing reports
- `crm_deals` + `crm_clients` + `crm_leads` → CRM/Sales reports
- `approval_requests` + `approval_decisions` → Approval analytics
- `hr.events` + `hr.event_bonuses` → HR reports

No new tables. No migrations. No schema changes.

### 3.2 Module Location

```
jarvis/reports/                    # New top-level section (like crm/, marketing/)
├── __init__.py                    # reports_bp = Blueprint('reports', __name__)
├── routes/
│   ├── __init__.py                # Route sub-module imports
│   ├── accounting.py              # /reports/api/accounting/*
│   ├── marketing.py               # /reports/api/marketing/*
│   ├── crm.py                     # /reports/api/crm/*
│   ├── approvals.py               # /reports/api/approvals/*
│   └── export.py                  # /reports/api/export/* (CSV/Excel)
└── repositories/
    ├── __init__.py
    ├── accounting_report_repo.py  # Read-only queries against invoices/allocations
    ├── marketing_report_repo.py   # Read-only queries against mkt_* tables
    ├── crm_report_repo.py         # Read-only queries against crm_* tables
    └── approval_report_repo.py    # Read-only queries against approval_* tables
```

### 3.3 Why Top-Level (Not Under `core/` or `accounting/`)

- Reports span **multiple sections** (accounting, marketing, CRM, HR, approvals)
- Follows precedent: `crm/`, `marketing/`, `dms/` are all top-level
- `core/` is for shared infrastructure, not business modules
- `accounting/` would be too narrow — reports cover all modules

### 3.4 Blueprint Registration

In `jarvis/app.py`, add to `_register_blueprints()`:
```python
from reports import reports_bp
flask_app.register_blueprint(reports_bp, url_prefix='/reports')
```

This matches the pattern used by `marketing_bp` (url_prefix='/marketing'), `approvals_bp` (url_prefix='/approvals'), `dms_bp` (url_prefix='/dms').

---

## 4. Permission Model

### 4.1 Existing Permissions (Already Seeded)

| Permission Key | Scope-Based | Source |
|----------------|-------------|--------|
| `accounting.reports.view` | Yes | `schema_roles.py:245` |
| `accounting.reports.export` | No | `schema_roles.py:246` |
| `marketing.report.view` | Yes | `schema_marketing.py:387` |

### 4.2 Permission Decorator Pattern

```python
# jarvis/reports/routes/accounting.py
from core.utils.api_helpers import v2_permission_required

def reports_permission_required(entity, action):
    """Reports V2 permission check. Delegates to v2_permission_required."""
    return v2_permission_required('accounting', entity, action)

# Usage:
@reports_bp.route('/api/accounting/summary', methods=['GET'])
@login_required
@reports_permission_required('reports', 'view')
@handle_api_errors
def api_accounting_summary():
    scope = getattr(g, 'permission_scope', 'all')
    ...
```

For marketing reports:
```python
@reports_bp.route('/api/marketing/summary', methods=['GET'])
@login_required
@v2_permission_required('marketing', 'report', 'view')
@handle_api_errors
def api_marketing_summary():
    ...
```

### 4.3 Scope Filtering

When `g.permission_scope` is set:
- `'all'` → no filter (Admin sees everything)
- `'department'` → filter by user's company/brand/department
- `'own'` → filter by `created_by = current_user.id`

This matches the existing pattern in `marketing/routes/projects.py:54-60`.

---

## 5. API Endpoints

### 5.1 Accounting Reports

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/reports/api/accounting/summary` | `accounting.reports.view` | Totals by period (month/quarter/year) |
| GET | `/reports/api/accounting/by-company` | `accounting.reports.view` | Invoice totals grouped by company |
| GET | `/reports/api/accounting/by-department` | `accounting.reports.view` | Invoice totals grouped by department |
| GET | `/reports/api/accounting/by-supplier` | `accounting.reports.view` | Invoice totals grouped by supplier |
| GET | `/reports/api/accounting/by-status` | `accounting.reports.view` | Invoice counts/totals by status |
| GET | `/reports/api/accounting/trends` | `accounting.reports.view` | Monthly trend data for charting |

**Common query parameters**: `date_from`, `date_to`, `company_id`, `brand`, `department`, `currency`

### 5.2 Marketing Reports

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/reports/api/marketing/summary` | `marketing.report.view` | Project counts by status, total budget |
| GET | `/reports/api/marketing/budget-utilization` | `marketing.report.view` | Planned vs spent across projects |
| GET | `/reports/api/marketing/kpi-overview` | `marketing.report.view` | KPI status distribution |
| GET | `/reports/api/marketing/by-channel` | `marketing.report.view` | Budget/spend by channel |

### 5.3 CRM Reports

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/reports/api/crm/deal-summary` | `sales.module.access` | Deal counts/values by brand, period |
| GET | `/reports/api/crm/lead-funnel` | `sales.module.access` | Lead counts by status |
| GET | `/reports/api/crm/sales-by-person` | `sales.module.access` | Sales performance by salesperson |

### 5.4 Approval Reports

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/reports/api/approvals/summary` | `approvals.queue.access` | Request counts by status |
| GET | `/reports/api/approvals/turnaround` | `approvals.queue.access` | Average time from request to resolution |

### 5.5 Export

| Method | URL | Permission | Description |
|--------|-----|------------|-------------|
| GET | `/reports/api/export/accounting` | `accounting.reports.export` | CSV/Excel export of accounting data |
| GET | `/reports/api/export/marketing` | `marketing.report.view` | CSV/Excel export of marketing data |
| GET | `/reports/api/export/crm` | `sales.module.access` | CSV/Excel export of CRM data |

---

## 6. Repository Layer — Query Patterns

### 6.1 Base Class Usage

All repositories extend `BaseRepository` from `core/base_repository.py`:

```python
from core.base_repository import BaseRepository

class AccountingReportRepository(BaseRepository):
    def get_summary(self, filters):
        sql = '''
            SELECT
                DATE_TRUNC(%s, i.invoice_date) AS period,
                COUNT(*) AS invoice_count,
                SUM(i.value_ron) AS total_ron,
                SUM(i.value_eur) AS total_eur
            FROM invoices i
            WHERE i.deleted_at IS NULL
              AND i.invoice_date BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY 1
        '''
        return self.query_all(sql, (
            filters.get('group_by', 'month'),
            filters['date_from'],
            filters['date_to'],
        ))
```

### 6.2 Key Query Considerations

1. **Always exclude soft-deleted records**: `WHERE deleted_at IS NULL` (invoices, mkt_projects)
2. **Scope filtering**: Inject company/department/created_by WHERE clauses based on `g.permission_scope`
3. **Date range required**: All report queries must require `date_from` and `date_to` to prevent full table scans
4. **Use existing indexes**: All GROUP BY columns already have indexes (company, brand, status, dates)
5. **No JOINs to non-existent tables**: There are no `vehicles`/`inventory`/`listings` tables — vehicle data is in `crm_deals`

---

## 7. Integration Points (No Modifications Needed)

| Existing Component | Integration | Changes Required |
|--------------------|-------------|------------------|
| `permissions_v2` table | Already has `accounting.reports.*` and `marketing.report.*` | **None** |
| `BaseRepository` | Reports repos extend it | **None** |
| `v2_permission_required` decorator | Used in route decorators | **None** |
| `@login_required` | Standard Flask-Login | **None** |
| `@handle_api_errors` | Standard error wrapper | **None** |
| `get_json_or_error()` | Not needed (GET-only endpoints) | **None** |
| `init_schema.py` | No new tables to register | **None** |

The **only file that needs modification** is `jarvis/app.py` (add 3 lines for blueprint registration).

---

## 8. Implementation Order

### Phase 1: Foundation (files: 4)
1. `jarvis/reports/__init__.py` — Blueprint creation
2. `jarvis/reports/routes/__init__.py` — Route sub-module imports
3. `jarvis/reports/repositories/__init__.py` — Repository exports
4. `jarvis/app.py` — Blueprint registration (3 lines added)

### Phase 2: Accounting Reports (files: 2)
5. `jarvis/reports/repositories/accounting_report_repo.py` — Read-only queries
6. `jarvis/reports/routes/accounting.py` — 6 GET endpoints

### Phase 3: Marketing Reports (files: 2)
7. `jarvis/reports/repositories/marketing_report_repo.py` — Read-only queries
8. `jarvis/reports/routes/marketing.py` — 4 GET endpoints

### Phase 4: CRM Reports (files: 2)
9. `jarvis/reports/repositories/crm_report_repo.py` — Read-only queries
10. `jarvis/reports/routes/crm.py` — 3 GET endpoints

### Phase 5: Approval Reports (files: 2)
11. `jarvis/reports/repositories/approval_report_repo.py` — Read-only queries
12. `jarvis/reports/routes/approvals.py` — 2 GET endpoints

### Phase 6: Export (files: 1)
13. `jarvis/reports/routes/export.py` — CSV/Excel export endpoints

**Total new files**: 13
**Modified files**: 1 (`app.py`)
**New tables**: 0
**New migrations**: 0

---

## 9. Conflict Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Collision with existing routes | **None** | No `/reports/` prefix used by any existing blueprint |
| Table schema changes | **None** | Read-only queries, no ALTER/CREATE TABLE |
| Permission conflicts | **None** | Uses existing seeded permissions |
| Import path conflicts | **None** | `reports` package name unused in codebase |
| Blueprint name collision | **None** | `'reports'` not registered in `app.py` |

---

## 10. Testing Strategy

```python
# tests/test_reports.py
def test_accounting_summary_requires_auth(client):
    """GET /reports/api/accounting/summary returns 401 without login."""
    resp = client.get('/reports/api/accounting/summary')
    assert resp.status_code in (401, 302)

def test_accounting_summary_requires_permission(client, logged_in_user_no_perms):
    """GET /reports/api/accounting/summary returns 403 without permission."""
    resp = client.get('/reports/api/accounting/summary')
    assert resp.status_code == 403

def test_accounting_summary_returns_data(client, logged_in_admin):
    """GET /reports/api/accounting/summary returns JSON with totals."""
    resp = client.get('/reports/api/accounting/summary?date_from=2026-01-01&date_to=2026-03-31')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'data' in data or 'summary' in data
```

---

## 11. Open Questions for Review

1. **HR Reports**: Should HR bonus/event reports be included in Phase 1, or deferred? The `hr.module.view` permission already exists.
2. **Dashboard endpoint**: Should there be a single `/reports/api/dashboard` that returns a unified summary across all modules the user has access to?
3. **Caching**: Should report queries use `core/cache.py` in-memory caching for expensive aggregations?
4. **Frontend**: Will the React SPA consume these endpoints? If so, should route files also serve a Jinja2 template at `/reports/` (like `/statements/` does)?
