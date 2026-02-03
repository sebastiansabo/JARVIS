# Changelog

## 2026-02-02
### HR Module Improvements
- **Employee Dropdown Display**: Shows department instead of "N/A" in employee dropdowns
  - `add_bonus.html` and `event_bonuses.html` updated
  - Displays: "Employee Name (Department)" format

- **Bulk Delete for Bonuses**: Select and delete multiple bonus records at once
  - Select All checkbox in table header
  - Individual checkboxes per row
  - "Delete Selected" button appears when items selected
  - API endpoint: `POST /hr/events/api/event-bonuses/bulk-delete`

- **Bulk Delete for Events**: Same functionality for Events list
  - API endpoint: `POST /hr/events/api/events/bulk-delete`

- **Bulk Delete for Users**: Same functionality in Settings → Users tab
  - API endpoint: `POST /api/users/bulk-delete`

### Profile Page Fixes
- **First Load Issue**: Fixed invoices not loading on first visit
  - Problem: When saved tab was `#invoices`, `tab.show()` didn't fire event
  - Solution: Explicitly call `loadInvoicesTab()` when saved tab is invoices

- **HR Events Not Showing**: Fixed profile HR Events tab not fetching bonuses
  - Problem: Queries used outdated JOIN through `hr.employees` table
  - Solution: `employee_id` now directly references `users.id`
  - Updated: `get_user_event_bonuses()`, `get_user_event_bonuses_summary()`, `get_user_event_bonuses_count()`

### Profile Page Performance Optimization
- **responsible_user_id FK**: Added indexed foreign key to allocations table
  - Replaces slow text-based JOIN (`LOWER(a.responsible) = LOWER(u.name)`)
  - Uses indexed integer FK lookup for fast profile page queries
  - Migration auto-populates user_id from existing responsible names
  - All allocation INSERT statements updated to set responsible_user_id
  - Fallback to text matching for unmigrated data

### Shared Invoice Edit Module Enhancement
- **invoice-edit.js**: Updated shared module to match full accounting.html functionality
  - **Smart Split Allocation**: Auto-redistribute percentages when adding/removing allocations
    - 1 allocation: 100%
    - 2 allocations: 50-50
    - 3+ allocations: 40% first, rest split equally
  - **Lock Allocations**: Lock button prevents allocation from being affected by redistribution
  - **Multi-line Reinvoice**: Support for multiple reinvoice destinations per allocation
  - **Allocation Comments**: Add comments to individual allocations
  - **Subdepartment Support**: Dropdown populated based on selected department
  - **VAT-aware Calculations**: Uses net value when VAT subtracted

- **Profile Page**: Edit Invoice modal now identical to accounting page
  - Uses same shared `invoice-edit.js` module
  - Full allocation management with smart split
  - Reinvoice destinations with multiple lines

## 2026-01-30
### Sync Modal with Period and Company Selection
- **Sync Modal**: Replaced dropdown with modal dialog for sync options
  - Period selection: 1, 3, 7, 15, 30 days preset buttons
  - Custom days input (max 90 days)
  - Company checkboxes with Select All / Deselect All
  - Only syncs received (inbound) invoices
- **Improved Sync Results**:
  - XML signature files shown separately from errors (not counted as errors)
  - "XML files (not invoices)" section with file icon
  - Actual errors shown in separate section

### Mappings Tab Column Configuration
- **Configure Columns**: Show/hide and reorder columns in Mappings tab
- **Persistent Config**: Settings saved to localStorage with version tracking

### Dialog Improvements
- **HTML Support**: `JarvisDialog.alert()` now supports `html: true` option
- **Skipped Details**: Renamed "Error Details" to "Skipped Details" in sync results

