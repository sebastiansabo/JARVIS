# BuyBack Contract P1 — Seller Legal Identity Capture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the seller's full legal identity on a BuyBack record (person: CNP + CI serie/nr + address; company: nr. reg + IBAN + legal rep) so a later phase can auto-fill a legally-complete purchase/consignație contract.

**Architecture:** Add seven nullable columns to `buyback_records`, thread them through the existing create/update whitelists + intake validation + PII-redaction, extend the best-effort CRM sync, and add a conditional "Date vânzător" sub-section to the intake/edit form. Pure additive change — no behavior changes to existing flows.

**Tech Stack:** Flask + raw parameterized psycopg2 (no ORM); React 19 + TypeScript + Tailwind; pytest (real localhost DB) + vitest.

**Spec:** `docs/superpowers/specs/2026-10-20-buyback-purchase-contract-design.md` (§4.1)

## Global Constraints

- All DDL idempotent: `ADD COLUMN IF NOT EXISTS` guarded by an `information_schema` check (match the existing pattern in `schema_buyback.py`).
- Never f-string a user value into SQL; values bound as `%s`. Column names in INSERT/UPDATE come only from server-controlled whitelists.
- New **sensitive PII** fields (`seller_cnp`, `seller_ci_serie`, `seller_ci_number`, `seller_iban`, `seller_address`) MUST be added to `_PII_LOG_FIELDS` (`buyback/routes/records.py:328`) so they are redacted from telemetry/logs.
- A badly-typed intake value (dict/list) MUST yield a clean 400, never a DB-level 500 → every new field is a text field in `_INTAKE_TEXT_FIELDS`.
- CRM sync is best-effort: only non-empty fields are written (an empty form field never clears existing CRM data); a CRM failure never fails the buyback save.
- No live PII in tests (use obviously-fake values like `cnp='1234567890123'`).
- Backend DB-backed tests run with `DATABASE_URL=postgresql://localhost/defaultdb` (the root conftest otherwise points at a dummy DB and the tests skip).
- Fields: universal `seller_address TEXT`; person `seller_cnp VARCHAR(13)`, `seller_ci_serie VARCHAR(10)`, `seller_ci_number VARCHAR(20)`; company `seller_reg_no VARCHAR(30)`, `seller_iban VARCHAR(34)`, `seller_legal_rep VARCHAR(255)`.

## Review Focus

- **Bad-typed value** (`seller_cnp: {}`) → must return 400, not 500 (Task 2 test).
- **PII in logs** → the five sensitive fields must be in `_PII_LOG_FIELDS` (Task 2 test).
- **Empty field must not clear CRM** → sync writes only non-empty keys (Task 3 test).
- **Company vs person** → person-only fields render for a person seller, company-only fields for a company seller (Task 5 test).
- **Serialization** → new fields appear in the record JSON so the detail page + later contract builder can read them (Task 2 test).

---

### Task 1: Schema — seller-identity columns

**Files:**
- Modify: `jarvis/migrations/domains/schema_buyback.py` (after the hold-columns loop, ~line 67)
- Test: `jarvis/tests/buyback/test_schema_buyback.py`

**Interfaces:**
- Produces: seven nullable columns on `buyback_records` — `seller_address, seller_cnp, seller_ci_serie, seller_ci_number, seller_reg_no, seller_iban, seller_legal_rep`.

- [ ] **Step 1: Write the failing test**

```python
# append to jarvis/tests/buyback/test_schema_buyback.py
def test_records_has_seller_identity_columns(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        create_schema_buyback(conn, cur)
        conn.commit()
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name='buyback_records'""")
        cols = {r[0] if not isinstance(r, dict) else r['column_name'] for r in cur.fetchall()}
        assert {'seller_address', 'seller_cnp', 'seller_ci_serie', 'seller_ci_number',
                'seller_reg_no', 'seller_iban', 'seller_legal_rep'}.issubset(cols)
    finally:
        release_db(conn)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_schema_buyback.py -k seller_identity -q`
Expected: FAIL (columns missing).

- [ ] **Step 3: Write minimal implementation**

In `schema_buyback.py`, immediately after the `for _col, _type in [ ('hold_prior_status', ...), ... ]:` idempotent-ALTER loop (ends ~line 67), add a second loop:

```python
    # ── Seller legal identity (for the purchase/consignație contract):
    # person CNP + CI, company reg/IBAN/legal-rep, universal address.
    # Idempotent per column — safe on already-seeded DBs.
    for _col, _type in [
        ('seller_address', 'TEXT'), ('seller_cnp', 'VARCHAR(13)'),
        ('seller_ci_serie', 'VARCHAR(10)'), ('seller_ci_number', 'VARCHAR(20)'),
        ('seller_reg_no', 'VARCHAR(30)'), ('seller_iban', 'VARCHAR(34)'),
        ('seller_legal_rep', 'VARCHAR(255)'),
    ]:
        cursor.execute(f'''
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='buyback_records' AND column_name='{_col}') THEN
                    ALTER TABLE buyback_records ADD COLUMN {_col} {_type};
                END IF;
            END $$;
        ''')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_schema_buyback.py -q`
