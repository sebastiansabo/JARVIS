# Invoice Auto-Archive — Implementation Plan

**Design spec:** `2026-06-05-invoice-auto-archive-design.md`
**Branch:** `dev`

---

## Phase 1: Database Schema + Migration

**Files to modify:**
- `jarvis/migrations/domains/schema_core.py`

**Changes:**
1. Add `archived_at TIMESTAMP DEFAULT NULL` column to `invoices` (IF NOT EXISTS migration)
2. Add `archive_after TIMESTAMP DEFAULT NULL` column to `invoices` (IF NOT EXISTS migration)
3. Create 3 partial indexes:
   - `idx_invoices_active_date` — active invoice queries (WHERE archived_at IS NULL AND deleted_at IS NULL)
   - `idx_invoices_archived` — archived invoice queries (WHERE archived_at IS NOT NULL AND deleted_at IS NULL)
   - `idx_invoices_pending_archive` — scheduler lookup (WHERE archive_after IS NOT NULL AND archived_at IS NULL)
4. Seed default archive settings in `notification_settings`:
   - `archive_enabled` = `true`
   - `archive_delay_hours` = `24`
   - `archive_trigger_status` = `processed`
   - `archive_job_interval_minutes` = `15`

**Verification:** Run app locally, confirm columns and indexes exist via `\d invoices` in psql.

---

## Phase 2: Backend — Repository Layer

**Files to modify:**
- `jarvis/accounting/invoices/repositories/invoice_repository.py`

**Changes:**

### 2a. Archive operation method
Add `archive_pending_invoices()` — bulk UPDATE where `archive_after <= NOW()` and `archived_at IS NULL`.

### 2b. Set/clear archive fields
Add `set_archive_after(invoice_id, archive_after_timestamp)` and `clear_archive_fields(invoice_id)` methods.

### 2c. Modify `get_all()` and `get_all_with_allocations()`
Add `archive_view` parameter (`'active'` | `'archived'` | `'all'`):
- `'active'` (default): existing `WHERE deleted_at IS NULL` becomes `WHERE archived_at IS NULL AND deleted_at IS NULL`
- `'archived'`: `WHERE archived_at IS NOT NULL AND deleted_at IS NULL`
- `'all'`: `WHERE deleted_at IS NULL` (same as today)

### 2d. Modify `get_count()` / summary methods
Pass through `archive_view` parameter to respect archive filtering.

### 2e. Add computed fields to SELECT
Add `archived_at`, `archive_after`, and computed `archive_pending` boolean to invoice SELECT queries.

**Verification:** Unit test — create invoice, set archive_after in past, call `archive_pending_invoices()`, confirm `archived_at` is set.

---

## Phase 3: Backend — Service Layer (Permission Guards + Status Hook)

**Files to modify:**
- `jarvis/accounting/invoices/services/invoice_service.py`

**Changes:**

### 3a. Archive permission guard in `update_invoice()`
After fetching `current_invoice`, check if `archived_at` is set. If so, only allow `Admin` and `Dep Contabilitate` roles. Return 403 for others.

### 3b. Delete guard
In delete methods (`soft_delete`, `permanent_delete`), block if `archived_at` is set. Return 403 for all roles.

### 3c. Status change hook
In `update_invoice()`, after successful update, detect status changes:
- If new status == configured `archive_trigger_status`:
  - Read `archive_delay_hours` from settings
  - Set `archive_after = NOW() + INTERVAL '{delay} hours'`
- If old status was trigger status and new status is different:
  - Clear `archive_after = NULL` and `archived_at = NULL`

### 3d. Read archive settings helper
Add `_get_archive_settings()` method that reads from `NotificationRepository().get_settings()` with the 4 archive keys. Cache in-memory for the request lifecycle.

**Verification:** Manual test — change invoice status to processed, verify `archive_after` is set. Change back, verify cleared.

---

## Phase 4: Backend — Settings API

**Files to modify:**
- `jarvis/core/settings/routes.py`

**Changes:**

### 4a. GET `/api/settings/archive`
Return current archive settings from `notification_settings` table. Login required.

### 4b. PUT `/api/settings/archive`
Update archive settings. Admin required. Validate:
- `archive_delay_hours`: integer 1-720
- `archive_job_interval_minutes`: integer 5-60
- `archive_trigger_status`: must exist in `dropdown_options` for `invoice_status`
- `archive_enabled`: boolean

Save each setting via `NotificationRepository().save_setting()`.

**Verification:** curl test — GET returns defaults, PUT updates, GET returns new values.

---

## Phase 5: Backend — Background Job

**Files to create:**
- `jarvis/tasks/archive_invoices.py`

**Files to modify:**
- `jarvis/tasks/cleanup.py`

**Changes:**

### 5a. Create `archive_invoices.py`
Function `archive_pending_invoices()`:
- Check `archive_enabled` setting; skip if disabled
- Call `InvoiceRepository().archive_pending_invoices()`
- Clear invoices cache on success
- Log count

### 5b. Register in `start_scheduler()`
Add job in `cleanup.py`:
```python
scheduler.add_job(
    archive_pending_invoices_task,
    'interval',
    minutes=15,  # default, read from settings on startup
    id='archive_invoices',
    replace_existing=True,
    misfire_grace_time=300,
    coalesce=True,
)
```

**Verification:** Temporarily set `archive_delay_hours=0`, create processed invoice, wait for job, confirm archived.

---

