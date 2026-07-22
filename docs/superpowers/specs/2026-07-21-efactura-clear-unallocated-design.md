# e-Factura — Unallocated Cleanup: Manual "Clear" Button + 10/10 Auto-Lifecycle

**Date:** 2026-07-21
**Status:** Approved (brainstorming) — pending implementation plan

## Problem

The e-Factura Unallocated tab accumulates thousands of imported invoices (10,006 at time of writing). Two gaps:

1. No way to bulk-clear the list on demand (only per-row / per-page actions today).
2. Stale unallocated invoices are already auto-purged, but by a **single-stage hard delete at 15 days with no recovery window** — too aggressive and unrecoverable.

The user wants: (a) a manual per-company **Clear** button, and (b) a safer automatic **two-stage lifecycle** — 10 days unallocated → Bin (recoverable), then 10 more days in Bin → permanent delete.

## Verified facts (against the codebase)

- e-Factura import **persists** rows into Postgres `efactura_invoices` (`services/sync_service.py::import_from_anaf`). The Unallocated list is a plain `SELECT`, not a live ANAF fetch.
- **"Unallocated" is a computed predicate**, not a status column:
  `jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL`
  (`repositories/invoice_repository.py::list_unallocated`).
- An invoice leaves the list when **allocated / transferred to accounting** (`send_to_module` sets `jarvis_invoice_id`, an FK to the main `invoices` table), **hidden** (`ignored = TRUE`), or **deleted / binned** (`deleted_at` set).
- Company filter = **`company_id` (number)**, local state in `UnallocatedTab.tsx` (`filters.company_id`); "all companies" = `undefined`. The Unallocated **count badge** (`getUnallocatedCount`) is **global** (no filter params).
- **Age column = `created_at`** (import timestamp). There is no `imported_at`; `issue_date` can predate import by weeks, so it is not used for age.
- **A scheduler already exists and already runs this class of job.** `jarvis/tasks/cleanup.py::start_scheduler()` (APScheduler `BackgroundScheduler`, single-worker file lock) registers ~30 jobs, bootstrapped from `jarvis/app.py`. The existing e-Factura job `cleanup_old_unallocated` runs every 6h via `jarvis/tasks/efactura.py::cleanup_old_unallocated_invoices()` and calls `delete_old_unallocated(days=15)` — a **HARD `DELETE FROM efactura_invoices`** (in `repositories/supplier_mapping_repository.py::delete_old_unallocated`, exposed on the invoice repo via mixin). `archive_invoices.py` is a good template for a settings-configurable, soft variant.

## Safety guarantee (cannot touch transferred/accounting invoices)

Transferred = allocated = `jarvis_invoice_id IS NOT NULL`. Every operation below carries `jarvis_invoice_id IS NULL` in its predicate, so **no allocated invoice is ever selected**. Even if one were, soft-delete only sets `deleted_at` on the `efactura_invoices` mirror row; the accounting invoice is a separate row in the `invoices` table and is never touched.

---

## Part 1 — Manual per-company "Clear" button

### Behavior
Soft-delete (→ Bin, recoverable) every currently-filtered unallocated invoice **for the selected company**, respecting active `direction` / date-range / `search` filters. "Clear exactly what I'm looking at, for this company."

### Placement
Inside `jarvis/frontend/src/pages/EFactura/UnallocatedTab.tsx`'s toolbar row (next to the company `Select` / column-toggle) — **not** the `index.tsx` header, because `filters.company_id` and `search` live in `UnallocatedTab`. Destructive-styled `Trash2` button labeled "Clear".

### All-companies guard
When `company_id === undefined`, the button is **disabled** with tooltip *"Select a company to clear."* No accidental all-company wipe.

### Flow
1. On click, fetch `efacturaApi.getUnallocatedIds({ ...filters, search })` — already scoped to `company_id` + active filters; yields the exact ID set and its length `N`.
2. `AlertDialog`: *"Clear N unallocated invoices for {companyName} to the Bin? You can restore them from the Bin."* — `N` is the fetched count (the global badge would be misleading).
3. Confirm → `efacturaApi.bulkDelete(ids)` → `POST /efactura/api/invoices/bulk-delete`, body `{ invoice_ids: ids }` (soft-delete → `deleted_at = NOW()`). Chunk into batches of ~5,000 IDs if the set is large (Postgres ~65,535 bound-param limit).
4. Success → invalidate query keys `['efactura-unallocated', ...]`, `['efactura-unallocated-count']`, Bin/hidden queries; toast *"Cleared N invoices to Bin."*
5. Error → toast; no cache invalidation.

