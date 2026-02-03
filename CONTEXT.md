# Bugetare - Application Context

## What is Bugetare?

Bugetare is an internal budget allocation system designed for a Romanian automotive group (Auto World). It manages marketing invoice processing and cost allocation across multiple companies, brands, and departments.

## Business Domain

### Organizational Structure
The system serves a multi-company structure:
- **Companies**: Multiple legal entities (e.g., Auto World SRL, Dacia Service)
- **Brands**: Business lines within companies (e.g., Ford, Dacia, Hyundai)
- **Departments**: Functional units (e.g., Marketing, Sales, Service)
- **Subdepartments**: Specialized teams within departments

### Core Workflow
1. **Invoice Upload**: User uploads a vendor invoice (PDF/image) + optional attachments
2. **AI Parsing**: Claude extracts invoice data (supplier, amount, date, VAT)
3. **Company Matching**: Customer VAT is matched to internal companies
4. **Cost Allocation**: Invoice cost is split across departments (percentages must sum to 100%)
5. **Reinvoicing**: Allocations can be flagged for internal reinvoicing to other entities
6. **Notifications**: Department managers receive email alerts for new allocations
7. **Drive Storage**: Invoices + attachments are archived in Google Drive with Year/Month/Company/Invoice structure
8. **Image Compression**: Attachment images (PNG/JPEG) are compressed via TinyPNG before upload

### Bulk Processing Workflow (`/bulk`)
1. **Multi-Upload**: Drag-and-drop multiple PDF invoices
2. **Auto-Detection**: System detects invoice type (Meta, Google Ads, eFactura, generic)
3. **Item Extraction**: Line items/campaigns extracted from invoices
4. **Summary Views**: By invoice, by item/campaign, by month, by supplier
5. **Bulk Distribute**: Allocate all processed invoices to departments in one batch
6. **Excel Export**: Multi-sheet report with all breakdowns

## Key Concepts

### Allocation
An allocation splits an invoice cost to a specific department:
- **Allocation Percent**: The percentage of the invoice assigned (e.g., 50%)
- **Allocation Value**: The monetary amount (calculated from invoice value × percent, or net value if VAT subtracted)
- **Locked**: Locked allocations don't change during redistribution
- **Comment**: Optional text comment for notes about the allocation

### VAT Subtraction
For invoices where allocations should be based on net value (excluding VAT):
- **Subtract VAT**: Checkbox to enable VAT subtraction
- **VAT Rate**: Dropdown with configurable rates (default: 19%, 9%, 5%, 0%)
- **Net Value**: Automatically calculated as Invoice Value / (1 + VAT_Rate/100)
- When enabled, allocation values use net value instead of gross invoice value

### Reinvoicing
Internal billing between entities:
- Original allocation to Department A
- Reinvoice to Company B / Department C
- Both the original and reinvoice department managers are notified

### Responsables
Department managers who receive allocation notifications:
- Assigned to specific departments
- Can be enabled/disabled for notifications
- Receive emails in Romanian with allocation details

## Technical Architecture

### Backend (Python/Flask)
```
jarvis/
├── app.py                      # Main Flask application
├── database.py                 # PostgreSQL operations, migrations
├── models.py                   # Data models (DepartmentUnit, InvoiceAllocation)
├── services.py                 # Company VAT matching utilities
├── core/                       # Core Platform (shared across sections)
│   ├── auth/                   # Authentication module
│   ├── services/               # Shared services
│   │   ├── drive_service.py    # Google Drive OAuth integration
│   │   ├── image_compressor.py # TinyPNG image compression
│   │   ├── currency_converter.py # BNR exchange rates (EUR/RON)
│   │   └── notification_service.py # SMTP email notifications
│   ├── settings/               # Platform settings
│   └── connectors/efactura/    # ANAF e-Factura connector
├── accounting/                 # Accounting Section
│   ├── bugetare/               # Invoice Budget Allocation
│   │   ├── routes.py           # Invoice routes
│   │   ├── invoice_parser.py   # Claude AI + regex template parsing
│   │   └── bulk_processor.py   # Bulk processing
│   └── statements/             # Bank Statement Parsing
└── hr/events/                  # HR Events module
```

### Frontend (Jinja2 + Bootstrap)
```
templates/
├── core/                       # Core templates
│   ├── login.html              # Authentication
│   ├── settings.html           # Users, VAT registry, notifications
│   ├── apps.html               # Apps landing page
│   └── guide.html              # User guide
├── accounting/
│   ├── bugetare/
│   │   ├── index.html          # Add Invoice page
│   │   ├── accounting.html     # Dashboard
│   │   ├── templates.html      # Template management
│   │   ├── bulk.html           # Bulk processing
│   │   └── efactura.html       # e-Factura unallocated invoices
│   └── statements/
│       └── index.html          # Bank statement upload
└── hr/events/                  # HR templates
```

### Database Schema (PostgreSQL)
- `invoices` - Invoice records with supplier, dates, amounts, currency, VAT fields
- `allocations` - Cost splits per invoice (company, dept, percent, value, locked)
- `invoice_templates` - Regex patterns for automated parsing
- `department_structure` - Organizational hierarchy
- `companies` - VAT registry for company matching
- `users` - Application users with bcrypt passwords
- `responsables` - Department managers for notifications
- `notification_log` - Email delivery tracking
- `notification_settings` - SMTP configuration
- `user_events` - Activity audit log (login, invoice CRUD, password changes)
- `vat_rates` - VAT rate definitions (id, name, rate)
- `efactura_invoices` - e-Factura invoices from ANAF (with override columns)
- `efactura_supplier_mappings` - Supplier categorization with default department/subdepartment
- `efactura_partner_types` - Partner types (Service, Merchandise)

