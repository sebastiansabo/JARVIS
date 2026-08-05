# Quick Non-Finalizing Notes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a KAM append a raw note to an in-progress visit without finalizing it.

**Architecture:** New single-responsibility `POST /visits/:id/quick-note` (IDOR + `in_progress` guard, reuses `add_note`, no finalize chain) + a `VisitDetailDialog` composer gated on `in_progress` + an `addQuickNote` API wrapper with detail/Hub-list invalidation. No schema change.

**Tech Stack:** Python/Flask (psycopg2, pytest test-client), React 19 + TypeScript + TanStack Query + shadcn/ui (Vitest).

## Global Constraints
- Work in the worktree `/Users/sebastiansabo/Documents/Git/JARVIS-fs-tenant` on branch `fs-quick-notes` (off `dev` 46b300801); ff-merge to `dev` at finish.
- No schema change; reuse `VisitRepository.add_note(visit_id, raw_note)` (raw only, `structured_note` stays NULL).
- Endpoint contract: IDOR (own visit) → 403; `status != 'in_progress'` → **409**; empty `raw_note` → 400; `> 10000` chars → 400; success → 201 `{success, note}`. Romanian error copy exactly as written in Task 1. It must NOT structure, complete, or notify.
- Backend test run from worktree root: `python3 -m pytest tests/test_field_sales_quick_note.py -v` (conftest sets dummy `DATABASE_URL` + mocks psycopg2). Backend syntax: `python3 -c "import ast; ast.parse(open('jarvis/field_sales/routes/visits.py').read())"`.
- Frontend commands run from `jarvis/frontend`: `npx tsc --noEmit`, `npx vitest run <path>`. Do NOT `npm run build` in task commits; commit **source only** (never `jarvis/static/react/*` or `tsconfig.tsbuildinfo`).
- The post-commit hook prints a repo-wide validation report with pre-existing unrelated failures — ignore it; confirm commits via `git log`.
- Romanian UI copy; iOS-standard sizing; match existing `VisitDetailDialog` styling.

---

### Task 1: Backend — `POST /visits/:id/quick-note`

**Files:**
- Modify: `jarvis/field_sales/routes/visits.py` (add the route after `api_visit_note`, which ends ~line 557)
- Test: `tests/test_field_sales_quick_note.py` (new)

**Interfaces:**
- Produces: route `POST /api/field-sales/visits/<int:visit_id>/quick-note` returning `{success: bool, note: {...}}` (201) or an error envelope. Frontend Task 2 calls it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_field_sales_quick_note.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
import pytest


@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


def test_quick_note_route_registered_and_auth_protected(client):
    # RED before impl: no such route -> 404 (not in the allowed set) -> fails.
    # GREEN after impl: the auth guard (@jwt_or_login_required/@field_sales_required)
    # rejects the unauthenticated POST with 401/403 or a 302 redirect to login,
    # never 404 (route now exists) and never 200/201 (handler not reached).
    resp = client.post('/api/field-sales/visits/1/quick-note', json={'raw_note': 'x'})
    assert resp.status_code != 404, 'route should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_field_sales_quick_note.py -v`
Expected: FAIL — unauthenticated POST to a non-existent route returns 404, which is excluded by the assertions.

- [ ] **Step 3: Implement the route**

In `jarvis/field_sales/routes/visits.py`, immediately after the end of `api_visit_note` (the `return jsonify(... 'visit_status': 'completed' ...)` / its `except` block, ~line 557), add:

```python
@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/quick-note', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_quick_note(visit_id):
    """Append a raw, non-finalizing note to an in-progress visit.

    Unlike POST /note, this does NOT AI-structure the note or complete the
    visit — it records what happened so far while the visit is still ongoing.
    """
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: only own visits
        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Poți adăuga note doar la vizitele tale'}), 403

        # Quick notes are for the "during the visit" window only.
        if visit['status'] != 'in_progress':
            return jsonify({'success': False, 'error': 'Poți adăuga note doar în timpul vizitei (vizita trebuie să fie în desfășurare)'}), 409

        data = request.get_json(silent=True) or {}
        raw_note = data.get('raw_note', '').strip()
        if not raw_note:
            return jsonify({'success': False, 'error': 'raw_note is required'}), 400
        if len(raw_note) > 10000:
            return jsonify({'success': False, 'error': 'raw_note must be under 10000 characters'}), 400

        note = _visit_repo.add_note(visit_id, raw_note)
        return jsonify({'success': True, 'note': note}), 201
    except Exception as e:
        logger.exception('Error adding quick note')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
```

- [ ] **Step 4: Run test + confirm the auth code**

Run: `python3 -m pytest tests/test_field_sales_quick_note.py -v`
Expected: PASS. If it fails because the actual unauthenticated status is some other code, print `resp.status_code` and widen the allowed set to the observed auth-rejection code (do NOT accept 200/201/404).