## Phase 6: Backend — Routes (Query Parameter)

**Files to modify:**
- `jarvis/accounting/invoices/routes/crud.py`
- `jarvis/accounting/invoices/routes/search.py`

**Changes:**

### 6a. Add `archive_view` query parameter
`GET /api/db/invoices?archive_view=active|archived|all` — pass through to repository.

### 6b. Add archive fields to response
Ensure `archived_at`, `archive_after`, `is_archived`, `archive_pending` are included in invoice list and detail responses.

**Verification:** curl — `/api/db/invoices?archive_view=archived` returns only archived invoices.

---

## Phase 7: Frontend — Types + API

**Files to modify:**
- `jarvis/frontend/src/types/invoices.ts`
- `jarvis/frontend/src/types/settings.ts`
- `jarvis/frontend/src/api/invoices.ts`
- `jarvis/frontend/src/api/settings.ts`

**Changes:**

### 7a. Invoice type update
Add `archived_at`, `archive_after`, `is_archived`, `archive_pending` to `Invoice` interface.

### 7b. Settings type
Add `ArchiveSettings` interface:
```typescript
interface ArchiveSettings {
  archive_enabled: boolean
  archive_delay_hours: number
  archive_trigger_status: string
  archive_job_interval_minutes: number
}
```

### 7c. API functions
- `invoicesApi.getInvoices(filters)` — add `archive_view` to filters
- `settingsApi.getArchiveSettings()` — GET `/api/settings/archive`
- `settingsApi.updateArchiveSettings(data)` — PUT `/api/settings/archive`

### 7d. InvoiceFilters type
Add `archive_view?: 'active' | 'archived' | 'all'` to `InvoiceFilters`.

**Verification:** TypeScript compiles without errors.

---

## Phase 8: Frontend — Invoice List (Archive View Toggle + Badge)

**Files to modify:**
- `jarvis/frontend/src/pages/Accounting/index.tsx`
- `jarvis/frontend/src/components/shared/StatusBadge.tsx`

**Changes:**

### 8a. Archive view toggle
Add segmented button group near the existing bin toggle:
```
[Active] [Archived] [All]    [🗑 Bin]
```
- Defaults to `Active`
- State stored in component (not persisted — always defaults to Active on page load)
- Changes `archive_view` param in API query

### 8b. "Archivation in X hours" badge
For invoices where `archive_pending === true`, show amber badge next to status:
- Text: `"Archivation in {remaining_time}"` computed from `archive_after` timestamp
- Tooltip with exact archive timestamp

### 8c. Read-only mode for archived view
When `archive_view === 'archived'`:
- Disable inline status/payment dropdowns (unless user is Admin/Conta — check via `useAuth()` role)
- Hide edit button in row actions (unless Admin/Conta)
- Hide delete button always
- Subtle gray/slate background tint on archived rows

### 8d. StatusBadge update
Add `archived` color mapping (gray/slate).

### 8e. Archived count badge
Show count on "Archived" tab button, similar to bin count badge.

**Verification:** Visual — toggle between views, verify badges, verify read-only enforcement.

---

## Phase 9: Frontend — Settings AccountingTab (Archive Settings Card)

**Files to modify:**
- `jarvis/frontend/src/pages/Settings/AccountingTab.tsx`

**Changes:**

Add `ArchiveSettingsSection` component at the top of AccountingTab (before VatRatesSection):

- Card with title "Invoice Archiving" and description
- Toggle: Enable Auto-Archive (`archive_enabled`)
- Dropdown: Trigger Status (`archive_trigger_status`) — populated from invoice_status dropdown options
- Number input: Archive Delay in hours (`archive_delay_hours`) with min/max validation
- Number input: Job Interval in minutes (`archive_job_interval_minutes`) with min/max validation
- Info text explaining the behavior
- Save button — calls `settingsApi.updateArchiveSettings()`
- Toast on success/error
- Uses `useQuery` + `useMutation` pattern matching existing sections

**Verification:** Visual — open Settings → Accounting, change values, save, refresh, values persist.

---

## Phase 10: Build + Deploy Verification

**Steps:**
1. `cd jarvis/frontend && npm run build` — verify zero TypeScript/build errors
2. `pytest tests/ -x -q` — verify all tests pass
3. `python3 -m py_compile jarvis/app.py` — verify imports resolve
4. `git status` — ensure all files committed
5. Test full flow locally:
   - Create invoice → set status to "Processed" → see "Archivation in 24h" badge
   - Check Settings → Accounting → Archive Settings card renders with defaults
   - Change delay to 0h → wait for job → verify invoice moves to Archived view
   - Switch to Archived view → verify invoice appears, is read-only
   - Switch to All view → verify both active and archived appear
   - As non-Admin user → verify cannot edit archived invoice

---

## Commit Strategy

| Commit | Phase | Message |
|--------|-------|---------|
| 1 | Phase 1 | `feat(db): add archived_at, archive_after columns and archive indexes to invoices` |
| 2 | Phase 2-3 | `feat(invoices): add archive repository methods, permission guards, and status hook` |
| 3 | Phase 4-5 | `feat(settings): add archive settings API and background archive job` |
| 4 | Phase 6 | `feat(invoices): add archive_view query parameter to invoice list routes` |
| 5 | Phase 7-9 | `feat(frontend): add archive view toggle, pending badge, and archive settings UI` |
| 6 | Phase 10 | `chore(invoices): build verification and final cleanup` |