Expected: PASS (all schema tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/migrations/domains/schema_buyback.py jarvis/tests/buyback/test_schema_buyback.py
git commit -m "feat(buyback): seller legal-identity columns on buyback_records"
```

---

### Task 2: Backend whitelists + serialization + PII redaction

**Files:**
- Modify: `jarvis/buyback/repositories/record_repository.py` (`_UPDATABLE_COLUMNS`, ~line 60)
- Modify: `jarvis/buyback/routes/records.py` (`_CREATE_FIELDS` ~line 33; `_PII_LOG_FIELDS` ~line 328)
- Modify: `jarvis/buyback/routes/_shared.py` (`_INTAKE_TEXT_FIELDS` ~line 260)
- Test: `jarvis/tests/buyback/test_routes_records.py`

**Interfaces:**
- Consumes: the Task 1 columns.
- Produces: create/update accept + persist the seven fields; they serialize into the record JSON; bad values 400; sensitive fields redacted from logs.

- [ ] **Step 1: Write the failing tests**

```python
# append to jarvis/tests/buyback/test_routes_records.py
_SELLER_ID = {
    'seller_address': 'Str. Exemplu 1, Cluj', 'seller_cnp': '1234567890123',
    'seller_ci_serie': 'CJ', 'seller_ci_number': '123456',
    'seller_reg_no': 'J12/345/2020', 'seller_iban': 'RO49AAAA1B31007593840000',
    'seller_legal_rep': 'Pop Ion',
}

def test_create_persists_seller_identity(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(**_SELLER_ID))
    assert r.status_code == 201, r.get_json()
    rec = r.get_json()['record']
    for k, v in _SELLER_ID.items():
        assert rec[k] == v

def test_update_persists_seller_identity(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'seller_cnp': '9999999999999'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['record']['seller_cnp'] == '9999999999999'

def test_create_rejects_dict_seller_cnp_as_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(seller_cnp={'x': 1}))
    assert r.status_code == 400, r.get_json()

def test_sensitive_seller_fields_are_pii_redacted():
    from buyback.routes.records import _PII_LOG_FIELDS
    assert {'seller_cnp', 'seller_ci_serie', 'seller_ci_number',
            'seller_iban', 'seller_address'}.issubset(_PII_LOG_FIELDS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_routes_records.py -k "seller_identity or pii_redacted or dict_seller_cnp" -q`
Expected: FAIL (fields dropped by whitelist; PII set missing them).

- [ ] **Step 3: Write minimal implementation**

In `record_repository.py` `_UPDATABLE_COLUMNS`, after `'seller_name', 'seller_email', 'seller_phone', 'seller_cui',`:
```python
    'seller_address', 'seller_cnp', 'seller_ci_serie', 'seller_ci_number',
    'seller_reg_no', 'seller_iban', 'seller_legal_rep',
```

In `routes/records.py` `_CREATE_FIELDS`, after `'seller_name', 'seller_email', 'seller_phone', 'seller_cui',`:
```python
    'seller_address', 'seller_cnp', 'seller_ci_serie', 'seller_ci_number',
    'seller_reg_no', 'seller_iban', 'seller_legal_rep',
```

In `routes/records.py` `_PII_LOG_FIELDS` (currently `frozenset({'seller_name', 'seller_email', 'seller_phone', 'seller_cui'})`), add:
```python
    'seller_address', 'seller_cnp', 'seller_ci_serie', 'seller_ci_number', 'seller_iban',
```

In `routes/_shared.py` `_INTAKE_TEXT_FIELDS`, add the same seven names to the tuple.

(`_serialize` is generic — no change; serialization is automatic once the columns are selected by `get_by_id`'s `SELECT *`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_routes_records.py -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add jarvis/buyback/repositories/record_repository.py jarvis/buyback/routes/records.py jarvis/buyback/routes/_shared.py jarvis/tests/buyback/test_routes_records.py
git commit -m "feat(buyback): accept+persist+redact seller legal-identity fields"
```

---

### Task 3: CRM sync of the new identity fields

**Files:**
- Modify: `jarvis/buyback/routes/records.py` (`_sync_client_contact`, ~lines 73-97)
- Test: `jarvis/tests/buyback/test_routes_records.py`

**Interfaces:**
- Consumes: the intake `data` dict + the linked `client_id`.
- Produces: `_shared.client_repo.update(client_id, {...})` also receives `cnp`, `nr_reg`, `responsible` when present (the 1:1-mappable CRM columns). CI serie/number + IBAN + free-text address stay record-only (no CRM column).

- [ ] **Step 1: Write the failing test**

```python
# append to jarvis/tests/buyback/test_routes_records.py
def test_sync_client_contact_pushes_cnp_regno_legalrep(monkeypatch):
    from buyback.routes import records as rec_mod
    captured = {}
    monkeypatch.setattr(rec_mod._shared.client_repo, 'update',
                        lambda cid, fields: captured.update(fields))
    rec_mod._sync_client_contact(42, {
        'seller_cnp': '1234567890123', 'seller_reg_no': 'J12/345/2020',
        'seller_legal_rep': 'Pop Ion', 'seller_ci_serie': 'CJ',  # CI not synced
    })
    assert captured.get('cnp') == '1234567890123'
    assert captured.get('nr_reg') == 'J12/345/2020'
    assert captured.get('responsible') == 'Pop Ion'
    assert 'ci_serie' not in captured and 'seller_ci_serie' not in captured
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_routes_records.py -k sync_client_contact_pushes -q`
Expected: FAIL (sync ignores the new fields).

- [ ] **Step 3: Write minimal implementation**

In `_sync_client_contact`, before the `if not updates: return` line, add:
```python
    cnp = str(data.get('seller_cnp') or '').strip()
    if cnp:
        updates['cnp'] = cnp
    reg_no = str(data.get('seller_reg_no') or '').strip()
    if reg_no:
        updates['nr_reg'] = reg_no
    legal_rep = str(data.get('seller_legal_rep') or '').strip()
    if legal_rep:
        updates['responsible'] = legal_rep
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_routes_records.py -k sync_client_contact -q`
Expected: PASS.

> Note: confirm `crm.repositories.client_repository.ClientRepository.update` whitelists `cnp`/`nr_reg`/`responsible`; if it drops unknown keys, add them to its allowed set in this task (same TDD cycle).

- [ ] **Step 5: Commit**

```bash
git add jarvis/buyback/routes/records.py jarvis/tests/buyback/test_routes_records.py
git commit -m "feat(buyback): sync seller cnp/reg/legal-rep to the CRM client"
```

---

### Task 4: Frontend types + form state + payload mapping

**Files:**
- Modify: `jarvis/frontend/src/types/buyback.ts` (`BuybackRecord`)
- Modify: `jarvis/frontend/src/pages/BuyBack/BuyBackForm.tsx` (`BuyBackFormState`, `emptyForm`, `recordToForm`, `CreatePayload`, `STRING_FIELDS`)
- Test: `jarvis/frontend/src/pages/BuyBack/payload.test.ts`

**Interfaces:**
- Consumes: the backend fields from Tasks 1-2.
- Produces: `buildCreatePayload` emits the seven fields when non-empty; `recordToForm` hydrates them for the edit flow.

- [ ] **Step 1: Write the failing test**

```typescript
// append to jarvis/frontend/src/pages/BuyBack/payload.test.ts
it('emits seller legal-identity fields when present, omits them when blank', () => {
  const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B',
    seller_cnp: '1234567890123', seller_ci_serie: 'CJ', seller_address: 'Str. 1',
    seller_reg_no: '', seller_iban: '  ' } as any)
  expect(p.seller_cnp).toBe('1234567890123')
  expect(p.seller_ci_serie).toBe('CJ')
  expect(p.seller_address).toBe('Str. 1')
  expect('seller_reg_no' in p).toBe(false)
  expect('seller_iban' in p).toBe(false)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/BuyBack/payload.test.ts`
Expected: FAIL (fields not in payload).

- [ ] **Step 3: Write minimal implementation**

In `types/buyback.ts` `BuybackRecord`, after `seller_cui: string | null`:
```typescript
  seller_address: string | null
  seller_cnp: string | null
  seller_ci_serie: string | null
  seller_ci_number: string | null
  seller_reg_no: string | null
  seller_iban: string | null
  seller_legal_rep: string | null
```

In `BuyBackForm.tsx`:
- `BuyBackFormState` (after `seller_cui?`): add the seven as `?: string`.
- `emptyForm`: add each as `''`.
- `recordToForm` (after `seller_cui: s(r.seller_cui)`): add `seller_address: s(r.seller_address), seller_cnp: s(r.seller_cnp), seller_ci_serie: s(r.seller_ci_serie), seller_ci_number: s(r.seller_ci_number), seller_reg_no: s(r.seller_reg_no), seller_iban: s(r.seller_iban), seller_legal_rep: s(r.seller_legal_rep),`.
- `CreatePayload` type: add the seven as `?: string`.
- `STRING_FIELDS` tuple: add the seven names (they're copied as-is, omitted when blank — exactly the behavior the test asserts).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/BuyBack/payload.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/types/buyback.ts jarvis/frontend/src/pages/BuyBack/BuyBackForm.tsx jarvis/frontend/src/pages/BuyBack/payload.test.ts
git commit -m "feat(buyback-ui): seller legal-identity fields in form state + payload"
```

---

### Task 5: "Date vânzător" form sub-section (conditional person/company)

**Files:**
- Modify: `jarvis/frontend/src/pages/BuyBack/BuyBackForm.tsx` (add the sub-section near the existing seller fields)
- Test: `jarvis/frontend/src/pages/BuyBack/BuyBackForm.identity.test.tsx` (new)

**Interfaces:**
- Consumes: `form.client_type` ('person' | 'company'), `form.seller_*`, and the `set(key, value)` updater.
- Produces: a rendered sub-section — address always; CNP + CI serie/nr for a person; nr. reg + IBAN + reprezentant legal for a company.

- [ ] **Step 1: Write the failing test**

```typescript
// jarvis/frontend/src/pages/BuyBack/BuyBackForm.identity.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 1, name: 'A' }, isLoading: false }) }))
vi.mock('@/api/buyback', () => ({ buybackApi: {
  getLookupOptions: () => Promise.resolve({}), getVinHistory: () => Promise.resolve({ history: [] }),
  getCompanies: () => Promise.resolve({ companies: [] }), searchCrmClients: () => Promise.resolve({ clients: [] }),
} }))
import BuyBackForm from './BuyBackForm'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter><BuyBackForm /></MemoryRouter></QueryClientProvider>)
}

describe('Date vânzător sub-section', () => {
  it('shows the section heading + an always-present address field', async () => {
    wrap()
    expect(await screen.findByText('Date vânzător')).toBeInTheDocument()
    expect(screen.getByText(/Adresă/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/BuyBack/BuyBackForm.identity.test.tsx`
Expected: FAIL (`Date vânzător` not found).

- [ ] **Step 3: Write minimal implementation**

In `BuyBackForm.tsx`, directly after the existing seller contact fields block (the group containing `seller_name`/`seller_email`/`seller_phone`/`seller_cui`), insert:

```tsx
<div className="space-y-2">
  <h3 className="text-sm font-semibold">Date vânzător</h3>
  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
    <div className="space-y-1.5 sm:col-span-2">
      <Label className="text-xs">Adresă</Label>
      <Input value={form.seller_address} onChange={(e) => set('seller_address', e.target.value)} placeholder="Stradă, nr., oraș, județ" />
    </div>
    {form.client_type !== 'company' && (
      <>
        <div className="space-y-1.5">
          <Label className="text-xs">CNP</Label>
          <Input value={form.seller_cnp} onChange={(e) => set('seller_cnp', e.target.value)} maxLength={13} placeholder="13 cifre" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1.5">
            <Label className="text-xs">CI serie</Label>
            <Input value={form.seller_ci_serie} onChange={(e) => set('seller_ci_serie', e.target.value.toUpperCase())} maxLength={10} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">CI număr</Label>
            <Input value={form.seller_ci_number} onChange={(e) => set('seller_ci_number', e.target.value)} maxLength={20} />
          </div>
        </div>
      </>
    )}
    {form.client_type === 'company' && (
      <>
        <div className="space-y-1.5">
          <Label className="text-xs">Nr. reg. com.</Label>
          <Input value={form.seller_reg_no} onChange={(e) => set('seller_reg_no', e.target.value)} placeholder="J12/345/2020" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">IBAN</Label>
          <Input value={form.seller_iban} onChange={(e) => set('seller_iban', e.target.value.toUpperCase())} maxLength={34} />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="text-xs">Reprezentant legal</Label>
          <Input value={form.seller_legal_rep} onChange={(e) => set('seller_legal_rep', e.target.value)} />
        </div>
      </>
    )}
  </div>
</div>
```

(`Label`, `Input`, and `set` are already imported/defined in this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/BuyBack/BuyBackForm.identity.test.tsx`
Expected: PASS.

- [ ] **Step 5: Full-build gate + commit**

```bash
cd jarvis/frontend && npm run build   # tsc -b + vite, must be clean
git add jarvis/frontend/src/pages/BuyBack/BuyBackForm.tsx jarvis/frontend/src/pages/BuyBack/BuyBackForm.identity.test.tsx
git commit -m "feat(buyback-ui): Date vânzător sub-section (person/company conditional)"
```

---

## Done-when

- The seven columns exist; create/update persist + serialize them; bad values 400; sensitive fields redacted.
- CRM sync pushes cnp/nr_reg/responsible (non-empty only).
- The intake/edit form shows "Date vânzător" with the correct person vs company fields.
- `DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/ -q` green; `cd jarvis/frontend && npm run build` clean; BuyBack vitest green.
- Then: code review → staging → prod (per the established cadence). Detail-page display of these fields is folded into P3 (the contract/Documente work).