### e-Factura OAuth Token Functions Restoration
- **Critical Fix**: Restored missing OAuth token management functions that were accidentally removed
  - `get_efactura_oauth_tokens(company_cif)` - Retrieve tokens from connectors table
  - `save_efactura_oauth_tokens(company_cif, tokens)` - Save/update OAuth tokens
  - `delete_efactura_oauth_tokens(company_cif)` - Disconnect (remove tokens)
  - `get_efactura_oauth_status(company_cif)` - Get authentication status

- **e-Factura Tables Restoration**: Restored all missing table definitions in `init_db()`
  - `efactura_company_connections` - Company sync connections
  - `efactura_invoices` - Invoice records from ANAF
  - `efactura_invoice_refs` - ANAF message IDs
  - `efactura_invoice_artifacts` - ZIP/XML/PDF storage
  - `efactura_sync_runs` - Sync tracking
  - `efactura_sync_errors` - Error logging
  - `efactura_oauth_tokens` - OAuth token storage table
  - `efactura_partner_types` - Supplier types (Service, Merchandise)
  - `efactura_supplier_mappings` - Supplier name mappings
  - `efactura_supplier_mapping_types` - Junction table for multi-type

- **Migrations Restored**:
  - `ignored`, `deleted_at` columns on efactura_invoices
  - `type_override`, `department_override`, `subdepartment_override` columns
  - `kod_konto`, `type_id`, `department`, `subdepartment`, `brand` on supplier_mappings
  - `hide_in_filter` on partner_types

- **Indexes Restored**: All e-Factura indexes including trigram indexes for fast ILIKE search

### Bulk Processor Enhancements
- **Session Caching**: Invoice data persists across page refresh (1-hour TTL)
- **Duplicate Detection**: Skip invoices with same invoice_number, show warning
- **Delete from List**: X button to remove individual invoices
- **Incremental Upload**: Add to existing list instead of replacing
- **Sticky Sidebar**: Left column stays visible while scrolling

### Select All Enhancement (e-Factura)
- **True Select All**: Selects ALL records matching filters, not just visible page
- **API Enhancement**: `get_unallocated_ids()` now supports `hide_typed` parameter
- **Toast Notification**: Shows count of selected invoices

## 2026-01-29
### Custom Dialog System
- **JarvisDialog**: Custom styled dialogs replacing native browser `alert()`, `confirm()`, `prompt()`
  - `JarvisDialog.alert(message, options)` - Styled alert with icon, animation
  - `JarvisDialog.confirm(message, options)` - Returns Promise with boolean result
  - `JarvisDialog.prompt(message, options)` - Returns Promise with input value
  - Types: info (blue), success (green), warning (orange), error (red), confirm (purple)
  - Full dark theme support with backdrop blur

- **JarvisToast**: Toast notifications for non-blocking feedback
  - `JarvisToast.success/error/warning/info(message, options)`
  - Auto-dismiss with progress bar (configurable duration)
  - Stacked notifications in top-right corner

- **Files**:
  - `jarvis/static/js/jarvis-dialogs.js` - Dialog and toast utilities
  - `jarvis/static/css/theme.css` - Dialog and toast CSS styles

### Role-Based Status Permissions
- **Database**: Added `min_role` column to `dropdown_options` table
  - Controls which roles can set/edit invoices with specific statuses
  - Default: 'Viewer' (all roles can access)
  - Migration sets 'Processed' status to require 'Manager' by default

- **Settings UI**: Min Role dropdown in Settings → Accounting → Invoice Statuses
  - Configure minimum role required for each status

- **Invoice Edit**: Status dropdown filtered based on user role
  - Users only see statuses they have permission to set
  - Edit button locked for invoices with restricted status

### Dynamic Status Row Coloring
- **Fully dynamic**: All status colors from database (no hardcoded CSS)
- **Inline styles**: Row coloring via computed `rgba()` from status options
- **Consistent**: Same approach in accounting.html and profile.html
- **Removed hardcoded CSS**: theme.css only has generic `tr[data-status]` transition rule

