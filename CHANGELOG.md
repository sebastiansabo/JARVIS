# Changelog

## 2026-01-28
### e-Factura Improvements
- **Sync filter**: Global sync now only fetches **received (Primite)** invoices from ANAF
  - Sent (outbound) invoices no longer imported during sync
  - Updated `sync_all()` in `efactura_service.py` with `filter_type='P'`

- **Tab caching**: Added client-side caching to prevent API reloads on tab switch
  - Each tab (Unallocated, Hidden, Bin, Mappings) tracks loaded state
  - Switching tabs uses cached data instead of reloading
  - Cache invalidated automatically when data changes (hide/unhide/delete/restore)

- **Mappings table improvements**:
  - Search by partner name, supplier name, VAT, or kod konto
  - Type filter dropdown (Service, Merchandise, No Type)
  - Page size selector (25, 50, 100, 200, All)
  - Client-side pagination with navigation controls
  - Consistent UI with collapsible Filters panel (matches Unallocated tab)

- **Partner Types table**: Added `efactura_partner_types` table for categorizing suppliers
  - Default types: Service, Merchandise
  - Migration fix: explicit commit after table creation for FK reference

- **Supplier Mapping Defaults**: Department and subdepartment fields on mappings
  - Pre-set default department/subdepartment for suppliers
  - Subdepartment dropdown filtered by department from company structure
  - Defaults displayed in Unallocated table columns

- **Invoice Overrides**: Invoice-level overrides for type, department, subdepartment
  - Override fields: `type_override`, `department_override`, `subdepartment_override`
  - Edit modal shows current values (from override or mapping default)
  - Changes affect only the individual invoice, not the supplier mapping
  - Bulk "Set Type" action for multiple selected invoices

- **"Hide Typed" Filter**: Toggle switch to hide invoices with assigned types
  - Server-side filtering (works across all pages, not just visible rows)
  - Located next to search field in Unallocated tab
  - State persisted in localStorage
  - **Configurable per type**: Each partner type has `hide_in_filter` setting
  - Types with `hide_in_filter=FALSE` remain visible when filter is ON

- **Partner Types Management**: Added to Global Settings and Connector Settings
  - Settings → Connectors → Partner Types section
  - Connector Settings → Partner Types tab
  - Toggle "Hide in Filter" per type
  - Add/edit/delete partner types
  - Soft-delete (deactivation) for safety

- **Column Configuration Versioning**: Automatic reset on schema changes
  - `COLUMN_CONFIG_VERSION` constant tracks schema version
  - User column configs reset when version changes
  - Prevents column mixing when new columns are added

### Performance Monitoring
- **Request timing middleware**: Tracks slow requests when `PERF_MONITOR=true`
  - Only logs requests slower than `PERF_MONITOR_MIN_MS` (default: 100ms)
  - Stores endpoint, method, duration, status code, user, query params
  - Adds `X-Response-Time` header to all responses
- **Performance reports table**: `performance_reports` for storing timing data
- **API endpoints**:
  - `GET /api/performance/reports` - List reports with filtering
  - `GET /api/performance/summary` - Statistics by endpoint (avg, max, p95)
  - `POST /api/performance/cleanup` - Delete old reports

### Database
- Added `type_id` column to `efactura_supplier_mappings` (FK to `efactura_partner_types`)
- Added `department` and `subdepartment` columns to `efactura_supplier_mappings`
- Added `type_override`, `department_override`, `subdepartment_override` columns to `efactura_invoices`
- Added `hide_in_filter` column to `efactura_partner_types` (controls "Hide Typed" filter behavior)
- Added `performance_reports` table for request timing analysis
- **Trigram indexes for faster search**: Added `pg_trgm` indexes on text search columns
  - `efactura_invoices`: partner_name, partner_cif, invoice_number
  - `efactura_supplier_mappings`: partner_name, supplier_name, partner_cif
  - Speeds up ILIKE searches significantly (uses GIN index)
- **Functional indexes for LOWER()**: Added indexes for case-insensitive JOINs
  - `idx_efactura_invoices_partner_name_lower`
  - `idx_efactura_mappings_partner_name_lower`
  - Speeds up supplier mapping lookups in queries
- Migration runs automatically on app startup via `init_db()`

### API
- `PUT /efactura/api/invoices/<id>/overrides` - Update invoice overrides
- `PUT /efactura/api/invoices/bulk-overrides` - Bulk update overrides for multiple invoices

## 2026-01-26
### e-Factura Connector - JARVIS Integration
- Added **e-Factura button** to Accounting navigation (between Invoices and Statements)
- Created **Unallocated Invoices page** at `/accounting/efactura`
  - Shows invoices imported from ANAF e-Factura that need allocation
  - Filters: Company, Direction, Date range, Search
  - Bulk selection with "Send to Invoices" action
  - Individual actions: Send to Invoices, View Details, Export PDF
