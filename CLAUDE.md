# J.A.R.V.I.S. - Enterprise Platform

## ⚠️ IMPORTANT: Branch Workflow

**DEFAULT BRANCH: `staging`** - All development work happens here first.

| Branch | Purpose | Deploy Target | Push Policy |
|--------|---------|---------------|-------------|
| `staging` | Development & testing | bugetare-staging app | Direct push OK |
| `main` | Production | bugetare app | **REQUIRES DOUBLE CONFIRMATION** |

### Workflow:
1. Work on `staging` branch
2. Test on staging app (bugetare-staging)
3. When ready for production: **Ask user for explicit confirmation TWICE before merging to main**

```bash
# Normal development
git checkout staging
git push origin staging

# Production deploy (REQUIRES DOUBLE CONFIRMATION)
git checkout main
git merge staging
git push origin main
```

## ⛔ CRITICAL: Protected Code Sections

**NEVER DELETE OR MODIFY** the following critical sections without explicit user confirmation:

### database.py - Protected Functions
These functions are **ESSENTIAL** for the application to work. Do NOT remove them:

```python
# e-Factura OAuth Token Functions (lines ~6444-6580)
- get_efactura_oauth_tokens(company_cif)    # Required for ANAF authentication
- save_efactura_oauth_tokens(company_cif, tokens)  # Required for ANAF authentication
- delete_efactura_oauth_tokens(company_cif)  # Required for ANAF authentication
- get_efactura_oauth_status(company_cif)     # Required for ANAF authentication
```

### database.py - Protected Table Definitions in init_db()
These CREATE TABLE statements are **ESSENTIAL**. Do NOT remove them:

```sql
-- e-Factura Connector Tables (lines ~1730-2050)
- efactura_company_connections
- efactura_invoices (with all migrations: ignored, deleted_at, overrides)
- efactura_invoice_refs
- efactura_invoice_artifacts
- efactura_sync_runs
- efactura_sync_errors
- efactura_oauth_tokens
- efactura_partner_types
- efactura_supplier_mappings
- efactura_supplier_mapping_types (junction table)
```

### Before Removing Any Code
1. **Search for usages**: `grep -r "function_name" jarvis/`
2. **Check imports**: Look for `from database import function_name`
3. **Verify no dependencies**: Ensure no other code relies on the function
4. **Ask user**: "This function appears to be used by X. Should I still remove it?"

### Recovery Procedure
If critical functions are accidentally removed:
1. Check git history: `git log --oneline --all -S "function_name"`
2. Find the last commit with the function: `git show <commit>:jarvis/database.py | grep -A50 "def function_name"`
3. Restore from that commit

## Project Overview
J.A.R.V.I.S. is a modular enterprise platform with multiple sections:
- **Accounting** → Bugetare (Invoice Budget Allocation), Statements (Bank Statement Parsing), e-Factura (ANAF Invoice Import)
- **HR** → Events (Employee Event Bonus Management)
- **Core Connectors** → e-Factura (ANAF RO e-Invoicing integration)
- **Future**: AFS, Sales, etc.

## Tech Stack
- **Backend**: Flask + Gunicorn
- **Database**: PostgreSQL (required)
- **AI**: Anthropic Claude API for invoice parsing
- **Storage**: Google Drive integration for invoice uploads
- **Deployment**: DigitalOcean App Platform via Docker

## Project Structure
```
jarvis/                           # Main application folder
├── app.py                        # Main Flask application
├── database.py                   # Database operations (PostgreSQL)
├── models.py                     # Data models and structure loading
├── services.py                   # Company VAT matching utilities
│
├── core/                         # Core Platform (shared across sections)
│   ├── __init__.py
│   ├── database.py               # Base DB connection pool
│   ├── config.py                 # Configuration settings
│   ├── auth/                     # Authentication module
│   │   ├── __init__.py
│   │   ├── models.py             # User model (Flask-Login)
│   │   ├── routes.py             # Auth blueprint routes (not registered - routes in app.py)
│   │   ├── repositories/
│   │   │   ├── user_repository.py    # User + password reset token CRUD
│   │   │   └── event_repository.py   # Audit event logging
│   │   └── services/
│   │       └── auth_service.py       # Auth business logic + password reset
│   ├── services/                 # Shared services
│   │   ├── drive_service.py      # Google Drive integration
│   │   ├── notification_service.py # SMTP email notifications
│   │   ├── image_compressor.py   # TinyPNG compression
│   │   └── currency_converter.py # BNR exchange rates
│   ├── settings/                 # Platform settings
│   │   ├── __init__.py
│   │   └── routes.py             # Settings routes
│   ├── connectors/               # External service connectors
│   │   └── efactura/             # ANAF e-Factura connector
│   │       ├── __init__.py       # Blueprint registration
│   │       ├── routes.py         # API endpoints
│   │       ├── anaf_client.py    # ANAF API client (OAuth/X.509)
│   │       ├── xml_parser.py     # UBL 2.1 XML parser
│   │       ├── models.py         # ParsedInvoice, InvoiceLineItem
│   │       ├── mock_client.py    # Development mock client
│   │       └── repositories/
│   │           └── invoice_repo.py  # Database operations
│   └── utils/
│       └── logging_config.py     # Structured logging
│
├── accounting/                   # Accounting Section
│   ├── __init__.py               # Section blueprint
│   ├── bugetare/                 # Bugetare App
│   │   ├── __init__.py           # App blueprint
│   │   ├── routes.py             # Invoice routes
│   │   ├── invoice_parser.py     # AI invoice parsing
│   │   └── bulk_processor.py     # Bulk processing
│   └── statements/               # Bank Statement Parsing App
│       ├── __init__.py           # App blueprint
│       ├── routes.py             # Statement API routes
│       ├── parser.py             # PDF parsing logic
│       ├── vendors.py            # Vendor pattern matching
│       └── database.py           # Statement DB functions
│
├── hr/                           # HR Section
│   ├── __init__.py               # Section blueprint
│   └── events/                   # Events App
│       ├── __init__.py           # App blueprint
│       ├── routes.py             # HR routes
│       └── database.py           # HR database functions
│
├── static/                       # Static assets
│   ├── css/
│   ├── js/
│   └── img/
│
└── templates/                    # Jinja2 templates
    ├── core/                     # Core templates
    │   ├── login.html
    │   ├── forgot_password.html  # Password reset request
    │   ├── reset_password.html   # Set new password
    │   ├── settings.html
    │   ├── apps.html
    │   └── guide.html
    ├── accounting/
    │   ├── bugetare/
    │   │   ├── index.html        # Add Invoice
    │   │   ├── accounting.html   # Dashboard
    │   │   ├── templates.html    # Template management
    │   │   ├── bulk.html         # Bulk processing
    │   │   └── efactura.html     # e-Factura unallocated invoices
    │   └── statements/
    │       └── index.html        # Bank statement upload & review
    └── hr/
        └── events/
            ├── event_bonuses.html
            ├── events.html
            └── employees.html
```