### e-Factura Duplicate Detection
- **Duplicate Detection Service**: Background service to detect duplicate invoices after ANAF sync
  - Exact matching: Finds duplicates by supplier name + invoice number
  - AI fallback (Claude): Fuzzy matching for similar supplier names and amounts
  - Pre-filters candidates by amount similarity (within 5%) and name similarity (>50%)
  - AI confidence threshold: 70% for duplicate confirmation

- **Duplicate Management UI**: Banner notification and management tools
  - Yellow alert banner appears when duplicates detected after sync
  - "View" button shows detailed list with exact vs AI-detected sections
  - "Mark All as Duplicates" links e-Factura invoices to existing invoices
  - Duplicates removed from Unallocated tab automatically

- **API Endpoints**:
  - `GET /efactura/api/invoices/duplicates` - Exact duplicate detection
  - `POST /efactura/api/invoices/mark-duplicates` - Mark exact duplicates
  - `GET /efactura/api/invoices/duplicates/ai` - AI-powered fuzzy duplicate detection
  - `POST /efactura/api/invoices/mark-duplicates/ai` - Mark AI-detected duplicates

- **Send to Invoice Module Improvements**:
  - Duplicate prevention: Checks for existing invoices before creating new ones
  - Automatic linking: Duplicate e-Factura invoices linked to existing jarvis_invoice_id
  - Status "Nebugetata" set for all imported invoices
  - Net value and VAT calculations preserved
  - PDF link generated pointing to e-Factura export endpoint
  - **Responsible auto-populated**: Looks up manager from `department_structure` table based on company/department

## 2026-01-28
### Architecture & Code Quality
- **e-Factura Architecture Refactoring**: Moved SQL operations from routes to repositories
  - `ensure_connection_for_oauth()` → CompanyConnectionRepository
  - `migrate_junction_table()` → SupplierMappingRepository
  - `bulk_set_types()` → SupplierMappingRepository
  - `get_by_name()` → PartnerTypeRepository
  - `get_unallocated_ids()` → InvoiceRepository
  - Removed unused `core.database` imports from routes.py

- **Validation Hooks Improvements**: All 7 hooks now pass with 0 warnings
  - **Cache Hook**: Skip internal metadata keys (`ttl`, `timestamp`, `key`, `data`)
  - **Resources Hook**: Added acceptable file list for `.read()` operations (parsers, mocks, routes, etc.)
  - **Performance Hook**:
    - Skip loops iterating over query results (`fetchall()`, `results`, etc.)
    - Skip loops over small collections (`transactions`, `allocations`, `items`, etc.)
    - Skip small/lookup tables from unbounded query warnings
    - Extended context window for commit detection (50 lines)

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
  - **Edit modal shows actual mapping defaults** in dropdowns (e.g., "-- Use Mapping Default (Aftersales) --")
  - Changes affect only the individual invoice, not the supplier mapping
  - Bulk "Set Type" action for multiple selected invoices

- **"Hide Typed" Filter**: Toggle switch to hide invoices with assigned types
  - Server-side filtering (works across all pages, not just visible rows)
  - Located next to search field in Unallocated tab
  - State persisted in localStorage
  - **Configurable per type**: Each partner type has `hide_in_filter` setting
  - Types with `hide_in_filter=FALSE` remain visible when filter is ON
  - **"Hidden by filter" indicator**: Shows count of filtered invoices (e.g., "5 invoices (3 hidden by filter)")

- **Auto-hide Invoices with Hidden Types**: Invoices automatically move to Hidden tab
  - On import: If partner has mapping with hidden type, invoice auto-hidden
  - On mapping create/update: Existing invoices for partner auto-hidden if type is hidden
  - On bulk type set: Existing invoices auto-hidden when setting hidden types
  - Repository methods: `partner_has_hidden_types()`, `auto_hide_if_typed()`, `auto_hide_all_by_partner()`

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
  - **Fix**: Column order now preserved when clicking Apply without changes (saves `order` property)

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