- Badge in navigation shows count of unallocated invoices
- **XML Parser module** (`core/connectors/efactura/xml_parser.py`)
  - Parses UBL 2.1 e-Factura XML format
  - Extracts seller/buyer info, amounts, dates, line items
- **Import from ANAF** functionality
  - Downloads ZIP from ANAF, extracts XML, parses invoice data
  - Stores XML content in database for PDF generation
  - Deduplication by ANAF message ID
- **Send to Invoice Module** workflow
  - Creates record in main `invoices` table
  - Marks e-Factura invoice as allocated (`jarvis_invoice_id`)
- **Database migration** (`002_add_jarvis_integration.sql`)
  - Added `jarvis_invoice_id` column to track allocation status
  - Added `xml_content` column for XML storage

### Company Brands Migration - FK-based Junction Table
- Migrated `company_brands` from TEXT-based to FK-based storage
- Schema: `company_brands.brand_id` now references `brands.id` (master table)
- Dropped `company_brands.brand` TEXT column
- Updated all code to JOIN with `brands` table for brand names:
  - `jarvis/hr/events/routes.py` - 5 endpoints updated
  - `jarvis/services.py` - `get_companies_with_vat()` updated
  - `jarvis/models.py` - `get_brands_for_company()` updated
- Updated Settings UI: Company modal now uses dropdown to select brands from master list
- Benefits: Data normalization, referential integrity, single source of truth for brand names

### Settings Company Structure - Master Tables
- Restored master lookup tables (`brands`, `departments`, `subdepartments`) with full CRUD
- These serve as vocabulary/picklist tables for Settings → Company Structure tabs
- Full API support: GET/POST/PUT/DELETE for brands, departments, subdepartments
- Structure Mapping tab queries `department_structure` directly (simplified, no JOINs)
- Soft delete support (is_active flag) for master table entries

### Connection Pool Fixes - Company Structure Endpoints
- Added `try/finally` blocks to 7 endpoints to ensure `release_db()` always called:
  - `api_get_companies_full`, `api_create_company`, `api_update_company`
  - `api_get_company_brands`, `api_get_brands_for_company`
  - `api_update_department`, `api_delete_department`
- Added proper error handling with `conn.rollback()` for write operations
- Prevents connection pool exhaustion on staging

### Database Migration - Staging
- Added `company_id` column to `department_structure` table on staging
- Populated `company_id` values by matching company names (31 rows updated)

## 2026-01-20
### Critical Fixes - Database Connection Management
- Fixed `conn.close()` → `release_db(conn)` in `services.py` (3 functions: add_company_with_vat, update_company_vat, delete_company)
- Fixed 8 functions in `hr/events/routes.py` to use `with get_db_connection() as conn:` context manager pattern
- Prevents connection pool exhaustion under load

### Critical Fixes - Transaction Deduplication
- Added `account_number` and `currency` to dedup query in `accounting/statements/database.py`
- Updated unique index in `database.py` to include all 6 columns (company_cui, account_number, transaction_date, amount, currency, description)
- Uses `IS NOT DISTINCT FROM` for NULL-safe comparisons

### Critical Fixes - Transaction Isolation
- Added PostgreSQL SAVEPOINTs to `save_transactions_with_dedup()` for partial rollback on duplicates
- Individual transaction failures no longer abort entire batch
- Returns count of duplicates skipped alongside new IDs

### High Priority - Code Refactoring
- Split `upload_statements()` (~180 lines) into focused helper functions:
  - `_validate_upload_files()` - File validation logic
  - `_process_single_statement()` - Single PDF processing
  - `_auto_match_new_transactions()` - Auto-matching logic
- Main function reduced to ~75 lines

### High Priority - Thread Safety
- Added `threading.RLock()` to vendor pattern cache in `accounting/statements/vendors.py`
- Functions `_load_patterns()`, `reload_patterns()`, and `match_vendor()` now thread-safe
- Pattern iteration uses local reference outside lock to minimize contention

### Code Cleanup
- Removed dead `save_transactions()` function (replaced by `save_transactions_with_dedup`)
- Updated tests to use the new function
- Added `psycopg2.errors` mock to `conftest.py` for UniqueViolation testing

## 2025-01-19
### Invoice Parser Improvements
- Fixed `normalize_vat_number()` to handle Irish VAT format with trailing letters (e.g., `IE9692928F`)
- Regex updated from `^([A-Z]{2})(\d+)$` to `^([A-Z]{2})(\d+[A-Z]?)$`

### Company VAT Matching
- Two-pass matching algorithm in `services.py`:
  1. First pass: Exact match after normalization (removes spaces, prefixes like CUI/CIF)
  2. Second pass: Numeric-only comparison (e.g., `CUI 225615` matches `RO 225615`)
- Auto-populate "Dedicated To (Company)" dropdown based on customer VAT extracted from invoice

### HR Module Data
- Synced HR data to staging database (113 employees, 25 events, 204 event_bonuses)