## URL Structure
| URL | Section | App | Page |
|-----|---------|-----|------|
| `/` | Core | - | Apps landing |
| `/login` | Core | Auth | Login |
| `/forgot-password` | Core | Auth | Request password reset |
| `/reset-password/<token>` | Core | Auth | Set new password |
| `/settings` | Core | Settings | Platform settings |
| `/add-invoice` | Accounting | Bugetare | Add invoice |
| `/accounting` | Accounting | Bugetare | Dashboard |
| `/templates` | Accounting | Bugetare | Templates |
| `/bulk` | Accounting | Bugetare | Bulk processor |
| `/accounting/efactura` | Accounting | e-Factura | Unallocated invoices |
| `/statements/` | Accounting | Statements | Bank statement upload |
| `/statements/mappings` | Accounting | Statements | Vendor mappings |
| `/hr/events/` | HR | Events | Event bonuses |
| `/hr/events/events` | HR | Events | Events list |
| `/hr/events/employees` | HR | Events | Employees |

## HR Module API Routes

The HR Events module uses nested blueprints with the following API structure:

| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/hr/events/api/employees` | List/create employees |
| GET/PUT/DELETE | `/hr/events/api/employees/<id>` | Get/update/delete employee |
| GET | `/hr/events/api/employees/search?q=` | Search employees |
| GET/POST | `/hr/events/api/events` | List/create events |
| GET/PUT/DELETE | `/hr/events/api/events/<id>` | Get/update/delete event |
| GET/POST | `/hr/events/api/event-bonuses` | List/create bonuses |
| POST | `/hr/events/api/event-bonuses/bulk` | Bulk create bonuses |
| GET/PUT/DELETE | `/hr/events/api/event-bonuses/<id>` | Get/update/delete bonus |
| GET | `/hr/events/api/export` | Export bonuses to Excel |
| GET | `/hr/events/api/structure/brands/<company>` | Get brands for company |

**Important**: HR templates use direct API paths (e.g., `/hr/events/api/employees/1`) rather than `url_for()` + relative paths to avoid nested URL issues with Flask blueprints.

## Key Commands

### Local Development
```bash
source venv/bin/activate
DATABASE_URL='postgresql://sebastiansabo@localhost:5432/defaultdb' PORT=5001 python jarvis/app.py
```

### Database
- PostgreSQL connection via `DATABASE_URL` environment variable (required)
- Tables auto-initialize on first run with seed data

### Docker Build
```bash
docker build -t bugetare .
docker run -p 8080:8080 -e DATABASE_URL="..." -e ANTHROPIC_API_KEY="..." bugetare
```

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string (required)
- `ANTHROPIC_API_KEY` - Claude API key for invoice parsing (stored in ~/.zshrc)
- `GOOGLE_CREDENTIALS_JSON` - Google Drive API credentials (service account)
- `GOOGLE_OAUTH_TOKEN` - Base64-encoded OAuth token for Google Drive (production)
- `TINYPNG_API_KEY` - TinyPNG API key for image compression (optional, has default)
- `EFACTURA_MOCK_MODE` - Set to `true` for development without ANAF certificate
- `PERF_MONITOR` - Set to `true` to enable performance monitoring (logs slow requests)
- `PERF_MONITOR_MIN_MS` - Minimum request duration (ms) to log (default: 100)

## Database Schema

### Unified Organizational Structure
The platform uses a normalized organizational hierarchy with foreign key references:

```
┌─────────────────────────────────────────────────────────────┐
│                      companies                               │
│  id | company                        | vat                   │
│  (Master table for all company names)                        │
└───────────────────────────┬─────────────────────────────────┘
                            │ company_id (FK)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 department_structure                         │
│  id | company_id | company | brand | department | subdept   │
│  (Single source of truth for org hierarchy)                  │
└───────────────────────────┬─────────────────────────────────┘
                            │ org_unit_id (FK)
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
    ┌────────────┐   ┌─────────────┐  ┌──────────────┐
    │allocations │   │responsables │  │hr.employees  │
    │(260 rows)  │   │(125 rows)   │  │(113 rows)    │
    └────────────┘   └─────────────┘  └──────────────┘
