# Bugetare - Invoice Budget Allocation System

## Project Overview
Flask-based web application for managing invoice allocations across companies, brands, and departments. Features AI-powered invoice parsing using Claude API.

## Tech Stack
- **Backend**: Flask + Gunicorn
- **Database**: PostgreSQL (required)
- **AI**: Anthropic Claude API for invoice parsing
- **Storage**: Google Drive integration for invoice uploads
- **Deployment**: DigitalOcean App Platform via Docker

## Project Structure
```
app/
├── app.py              # Main Flask application and routes
├── database.py         # Database operations (PostgreSQL)
├── models.py           # Data models and structure loading
├── services.py         # Business logic for allocations
├── invoice_parser.py   # AI-powered invoice parsing with Claude
├── bulk_processor.py   # Bulk invoice processing and Excel report generation
├── drive_service.py    # Google Drive integration
├── image_compressor.py # TinyPNG image compression for attachments
├── currency_converter.py # BNR exchange rate fetching and conversion
├── notification_service.py # SMTP email notifications
├── google_ads_connector.py # Google Ads invoice fetching (DISABLED)
├── anthropic_connector.py  # Anthropic billing invoice fetching (DISABLED)
├── config.py           # Configuration settings
└── templates/          # Jinja2 HTML templates
    └── buffer.html     # Invoice buffer page (DISABLED)
```

## Key Commands