## 2025-01-16
### Architecture Refactoring - J.A.R.V.I.S. Platform
- **Renamed `app/` folder to `jarvis/`** - reflects platform branding
- **New modular architecture** with section/app hierarchy:
  - `jarvis/core/` - Shared platform infrastructure (auth, services, settings, utils)
  - `jarvis/accounting/bugetare/` - Accounting section with Bugetare app
  - `jarvis/hr/events/` - HR section with Events app
- **Moved shared services to `core/services/`**:
  - drive_service.py (Google Drive integration)
  - notification_service.py (SMTP email)
  - image_compressor.py (TinyPNG)
  - currency_converter.py (BNR rates)
- **Moved utilities to `core/utils/`**:
  - logging_config.py (structured logging)
  - config.py (configuration)
- **Template reorganization**:
  - `templates/core/` - Core templates (login, settings, apps, guide)
  - `templates/accounting/bugetare/` - Accounting templates
  - `templates/hr/events/` - HR templates
- **Blueprint hierarchy** for nested section/app routing:
  - HR section (`/hr`) → Events app (`/hr/events/`)
- Updated Dockerfile and Procfile for `jarvis/` folder
- Added color picker for dropdown options (Invoice Status, Payment Status)
- Fixed theme settings logo to support custom SVG icons

### HR Module Fixes
- Fixed HR templates API URL construction (use direct `/hr/events/api/...` paths)
- Fixed HR modal theme styling (removed hardcoded dark mode classes)
- Fixed summary card text color - white text preserved on colored cards in light theme

## 2025-01-14
- Added "By Supplier" tab to Accounting dashboard (cost summary per supplier)
- Summary total row at bottom of all summary tables (By Company, Department, Brand, Supplier)
- Fixed deleted_at filter for summary queries (excluded soft-deleted invoices)
- TikTok invoice template support in bulk processor
- Clickable sort arrows on Date and Value columns in Accounting dashboard
- Sort options: Date (Newest/Oldest), Value (Highest/Lowest)
- Fixed date sorting to compare full dates (year-month-day)
- Memory optimization: Gunicorn worker recycling (--max-requests 500)
- Memory optimization: Summary cache size limit (50 entries max per type)
- Memory optimization: Expired cache cleanup on health check endpoint

## 2025-01-13
- Elasticsearch-like search for invoices (AND logic, partial matching)
- Added search button and clear button to Accounting dashboard

## 2025-01-12
- Bulk Processor UI: progress indicator, sticky header, manager lookup fix
- Fixed driveLink for consecutive uploads

## 2025-01-11
- Fixed manager-by-brand selection in allocation dropdowns
- Fixed VAT handling in `update_invoice_allocations()` - uses net value when VAT subtraction enabled
- Fixed Status "Eronata" row color dynamic update
- Enhanced Invoice Details modal (VAT info, net value, allocation summary)

## 2025-01-10
- Added Invoice Status and Payment Status filters to Accounting dashboard
- Summary cards: hidden by default, reflect filtered data
- Format-based template matching for eFactura
- AI fallback for missing fields in template parsing
- Keep-alive GitHub workflow for cold start prevention

## 2025-01-09
- Performance: N+1 query fix, summary query caching (60s TTL)
- Admin-configurable default column configuration
- Fixed role permission editing stale data bug
- Invoice list caching (60s TTL)

## 2025-01-08
- Department CC email feature
- GOOGLE_OAUTH_TOKEN env var with base64 encoding
- BNR currency converter module
- EUR/RON toggle on dashboard

## 2025-01-07
- Simplified database.py to PostgreSQL-only
- Fixed Meta template regex, English date parsing, date serialization
- Edit allocation modal: single company dropdown, smart split redistribution
- Collapsible Split Values column
- "By Brand" tab view

## 2025-01-06
- Moved Drive upload to allocation confirmation
- Flask-Login authentication
- VAT Registry moved to Settings
- Email notification system (Office365 SMTP)
- Global CC Address, notification toggle

## 2025-01-05
- Lock allocation feature with persistence
- Activity Logs tab (admin-only)
- Invoice attachments with TinyPNG compression
- Allocation comments
- Payment Status feature

## 2025-01-04
- Multi-destination reinvoice with locks and comments
- VAT subtraction feature
- User Guide page

## 2025-01-03
- Loading overlay on login for cold starts
- Pagination on Accounting dashboard
- Flask-Compress (84% size reduction)
- Health check endpoint
- Remember Me cookie (30 days)
- ETag and Cache-Control headers

## 2025-01-02
- Bulk Invoice Processor (`/bulk`)
- Bulk Distribute feature
- Meta invoice item parser improvements
- eFactura parsing support
- Google Ads invoice parsing

## 2025-01-01
- Role permission fixes (can_edit_invoices)
- Department-specific CC emails
- Connector infrastructure (disabled)
- Dynamic currency in summary tables
- Production stability (1GB RAM, Gunicorn timeouts)