```

### Public Schema (Accounting)
- `companies` - Company registry (id, company, vat, brands) - **Master table**
- `department_structure` - Organizational hierarchy with company_id FK
  - id, company_id (FK), company, brand, department, subdepartment, manager, marketing, cc_email
- `invoices` - Invoice header records (includes subtract_vat, vat_rate_id, net_value)
- `allocations` - Department allocation splits with org_unit_id FK
- `responsables` - Employee records with org_unit_id FK
- `reinvoice_destinations` - Reinvoicing targets with org_unit_id FK
- `invoice_templates` - AI parsing templates per supplier
- `users` - Application users with bcrypt passwords and role permissions
- `user_events` - Activity log for user actions (login, invoice operations)
- `password_reset_tokens` - Time-limited tokens for self-service password reset (1-hour expiry, single-use)
- `vat_rates` - VAT rate definitions (id, name, rate)
- `dropdown_options` - Configurable dropdown options (invoice_status, payment_status)
  - id, dropdown_type, value, label, color, opacity, sort_order, is_active, min_role
  - `min_role` controls which user roles can set invoices to this status
- `connectors` - External service connectors (Google Ads, Anthropic) - DISABLED
- `vendor_mappings` - Regex patterns to match bank transactions to suppliers
- `bank_statement_transactions` - Parsed transactions from bank statements
- `efactura_invoices` - e-Factura invoices imported from ANAF (jarvis_invoice_id links to invoices table)

### HR Schema (`hr.`)
The HR module uses a separate PostgreSQL schema for data isolation:

- `hr.employees` - Employee records with org_unit_id FK to department_structure
  - id, name, department, brand, company, org_unit_id (FK), user_id (FK to users), is_active
- `hr.events` - Event definitions with company_id FK to companies
  - id, name, start_date, end_date, company, brand, company_id (FK), description, created_by
- `hr.event_bonuses` - Individual bonus records per employee/event
  - id, employee_id (FK), event_id (FK), year, month, participation_start, participation_end
  - bonus_days, hours_free, bonus_net, bonus_type_id (FK), details, allocation_month, created_by, created_at, updated_at
- `hr.event_bonus_types` - Bonus type definitions (amount per day/period)
  - id, name, amount, days_per_amount, is_active

**Note**: HR schema auto-creates on app startup via `init_db()` in `jarvis/database.py`

### Foreign Key Relationships
| Table | Column | References |
|-------|--------|------------|
| department_structure | company_id | companies.id |
| allocations | org_unit_id | department_structure.id |
| responsables | org_unit_id | department_structure.id |
| reinvoice_destinations | org_unit_id | department_structure.id |
| hr.employees | org_unit_id | department_structure.id |
| hr.events | company_id | companies.id |
| efactura_invoices | jarvis_invoice_id | invoices.id |

## Bank Statement Module

### Overview
The Statements module (`jarvis/accounting/statements/`) parses UniCredit bank statement PDFs, extracts card transactions, matches them to known vendors, and generates invoice records.

### API Routes

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/statements/` | Statement upload page |
| POST | `/statements/api/upload` | Upload & parse statement PDFs |
| GET | `/statements/api/transactions` | List transactions (with filters) |
| PUT | `/statements/api/transactions/<id>` | Update transaction |
| POST | `/statements/api/transactions/bulk-ignore` | Bulk ignore transactions |
| POST | `/statements/api/create-invoices` | Generate invoices from transactions |
| GET | `/statements/api/mappings` | List vendor mappings |
| POST | `/statements/api/mappings` | Create vendor mapping |
| PUT | `/statements/api/mappings/<id>` | Update vendor mapping |
| DELETE | `/statements/api/mappings/<id>` | Delete vendor mapping |
| GET | `/statements/api/summary` | Transaction statistics |

### Vendor Mappings
Vendor mappings use regex patterns to match bank transaction descriptions to suppliers:

| Pattern | Supplier | Notes |
|---------|----------|-------|
| `FACEBK\s*\*` | Meta | Facebook/Instagram Ads |
| `GOOGLE\s*\*\s*ADS` | Google Ads | Advertising |
| `GOOGLE\s*CLOUD` | Google Cloud | Infrastructure |
| `CLAUDE\.AI` | Anthropic | AI subscription |
| `OPENAI\s*\*\s*CHATGPT` | OpenAI | AI subscription |
| `DIGITALOCEAN` | DigitalOcean | Infrastructure |
| `DREAMSTIME` | Dreamstime | Stock photos |
| `SHOPIFY\s*\*` | Shopify | E-commerce |

### Transaction Status
- `pending` - Newly parsed, awaiting review
- `matched` - Vendor matched via pattern
- `ignored` - Excluded (internal transfers, etc.)
- `invoiced` - Invoice record created

### Workflow
1. Upload UniCredit PDF statements
2. Parser extracts transactions (date, amount, description)
3. Vendor matching identifies known suppliers
4. Internal transfers auto-ignored ("alim card")
5. Review transactions, add mappings for unmatched vendors
6. Select matched transactions → Create invoices

## e-Factura Connector

### Overview
The e-Factura connector (`jarvis/core/connectors/efactura/`) integrates with ANAF's RO e-Invoicing system to fetch invoices automatically and send them to the JARVIS Invoice Module for allocation.

### Architecture
```
ANAF SPV API ──────┐
(X.509 Auth)       │
                   ▼
            ┌──────────────┐
            │ ANAF Client  │  anaf_client.py / mock_client.py
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │  XML Parser  │  xml_parser.py (UBL 2.1)
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │   Database   │  efactura_invoices table
            └──────┬───────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
Unallocated    View Details   Export PDF
Page           (JSON)         (ANAF API)
```

### API Routes

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/efactura/` | Connector settings page |
| POST | `/efactura/api/import` | Import invoices from ANAF |
| GET | `/efactura/api/invoices/unallocated` | List unallocated invoices |
| GET | `/efactura/api/invoices/unallocated/count` | Count for badge |
| POST | `/efactura/api/invoices/send-to-module` | Send to Invoice Module |
| GET | `/efactura/api/invoices/<id>/pdf` | Export PDF from XML |
| GET | `/efactura/api/messages` | List ANAF messages (SPV inbox) |
| PUT | `/efactura/api/invoices/<id>/overrides` | Update invoice overrides (type, department, subdepartment) |
| PUT | `/efactura/api/invoices/bulk-overrides` | Bulk update overrides for multiple invoices |
| GET | `/efactura/api/supplier-mappings` | List supplier mappings with types |
| POST | `/efactura/api/supplier-mappings` | Create supplier mapping |
| PUT | `/efactura/api/supplier-mappings/<id>` | Update supplier mapping |
| DELETE | `/efactura/api/supplier-mappings/<id>` | Delete supplier mapping |
| GET | `/efactura/api/partner-types` | List partner types (Service, Merchandise) |
| GET | `/efactura/oauth/status?cif=X` | Get OAuth authentication status for company |
| POST | `/efactura/oauth/refresh` | Manually refresh OAuth access token |
| POST | `/efactura/oauth/revoke` | Revoke OAuth tokens (disconnect company) |

### OAuth Token Functions (database.py) ⚠️ CRITICAL

These functions manage ANAF OAuth authentication. **DO NOT DELETE**:

| Function | Purpose |
|----------|---------|
| `get_efactura_oauth_tokens(cif)` | Get OAuth tokens from `connectors` table |
| `save_efactura_oauth_tokens(cif, tokens)` | Save/update tokens (creates connector if needed) |
| `delete_efactura_oauth_tokens(cif)` | Remove tokens, set connector status to disconnected |
| `get_efactura_oauth_status(cif)` | Get auth status (authenticated, expires_at, is_expired) |

**Storage**: Tokens are stored in the `connectors` table with `connector_type = 'efactura'` and `name = company_cif`. The `credentials` JSONB column contains:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": "2026-04-30T12:00:00",
  "token_type": "Bearer"
}
```

