# Edit Client Details — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any Field Sales user edit a client's contact/address fields from the Client 360 card.

**Architecture:** New `PUT /api/field-sales/clients/:id` (`@field_sales_required`, no tenant gate) that filters the body to an FS whitelist and reuses `crm.ClientRepository.update`; the 360 normalizer exposes the already-returned `crm_clients` row; `ClientCard360` gains an edit section. No schema change.

**Tech Stack:** Python/Flask (psycopg2, pytest test-client), React 19 + TypeScript + TanStack Query (Vitest).

## Global Constraints
- Work in the worktree `/Users/sebastiansabo/Documents/Git/JARVIS-fs-tenant` on branch `fs-edit-client` (off `dev` 787699eec); ff-merge to `dev` at finish.
- No schema change. The write reuses `crm.repositories.client_repository.ClientRepository.update(client_id, data)` (whitelists via `_EDITABLE`, `''`→NULL, syncs `name_normalized`, returns the fresh row).
- FS-editable field set (a module constant `FS_EDITABLE`): `display_name, contact_person, phone, email, street, city, region, country, company_name, nr_reg`. The route filters the incoming body to this set BEFORE calling `update` — never pass through `is_blacklisted`, `client_type`, `cui`, `eurofib_konto_debit`, or `driver_license_number`.
- Access: `@jwt_or_login_required` + `@field_sales_required` only — any FS user, no tenant/ownership gate (deliberate; `crm_clients` is a shared master record). State this in the endpoint docstring.
- Backend test from worktree root: `python3 -m pytest tests/test_field_sales_edit_client.py -v` (conftest sets dummy `DATABASE_URL` + mocks psycopg2). Backend syntax: `python3 -c "import ast; ast.parse(open('jarvis/field_sales/routes/clients.py').read())"`.
- Frontend commands run from `jarvis/frontend`: `npx tsc --noEmit`, `npx vitest run <path>`. Do NOT `npm run build` in task commits; commit **source only** (never `jarvis/static/react/*` or `tsconfig.tsbuildinfo`).
- The post-commit hook prints a repo-wide validation report with pre-existing unrelated failures — ignore it; confirm commits via `git log`.
- Romanian UI copy; iOS-standard sizing; match existing `ClientCard360` styling.

---

### Task 1: Backend — `PUT /api/field-sales/clients/:id`

**Files:**
- Modify: `jarvis/field_sales/routes/clients.py` (add `FS_EDITABLE` const + the route; place after `api_client_enrich`, before the `companies` route)
- Test: `tests/test_field_sales_edit_client.py` (new)

**Interfaces:**
- Produces: `PUT /api/field-sales/clients/<int:client_id>` returning `{success, client}` (200) / error envelope. Frontend Task 2 calls it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_field_sales_edit_client.py`:

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


def test_edit_client_route_registered_and_auth_protected(client):
    # RED before impl: no such route -> 404 -> excluded by the assertions.
    # GREEN after impl: the auth guard rejects the unauthenticated PUT with
    # 401/403 or a 302 login redirect, never 404 (route exists) or 200.
    resp = client.put('/api/field-sales/clients/1', json={'phone': '0722000000'})
    assert resp.status_code != 404, 'route should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_field_sales_edit_client.py -v`
Expected: FAIL — the route doesn't exist yet (404).

- [ ] **Step 3: Implement the endpoint**

In `jarvis/field_sales/routes/clients.py`, add a module constant near the top (after the imports/`logger`):

```python
# Fields a Field Sales user may edit on the shared crm_clients master record.
# A subset of crm.ClientRepository._EDITABLE — excludes CRM-admin/fiscal fields.
FS_EDITABLE = {
    'display_name', 'contact_person', 'phone', 'email', 'street',
    'city', 'region', 'country', 'company_name', 'nr_reg',
}
```

Then add the route immediately after `api_client_enrich` (and before `api_field_sales_companies`):