## Key Features

### AI Invoice Parsing
- **Template Mode**: Regex patterns for known suppliers (Meta, Google Ads)
- **AI Mode**: Claude claude-sonnet-4-20250514 vision as fallback for unknown invoices
- Auto-detects template by supplier VAT in invoice text

### Currency Conversion
- Fetches BNR (National Bank of Romania) exchange rates
- Converts all invoices to RON and EUR
- Stores original currency + both converted values

### Invoice Attachments
- Upload additional files (images, PDFs, docs) with invoices
- Max 5MB per file
- Attachments stored in same Drive folder as main invoice
- Folder icon in Accounting list opens invoice's Drive folder
- Images (PNG/JPEG) automatically compressed via TinyPNG API

### Smart Allocation Redistribution
- Adding new allocation rows redistributes percentages
- **Lock Feature**: Lock icon prevents allocation from being redistributed
- Validation: Total must equal 100% (allows 0.1% overdraft for rounding)

### Email Notifications
- SMTP integration (Office365/Exchange supported)
- Romanian language emails
- HTML + plain text format
- Global CC option
- Separate sections for allocation and reinvoice details

### e-Factura Integration
ANAF RO e-Invoicing connector for automatic invoice import:
- **Sync from ANAF**: Fetches received invoices (Primite) from ANAF SPV
- **XML Parsing**: UBL 2.1 format extraction of seller/buyer info, amounts, dates
- **Supplier Mappings**: Categorize suppliers with types (Service, Merchandise) and default department/subdepartment
- **Invoice Overrides**: Override type, department, subdepartment at invoice level
- **"Hide Typed" Filter**: Toggle to hide invoices with assigned partner types
- **Send to Module**: Transfer e-Factura invoices to main JARVIS Invoice Module for allocation
- **Tab Caching**: Client-side caching prevents API reloads on tab switch

### Activity Logs (Admin-only)
Audit trail for user actions in the Settings → Activity Logs tab:
- **Event Types**: login, logout, login_failed, password_changed, invoice_created, invoice_updated, invoice_deleted, invoice_restored, invoice_permanently_deleted, allocations_updated
- **Filterable**: By user, event type, and date range
- **Tracks**: User email, IP address, user agent, timestamp, description
- **API Endpoints**: `/api/events`, `/api/events/types`

## Deployment

### DigitalOcean App Platform
- Docker container (Dockerfile + Gunicorn)
- PostgreSQL managed database
- Auto-deploy on push to main branch
- Environment variables: DATABASE_URL, ANTHROPIC_API_KEY, GOOGLE_OAUTH_TOKEN

### Local Development
```bash
source venv/bin/activate
DATABASE_URL='postgresql://user@localhost:5432/defaultdb' PORT=5001 python app/app.py
```

## API Endpoints

### Invoice Operations
- `POST /api/save-invoice` - Create invoice with allocations
- `GET /api/invoices` - List all invoices with allocations
- `PUT /api/invoices/<id>` - Update invoice details
- `PUT /api/invoices/<id>/allocations` - Update allocations
- `PUT /api/allocations/<id>/comment` - Update allocation comment
- `DELETE /api/invoices/<id>` - Soft delete invoice

### Parsing
- `POST /api/parse-invoice` - AI parse uploaded file
- `POST /api/parse-with-template` - Parse using specific template

### Attachments
- `POST /api/drive/upload-attachment` - Upload attachment to invoice's Drive folder
- `GET /api/drive/folder-link` - Get Drive folder URL from file link

### Structure
- `GET /api/companies` - List companies
- `GET /api/structure` - Full department hierarchy
- `GET /api/departments/<company>` - Departments for company
- `GET /api/subdepartments/<company>/<dept>` - Subdepartments

### Settings
- `GET/POST /api/notification-settings` - SMTP configuration
- `GET/POST/PUT/DELETE /api/responsables` - Manager management
- `GET /api/events` - Activity logs with filters (user, type, date_from, date_to)
- `GET /api/events/types` - List of distinct event types

## User Roles

Role-based access via `can_access_settings` permission:
- **Admin users** (`can_access_settings=true`): Full access including Settings page and Activity Logs
- **Regular users** (`can_access_settings=false`): Can add/view invoices but cannot access Settings

Future: Additional roles like viewer, department manager.

## Localization

- UI: English with Romanian labels where appropriate
- Emails: Romanian
- Dates: ISO storage, DD.MM.YYYY display
- Currency: RON primary, EUR secondary

## Performance Optimizations

### Compression
- Flask-Compress enabled for gzip/brotli compression
- 84% size reduction on HTML pages (188KB → 29KB)

### Caching
- ETag headers on JSON API responses (304 Not Modified support)
- Cache-Control headers:
  - API endpoints: 5 minutes (`private, max-age=300`)
  - Login/Guide pages: 1 hour (`private, max-age=3600`)
  - Health endpoint: `no-cache` (always validate)

### Session Management
- Remember Me cookie: 30 days duration
- Secure cookie settings (HttpOnly, SameSite=Lax)

### Cold Start Prevention
- Health check endpoint (`/health`) for uptime monitoring
- DigitalOcean health check configured (10s period)
- Loading overlay on login page during cold starts

## User Guide

Built-in documentation available at `/guide` covering:
- Adding invoices and AI parsing
- Cost allocation and locking
- VAT subtraction feature
- Multi-destination reinvoicing
- Dashboard navigation and filters
- Settings management (admin)
- Keyboard shortcuts and tips

Access via user dropdown menu → "User Guide" on any page.