### Database Table (`efactura_invoices`)

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| anaf_message_id | VARCHAR(100) | ANAF message ID (unique) |
| upload_index | INTEGER | Index in ZIP file |
| invoice_number | VARCHAR(100) | Invoice number |
| issue_date | DATE | Issue date |
| due_date | DATE | Due date |
| seller_name | VARCHAR(255) | Supplier name |
| seller_cif | VARCHAR(50) | Supplier VAT |
| buyer_name | VARCHAR(255) | Customer name |
| buyer_cif | VARCHAR(50) | Customer VAT |
| total_amount | DECIMAL(15,2) | Total with VAT |
| total_vat | DECIMAL(15,2) | VAT amount |
| currency | VARCHAR(10) | Currency code |
| direction | VARCHAR(10) | 'inbound' or 'outbound' |
| xml_content | TEXT | Stored XML for PDF generation |
| jarvis_invoice_id | INTEGER | FK to invoices table (NULL = unallocated) |
| type_override | TEXT | Invoice-level type override (comma-separated type IDs) |
| department_override | VARCHAR(255) | Invoice-level department override |
| subdepartment_override | VARCHAR(255) | Invoice-level subdepartment override |
| created_at | TIMESTAMP | Import timestamp |

### Database Table (`efactura_supplier_mappings`)

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| seller_cif | VARCHAR(50) | Supplier VAT (unique) |
| seller_name | VARCHAR(255) | Supplier name |
| type_ids | TEXT | Comma-separated partner type IDs (e.g., "1,2") |
| department | VARCHAR(255) | Default department for this supplier |
| subdepartment | VARCHAR(255) | Default subdepartment for this supplier |
| created_at | TIMESTAMP | Creation timestamp |

### Database Table (`efactura_partner_types`)

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| name | VARCHAR(100) | Type name (e.g., "Service", "Merchandise") |
| description | TEXT | Optional description |
| is_active | BOOLEAN | Whether type is active (default true) |
| hide_in_filter | BOOLEAN | When true, invoices with this type are hidden by "Hide Typed" filter (default true) |

### Database Indexes (Performance)
Trigram indexes (pg_trgm) for faster ILIKE text searches:

| Table | Column | Index Name |
|-------|--------|------------|
| efactura_invoices | partner_name | idx_efactura_invoices_partner_name_trgm |
| efactura_invoices | partner_cif | idx_efactura_invoices_partner_cif_trgm |
| efactura_invoices | invoice_number | idx_efactura_invoices_invoice_number_trgm |
| efactura_supplier_mappings | partner_name | idx_efactura_mappings_partner_name_trgm |
| efactura_supplier_mappings | supplier_name | idx_efactura_mappings_supplier_name_trgm |
| efactura_supplier_mappings | partner_cif | idx_efactura_mappings_partner_cif_trgm |

These GIN indexes use the `pg_trgm` extension and significantly speed up search queries with ILIKE patterns.

### Unique Constraints
| Table | Constraint | Description |
|-------|------------|-------------|
| efactura_supplier_mappings | idx_efactura_supplier_mappings_partner_name_unique | Case-insensitive unique on `LOWER(partner_name)` WHERE `is_active = TRUE` - prevents duplicate supplier mappings |

### XML Parser (`xml_parser.py`)
Parses UBL 2.1 e-Factura XML documents:
- Extracts seller/buyer info (name, CIF, address)
- Extracts amounts (total, VAT, net)
- Extracts payment terms and bank account
- Parses line items with quantities and unit prices
- Handles VAT breakdown by rate

### Mock Client
For development without ANAF certificate:
- Set `EFACTURA_MOCK_MODE=true` in environment
- Returns simulated messages and invoices
- Allows testing full workflow without API access

### Accounting Module Integration
The Unallocated Invoices page (`/accounting/efactura`):
- Shows e-Factura invoices not yet sent to Invoice Module
- Filters: Company, Direction (Inbound/Outbound), Date range, Search
- Bulk selection with "Send to Invoices" action
- Individual actions: Send to Invoices, View Details, Export PDF
- Badge in accounting navigation shows unallocated count

### Workflow
1. **Import from ANAF**: Fetch messages from SPV inbox
2. **Parse XML**: Extract invoice data using UBL 2.1 parser
3. **Store**: Save to `efactura_invoices` table with XML content
4. **Detect Duplicates**: Background check for existing invoices (exact + AI matching)
5. **Review**: View unallocated invoices in `/accounting/efactura`
6. **Send to Module**: Create record in main `invoices` table
7. **Mark Allocated**: Set `jarvis_invoice_id` to link records

### Duplicate Detection
Automatic detection of duplicate invoices after ANAF sync:

**Two-Layer Detection:**
1. **Exact Matching**: Finds duplicates by supplier name + invoice number (case-insensitive)
2. **AI Fallback (Claude)**: Fuzzy matching for similar supplier names and amounts
   - Pre-filters by amount similarity (within 5%)
   - Pre-filters by supplier name similarity (>50% using SequenceMatcher)
   - AI analyzes candidates with confidence threshold (70%)