```python
@field_sales_bp.route('/api/field-sales/clients/<int:client_id>', methods=['PUT'])
@jwt_or_login_required
@field_sales_required
def api_field_sales_client_update(client_id):
    """Edit a client's contact/address details from the Field Sales 360 card.

    Any field_sales user may edit any client — there is NO tenant/ownership
    gate (deliberate): crm_clients is a shared master record, so a correction
    (e.g. a phone number) is global. Only the FS_EDITABLE subset is accepted;
    the actual write reuses crm.ClientRepository.update (whitelist + name sync).
    """
    try:
        data = request.get_json(silent=True) or {}
        filtered = {k: v for k, v in data.items() if k in FS_EDITABLE}
        if not filtered:
            return jsonify({'success': False, 'error': 'Niciun câmp editabil'}), 400

        from crm.repositories.client_repository import ClientRepository
        client = ClientRepository().update(client_id, filtered)
        if not client:
            return jsonify({'success': False, 'error': 'Client negăsit sau niciun câmp editabil'}), 404
        return jsonify({'success': True, 'client': client})
    except Exception as e:
        logger.exception('Error updating client')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
```

- [ ] **Step 4: Run test + confirm auth code**

Run: `python3 -m pytest tests/test_field_sales_edit_client.py -v`
Expected: PASS (unauthenticated PUT → 401, matching the sibling quick-note route). If a different auth-rejection code appears, print it and widen the allowed set — never accept 200/404.

- [ ] **Step 5: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('jarvis/field_sales/routes/clients.py').read())" && echo OK
git add jarvis/field_sales/routes/clients.py tests/test_field_sales_edit_client.py
git commit -m "feat(field-sales): PUT client-edit endpoint (FS whitelist, reuses ClientRepository.update)"
```

---

### Task 2: Frontend — expose client row + `updateClient` + edit section

**Files:**
- Modify: `jarvis/frontend/src/api/fieldSales.ts` (`FSClientRaw`, `FSClient360.client`, `getClient360` normalizer, `updateClient`)
- Modify: `jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx` (`useState` import, `ClientContactSection`, render it, read `data.client`)
- Test: `jarvis/frontend/src/api/fieldSales.fs.test.ts` (append), `jarvis/frontend/src/pages/FieldSales/ClientCard360.test.tsx` (new)

**Interfaces:**
- Consumes: `PUT /clients/:id` (Task 1).

- [ ] **Step 1: Write the failing tests**

Append to `jarvis/frontend/src/api/fieldSales.fs.test.ts` (inside the `describe('fieldSalesApi company-scoping wrappers')` block or a sensible existing block that has `get`/`put` spies — use the same `get`/`put` mocks the file already sets up):

```tsx
  it('updateClient PUTs the field-sales client route with the given fields', async () => {
    await fieldSalesApi.updateClient(760, { phone: '0722111222', city: 'Cluj' })
    expect(put).toHaveBeenCalledWith('/api/field-sales/clients/760', { phone: '0722111222', city: 'Cluj' })
  })

  it('getClient360 surfaces the raw client row', async () => {
    get.mockResolvedValueOnce({ client: { id: 760, display_name: 'ACME', phone: '0722000000' }, profile: null })
    const res = await fieldSalesApi.getClient360(760)
    expect(res.client).toEqual({ id: 760, display_name: 'ACME', phone: '0722000000' })
  })
```

Create `jarvis/frontend/src/pages/FieldSales/ClientCard360.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getClient360 = vi.fn()
const updateClient = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: {
  getClient360: (...a: unknown[]) => getClient360(...a),
  updateClient: (...a: unknown[]) => updateClient(...a),
  refreshFiscal: vi.fn(),
} }))
import ClientCard360 from './ClientCard360'

