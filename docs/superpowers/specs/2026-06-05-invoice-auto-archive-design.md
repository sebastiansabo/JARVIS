# Invoice Auto-Archive Design Spec

## Problem

All invoices (current and historical) live in the same `invoices` table with no separation. Every query — list, search, summary, dashboard — scans the entire table. Accountants typically work with current-period invoices but pay the query cost of years of historical data.

## Solution

Auto-archive invoices 24 hours after their status changes to `processed`. Archived invoices move out of the default active view but remain fully searchable. A "pending archive" badge warns accountants during the 24h grace period.

## Behavior

### Archive Lifecycle

1. **Invoice status set to `processed`** → `archive_after` column set to `NOW() + INTERVAL '1 day'`
2. **During 24h window** → invoice stays in active view, shows **"Archivation in 1 day"** badge
3. **After 24h** → background job sets `archived_at = NOW()`, invoice moves to archive view
4. **If status changed away from `processed` during window** → `archive_after` cleared, archiving cancelled

### Archive Rules

- Archived invoices are **read-only** for most roles
- Only **Admin** and **Dep Contabilitate** roles can edit archived invoices
- Archived invoices cannot be deleted (soft or hard)
- No manual unarchive — if Admin/Conta changes status back from `processed`, the invoice returns to active view automatically (`archived_at` cleared)

### Permission Matrix Update

| Action | Viewer | User | HR | Manager | Dep Contabilitate | Admin |
|--------|--------|------|-----|---------|-------------------|-------|
| View archived invoices | Yes | Yes | Yes | Yes | Yes | Yes |
| Search archived invoices | Yes | Yes | Yes | Yes | Yes | Yes |
| Edit archived invoices | No | No | No | No | **Yes** | **Yes** |
| Delete archived invoices | No | No | No | No | No | No |
| Change archived status | No | No | No | No | **Yes** | **Yes** |

## Database Changes

### Schema: `invoices` table

Add two columns:

```sql
ALTER TABLE invoices ADD COLUMN archived_at TIMESTAMP DEFAULT NULL;
ALTER TABLE invoices ADD COLUMN archive_after TIMESTAMP DEFAULT NULL;
```

### Indexes

```sql
-- Fast active invoice queries (most common path)
CREATE INDEX idx_invoices_active_date ON invoices(invoice_date DESC)
  WHERE archived_at IS NULL AND deleted_at IS NULL;

-- Fast archive queries
CREATE INDEX idx_invoices_archived ON invoices(archived_at DESC)
  WHERE archived_at IS NOT NULL AND deleted_at IS NULL;

-- Scheduler: find invoices ready to archive
CREATE INDEX idx_invoices_pending_archive ON invoices(archive_after)
  WHERE archive_after IS NOT NULL AND archived_at IS NULL;
```

## Backend Changes

### 1. Migration (`schema_core.py`)

Add `archived_at` and `archive_after` columns with conditional migration (IF NOT EXISTS pattern matching existing codebase).

### 2. Archive Scheduler

New function in `invoice_repository.py`:

```python
def archive_pending_invoices(self):
    """Archive invoices whose archive_after has passed. Returns count archived."""
    def _work(cursor):
        cursor.execute('''
            UPDATE invoices
            SET archived_at = CURRENT_TIMESTAMP
            WHERE archive_after IS NOT NULL
              AND archive_after <= CURRENT_TIMESTAMP
              AND archived_at IS NULL
              AND deleted_at IS NULL
            RETURNING id
        ''')
        return cursor.rowcount
    return self._execute_in_transaction(_work)
```

Triggered by a periodic background task (Flask scheduler or cron endpoint), running every 15 minutes.

### 3. Status Change Hook (`invoice_service.py`)

When status changes to `processed`:
- Set `archive_after = NOW() + INTERVAL '1 day'`

When status changes away from `processed`:
- Clear `archive_after = NULL`
- Clear `archived_at = NULL` (if already archived, unarchive)

### 4. Query Modifications (`invoice_repository.py`)

All existing list/summary queries gain an `archive_view` parameter:

- `'active'` (default): `WHERE archived_at IS NULL AND deleted_at IS NULL`
- `'archived'`: `WHERE archived_at IS NOT NULL AND deleted_at IS NULL`
- `'all'`: `WHERE deleted_at IS NULL`

### 5. Edit Permission Guard (`invoice_service.py`)

In `update_invoice()`, add check:

```python
if current_invoice.get('archived_at'):
    if user.role_name not in ('Admin', 'Dep Contabilitate'):
        return ServiceResult(
            success=False,
            error='Archived invoices are read-only. Only Admin or Contabilitate can edit.',
            status_code=403,
        )
```

### 6. Delete Guard (`invoice_service.py`)

Block all delete operations on archived invoices:

```python
if current_invoice.get('archived_at'):
    return ServiceResult(
        success=False,
        error='Archived invoices cannot be deleted.',
        status_code=403,
    )
```

### 7. API Response Enhancement

Add computed fields to invoice API responses:
- `is_archived: boolean` — whether `archived_at IS NOT NULL`
- `archive_pending: boolean` — whether `archive_after IS NOT NULL AND archived_at IS NULL`
- `archive_after: string | null` — ISO timestamp of pending archive