**API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/efactura/api/invoices/duplicates` | GET | Detect exact duplicates |
| `/efactura/api/invoices/mark-duplicates` | POST | Mark exact duplicates |
| `/efactura/api/invoices/duplicates/ai` | GET | Detect AI fuzzy duplicates |
| `/efactura/api/invoices/mark-duplicates/ai` | POST | Mark AI duplicates with explicit mappings |

**UI Features:**
- Yellow banner appears when duplicates detected after sync
- "View" button shows detailed list (exact vs AI-detected sections)
- "Mark All as Duplicates" links e-Factura invoices to existing `jarvis_invoice_id`
- Duplicates automatically removed from Unallocated tab

**Send to Module Enhancements:**
- Duplicate prevention: Checks before INSERT, skips if exists
- Status set to "Nebugetata" for all imported invoices
- Net value and VAT calculations preserved from e-Factura
- PDF link points to `/efactura/api/invoices/{id}/pdf`

### Supplier Mappings
Supplier mappings define default categorization for invoices from specific suppliers:

**Features:**
- **Partner Types**: Multi-select types (Service, Merchandise) per supplier
- **Default Department**: Pre-set department for new invoices from this supplier
- **Default Subdepartment**: Pre-set subdepartment (filtered by department from `department_structure`)

**Workflow:**
1. When an invoice is imported, system looks for a mapping by `seller_cif`
2. If found, the mapping's types/department/subdepartment become defaults
3. Defaults appear in Unallocated list columns (Type, Department, Subdepartment)
4. Users can override defaults at the invoice level without changing the mapping

**Subdepartment Filtering:**
- Subdepartment dropdown only shows options that exist for the selected department
- Data comes from `department_structure` table (same as company org hierarchy)
- If a department has no subdepartments in the structure, the dropdown is disabled

### Invoice Overrides
Individual invoices can have overrides that take precedence over supplier mapping defaults:

**Override Fields:**
- `type_override` - Comma-separated type IDs (e.g., "1,2" for Service + Merchandise)
- `department_override` - Department name
- `subdepartment_override` - Subdepartment name (filtered by department)

**Display Logic:**
- If invoice has override → show override value
- Else if supplier mapping exists → show mapping default
- Else → show empty

**Edit Modal:**
- Click edit icon on invoice row to open override modal
- Shows current values (from override or mapping default)
- Subdepartment dropdown filters based on selected department
- Changes only affect the individual invoice, not the supplier mapping

**Bulk Override:**
- Select multiple invoices in Unallocated tab
- Click "Set Type" dropdown → select type(s)
- All selected invoices get the same type override

### "Hide Typed" Filter
Toggle switch to filter out invoices that have partner types with `hide_in_filter=TRUE`:

**Configuration:**
- Located next to search field in Unallocated tab
- Server-side filtering (works across all pages, not just visible rows)
- State persisted in localStorage as `efacturaHideTyped`
- Each partner type has a configurable `hide_in_filter` setting (default: true)

**Partner Type Settings:**
- Configure in **Settings → Connectors → Partner Types** or **Connector Settings → Partner Types tab**
- Toggle "Hide in Filter" per type to control visibility behavior
- Types with `hide_in_filter=FALSE` remain visible even when "Hide Typed" is ON

**Use Case:**
- Focus on unclassified invoices that need attention
- Quickly identify invoices without partner type assignment
- Customize which types should be hidden (e.g., hide Service but show Merchandise)

### Column Configuration Versioning
The e-Factura page uses versioned column configurations to handle schema changes:

**How it works:**
- `COLUMN_CONFIG_VERSION` constant tracks schema version
- When new columns are added, version is bumped
- If user's saved config version differs, config resets to defaults
- Prevents column mixing when new columns are added

**Storage:**
- `efacturaColumnConfig` - Column visibility and order
- `efacturaColumnConfigVersion` - Version number for migration

## Deployment
Configured via `.do/app.yaml` for DigitalOcean App Platform with auto-deploy on push to main branch.

## Invoice Parsing System

### Two Parsing Modes
1. **AI Parsing** (default fallback): Uses Claude claude-sonnet-4-20250514 vision to extract invoice data from PDFs/images
2. **Template-based Parsing**: Uses regex patterns for faster, consistent extraction from known suppliers

### Template Structure (`invoice_templates` table)
Templates define how to extract data from invoices:
- `name` - Template identifier (e.g., "Meta", "Google Ads")
- `template_type` - "fixed" (static supplier info) or "format" (extract supplier via regex)
- `supplier` / `supplier_vat` - Fixed supplier information
- `customer_vat` - Fixed customer VAT (optional)
- `customer_vat_regex` - Regex to extract customer VAT from invoice text
- `invoice_number_regex` - Regex to extract invoice number
- `invoice_date_regex` - Regex to extract invoice date
- `invoice_value_regex` - Regex to extract total value
- `currency` / `currency_regex` - Currency info

### Parsing Flow (`invoice_parser.py`)

**When template is explicitly selected** (user picks from dropdown):
1. `parse_invoice_with_template_from_bytes()` is called
2. Text extracted from PDF using PyPDF2
3. `apply_template()` sets fixed values + extracts customer_vat via regex
4. Invoice number, date, value extracted using template regex patterns
5. **NO AI is used** - pure regex parsing

**When no template selected** (auto-detect mode):
1. `auto_detect_and_parse()` is called
2. Text extracted from PDF
3. Searches for matching template by supplier VAT in text
4. **If template found** → uses `parse_with_template()` (regex only, no AI)
5. **If NO template found** → falls back to `parse_invoice()` (AI parsing with Claude)

**AI is ONLY used as fallback** when:
- No template explicitly selected AND
- No matching template auto-detected by supplier VAT

### Key Functions
- `apply_template(template, text)` - Apply template values, extract customer_vat via regex
- `parse_with_template(file_path, template)` - Full template-based parsing
- `parse_invoice(file_path)` - AI-based parsing using Claude vision
- `auto_detect_and_parse()` - Auto-detects template by supplier VAT, falls back to AI

### Regex Pattern Requirements
- Patterns MUST have capture groups `()` to extract values
- Multiple groups are concatenated (e.g., series + number)
- First non-None group is used when multiple alternations exist

### Current Templates (in database)
1. **Meta** (ID 1) - Facebook/Instagram ads invoices
   - `invoice_number_regex`: `(FBADS-\d+-\d+)|ID\s+tranzac[tț]ie\s+(\d+-\d+)`
   - `invoice_date_regex`: `(\d{1,2}\s+\w{3}\.?\s*\d{4})`
   - `invoice_value_regex`: `Efectuat[aă]?\s*([\d.,]+)\s*(?:RON|EUR|USD)?`
   - `customer_vat_regex`: `VAT[:\s]*([A-Z]{2}[\s]?\d+)|S\.C\..*?VAT[:\s]*([A-Z]{2}[\s]?\d+)`

2. **Dreamstime** (ID 2) - Stock photo invoices
3. **Google Ads** (ID 3) - Google advertising invoices

### Company VAT Matching
When customer_vat is extracted from an invoice, it's matched against the `companies` table to auto-populate the "Dedicated To (Company)" dropdown.

**Matching Algorithm** (`services.py`):

1. **Normalization** (`normalize_vat()` in services.py):
   - Removes prefixes: `CUI:`, `CUI`, `CIF:`, `CIF`, `VAT:`, etc.
   - Removes separators: spaces, dashes, dots, slashes
   - Returns cleaned VAT string

2. **Two-Pass Matching** (`match_company_by_vat()`):
   - **First pass**: Exact match after normalization
     - `RO 225615` normalized → `RO225615` matches `RO225615`
   - **Second pass**: Numeric-only comparison (if first pass fails)
     - `CUI 225615` → extracts `225615` → matches `RO 225615` (which also extracts to `225615`)

**VAT Number Normalization** (`invoice_parser.py`):

The `normalize_vat_number()` function handles various VAT formats:
```python
'RO 225615'     → 'RO225615'      # Country code preserved
'CUI 225615'    → '225615'        # Prefix removed, numbers only
'CIF: RO 225615'→ 'RO225615'      # Multiple prefixes handled
'IE9692928F'    → 'IE9692928F'    # Irish VAT with trailing letter preserved
```

## MCP Server Setup
To enable DigitalOcean integration in Claude Code, add the MCP server:
```bash
claude mcp add digitalocean -- npx -y @digitalocean/mcp --api-token YOUR_DO_API_TOKEN
```
Restart Claude Code after adding to use DO management tools.

## Date Handling

### Date Format Standards
- **Storage**: ISO format `YYYY-MM-DD` in PostgreSQL DATE columns
- **Display**: Romanian format `DD.MM.YYYY` using `formatDateRomanian()` in JavaScript

### Date Parsing (`invoice_parser.py`)
The `parse_romanian_date()` function handles multiple date formats:
- **Romanian**: `'22 nov. 2025'`, `'22 noiembrie 2025'`
- **English**: `'Nov 21, 2025'`, `'November 1, 2025'`
- **Numeric**: `'22.11.2025'`, `'22/11/2025'`, `'22-11-2025'`
- **ISO**: `'2025-11-22'`

All formats are converted to ISO `YYYY-MM-DD` for database storage.

### Date Serialization (`database.py`)
The `dict_from_row()` function converts Python date objects to ISO format strings for JSON API responses. This ensures HTML date inputs receive proper `YYYY-MM-DD` values.

## Allocation Rules

### Single Company Constraint
- Each invoice is allocated to a **single company** (via "Dedicated To (Company)" dropdown)
- Allocations can be split across multiple departments/brands **within that company**
- The edit allocation modal enforces the same constraint as the invoice input form

### Allocation Fields
- `company` - Company receiving the allocation (same for all rows)
- `brand` - Optional brand within the company
- `department` - Required department
- `subdepartment` - Optional subdepartment
- `allocation_percent` - Percentage (must sum to 100%)
- `allocation_value` - Calculated from invoice_value * allocation_percent (or net_value if VAT subtracted)
- `responsible` - Auto-populated from department_structure
- `reinvoice_to` - Optional company for reinvoicing
- `reinvoice_department` - Optional department within the reinvoice target company
- `reinvoice_subdepartment` - Optional subdepartment within the reinvoice target department

### VAT Subtraction Feature
For invoices where VAT should be excluded from allocation values:
1. Check the "Subtract VAT" checkbox on the invoice form
2. Select a VAT rate from the dropdown (19%, 9%, 5%, 0%)
3. Net Value is automatically calculated: `Invoice Value / (1 + VAT_Rate/100)`
4. Allocation values are calculated from the **net value** instead of gross value
5. Both Add Invoice page and Edit Invoice modal support VAT subtraction
6. VAT rates are managed in Settings → VAT Rates tab

**Database fields:**
- `subtract_vat` (BOOLEAN) - Whether VAT subtraction is enabled
- `vat_rate_id` (INTEGER) - Foreign key to `vat_rates` table
- `net_value` (REAL) - Calculated net value after VAT subtraction

**VAT Rates table (`vat_rates`):**
- `id` - Primary key
- `name` - Display name (e.g., "19%")
- `rate` - Decimal rate (e.g., 19.0)

### Lock Allocation Feature
When working with multiple allocations (3+), percentages automatically redistribute when adding or modifying rows. To prevent specific allocations from being affected:
1. Click the lock icon (🔓) next to the allocation row
2. Icon changes to locked state (🔒) with yellow background
3. Locked allocations maintain their percentage during redistribution
4. Unlocked rows receive the remaining percentage (100% - locked total)
5. **Lock state is persisted to database** - when viewing/editing invoices, locked allocations remain locked

### Multi-Destination Reinvoice Feature
Allocations can be marked for reinvoicing to multiple companies/departments:
1. Check the "Reinvoice to:" checkbox on an allocation
2. First reinvoice line appears with 100% of allocation value
3. Click "+ Add Reinvoice Line" to add more destinations
4. Each line has: Company, Brand (if applicable), Department, Subdepartment dropdowns
5. Value and percentage fields are bidirectionally synced
6. Total reinvoice percentage cannot exceed 100%

#### Reinvoice Line Lock Feature
To prevent a reinvoice line's values from changing when adding more lines:
1. Click the lock icon (🔓) next to the reinvoice line
2. Icon changes to locked state (🔒) with yellow background
3. Locked lines maintain their percentage/value during redistribution
4. When adding a new line, only unlocked lines share the remaining percentage
5. Example: Lock a line at 100%, add new line → locked line stays 100%, new line gets 0%

#### Reinvoice Line Comments
Each reinvoice line can have an optional comment:
1. Click the chat icon (💬) next to the reinvoice line
2. Enter comment in the prompt dialog
3. If comment exists, button turns blue and shows comment on hover
4. Comments are included in the `reinvoice_destinations` array when saving

This allows tracking which allocations need to be billed to multiple entities within the organization.

## Accounting Dashboard

### Tab Views
The accounting dashboard (`/accounting`) provides multiple views:
1. **Invoices** - List of all invoices with configurable columns
2. **By Company** - Summary grouped by company
3. **By Department** - Summary grouped by department
4. **By Brand** - Summary grouped by brand (Linie de business)

### Collapsible Split Values
The Split Values column displays allocation details in a collapsible format:
- Summary line shows: `X allocations • Y RON`
- Yellow `(→)` indicator appears if any allocations have reinvoice targets
- Click +/- icon to expand/collapse allocation details
- Each allocation shows department, brand, value, percentage, and reinvoice target

### Column Configuration
Each tab has its own column configuration stored in localStorage:
- `accountingColumnConfig` - Invoices tab
- `companyColumnConfig` - By Company tab
- `departmentColumnConfig` - By Department tab
- `brandColumnConfig` - By Brand tab

Use "Configure Columns" button to show/hide and reorder columns.

## Google Drive Integration

### Authentication
The app uses OAuth2 for Google Drive access (service accounts don't have storage quota for regular Drive folders).

**Local Development:**
- OAuth credentials stored in `oauth-credentials.json` (OAuth 2.0 Desktop Client)
- Token stored in `oauth-token.json` (auto-refreshed)
- Run `python -c 'from app.drive_service import setup_oauth; setup_oauth()'` to authenticate

**Production (DigitalOcean):**
- Set `GOOGLE_OAUTH_TOKEN` environment variable with base64-encoded contents of `oauth-token.json`
- Generate with: `base64 -i oauth-token.json | tr -d '\n'`
- The `drive_service.py` automatically decodes base64 tokens (avoids JSON parsing issues in env vars)

### Upload Workflow
Drive upload happens **after allocation confirmation** (not during parsing):
1. User uploads invoice file → parsing extracts data (no Drive upload)
2. User configures allocations
3. User clicks "Save Distribution" → file uploaded to Drive, then saved to DB
4. Files organized by: `Root Folder / Year / Supplier / filename`

This ensures only confirmed invoices are uploaded to Drive.

### Invoice Attachments
Users can upload additional files (images, PDFs, documents) with invoices:
1. On the Invoice Input page, click "Add files to upload with invoice" section
2. Select multiple files (max 5MB each)
3. Attachments are uploaded to the same Google Drive folder as the main invoice
4. Images (PNG, JPEG) are automatically compressed via TinyPNG API before upload
5. Progress indicator shows "Uploading attachment X/Y..." during upload
6. In Accounting list, a folder icon appears next to "View" for invoices with Drive files

### Image Compression (`image_compressor.py`)
Automatic image compression using TinyPNG API:
- Compresses PNG and JPEG images before Drive upload
- Reduces file size by 40-70% typically
- Falls back to original if compression fails
- Returns compression stats (original_size, compressed_size, saved_percent)

## Currency Conversion

### BNR Exchange Rates (`currency_converter.py`)
Automatic currency conversion using BNR (National Bank of Romania) exchange rates:
- Fetches rates from `https://www.bnr.ro/nbrfxrates.xml` (current year)
- Historical rates from `https://www.bnr.ro/files/xml/years/nbrfxrates{YEAR}.xml`
- In-memory cache to avoid repeated API calls
- Fallback to previous days for weekends/holidays (up to 10 days back)

