# J.A.R.V.I.S. User Guide

> Last updated: 2026-02-16

## Table of Contents

- [📊 Accounting](#-accounting)
  - [Add Invoice](#add-invoice)
  - [Accounting Dashboard](#accounting-dashboard)
  - [e-Factura](#e-factura)
  - [Bank Statements](#bank-statements)
  - [Templates](#templates)
  - [Bulk Processor](#bulk-processor)
- [👥 HR](#-hr)
  - [Event Bonuses](#event-bonuses)
  - [Events Management](#events-management)
- [✅ Approvals](#-approvals)
  - [Approval Queue](#approval-queue)
  - [Delegations](#delegations)
  - [Flow Configuration](#flow-configuration)
- [⚙️ Core](#️-core)
  - [Settings](#settings)
  - [Profile](#profile)

---

## 📊 Accounting

### Add Invoice

**URL:** `/add-invoice`

Upload and process invoices with AI-powered parsing.

**Features:**
- **File Upload:** Drag & drop or click to upload PDF/image
- **AI Parsing:** Claude analyzes invoice and extracts data automatically
- **Template Selection:** Use saved templates for recurring suppliers
- **Manual Entry:** Override AI results or enter data manually

**Allocation Section:**
- Add multiple department allocations (must sum to 100%)
- Lock allocations to prevent auto-redistribution
- Set reinvoice destinations for cost recovery
- Auto-lookup responsible person from department structure

**Actions:**
| Button | Function |
|--------|----------|
| Parse Invoice | Run AI analysis on uploaded file |
| Save Distribution | Save invoice with allocations |
| Add Allocation | Add new department allocation row |
| Clear | Reset form |

---

### Accounting Dashboard

**URL:** `/accounting`

Central hub for viewing and managing all invoices.

**Tabs:**
| Tab | Description |
|-----|-------------|
| Invoices | Full invoice list with filters |
| By Company | Grouped by company |
| By Department | Grouped by department |
| By Brand | Grouped by brand |

**Features:**
- **Search:** Filter by supplier, invoice number, description
- **Date Range:** Filter by invoice date
- **Status Filters:** Invoice status, payment status
- **Column Config:** Show/hide and reorder columns
- **Presets:** Save and restore filter combinations
- **Tags:** Assign and filter by tags
- **Export:** Download as CSV

**Invoice Actions:**
| Action | Description |
|--------|-------------|
| View | Open invoice details modal |
| Edit | Modify invoice and allocations |
| Delete | Move to recycle bin |
| Drive | Open invoice file in Google Drive |

**Split Values Column:**
- Shows allocation breakdown
- Click +/- to expand/collapse details
- Yellow (→) indicates reinvoice destinations
- Lock icon shows retained allocations

---

### e-Factura

**URL:** `/accounting/efactura`

Import and process invoices from ANAF's e-Factura system.

**Tabs:**
| Tab | Description |
|-----|-------------|
| Unallocated | Invoices pending allocation (includes hidden) |
| Mappings | Supplier mapping rules (type, dept, brand) |

**Features:**
- **Sync from ANAF:** Fetch new invoices via OAuth
- **Duplicate Detection:** AI-powered duplicate matching
- **Supplier Mappings:** Default types/departments per supplier
- **Bulk Operations:** Select multiple invoices for batch actions

**Filters:**
- Company (buyer)
- Direction (Inbound/Outbound)
- Partner Type (Service, Merchandise, etc.)
- Hide Typed toggle
- Date range
- Search

**Actions:**
| Action | Description |
|--------|-------------|
| Send to Module | Create invoice in accounting system |
| Set Type | Assign partner type(s) |
| Set Department | Override department allocation |
| View Details | Show full invoice data |
| Export PDF | Download invoice as PDF |
| Mark Duplicate | Link to existing invoice |
| Ignore/Delete | Remove from unallocated list |

---

### Bank Statements

**URL:** `/statements/`

Parse bank statements and create invoices from transactions.

**Features:**
- **PDF Upload:** UniCredit statement parsing
- **Auto-Matching:** Regex patterns match vendors
- **Transaction List:** View all parsed transactions
- **Bulk Actions:** Ignore or invoice multiple items

**Transaction States:**
| Status | Description |
|--------|-------------|
| Pending | Awaiting review |
| Matched | Vendor identified via mapping |
| Ignored | Excluded from processing |
| Invoiced | Invoice created |

**URL:** `/statements/mappings`

Manage vendor pattern mappings.

**Mapping Fields:**
- Pattern (regex)
- Supplier name
- Supplier VAT
- Default type

---

### Templates

**URL:** `/templates`

Manage invoice parsing templates for recurring suppliers.

**Template Types:**
| Type | Description |
|------|-------------|
| Fixed | Static supplier info |
| Format | Regex-based extraction |

**Fields:**
- Supplier name/VAT
- Invoice number regex
- Date regex
- Value regex
- Currency

---

### Bulk Processor

**URL:** `/bulk`

Analyze multiple invoices for campaign/line item breakdown.

**Features:**
- Upload multiple PDFs
- Extract campaign costs (Meta, Google Ads)
- Aggregate by month/supplier/campaign
- Export detailed reports

---

## 👥 HR

### Event Bonuses

**URL:** `/hr/events/`

Manage employee bonuses for events.

**Features:**
- **Bonus List:** View all assigned bonuses
- **Filters:** Company, brand, department, month, year
- **Add Bonus:** Assign bonus to employee
- **Bulk Add:** Multiple employees at once
- **Export:** Download for payroll

**Bonus Fields:**
| Field | Description |
|-------|-------------|
| Employee | User from system |
| Event | Associated event |
| Participation Period | Start/end dates |
| Bonus Days | Days worked |
| Bonus Net | Amount to pay |
| Allocation Month | Payroll month |

**Lock System:**
- Bonuses lock on day 5 of following month
- January bonuses lock February 5th
- Admin users can edit after lock

---

### Events Management

**URL:** `/hr/events/events`

Create and manage events.

**Event Fields:**
- Name
- Company
- Brand
- Start/End date
- Description

---

## ✅ Approvals

### Approval Queue

**URL:** `/approvals`

Review and process approval requests assigned to you.

**Tabs:**
| Tab | Description |
|-----|-------------|
| My Queue | Requests waiting for your decision |
| My Requests | Requests you submitted |
| All Requests | All requests across the organization |
| Delegations | Manage approval delegations |

**Stat Cards:**
- Pending Queue (items awaiting your action)
- My Pending (your submitted requests still in progress)
- My Approved (your approved submissions)
- Total requests

**Queue Actions:**
| Action | Description |
|--------|-------------|
| Approve | Advance to next step (or final approval) |
| Reject | Reject the request (comment required) |
| Return | Send back to submitter for changes (comment required) |
| Escalate | Bump to next step's approver |
| Cancel | Cancel your own submitted request |

**Request Detail Dialog:**
- Click any request to open full details
- Shows: entity context, step progress bar, decision timeline, audit trail
- Action buttons at the bottom

**Sidebar Badge:**
- Red badge on the Approvals menu item shows your pending queue count
- Updates every 30 seconds

---

### Delegations

**URL:** `/approvals` → Delegations tab

Delegate your approval authority to another user (e.g. vacation coverage).

**Fields:**
| Field | Description |
|-------|-------------|
| Delegate To | User who will receive your approvals |
| Start Date | When delegation begins |
| End Date | When delegation expires |
| Reason | Optional note (e.g. "On vacation") |

- Active delegations are shown in a list with a Revoke button
- Expired delegations are automatically cleaned up by the system (hourly)

---

### Flow Configuration

**URL:** `/settings` → Approvals tab (Admin only)

Define approval workflows that control how entities get approved.

**Concepts:**
- **Flow** = a named workflow for a specific entity type (e.g. "Invoice Approval")
- **Step** = one stage in the flow (e.g. "Manager Review" → "Finance Approval")
- Steps are executed in order; each must be approved before the next begins

**Creating a Flow:**
1. Go to Settings → Approvals
2. Click **New Flow**
3. Fill in: Name, Entity Type (Invoice, e-Factura Invoice, etc.), Priority
4. Optionally set Auto-reject timeout (hours)
5. Save, then add Steps

**Adding Steps to a Flow:**
1. Expand the flow row
2. Click **Add Step**
3. Choose approver type:

| Approver Type | Description |
|---------------|-------------|
| Specific User | A named user must approve |
| Role | Any user with that role can approve |
| Department Manager | The manager of the entity's department |

4. Set optional: Min approvals, Requires all, Timeout hours, Reminder hours
5. Save — steps execute in the order shown

**How Matching Works:**
- When a user submits an entity, the engine finds all active flows for that entity type
- The flow with the highest priority is selected
- If no flow matches, submission fails with an error

**Entity Widget:**
- The ApprovalWidget appears on invoices (expanded row, edit dialog) and e-Factura detail dialog
- Shows current approval status, submit button, and history
- Compact mode (accounting rows) shows just a status badge

---

## ⚙️ Core

### Settings

**URL:** `/settings`

Platform configuration.

**Tabs:**
| Tab | Description |
|-----|-------------|
| Users | User accounts and permissions |
| Roles | Role definitions and permission matrix |
| Structure | Company → Brand → Dept mapping |
| Accounting | VAT rates, dropdown options, invoice config |
| HR | HR-specific settings |
| Themes | UI theme customization |
| Menus | Navigation menu configuration |
| Tags | Tag groups and definitions |
| Notifications | SMTP and email settings |
| Activity | System activity log |
| Approvals | Approval flow builder (see [Flow Configuration](#flow-configuration)) |
| Connectors | e-Factura OAuth and supplier types |
| AI Agent | LLM models, RAG config, data sources |

**User Roles:**
| Role | Permissions |
|------|-------------|
| User | View own invoices |
| Manager | View department invoices |
| Approver | Approve invoices |
| Admin | Full access |

---

### Profile

**URL:** `/profile`

Personal dashboard and activity.

**Tabs:**
| Tab | Description |
|-----|-------------|
| My Invoices | Invoices you created |
| HR Events | Your bonus history |
| Activity | Login and action history |

---

## Common Workflows

### Adding an Invoice
1. Go to **Add Invoice** (`/add-invoice`)
2. Upload PDF or image
3. Wait for AI parsing
4. Review extracted data
5. Add allocations (department, %, responsible)
6. Click **Save Distribution**

### Processing e-Factura
1. Go to **e-Factura** (`/accounting/efactura`)
2. Click **Sync from ANAF**
3. Check for duplicates (yellow banner)
4. Set department/type overrides
5. Select invoices → **Send to Module**

### Bank Statement Processing
1. Go to **Statements** (`/statements/`)
2. Upload UniCredit PDF
3. Review matched transactions
4. Add mappings for unknown vendors
5. Select → **Create Invoices**

### Submitting for Approval
1. Open an invoice (expand row or edit dialog) or e-Factura detail
2. Find the **Approval** widget
3. Click **Submit for Approval**
4. Optionally add a note
5. Click **Submit** — request enters the approval queue
6. Track status in **Approvals** → **My Requests**

### Approving a Request
1. Go to **Approvals** (`/approvals`)
2. Review items in **My Queue**
3. Click **Approve** for quick approval, or click the row for details
4. In the detail dialog: review context, add comment, then Approve/Reject/Return

### Managing Allocations
1. Go to **Accounting** (`/accounting`)
2. Find invoice → **Edit**
3. Modify allocations
4. Lock allocations to preserve values
5. Add reinvoice destinations if needed
6. **Save**

---

## Tips & Shortcuts

| Tip | Description |
|-----|-------------|
| **Column Config** | Click "Columns" to show/hide table columns |
| **Presets** | Save filter combinations for quick access |
| **Bulk Select** | Header checkbox selects all visible rows |
| **Tags** | Use tags to organize and filter invoices |
| **Search** | Most pages have a search box in the filter panel |
| **Recycle Bin** | Deleted items can be restored |