const client360 = {
  client: { id: 760, display_name: 'ACME SRL', contact_person: 'Ion', phone: '0722000000', email: 'a@b.ro', street: null, city: 'Cluj', region: null, country: null, company_name: 'ACME SRL', nr_reg: 'J12/34/2020' },
  profile: { client_type: 'company', industry: null, fleet_size: 0, priority: 'medium', renewal_score: 0 },
  fleet: [], last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ClientCard360 edit', () => {
  beforeEach(() => {
    getClient360.mockReset(); updateClient.mockReset()
    getClient360.mockResolvedValue(client360)
    updateClient.mockResolvedValue({ success: true, client: client360.client })
  })

  it('reveals the edit form prefilled from the client row, saves, and invalidates', async () => {
    wrap(<ClientCard360 clientId={760} clientName="ACME SRL" />)
    fireEvent.click(await screen.findByRole('button', { name: /editeaz/i }))
    // Prefill: the existing phone shows in an input.
    const phone = await screen.findByDisplayValue('0722000000')
    fireEvent.change(phone, { target: { value: '0722999888' } })
    fireEvent.click(screen.getByRole('button', { name: /salveaz/i }))
    await waitFor(() => expect(updateClient).toHaveBeenCalledWith(760, expect.objectContaining({ phone: '0722999888' })))
  })

  it('cancel exits edit mode without calling updateClient', async () => {
    wrap(<ClientCard360 clientId={760} clientName="ACME SRL" />)
    fireEvent.click(await screen.findByRole('button', { name: /editeaz/i }))
    fireEvent.click(screen.getByRole('button', { name: /anuleaz/i }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /salveaz/i })).not.toBeInTheDocument())
    expect(updateClient).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run (from `jarvis/frontend`):
`npx vitest run src/api/fieldSales.fs.test.ts src/pages/FieldSales/ClientCard360.test.tsx`
Expected: FAIL — `updateClient` undefined on the api; no "Editează" button / no prefilled input; `res.client` undefined.

- [ ] **Step 3: Add `FSClientRaw`, `FSClient360.client`, normalizer, `updateClient`**

In `jarvis/frontend/src/api/fieldSales.ts`:

(a) Add the interface (near `FSClient360`):

```ts
export interface FSClientRaw {
  id: number
  display_name: string | null
  contact_person: string | null
  phone: string | null
  email: string | null
  street: string | null
  city: string | null
  region: string | null
  country: string | null
  company_name: string | null
  nr_reg: string | null
  cui?: string | null
}
```

(b) Add `client: FSClientRaw | null` to the `FSClient360` interface.

(c) In `getClient360`'s `.then((res) => ({ ... }))` mapping, add:

```ts
      client: (res.client as FSClient360['client']) ?? null,
```

(d) Add the wrapper to `fieldSalesApi` (next to `getClient360`):

```ts
  updateClient: (clientId: number, data: Partial<FSClientRaw>) =>
    api.put<{ success: boolean; client: FSClientRaw }>(`/api/field-sales/clients/${clientId}`, data),
```

- [ ] **Step 4: Add the edit section to ClientCard360**

In `jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx`:

(a) Add the React import at the top (the file currently imports only from `@tanstack/react-query` and icons):

```ts
import { useState } from 'react'
```

(b) Import `FSClientRaw` in the existing `@/api/fieldSales` type import block.

(c) Add this subcomponent (above the main `ClientCard360` component):

```tsx
const CONTACT_FIELDS: { key: keyof FSClientRaw; label: string; type?: string }[] = [
  { key: 'display_name', label: 'Nume' },
  { key: 'contact_person', label: 'Persoană contact' },
  { key: 'phone', label: 'Telefon' },
  { key: 'email', label: 'Email', type: 'email' },
  { key: 'company_name', label: 'Companie' },
  { key: 'nr_reg', label: 'Nr. reg.' },
  { key: 'street', label: 'Stradă' },
  { key: 'city', label: 'Oraș' },
  { key: 'region', label: 'Județ' },
  { key: 'country', label: 'Țară' },
]

function ClientContactSection({ clientId, client }: { clientId: number; client: FSClientRaw | null }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<FSClientRaw>>({})

  const startEdit = () => {
    setForm(Object.fromEntries(CONTACT_FIELDS.map(({ key }) => [key, (client?.[key] as string) ?? ''])))
    setEditing(true)
  }

  const mutation = useMutation({
    mutationFn: () => fieldSalesApi.updateClient(clientId, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['field-sales-client360', clientId] })
      setEditing(false)
    },
  })
  const err = mutation.error as ApiErr

  return (
    <div className="rounded-2xl bg-card border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Date contact</h3>
        {!editing && (
          <button onClick={startEdit} className="rounded-full bg-secondary px-2.5 py-1.5 text-xs font-semibold text-foreground active:bg-secondary/80 transition-colors">
            Editează
          </button>
        )}
      </div>
      {!editing ? (
        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {CONTACT_FIELDS.map(({ key, label }) => (
            <div key={key} className="text-sm">
              <span className="text-muted-foreground">{label}: </span>
              <span className="text-foreground break-words">{(client?.[key] as string) || '-'}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {CONTACT_FIELDS.map(({ key, label, type }) => (
              <label key={key} className="block text-xs">
                <span className="text-muted-foreground">{label}</span>
                <input
                  type={type ?? 'text'}
                  value={(form[key] as string) ?? ''}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="mt-1 h-11 w-full rounded-xl border border-border bg-background px-3 text-base focus:outline-none focus:ring-2 focus:ring-teal-600/40"
                />
              </label>
            ))}
          </div>
          {mutation.isError && <p className="text-xs text-destructive">{err?.data?.error ?? 'Eroare la salvare'}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={() => setEditing(false)} className="h-11 rounded-xl border border-border px-4 text-sm font-semibold active:bg-muted">Anulează</button>
            <button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="h-11 rounded-xl bg-teal-600 px-4 text-sm font-semibold text-white active:bg-teal-700 disabled:opacity-60">
              {mutation.isPending ? 'Se salvează...' : 'Salvează'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
```

(d) In the main `ClientCard360` component, read the client row and render the section under the header:

```tsx
  const client = data?.client ?? null
```

and immediately after `<HeaderSection … />` in the returned JSX:

```tsx
      <ClientContactSection clientId={clientId} client={client} />
```

- [ ] **Step 5: Run tests + typecheck**

Run (from `jarvis/frontend`):
`npx vitest run src/api/fieldSales.fs.test.ts src/pages/FieldSales/ClientCard360.test.tsx` → all pass.
`npx tsc --noEmit` → clean.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/api/fieldSales.ts jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx jarvis/frontend/src/api/fieldSales.fs.test.ts jarvis/frontend/src/pages/FieldSales/ClientCard360.test.tsx
git commit -m "feat(field-sales): edit-client section in Client 360 card"
```

---

### Task 3: Verify + final review + ff-merge

**Files:** none.

- [ ] **Step 1: Backend gates** — `python3 -m pytest tests/test_field_sales_edit_client.py -v` → pass; `python3 -c "import ast; ast.parse(open('jarvis/field_sales/routes/clients.py').read())" && echo OK`.
- [ ] **Step 2: Frontend gates** (from `jarvis/frontend`) — `npx tsc --noEmit` clean; `npx vitest run` full suite green, pristine.
- [ ] **Step 3: Build check, then revert** — `npm run build` succeeds; then (worktree root) `git checkout -- jarvis/static/react jarvis/frontend/tsconfig.tsbuildinfo && git clean -fdq jarvis/static/react` → tree clean.
- [ ] **Step 4: Final scoped review** — review `dev..HEAD` (2 implementation commits) via superpowers:requesting-code-review. Address Critical/Important findings.
- [ ] **Step 5: Rebase onto dev + ff-merge** (dev is checked out & may be dirty in the main folder `/Users/sebastiansabo/Documents/Git/JARVIS`):
```bash
git rebase dev
# re-run gates after rebase: pytest + (from jarvis/frontend) npx tsc --noEmit && npx vitest run
git merge-base --is-ancestor dev fs-edit-client && \
  git -C /Users/sebastiansabo/Documents/Git/JARVIS merge --ff-only fs-edit-client
```
Confirm the main folder's uncommitted work is preserved. If `git rebase dev` conflicts (files are disjoint from dev's calendar/testdrive work), STOP and surface.
- [ ] **Step 6: Update memory** — mark Phase 2 Slice 3 shipped in `project_fs_tenant_isolation.md` + `MEMORY.md` pointer.

## Self-Review
- **Spec coverage:** FS-whitelisted PUT reusing ClientRepository.update, any-FS-user, no tenant gate (Task 1) ✓; expose client row + updateClient + edit section with prefill/save/cancel + 360 invalidation (Task 2) ✓; registration/auth test + frontend contract tests (Tasks 1–2) ✓; verify + merge (Task 3) ✓.
- **Placeholders:** none — exact code and commands throughout; the one runtime unknown (unauth status) is handled in Task 1 Step 4.
- **Type consistency:** `FSClientRaw` used in `FSClient360.client`, `updateClient(clientId, Partial<FSClientRaw>)`, `CONTACT_FIELDS` keys, and the tests; `updateClient(760, {...})` matches the wrapper signature; invalidation key `['field-sales-client360', clientId]` matches the card's own query key; `ApiErr` reused from the existing type in ClientCard360.