### Invoice Currency Storage
Each invoice stores:
- `currency` - Original invoice currency (RON, EUR, USD, etc.)
- `invoice_value` - Original amount in invoice currency
- `value_ron` - Converted amount in RON
- `value_eur` - Converted amount in EUR
- `exchange_rate` - EUR/RON rate used for conversion

### Dashboard Currency Toggle
The "Total Value" card on the accounting dashboard has a EUR/RON toggle switch:
- Stored in localStorage as `totalValueDisplayCurrency`
- Shows either total in RON or converted total in EUR
- Uses BNR exchange rates from invoice dates

## Bulk Invoice Processor (`bulk_processor.py`)

### Overview
The bulk processor handles analysis of multiple invoices at once, extracting line items/campaigns and generating reports.

### Meta Invoice Item Parsing
The `parse_meta_invoice()` function uses dynamic line-by-line parsing to extract ALL invoice items:

**Algorithm:**
1. **Preprocess text** - Split concatenated item headers that PDF extraction merges:
   - `RON[CA]` → `RON\n[CA]`
   - `RON(Postare:)` → `RON\n(Postare:)`
   - `RON(Stoc_)` → `RON\n(Stoc_)`
   - `RON(GENERARE)` → `RON\n(GENERARE)`

2. **Line-by-line scan** - For each line, check if next line matches date range + value pattern:
   - Pattern: `\d{1,2}\s+\w+\.?\s+202\d.*\d{2}:\d{2}([\d.,]+)\s*RON`
   - Example: `29 oct. 2025, 00:00 - 4 nov. 2025, 17:31380,30 RON`

