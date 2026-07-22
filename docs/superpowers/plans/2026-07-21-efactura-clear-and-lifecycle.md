# e-Factura Unallocated Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual per-company "Clear" button to the e-Factura Unallocated tab, replace the existing 15-day hard-delete with a safer 10-day→Bin→10-day→purge auto-lifecycle, and remove the unallocated-count widget from the main Dashboard.

**Architecture:** Backend adds two repository methods (soft-delete stage, purge stage) and rewires the existing 6-hourly APScheduler job to run both stages. Frontend adds a Clear button + confirm dialog wired to the existing `getUnallocatedIds` + `bulk-delete` endpoints, and deletes the Dashboard `EFacturaWidget` plus its now-dead in-page toggle.

**Tech Stack:** Python (Flask, psycopg2, APScheduler), React + TypeScript (TanStack Query, Vite, shadcn/ui).

## Global Constraints

- Work only on the local `dev` branch (JARVIS git workflow). Do not push to staging/main.
- Backend tests live in `tests/` at repo root and mock DB via `core.base_repository` (`get_db`, `get_cursor`, `release_db`). `BaseRepository.execute(sql, params)` returns `cursor.rowcount`.
- Repo working directory for all commands: `/Users/sebastiansabo/Documents/Git/JARVIS`.
- Frontend has no unit-test runner (no vitest); frontend verification = `npm run build` (runs `tsc -b && vite build`) from `jarvis/frontend`.
- Age is always measured on `efactura_invoices.created_at` (import time), never `issue_date`.
- Every operation must carry `jarvis_invoice_id IS NULL` so allocated/transferred invoices are never touched.
- Auto-lifecycle thresholds are module constants: `UNALLOCATED_BIN_DAYS = 10`, `BIN_PURGE_DAYS = 10`.
- End every commit message with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Backend — Stage 1 soft-delete repo method

**Files:**
- Modify: `jarvis/core/connectors/efactura/repositories/supplier_mapping_repository.py` (add after `delete_old_unallocated`, which ends at line ~354)
- Test: `tests/test_efactura_module.py`