### 8. New API Endpoint

```
GET /api/db/invoices/archived — returns archived invoices with same filters as active
```

Or reuse existing endpoint with `?archive_view=active|archived|all` query parameter.

## Frontend Changes

### 1. Type Update (`types/invoices.ts`)

```typescript
export interface Invoice {
  // ... existing fields ...
  archived_at: string | null
  archive_after: string | null
  is_archived: boolean
  archive_pending: boolean
}
```

### 2. View Toggle (`index.tsx`)

Replace or extend the existing bin toggle area with an archive view selector:

```
[Active] [Archived] [All]    [🗑 Bin]
```

- **Active** (default): shows non-archived invoices
- **Archived**: shows archived invoices only
- **All**: shows everything
- Bin toggle remains separate (orthogonal to archive)

### 3. "Archivation in 1 day" Badge

For invoices where `archive_pending === true`, render a badge next to the status:

- Color: amber/orange
- Text: **"Archivation in 1 day"** (or countdown if < 1 day remaining)
- Position: next to the status badge in the table row

### 4. Read-Only Mode for Archived Invoices

When viewing archived invoices:
- Disable inline status/payment dropdowns (unless Admin/Conta)
- Hide edit button in row actions (unless Admin/Conta)
- Hide delete button always
- Show "Archived" visual indicator (subtle background tint or icon)

### 5. StatusBadge Update (`StatusBadge.tsx`)

Add `archived` status color mapping (e.g., gray/slate for archived state).

## Configurable Archive Settings (Settings → Accounting)

A new **"Invoice Archiving"** card in the AccountingTab settings page. All values stored as key-value pairs in `notification_settings` table (same pattern as HR bonus lock day).

### Settings Fields

| Setting Key | Label | Type | Default | Description |
|---|---|---|---|---|
| `archive_enabled` | Enable Auto-Archive | Toggle (on/off) | `true` | Master switch — when off, no archiving happens |
| `archive_delay_hours` | Archive Delay | Number input (hours) | `24` | Hours to wait after status becomes `processed` before archiving. Min: 1, Max: 720 (30 days) |
| `archive_trigger_status` | Trigger Status | Dropdown | `processed` | Which invoice status triggers archiving. Populated from `invoice_status` dropdown options |
| `archive_job_interval_minutes` | Job Interval | Number input (minutes) | `15` | How often the background job checks for invoices to archive. Min: 5, Max: 60 |

### Settings UI Card

```
┌─────────────────────────────────────────────────────────┐
│ Invoice Archiving                                       │
│ Configure automatic archiving of processed invoices.    │
│                                                         │
│ Enable Auto-Archive          [====ON====]               │
│                                                         │
│ Trigger Status               [Processed ▾]              │
│ Archive Delay                [24] hours                  │
│ Background Job Interval      [15] minutes               │
│                                                         │
│ ℹ Invoices with the trigger status will show an         │
│   "Archivation in X hours" badge and be automatically   │
│   archived after the delay period.                      │
│                                                         │
│                                        [Save Settings]  │
└─────────────────────────────────────────────────────────┘
```

### API Endpoints

```
GET  /api/settings/archive     → returns current archive settings
PUT  /api/settings/archive     → updates archive settings (Admin only)
```

Response format:
```json
{
  "success": true,
  "settings": {
    "archive_enabled": true,
    "archive_delay_hours": 24,
    "archive_trigger_status": "processed",
    "archive_job_interval_minutes": 15
  }
}
```

### Backend Integration

- **Status change hook** reads `archive_trigger_status` and `archive_delay_hours` from settings (cached) instead of hardcoded values
- **Background job** reads `archive_job_interval_minutes` on startup and reschedules if changed via settings
- **Archive badge** text dynamically shows the configured delay (e.g., "Archivation in 24h" or "Archivation in 3 days")
- When `archive_enabled = false`, the status change hook skips setting `archive_after`, and the background job skips execution

## Background Job

Registered in `tasks/cleanup.py` using APScheduler (existing scheduler infrastructure with file-lock guard for multi-worker safety).

New task file: `tasks/archive_invoices.py`

```python
def archive_pending_invoices():
    """Archive invoices whose archive_after has passed."""
    from core.notifications.repositories import NotificationRepository
    settings = NotificationRepository().get_settings()
    if settings.get('archive_enabled', 'true') != 'true':
        return
    
    from accounting.invoices.repositories.invoice_repository import InvoiceRepository
    repo = InvoiceRepository()
    count = repo.archive_pending_invoices()
    if count:
        logger.info(f'Archived {count} invoices')
        clear_invoices_cache()
```

Registered in `start_scheduler()` with configurable interval (default 15 minutes).

## Testing

- Set invoice to `processed` → verify `archive_after` is set to +24h
- Wait (or manually advance) past 24h → verify `archived_at` is set
- Change status back from `processed` during window → verify archive cancelled
- Query with `archive_view=active` → archived invoices excluded
- Query with `archive_view=archived` → only archived invoices
- Try editing archived invoice as User role → 403
- Try editing archived invoice as Admin → success
- Try deleting archived invoice → 403 for all roles
- Verify cache invalidation after archive job runs