### Local Development
```bash
source venv/bin/activate
DATABASE_URL='postgresql://sebastiansabo@localhost:5432/defaultdb' PORT=5001 python app/app.py
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

## Database Schema
- `invoices` - Invoice header records (includes subtract_vat, vat_rate_id, net_value)
- `allocations` - Department allocation splits
- `invoice_templates` - AI parsing templates per supplier
- `department_structure` - Company/department hierarchy
- `companies` - Company VAT registry for matching
- `users` - Application users with bcrypt passwords and role permissions
- `user_events` - Activity log for user actions (login, invoice operations)
- `vat_rates` - VAT rate definitions (id, name, rate)
- `connectors` - External service connectors (Google Ads, Anthropic) - DISABLED

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
When customer_vat is extracted, it's matched against `companies` table to auto-select company in UI.

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

## Recent Changes
- Added admin-configurable default column configuration for Accounting dashboard
  - "Set as Default for All" button in Configure Columns modal (visible to admins only)
  - Admins can set default column arrangements for all tabs (Invoices, By Company, By Department, By Brand)
  - Users without localStorage config will see admin-set defaults
  - Users can still personalize columns (localStorage overrides server default)
  - "Reset to Default" button resets to server default (if set) or hardcoded defaults
  - Stored in `notification_settings` table with keys: `default_columns_accounting`, `default_columns_company`, `default_columns_department`, `default_columns_brand`
- Fixed role permission editing stale data bug
  - Root cause: `/api/roles` was in `CACHEABLE_API_ENDPOINTS` with 5-minute browser cache
  - Browser cached `/api/roles` responses, causing stale data after permission edits
  - Fix: Removed `/api/roles` from cacheable endpoints in app.py
  - Also added `autocommit=True` in database.py `get_db()` for fresh transaction snapshots
- Fixed missing `can_edit_invoices` permission in role create/update API endpoints
  - Both POST and PUT `/api/roles` now properly handle the edit permission
  - All 8 role permissions are now consistent across database, API, and frontend
- Added invoice list caching (60s TTL) for faster accounting page loads
  - Cache key includes all query parameters (limit, offset, filters)
  - Automatic invalidation on invoice CRUD operations
- Fixed allocation percentage validation tolerance (0.01% → 0.1%) to handle floating-point precision errors
- Added department CC email feature: each department can have a CC email that receives all allocation notifications for that department
  - CC Email field in Department Structure modal (Settings → Department Structure)
  - Combined with global CC: both global and department CC emails receive notifications
  - Notifications use exact department matching (not partial LIKE matching)
- Added GOOGLE_OAUTH_TOKEN env var support with base64 encoding for production
- Added missing `requests` package to requirements.txt (for BNR currency converter)
- Added BNR currency converter module for automatic EUR/RON conversion
- Added EUR/RON toggle on accounting dashboard Total Value card
- Fixed currency display in Split Values, Reinvoice To columns and invoice detail modal (was hardcoded to RON)
- Simplified database.py to PostgreSQL-only (removed SQLite)
- Added customer_vat_regex extraction for all template types (not just "format")
- Fixed Meta template invoice_number_regex to include capture groups
- Fixed English date format parsing (e.g., 'Nov 21, 2025' from Shopify/Google invoices)
- Fixed date serialization in API responses (was returning HTTP date format instead of ISO)
- Updated edit allocation modal to use single "Dedicated Company" dropdown (consistent with invoice input)
- Added smart split redistribution when adding/removing allocations in edit mode
- Added collapsible Split Values column with +/- toggle and allocation summary
- Added "By Brand" (Linie de business) tab view with Invoice #, Value, Split Values columns
- Moved Drive upload from parsing to allocation confirmation (Save Distribution)
- Added Flask-Login authentication with login required for all routes
- Added user password management with bcrypt hashing in database.py
- Moved VAT Registry from Add Invoice page to Settings → Company Configuration tab
- Company dropdown in Department Structure modal now populated from VAT Registry
- Added edit functionality to VAT Registry entries (Edit VAT Registry modal)
- Added password field to user creation/editing forms in Settings → Users
- Removed "Open in Drive" button from Invoice Details modal
- Repositioned Invoice Details modal buttons: Edit/Delete on left, Close on right
- Fixed import error in user creation (from database import set_user_password)
- Added email notification system with Office365 SMTP support
- Fixed notification_service.py to use correct settings keys (from_email, smtp_tls)
- Fixed allocation value calculation in notification emails (was showing 0.00)
- Added flask-login to requirements.txt for production deployment
- Synced local database to DigitalOcean production
- Added Global CC Address field to Settings → Notifications (all emails copied to this address)
- Added notification toggle to Edit Invoice modal (default OFF, only sends if validation passes)
- Reinvoice department managers now receive allocation notifications
- Email templates now include reinvoice details (company/department/subdepartment)
- Changed Google Drive folder structure to Year/Month/Company/InvoiceNo
- Email templates translated to Romanian with separate Alocare and Refacturare sections
- Added lock button to allocation rows (prevents locked allocations from being redistributed when adding/modifying other allocations)
- Hidden empty Brand/Subdepartment columns in allocation forms (only shows when options exist)
- Moved currency label into Value field label (e.g., "Value (RON)") for wider input field
- Fixed single-row allocation value editing (percentage now updates when editing value field on single allocation row)
- Lock state now persisted to database (locked allocations stay locked when viewing/editing invoices)
- Added Activity Logs tab to Settings page (admin-only) with filters for user, event type, date range
- Added event logging for invoice operations: invoice_created, invoice_updated, invoice_deleted, invoice_restored, invoice_permanently_deleted, allocations_updated
- Added invoice attachments feature: upload additional files (images, PDFs, docs) with invoices
- Added TinyPNG image compression for attachments (reduces file size before Drive upload)
- Added folder icon in Accounting list to open invoice's Google Drive folder
- Added upload progress indicator showing "Uploading attachment X/Y..."
- Added `/api/drive/upload-attachment` and `/api/drive/folder-link` API endpoints
- Added allocation comment feature: comment button on each allocation row in Add Invoice and Edit Invoice
- Added `PUT /api/allocations/<id>/comment` endpoint for updating allocation comments directly
- Fixed DocumentFragment closure bug in index.html allocation comment button click handler
- Added Payment Status feature: track invoice payment status (Paid/Not Paid)
  - Payment Status dropdown on Add Invoice page
  - Payment Status column in Accounting dashboard table (inline dropdown)
  - Payment Status row in Invoice Details modal (editable dropdown)
- Added multi-destination reinvoice feature: reinvoice to multiple companies/departments per allocation
- Added lock button to reinvoice lines: locked lines maintain their values when adding new lines
- Added comment button to reinvoice lines: add optional comments to each reinvoice destination
- Fixed `const` to `let` bug in addReinvoiceLine for locked line redistribution
- Added VAT subtraction feature: subtract VAT from invoice value to calculate net value for allocations
  - Checkbox + VAT rate dropdown on Add Invoice page and Edit Invoice modal
  - Net value automatically calculated: Invoice Value / (1 + VAT_Rate/100)
  - Allocation values use net value when VAT subtraction is enabled
  - VAT rates managed in Settings → VAT Rates tab (seeded with 19%, 9%, 5%, 0%)
- Fixed Edit Invoice modal allocation values not updating when VAT is toggled
- Added User Guide page (`/guide`) with comprehensive documentation for all features
- Added User Guide link to all navigation dropdowns across all pages
- Added loading overlay on login page for cold start delays (spinner with "Signing in..." message)
- Added list pagination to Accounting dashboard (25/50/100/All rows per page)
- Added Flask-Compress for gzip/brotli compression (84% size reduction)
- Added health check endpoint (`/health`) for uptime monitoring and cold start prevention
- Fixed "Remember Me" cookie - now persists for 30 days with proper secure settings
- Added ETag headers for JSON API responses (304 Not Modified support)
- Added Cache-Control headers for static pages and API endpoints
- Added "Clear Form" button on New Invoice page to reset all form fields and state
- Added Net Value column to Accounting dashboard (show/hide via Configure Columns)
- Updated New Invoice page to full-width layout matching Accounting page (container-fluid)
- Added Bulk Invoice Processor (`/bulk`) for analyzing multiple invoices at once
  - Upload multiple PDF invoices via drag-and-drop
  - Automatic invoice type detection (Meta, Google Ads, generic)
  - Campaign-level cost extraction for Meta/Facebook Ads invoices
  - Summary views: by invoice, by campaign, by month, by supplier
  - Excel export with multiple sheets (Summary, Monthly, Campaigns, Suppliers, Campaign Matrix)
  - Navigation links added to New Invoice and Accounting pages
- Added Bulk Distribute feature to Bulk Invoice Processor
  - New "Bulk Distribute" tab allows allocating processed invoices to company departments
  - Two modes: "By Invoice" (allocate each invoice) or "By Campaign" (view campaign totals)
  - Each line has company/brand/department/subdepartment dropdowns with manager display
  - Progress tracking shows allocated items count and value
  - "Save All to Accounting" button saves all allocated invoices to database
  - Uses the same `/api/submit` endpoint as New Invoice page (same validation, notifications, logging)
- Improved Meta invoice item parser for 100% extraction coverage
  - Renamed "campaigns" to "items" throughout bulk processor (supports all invoice types)
  - Dynamic line-by-line parsing instead of specific regex patterns for prefixes
  - Handles PDF text extraction quirks where items are concatenated after "RON"
  - Preprocesses text to split concatenated item headers (e.g., "RON[CA]" → "RON\n[CA]")
  - Pattern detection: item name on one line, date range + value on next line
  - Skip keywords filter out metadata (Afișări, Meta Platforms, Dublin, etc.)
  - Returns both `items` and `campaigns` keys for frontend compatibility
- Added automatic retry for cold start network errors in Bulk Distribute
  - `fetchWithRetry()` function with 2 retries and exponential backoff (1s, 2s delay)
  - Applied to `/api/submit` call for saving invoices
  - Applied to `/api/drive/upload` call for Drive upload
  - Applied to `/api/invoices/{id}/drive-link` PUT call for saving drive link
  - Fixes "Load failed" errors on first save attempt after cold start
- Added eFactura (Romanian e-invoice) parsing support
  - Detects eFactura format by presence of "RO eFactura" or "efactura" in text
  - Extracts invoice number, date, supplier, customer VAT from eFactura format
  - Parses line items with automatic NET to GROSS value conversion
  - Each line item has VAT rate extracted and applied: `gross = net * (1 + vat_rate/100)`
  - Items sum to invoice total (100%) for proper allocation percentage validation
- Added Google Ads invoice parsing in bulk processor
  - Detects "Google Ads" or "Google Ireland" in invoice text
  - Extracts campaign names and costs (e.g., "[CA] S Skoda modele")
  - Uses AI fallback for reliable extraction
  - Campaign values sum to 100% of invoice value
- Added health endpoint version for deployment verification (`/health` returns `version` field)
- Fixed role permission editing not persisting (can_edit_invoices was missing from API endpoints)
  - Added `can_edit_invoices` parameter to both `api_create_role` (POST) and `api_update_role` (PUT)
  - All 8 role permissions now properly saved: can_add_invoices, can_edit_invoices, can_delete_invoices, can_view_invoices, can_access_accounting, can_access_settings, can_access_connectors, can_access_templates
- Enhanced notification service with department-specific CC emails
  - `send_email()` now accepts optional `department_cc` parameter
  - Both global CC and department CC addresses receive notification copies
  - Duplicate CC addresses are automatically filtered out
  - Department CC is looked up via `get_department_cc_email(company, department)`
- Added connector infrastructure for automatic invoice fetching (DISABLED)
  - Buffer page (`/buffer`) - universal inbox for invoices from connectors
  - Google Ads connector with multi-account support and Playwright browser automation
  - Anthropic connector for billing invoice fetching
  - Connectors page (`/connectors`) with multi-account management UI
  - `get_connectors_by_type()` function in database.py for multi-account support
  - Feature temporarily disabled due to Google's security measures (passkeys, 2FA)
  - All connector routes return "Coming Soon" or redirect to accounting
  - API endpoints return 503 status with "feature coming soon" message
- Fixed dynamic currency display in summary tables (By Company, By Department, By Brand)
  - Summary queries now include currency grouping to show correct currency per row
  - Rows are grouped by entity + currency (e.g., same company appears twice if it has RON and EUR invoices)
  - Replaced hardcoded "RON" with dynamic `row.currency` in all three summary table render functions
  - Split values in By Brand table now also pass currency to formatColumnValue()

## Connector Infrastructure (DISABLED)

### Overview
The connector system allows automatic invoice fetching from external services. Currently **disabled** due to authentication challenges with Google's security measures.

### Components

**Buffer Page** (`/buffer` → redirects to `/accounting`)
- Universal inbox for invoices from all connectors
- Fetch buttons for each connector type (Anthropic, Google Ads)
- Checkbox selection for sending invoices to bulk processor
- Source badges showing invoice origin

**Connectors Page** (`/connectors` → shows "Coming Soon")
- Multi-account management for Google Ads
- Credential storage with encryption
- Connect/disconnect functionality

**Google Ads Connector** (`google_ads_connector.py`)
- Playwright browser automation for invoice fetching
- Persistent browser context with session cookies
- Multi-account support via `connectors` table
- Subprocess execution to avoid Flask asyncio conflicts
- Unique temp directories per session to avoid browser lock conflicts

**Anthropic Connector** (`anthropic_connector.py`)
- API-based billing invoice fetching
- Uses Anthropic API credentials

### Database Support
- `connectors` table stores connector configurations
- `get_connectors_by_type(type)` returns all connectors of given type
- Credentials stored encrypted in `credentials` JSON column
- Config options in `config` JSON column (e.g., account_id)

### Why Disabled
Google's authentication requires:
- Passkey/security key verification
- 2FA prompts that can't be automated
- Browser fingerprinting that blocks automation

Future options:
1. OAuth-based authentication (requires Google API access)
2. Manual session cookie import
3. Google Ads API integration (requires developer account)