**Interfaces:**
- Produces: `EFacturaInvoiceRepository.soft_delete_old_unallocated(days: int = 10) -> int` (exposed via mixin inheritance, same as `delete_old_unallocated`). Returns the number of rows moved to the Bin.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_efactura_module.py` (append a new test class near the other repository tests):

```python
class TestUnallocatedLifecycle:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_soft_delete_old_unallocated(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 7

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        count = repo.soft_delete_old_unallocated(days=10)

        assert count == 7
        sql = mock_cursor.execute.call_args[0][0]
        assert 'UPDATE efactura_invoices' in sql
        assert 'SET deleted_at = NOW()' in sql
        assert 'jarvis_invoice_id IS NULL' in sql
        assert 'ignored = FALSE' in sql
        assert 'deleted_at IS NULL' in sql
        assert 'created_at <' in sql
        mock_conn.commit.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_efactura_module.py::TestUnallocatedLifecycle::test_soft_delete_old_unallocated -v`
Expected: FAIL with `AttributeError: 'EFacturaInvoiceRepository' object has no attribute 'soft_delete_old_unallocated'`.

- [ ] **Step 3: Write minimal implementation**

In `supplier_mapping_repository.py`, immediately after the `delete_old_unallocated` method (after line ~354), add:

```python
    def soft_delete_old_unallocated(self, days: int = 10) -> int:
        """Stage 1 of the auto-lifecycle: soft-delete (move to Bin) unallocated
        invoices older than N days by import date. Recoverable from the Bin."""
        try:
            sql = """
                UPDATE efactura_invoices
                SET deleted_at = NOW()
                WHERE jarvis_invoice_id IS NULL
                  AND ignored = FALSE
                  AND deleted_at IS NULL
                  AND created_at < NOW() - INTERVAL '%s days'
            """
            count = self.execute(sql, [days])
            logger.info(f"Auto-lifecycle: soft-deleted {count} unallocated invoices to Bin (>{days} days)")
            return count
        except Exception as e:
            logger.error(f"Failed to soft-delete old unallocated invoices: {e}")
            return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_efactura_module.py::TestUnallocatedLifecycle::test_soft_delete_old_unallocated -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/connectors/efactura/repositories/supplier_mapping_repository.py tests/test_efactura_module.py
git commit -m "feat(efactura): add stage-1 soft-delete for old unallocated invoices

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Backend — Stage 2 Bin-purge repo method

**Files:**
- Modify: `jarvis/core/connectors/efactura/repositories/supplier_mapping_repository.py` (add after `soft_delete_old_unallocated` from Task 1)
- Test: `tests/test_efactura_module.py`

**Interfaces:**
- Produces: `EFacturaInvoiceRepository.purge_binned_old(days: int = 10) -> int`. Permanently deletes unallocated invoices whose `deleted_at` is older than N days. Returns the number of rows purged.

- [ ] **Step 1: Write the failing test**

Add to the `TestUnallocatedLifecycle` class in `tests/test_efactura_module.py`:

```python
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_purge_binned_old(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 3

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        count = repo.purge_binned_old(days=10)

        assert count == 3
        sql = mock_cursor.execute.call_args[0][0]
        assert 'DELETE FROM efactura_invoices' in sql
        assert 'jarvis_invoice_id IS NULL' in sql
        assert 'deleted_at IS NOT NULL' in sql
        assert 'deleted_at <' in sql
        mock_conn.commit.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_efactura_module.py::TestUnallocatedLifecycle::test_purge_binned_old -v`
Expected: FAIL with `AttributeError: ... has no attribute 'purge_binned_old'`.

- [ ] **Step 3: Write minimal implementation**

In `supplier_mapping_repository.py`, immediately after `soft_delete_old_unallocated`, add:

```python
    def purge_binned_old(self, days: int = 10) -> int:
        """Stage 2 of the auto-lifecycle: permanently delete any unallocated
        invoice that has been in the Bin (deleted_at set) longer than N days.
        Applies to both auto-binned and manually-deleted invoices. Allocated
        invoices are never purged."""
        try:
            sql = """
                DELETE FROM efactura_invoices
                WHERE jarvis_invoice_id IS NULL
                  AND deleted_at IS NOT NULL
                  AND deleted_at < NOW() - INTERVAL '%s days'
            """
            count = self.execute(sql, [days])
            logger.info(f"Auto-lifecycle: purged {count} invoices from Bin (>{days} days)")
            return count
        except Exception as e:
            logger.error(f"Failed to purge old binned invoices: {e}")
            return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_efactura_module.py::TestUnallocatedLifecycle::test_purge_binned_old -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/connectors/efactura/repositories/supplier_mapping_repository.py tests/test_efactura_module.py
git commit -m "feat(efactura): add stage-2 bin purge for old deleted invoices

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Backend — rewire the scheduled job to the two-stage lifecycle

**Files:**
- Modify: `jarvis/tasks/efactura.py` (full rewrite of the task function; add constants)
- Test: `tests/test_efactura_tasks.py` (create)

**Interfaces:**
- Consumes: `EFacturaInvoiceRepository.soft_delete_old_unallocated` (Task 1), `EFacturaInvoiceRepository.purge_binned_old` (Task 2).
- Produces: `tasks.efactura.cleanup_old_unallocated_invoices()` now runs Stage 1 then Stage 2. `tasks.efactura.UNALLOCATED_BIN_DAYS = 10`, `tasks.efactura.BIN_PURGE_DAYS = 10`. The scheduler registration in `jarvis/tasks/cleanup.py` (lines 70–78, `id='cleanup_old_unallocated'`, every 6h) is unchanged — it already calls this function.

- [ ] **Step 1: Write the failing test**

Create `tests/test_efactura_tasks.py`:

```python
"""Tests for e-Factura scheduled lifecycle task."""
import sys
import os
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


def test_lifecycle_runs_both_stages():
    from tasks import efactura

    mock_repo = MagicMock()
    mock_repo.soft_delete_old_unallocated.return_value = 5
    mock_repo.purge_binned_old.return_value = 2

    with patch(
        'core.connectors.efactura.repositories.invoice_repository.EFacturaInvoiceRepository',
        return_value=mock_repo,
    ):
        efactura.cleanup_old_unallocated_invoices()

    mock_repo.soft_delete_old_unallocated.assert_called_once_with(days=efactura.UNALLOCATED_BIN_DAYS)
    mock_repo.purge_binned_old.assert_called_once_with(days=efactura.BIN_PURGE_DAYS)


def test_lifecycle_thresholds_are_ten():
    from tasks import efactura
    assert efactura.UNALLOCATED_BIN_DAYS == 10
    assert efactura.BIN_PURGE_DAYS == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_efactura_tasks.py -v`
Expected: FAIL — `AttributeError: module 'tasks.efactura' has no attribute 'UNALLOCATED_BIN_DAYS'` and the call assertions fail (current function calls `delete_old_unallocated(days=15)`).

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `jarvis/tasks/efactura.py` with:

```python
"""e-Factura scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.efactura')

# Auto-lifecycle thresholds (days)
UNALLOCATED_BIN_DAYS = 10   # Stage 1: unallocated this long (by import date) -> soft-delete to Bin
BIN_PURGE_DAYS = 10         # Stage 2: in Bin this long -> permanent delete


def cleanup_old_unallocated_invoices():
    """Two-stage lifecycle for unallocated e-Factura invoices.

    Stage 1: unallocated for >UNALLOCATED_BIN_DAYS (by created_at) -> soft-delete to Bin (recoverable).
    Stage 2: in Bin for >BIN_PURGE_DAYS -> permanent delete.
    """
    try:
        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        binned = repo.soft_delete_old_unallocated(days=UNALLOCATED_BIN_DAYS)
        purged = repo.purge_binned_old(days=BIN_PURGE_DAYS)
        if binned or purged:
            logger.info(
                f"e-Factura lifecycle: binned {binned} unallocated (>{UNALLOCATED_BIN_DAYS}d), "
                f"purged {purged} from Bin (>{BIN_PURGE_DAYS}d)"
            )
    except Exception as e:
        logger.error(f"e-Factura lifecycle task failed: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_efactura_tasks.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tasks/efactura.py tests/test_efactura_tasks.py
git commit -m "feat(efactura): replace 15d hard-delete with 10/10 two-stage lifecycle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Frontend — per-company Clear button

**Files:**
- Modify: `jarvis/frontend/src/pages/EFactura/UnallocatedTab.tsx`

**Interfaces:**
- Consumes: `efacturaApi.getUnallocatedIds(filters)` (returns `number[]`), `efacturaApi.bulkDelete(ids)`, existing `invalidateAll()`, `filters`, `search`, `companies`, and the `ConfirmDialog` component (already imported).
- Produces: no exported symbols; adds a Clear button + confirm dialog inside `UnallocatedTab`.

No unit tests (no frontend test runner). Verification = typecheck/build + manual.

- [ ] **Step 1: Add Clear state, derived company, handler, and mutation**

In `UnallocatedTab.tsx`, after the `deleteMut` mutation (ends at line ~222), add:

```tsx
  // ── Clear (per-company bulk soft-delete to Bin) ──────────
  const [clearOpen, setClearOpen] = useState<{ ids: number[]; companyName: string } | null>(null)
  const [clearLoading, setClearLoading] = useState(false)

  const handleClearClick = async () => {
    if (filters.company_id == null) return
    setClearLoading(true)
    try {
      const ids = await efacturaApi.getUnallocatedIds({ ...filters, search: search || undefined })
      if (ids.length === 0) return
      const companyName = companies.find((c) => c.id === filters.company_id)?.name ?? 'this company'
      setClearOpen({ ids, companyName })
    } finally {
      setClearLoading(false)
    }
  }

  const clearMut = useMutation({
    mutationFn: async (ids: number[]) => {
      const CHUNK = 5000
      for (let i = 0; i < ids.length; i += CHUNK) {
        await efacturaApi.bulkDelete(ids.slice(i, i + CHUNK))
      }
    },
    onSuccess: () => {
      setClearOpen(null)
      invalidateAll()
    },
  })
```

Note: `companies` is already defined at line ~119 (`const companies = unallocData?.companies ?? []`). `invalidateAll` is defined at line ~150. Both are in scope here.

- [ ] **Step 2: Add the Clear button to the desktop toolbar**

In the `!showFilters` desktop toolbar branch, locate the `ml-auto` group (line ~517):

```tsx
            <div className="ml-auto flex items-center gap-2">
              {onShowHiddenChange && (
```

Insert the Clear button as the first child of that `div`, before the `{onShowHiddenChange && (` block:

```tsx
            <div className="ml-auto flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="text-destructive"
                disabled={filters.company_id == null || clearLoading}
                onClick={handleClearClick}
                title={filters.company_id == null ? 'Select a company to clear' : "Clear this company's unallocated list to the Bin"}
              >
                <Trash2 className="mr-1 h-3 w-3" /> Clear
              </Button>
              {onShowHiddenChange && (
```

(`Button` and `Trash2` are already imported at lines 18 and 14.)

- [ ] **Step 3: Render the confirm dialog**

Find the closing `</div>` of the component's root `<div className="space-y-4">` (the final return block). Immediately before the existing bottom-of-component dialogs/ConfirmDialog, add this ConfirmDialog:

```tsx
      <ConfirmDialog
        open={clearOpen != null}
        onOpenChange={(o) => { if (!o) setClearOpen(null) }}
        title="Clear unallocated invoices"
        description={
          clearOpen
            ? `Clear ${clearOpen.ids.length} unallocated invoice${clearOpen.ids.length === 1 ? '' : 's'} for ${clearOpen.companyName} to the Bin? You can restore them from the Bin.`
            : ''
        }
        confirmLabel="Clear to Bin"
        destructive
        onConfirm={() => { if (clearOpen) clearMut.mutate(clearOpen.ids) }}
      />
```

If it is unclear where the existing dialogs are rendered, search the file for `<ConfirmDialog` and place the new one adjacent to it (both must be inside the returned JSX tree).

- [ ] **Step 4: Typecheck / build to verify**

Run: `cd jarvis/frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Manual verification**

Run the app, open e-Factura → Unallocated, toggle Filters on, select a company. Confirm:
- Clear button is disabled with tooltip "Select a company to clear" when "All companies" is selected.
- With a company selected, Clear opens a dialog showing the correct count for that company.
- Confirming moves those rows out of Unallocated (other companies untouched) and into the Bin, where they can be restored.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/EFactura/UnallocatedTab.tsx
git commit -m "feat(efactura): add per-company Clear button to unallocated tab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Frontend — remove the unallocated counter widget from the Dashboard

**Files:**
- Modify: `jarvis/frontend/src/pages/Dashboard/widgets.tsx` (delete `EFacturaWidget`)
- Modify: `jarvis/frontend/src/pages/Dashboard/types.ts` (delete the `efactura_status` registry entry)
- Modify: `jarvis/frontend/src/pages/Dashboard/index.tsx` (remove import + map entry)
- Modify: `jarvis/frontend/src/pages/EFactura/index.tsx` (remove the now-dead Dashboard toggle button + hook)

**Interfaces:**
- Removes: the `EFacturaWidget` export and the `efactura_status` dashboard widget registration. No other module may reference them after this task.

- [ ] **Step 1: Delete the `EFacturaWidget` component**

In `jarvis/frontend/src/pages/Dashboard/widgets.tsx`, delete the entire block from the `// ── e-Factura Status ──` comment (line ~149) through the end of the `EFacturaWidget` function (line ~179), i.e. remove:

```tsx
// ── e-Factura Status ──

export function EFacturaWidget({ enabled }: { enabled: boolean }) {
  ...
}
```

Then, if `Receipt` is no longer referenced anywhere in `widgets.tsx`, remove `Receipt` from its lucide-react import. (Verify with a search for `Receipt` in the file after deletion.)

- [ ] **Step 2: Remove the registry entry in `types.ts`**

In `jarvis/frontend/src/pages/Dashboard/types.ts`, delete the `efactura_status` object (lines ~61–69):

```tsx
  {
    id: 'efactura_status',
    name: 'e-Factura',
    icon: Receipt,
    permission: 'can_access_efactura',
    defaultLayout: { w: 2, h: 3, minW: 2, minH: 2 },
    defaultVisible: true,
    statCards: [{ key: 'unallocated_efactura', title: 'Unallocated e-Factura', icon: Receipt }],
  },
```

Then, if `Receipt` is no longer referenced elsewhere in `types.ts`, remove it from the imports. (Search for `Receipt` after deletion.)

- [ ] **Step 3: Remove the import and map entry in `Dashboard/index.tsx`**

In `jarvis/frontend/src/pages/Dashboard/index.tsx`:
- In the `from './widgets'` import block (lines ~21–30), remove the `EFacturaWidget,` line.
- In `WIDGET_COMPONENTS` (lines ~74–83), remove the line `efactura_status: EFacturaWidget,`.

- [ ] **Step 4: Remove the dead Dashboard toggle in `EFactura/index.tsx`**

In `jarvis/frontend/src/pages/EFactura/index.tsx`:
- Remove line ~46: `const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('efactura_status')`.
- Remove the toggle Button (lines ~88–90):

```tsx
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={toggleDashboardWidget} title={isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}>
              <LayoutDashboard className="h-4 w-4" />
            </Button>
```

- Remove the now-unused `useDashboardWidgetToggle` import and the `LayoutDashboard` icon import from this file. (Search for each after deletion to confirm no other use.)

- [ ] **Step 5: Typecheck / build to verify**

Run: `cd jarvis/frontend && npm run build`
Expected: build succeeds with no TypeScript errors (in particular, no "unused import" or "cannot find name EFacturaWidget" errors). If an unused-import error appears, remove that import and rebuild.

- [ ] **Step 6: Manual verification**

Run the app, open the main Dashboard. Confirm the "e-Factura / unallocated invoices to review" stat card is gone, the Customize sheet no longer lists an e-Factura widget, and the e-Factura page header no longer shows the LayoutDashboard toggle button. The Unallocated tab badge (orange count next to the "Unallocated" tab) is unaffected — it should still appear.

- [ ] **Step 7: Commit**

```bash
git add jarvis/frontend/src/pages/Dashboard/widgets.tsx jarvis/frontend/src/pages/Dashboard/types.ts jarvis/frontend/src/pages/Dashboard/index.tsx jarvis/frontend/src/pages/EFactura/index.tsx
git commit -m "feat(dashboard): remove e-Factura unallocated counter widget

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Manual per-company Clear button (soft-delete to Bin, respects filters, disabled in all-companies) → Task 4. ✓
- 10-day → Bin (Stage 1) → Task 1 + Task 3. ✓
- 10-day-in-Bin → purge (Stage 2), applies to everything in Bin → Task 2 + Task 3. ✓
- Replace existing 15-day hard-delete → Task 3 (rewrites `tasks/efactura.py`). ✓
- Reuse existing endpoints, no new backend routes → Task 4 uses `getUnallocatedIds` + `bulkDelete`. ✓
- Remove unallocated counter from Dashboard → Task 5. ✓
- Age measured on `created_at`, allocated invoices never touched → enforced in Task 1/2 SQL predicates. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every test shows assertions. ✓

**Type consistency:** `soft_delete_old_unallocated(days: int) -> int` and `purge_binned_old(days: int) -> int` referenced identically in Tasks 1–3. Constants `UNALLOCATED_BIN_DAYS` / `BIN_PURGE_DAYS` referenced identically in Task 3 impl and tests. `clearOpen` shape `{ ids: number[]; companyName: string }` consistent across Task 4 steps. ✓

**Note on the manual `POST /api/invoices/cleanup-old` route:** intentionally left unchanged (now largely redundant), per spec "out of scope."
