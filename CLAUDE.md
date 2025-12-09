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
├── app.py           # Main Flask application and routes
├── database.py      # Database operations (PostgreSQL)
├── models.py        # Data models and structure loading
├── services.py      # Business logic for allocations
├── invoice_parser.py # AI-powered invoice parsing with Claude
├── drive_service.py # Google Drive integration
├── config.py        # Configuration settings
└── templates/       # Jinja2 HTML templates
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
- `GOOGLE_CREDENTIALS_JSON` - Google Drive API credentials

## Database Schema
- `invoices` - Invoice header records
- `allocations` - Department allocation splits
- `invoice_templates` - AI parsing templates per supplier
- `department_structure` - Company/department hierarchy
- `companies` - Company VAT registry for matching

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
- `allocation_value` - Calculated from invoice_value * allocation_percent
- `responsible` - Auto-populated from department_structure
- `reinvoice_to` - Optional company for reinvoicing
- `reinvoice_department` - Optional department within the reinvoice target company
- `reinvoice_subdepartment` - Optional subdepartment within the reinvoice target department

### Complex Reinvoice Feature
Allocations can be marked for reinvoicing to a specific company/department/subdepartment:
1. Check the "Reinvoice to:" checkbox on an allocation
2. Select the target company from the first dropdown
3. The department dropdown populates based on selected company (via `/api/departments/{company}`)
4. The subdepartment dropdown populates based on selected department (via `/api/subdepartments/{company}/{dept}`)
5. Reinvoice destination is displayed as: `Company / Department / Subdepartment`

This allows tracking which allocations need to be billed to another entity within the organization.

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

## Recent Changes
- Simplified database.py to PostgreSQL-only (removed SQLite)
- Added customer_vat_regex extraction for all template types (not just "format")
- Fixed Meta template invoice_number_regex to include capture groups
- Fixed English date format parsing (e.g., 'Nov 21, 2025' from Shopify/Google invoices)
- Fixed date serialization in API responses (was returning HTTP date format instead of ISO)
- Updated edit allocation modal to use single "Dedicated Company" dropdown (consistent with invoice input)
- Added smart split redistribution when adding/removing allocations in edit mode
- Added collapsible Split Values column with +/- toggle and allocation summary
- Added "By Brand" (Linie de business) tab view with Invoice #, Value, Split Values columns
