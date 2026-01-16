# Changelog

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