3. **Skip metadata** - Filter out non-item lines using skip keywords:
   - `de Afișări`, `Afișări`, `Meta Platforms`, `Merrion Road`, `Dublin`, `Ireland`, `VAT Reg`, etc.

4. **Extract value** - Parse the value from date range line and add to items dict

**Data Structure:**
```python
{
    'items': {  # Generic name for all invoice types
        '[CA] Traffic - Interese - Modele masini': 380.30,
        'Postare: „Audi RS6..."': 4.37,
        'Stoc_DWA - TEST': 522.27,
        ...
    },
    'campaigns': {...}  # Alias of items for frontend compatibility
}
```

### Return Structure
The `process_invoices()` function returns:
```python
{
    'invoices': [...]  # List with items/campaigns per invoice
    'by_item': {...}   # Aggregated items across all invoices
    'by_campaign': {...}  # Alias for frontend compatibility
    'by_month': {...}
    'by_supplier': {...}
    'total': float
    'currency': str
}
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Settings Company Structure

### Data Architecture
The Settings → Company Structure page uses master lookup tables for vocabulary management:

| Tab | Data Source | Mode |
|-----|-------------|------|
| Companies | `companies` table | Full CRUD |
| Brands | `brands` table | Full CRUD |
| Departments | `departments` table | Full CRUD |
| Subdepartments | `subdepartments` table | Full CRUD |
| Structure Mapping | `department_structure` | Full CRUD |
| Employees | `hr.employees` | Full CRUD |

### Master Lookup Tables
These tables define the vocabulary of available options:
- `brands` (id, name, is_active) - Brand names
- `departments` (id, name, is_active) - Department names
- `subdepartments` (id, name, is_active) - Subdepartment names

### Department Structure Table
The `department_structure` table maps companies to brands, departments, and managers:
- `id` - Primary key
- `company_id` - FK to companies table (required for API)
- `company` - Company name (denormalized for display)
- `brand`, `department`, `subdepartment` - Text values from master tables
- `manager`, `marketing` - Manager/marketing contact names (display only)
- `manager_ids`, `marketing_ids` - **Integer arrays for user IDs** (used for notifications)
- `cc_email` - Optional email address CC'd on all allocation notifications for this department

**Note**: `manager_ids` is the primary field for notification lookups. The `manager` field is kept for display purposes. When selecting a manager in the UI, both fields are populated automatically.

### API Endpoints
| Endpoint | Methods | Notes |
|----------|---------|-------|
| `/hr/events/api/master/brands` | GET, POST | List/create brands |
| `/hr/events/api/master/brands/<id>` | PUT, DELETE | Update/soft-delete brand |
| `/hr/events/api/master/departments` | GET, POST | List/create departments |
| `/hr/events/api/master/departments/<id>` | PUT, DELETE | Update/soft-delete department |
| `/hr/events/api/master/subdepartments` | GET, POST | List/create subdepartments |
| `/hr/events/api/master/subdepartments/<id>` | PUT, DELETE | Update/soft-delete subdepartment |
| `/hr/events/api/structure/departments-full` | GET | Structure mapping list |
| `/hr/events/api/structure/departments` | POST | Create structure entry |
| `/hr/events/api/structure/departments/<id>` | PUT, DELETE | Update/delete structure entry |

## Custom Dialog System

The platform uses custom styled dialogs instead of native browser `alert()`, `confirm()`, `prompt()`.

### Files
- `jarvis/static/js/jarvis-dialogs.js` - Dialog and toast JavaScript utilities
- `jarvis/static/css/theme.css` - Dialog and toast CSS styles (end of file)

### Usage
```javascript
// Alert dialog (returns Promise)
JarvisDialog.alert('Error message', { type: 'error', title: 'Error' });