- [ ] **Step 5: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('jarvis/field_sales/routes/visits.py').read())" && echo OK
git add jarvis/field_sales/routes/visits.py tests/test_field_sales_quick_note.py
git commit -m "feat(field-sales): add quick-note endpoint for in-progress visits"
```

---

### Task 2: Frontend — API wrapper + composer + tests

**Files:**
- Modify: `jarvis/frontend/src/api/fieldSales.ts` (`addQuickNote`)
- Modify: `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx` (composer + mutation)
- Test: `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.quicknote.test.tsx` (new)

**Interfaces:**
- Consumes: the `POST /quick-note` endpoint (Task 1).

- [ ] **Step 1: Write the failing tests**

Create `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.quicknote.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getVisit = vi.fn()
const addQuickNote = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: {
  getVisit: (...a: unknown[]) => getVisit(...a),
  getVisitTasks: vi.fn().mockResolvedValue({ success: true, tasks: [] }),
  updateVisit: vi.fn(),
  addQuickNote: (...a: unknown[]) => addQuickNote(...a),
} }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
import { VisitDetailDialog } from './VisitDetailDialog'

const visitResp = (status: string) => ({ success: true, visit: {
  id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', visit_type: 'general', status,
  client_name: 'ACME SRL', kam_name: 'George Pop', notes: [],
} })

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VisitDetailDialog quick note', () => {
  beforeEach(() => {
    getVisit.mockReset(); addQuickNote.mockReset()
    addQuickNote.mockResolvedValue({ success: true, note: { id: 1, raw_note: 'x', created_at: '' } })
  })

  it('shows the composer when the visit is in_progress', async () => {
    getVisit.mockResolvedValue(visitResp('in_progress'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    expect(await screen.findByPlaceholderText(/noteaz/i)).toBeInTheDocument()
  })

  it('hides the composer for a planned visit', async () => {
    getVisit.mockResolvedValue(visitResp('planned'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    // "Editeaza" renders once the visit has loaded, independent of status.
    await screen.findByRole('button', { name: /editeaza/i })
    expect(screen.queryByPlaceholderText(/noteaz/i)).not.toBeInTheDocument()
  })

  it('hides the composer for a completed visit', async () => {
    getVisit.mockResolvedValue(visitResp('completed'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    await screen.findByRole('button', { name: /editeaza/i })
    expect(screen.queryByPlaceholderText(/noteaz/i)).not.toBeInTheDocument()
  })

  it('disables add until text is entered, then calls addQuickNote(9, text) and clears', async () => {
    getVisit.mockResolvedValue(visitResp('in_progress'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    const box = await screen.findByPlaceholderText(/noteaz/i) as HTMLTextAreaElement
    const btn = screen.getByRole('button', { name: /adaug[aă] not[aă]/i })
    expect(btn).toBeDisabled()
    fireEvent.change(box, { target: { value: 'client vrea X5' } })
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn)
    await waitFor(() => expect(addQuickNote).toHaveBeenCalledWith(9, 'client vrea X5'))
    await waitFor(() => expect(box.value).toBe(''))
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run (from `jarvis/frontend`): `npx vitest run src/pages/FieldSales/VisitDetailDialog.quicknote.test.tsx`
Expected: FAIL — no composer/placeholder rendered, `addQuickNote` undefined on the mock.

- [ ] **Step 3: Add the API wrapper**

In `jarvis/frontend/src/api/fieldSales.ts`, add to the `fieldSalesApi` object (next to `createVisit`; `FSVisitNote` is already defined/used in this file):

```ts
  addQuickNote: (visitId: number, rawNote: string) =>
    api.post<{ success: boolean; note: FSVisitNote }>(`/api/field-sales/visits/${visitId}/quick-note`, { raw_note: rawNote }),
```

- [ ] **Step 4: Add the composer + mutation to VisitDetailDialog**

In `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx`:

(a) Add quick-note state next to the other `useState` hooks (after `const [activeTab, setActiveTab] = useState('info')`):

```tsx
  const [quickNote, setQuickNote] = useState('')
```

(b) Add the mutation right after `updateMutation` (~line 142):

```tsx
  const quickNoteMutation = useMutation({
    mutationFn: (text: string) => fieldSalesApi.addQuickNote(visitId!, text),
    onSuccess: () => {
      setQuickNote('')
      queryClient.invalidateQueries({ queryKey: ['fs-visit-detail', visitId] })
      queryClient.invalidateQueries({ queryKey: ['field-sales-visits'] })
      queryClient.invalidateQueries({ queryKey: ['field-sales-mine'] })
      queryClient.invalidateQueries({ queryKey: ['field-sales-cal'] })
      toast.success('Notă adăugată')
    },
    onError: () => toast.error('Eroare la adăugarea notei'),
  })
```

(c) In the info tab, immediately BEFORE the `{/* Notes */}` block (~line 418), add the composer (gated on `in_progress`). `Label`, `Textarea`, `Button`, `MessageSquare` are already imported:

```tsx
                {/* Quick note composer — only while the visit is in progress. */}
                {visit.status === 'in_progress' && (
                  <div className="rounded-lg border p-3 space-y-2">
                    <Label htmlFor="quick-note" className="text-sm font-semibold flex items-center gap-1.5">
                      <MessageSquare className="h-4 w-4" />
                      Adaugă notă
                    </Label>
                    <Textarea
                      id="quick-note"
                      value={quickNote}
                      onChange={(e) => setQuickNote(e.target.value)}
                      placeholder="Notează ce s-a discutat până acum..."
                      rows={3}
                    />
                    <div className="flex justify-end">
                      <Button
                        size="sm"
                        onClick={() => quickNoteMutation.mutate(quickNote.trim())}
                        disabled={!quickNote.trim() || quickNoteMutation.isPending}
                      >
                        {quickNoteMutation.isPending ? 'Se salvează...' : 'Adaugă notă'}
                      </Button>
                    </div>
                  </div>
                )}
```

- [ ] **Step 5: Run tests + typecheck**

Run (from `jarvis/frontend`):
`npx vitest run src/pages/FieldSales/VisitDetailDialog.quicknote.test.tsx` → 4 pass.
`npx tsc --noEmit` → clean.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/api/fieldSales.ts jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.quicknote.test.tsx
git commit -m "feat(field-sales): quick-note composer in visit detail (in-progress only)"
```

---

### Task 3: Verify + final review + ff-merge

**Files:** none (verification + integration).

- [ ] **Step 1: Backend gates**

Run (worktree root): `python3 -m pytest tests/test_field_sales_quick_note.py -v` → pass.
`python3 -c "import ast; ast.parse(open('jarvis/field_sales/routes/visits.py').read())" && echo OK`.

- [ ] **Step 2: Frontend gates**

Run (from `jarvis/frontend`): `npx tsc --noEmit` → clean; `npx vitest run` → full suite green, pristine.

- [ ] **Step 3: Manual guard check (localhost)**

Because the 409/403/201 branch logic is not exercised by an authenticated automated test, verify it once against localhost: with the app running (backend on :5001), an in-progress own visit accepts a quick note (201, appears in the detail notes list, visit stays in_progress) and a non-in_progress visit is rejected 409. Record the result in the ledger. If the app can't be driven in this environment, note that and rely on the frontend contract test + registration test.

- [ ] **Step 4: Build check, then revert artifacts**

Run (from `jarvis/frontend`): `npm run build` → succeeds.
Then (worktree root): `git checkout -- jarvis/static/react jarvis/frontend/tsconfig.tsbuildinfo && git clean -fdq jarvis/static/react` → tree clean (only `node_modules` untracked).

- [ ] **Step 5: Final scoped review**

Request a review of `dev..HEAD` (the 2 implementation commits) via superpowers:requesting-code-review. Address any Critical/Important findings.

- [ ] **Step 6: Rebase onto dev + ff-merge** (dev is checked out & may be dirty in the main folder `/Users/sebastiansabo/Documents/Git/JARVIS`)

```bash
git rebase dev
# re-run gates after rebase: pytest + (from jarvis/frontend) npx tsc --noEmit && npx vitest run
git merge-base --is-ancestor dev fs-quick-notes && \
  git -C /Users/sebastiansabo/Documents/Git/JARVIS merge --ff-only fs-quick-notes
```
Confirm the main folder's uncommitted work is preserved. If `git rebase dev` conflicts (files are disjoint from dev's calendar/testdrive work, so it shouldn't), STOP and surface.

- [ ] **Step 7: Update memory**

Update `project_fs_tenant_isolation.md` (mark Phase 2 Slice 2 shipped) + the `MEMORY.md` pointer.

## Self-Review
- **Spec coverage:** endpoint with IDOR + in_progress 409 guard + raw-only `add_note` (Task 1) ✓; api wrapper + composer gated on in_progress + invalidation (Task 2) ✓; registration/auth test + frontend contract tests + manual guard check (Tasks 1–3) ✓; tenant-awareness inherited, no new surface ✓; verify + merge (Task 3) ✓.
- **Placeholders:** none — exact code and commands throughout. The one runtime unknown (exact unauthenticated status code) is handled explicitly in Task 1 Step 4.
- **Type consistency:** `addQuickNote(visitId, rawNote)` signature matches the test's `addQuickNote(9, 'client vrea X5')` and the `quickNoteMutation` call; `FSVisitNote` reused; invalidation keys match the Hub panel's (`field-sales-visits`/`field-sales-mine`/`field-sales-cal`) and the detail key `['fs-visit-detail', visitId]`.