### Backend
**No new endpoint.** Reuses existing `GET /efactura/api/invoices/unallocated/ids` (honors `company_id`, `direction`, dates, `search`, `hide_typed`) and `POST /efactura/api/invoices/bulk-delete` (soft-delete, no app-level batch cap).

### Edge cases
All-companies view → disabled. `N = 0` → disabled. Large `N` → chunked bulk-delete with a pending/spinner state. Error → toast, list unchanged.

---

## Part 2 — Automatic 10/10 two-stage lifecycle

Replaces the existing single-stage 15-day hard delete with a recoverable two-stage flow. Both stages run inside the **existing** 6-hourly job (rename/extend `cleanup_old_unallocated_invoices` in `jarvis/tasks/efactura.py`; keep its registration in `cleanup.py`). No new scheduler infrastructure.

Thresholds are module constants for v1 (YAGNI on a settings UI): `UNALLOCATED_BIN_DAYS = 10`, `BIN_PURGE_DAYS = 10`. (Future: lift into `notification_settings` following the `archive_invoices` pattern.)

### Stage 1 — auto soft-delete to Bin (recoverable)
Unallocated invoices whose **import age** exceeds 10 days move to the Bin.

New repo method (soft variant of `delete_old_unallocated`):
```sql
UPDATE efactura_invoices
SET deleted_at = NOW()
WHERE jarvis_invoice_id IS NULL   -- unallocated (never allocated/transferred)
  AND ignored = FALSE             -- not hidden
  AND deleted_at IS NULL          -- not already binned
  AND created_at < NOW() - INTERVAL '10 days';
```
Returns the affected-row count for logging.

### Stage 2 — purge Bin after 10 days (permanent)
Any unallocated invoice sitting in the Bin for 10+ days is permanently removed — regardless of how it got there (auto-timer, manual Clear button, or per-row delete). The Bin is a uniform 10-day recovery window for all deletions.

Repurposes / mirrors the existing hard-delete:
```sql
DELETE FROM efactura_invoices
WHERE jarvis_invoice_id IS NULL   -- never hard-delete an allocated invoice
  AND deleted_at IS NOT NULL      -- currently in the Bin
  AND deleted_at < NOW() - INTERVAL '10 days';
```
Returns the deleted-row count for logging.

### Job wiring
- One task function runs Stage 1 then Stage 2 per invocation, every 6h (existing cadence), logging both counts (`soft-deleted N, purged M`), matching existing job logging style.
- The current `delete_old_unallocated(days=15)` hard-delete call is removed from the scheduled path (its 15-day behavior is superseded by 10/10).
- The manual `POST /api/invoices/cleanup-old` admin route may remain as an escape hatch but is now largely redundant; leaving it unchanged is acceptable (out of scope to modify).

### Interaction with the manual Clear button
The Clear button soft-deletes to the Bin, so cleared invoices enter Stage 2 and auto-purge after 10 days — one consistent lifecycle, no special-casing.

### Data-safety note
Stage 2 is a **hard delete**, which is an exception to the CLAUDE.md "soft-delete financial data" rule. This is already an existing exception (the current job hard-deletes at 15 days). The new design is strictly safer: a 10-day recoverable Bin window precedes the purge, and allocated/transferred invoices are always excluded. Purged rows are only recoverable by re-importing from ANAF (if the source message still exists).

---

## Testing

### Manual Clear (Part 1)
Select a company → Clear → dialog shows correct count → those rows leave Unallocated (other companies untouched) → appear in Bin and restore correctly → allocated invoices never affected. Disabled-state check in all-companies mode.

### Auto-lifecycle (Part 2) — backend tests
- Stage 1: invoice `created_at` 11 days ago, unallocated → gains `deleted_at`; 9 days ago → untouched; allocated 11 days → untouched; already-hidden (`ignored`) → untouched.
- Stage 2: binned (`deleted_at`) 11 days ago, unallocated → hard-deleted; 9 days ago → remains; allocated + binned → **not** deleted (guard holds).
- Re-run idempotency: a second immediate run deletes/purges nothing new.
- Predicate assertion: `get_unallocated_ids` and both stage queries only ever match `jarvis_invoice_id IS NULL` rows.

## Out of scope (YAGNI)
- No settings UI for the thresholds (hardcoded 10/10 constants for v1).
- No new "clear by company" backend endpoint (reuse `ids` + `bulk-delete`).
- No all-companies one-shot manual clear.
- No change to the global count badge.
- No changes to the accounting `invoices` table or its separate `archive_invoices` job.