// Confirm dialog (returns Promise<boolean>)
const confirmed = await JarvisDialog.confirm('Delete this?', { danger: true });

// Prompt dialog (returns Promise<string|null>)
const value = await JarvisDialog.prompt('Enter name:', { defaultValue: 'John' });

// Toast notifications (auto-dismiss)
JarvisToast.success('Saved successfully!');
JarvisToast.error('Failed to save');
JarvisToast.warning('Please check inputs');
JarvisToast.info('Processing...');
```

### Options
| Option | Type | Description |
|--------|------|-------------|
| `type` | string | Icon/color: 'info', 'success', 'warning', 'error', 'confirm' |
| `title` | string | Dialog title (default based on type) |
| `buttonText` | string | OK button text for alert |
| `confirmText` | string | Confirm button text for confirm |
| `cancelText` | string | Cancel button text |
| `danger` | boolean | Red confirm button for destructive actions |
| `duration` | number | Toast auto-dismiss time in ms (0 = no auto-dismiss) |

## Email Notification Service

### Overview
The notification service (`jarvis/core/services/notification_service.py`) sends email notifications to managers when invoices are allocated to their department.

### Manager Lookup via department_structure
Notifications are sent to managers defined in `department_structure` for the company + department combination:

| Step | Description |
|------|-------------|
| 1 | Look up `department_structure` row for company + department |
| 2 | Use `manager_ids` array to find users (preferred) |
| 3 | Fall back to looking up user by `manager` name if `manager_ids` is NULL |
| 4 | Filter users by `is_active = TRUE` AND `notify_on_allocation = TRUE` |

**Important**: Managers are assigned per company + department in Settings → Company Structure. The `manager_ids` integer array stores user IDs directly for efficient lookup.

### Key Functions

| Function | File | Description |
|----------|------|-------------|
| `get_responsables_by_department(department, company)` | database.py | Looks up managers from department_structure |
| `find_responsables_for_allocation(allocation)` | notification_service.py | Finds all users to notify for an allocation |
| `notify_allocation(invoice_data, allocation)` | notification_service.py | Sends notification emails |
| `get_department_cc_email(company, department)` | database.py | Looks up CC email from department_structure |

### Department CC Email
Each department structure entry can have an optional `cc_email`. When `notify_allocation()` runs:
1. Looks up `cc_email` via `get_department_cc_email(company, department)`
2. Passes it as `department_cc` parameter to `send_email()`
3. `send_email()` combines global CC + department CC (with deduplication)

### Reinvoice Notifications
When an allocation has a `reinvoice_to` target, additional notifications are sent:
- Uses `reinvoice_to` as the company filter
- Uses `reinvoice_department` as the department filter
- Same filtering rules apply (company + department + active + notify)

### SMTP Configuration
SMTP settings are stored in the `notification_settings` table:
- `smtp_host`, `smtp_port`, `smtp_tls`
- `smtp_username`, `smtp_password`
- `from_email`, `from_name`
- `global_cc` - Optional CC address for all notifications

## Disabled Features

Some connector infrastructure remains disabled:
- **Google Ads connector** (`google_ads_connector.py`) - for future invoice auto-fetching
- **Anthropic connector** (`anthropic_connector.py`) - for future invoice auto-fetching

**Active connectors**: e-Factura (ANAF RO e-Invoicing) is fully functional in `core/connectors/efactura/`.