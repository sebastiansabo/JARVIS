# Test Drive CRM Client — Company/CUI + De-duplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Test Drive client-create flow (mobile) capture person **or** company clients, and stop it from creating duplicate CRM clients.

**Architecture:** Extend the existing `crm_clients` model with a `cui` (company tax id) and reuse its `company_name` + `client_type`. A "match-or-create" endpoint checks CRM by **email/phone** (persons) or **CUI** (companies) before inserting; the mobile `CreateClientPanel` gets a "Persoană juridică" toggle and offers an existing match instead of duplicating. OCR already pre-fills name/serie-permis/expiry (4b) — unchanged.

**Tech Stack:** Flask + psycopg2 (JARVIS backend), React + TS (jarvis-mobile-2, Capacitor), Postgres.

## Global Constraints

- **GDPR:** CNP is **NOT** a de-dup key and must not gate/index client identity. De-dup keys are **email + phone** (persons) and **CUI** (companies) only.
- **Two repos:** backend = `JARVIS` (deploy dev→staging→main, space pushes ≥30s); mobile = `jarvis-mobile-2` (push `main` → CI). Never hard-delete client data (soft/merge only).
- **Migrations:** additive + idempotent (`IF NOT EXISTS`), value-preserving.
- **Soft guard only:** ALL keys (email/phone/CUI) are soft — on a match the form *offers* the existing client, but nothing blocks the insert and there are **no DB unique constraints**. The consilier always decides.
- Romanian UI copy in the mobile form; keep existing field styling (`inputClass`).

---

## File Structure

**Backend (JARVIS):**
- `jarvis/migrations/domains/schema_crm.py` — add `cui` column + partial unique index on `email`.
- `jarvis/crm/repositories/client_repository.py` — add `cui` param to `create()`; add `find_duplicate(email, phone, cui)`.
- `jarvis/foi_parcurs/routes/test_drive.py` — `api_create_crm_client`: accept `company_name`/`cui`/`is_company`, set `client_type`; add `GET /api/foi-parcurs/crm-clients/check`.

**Mobile (jarvis-mobile-2):**
- `src/hooks/useApi.ts` — `CreateCrmClientPayload` gains `company_name`/`cui`/`is_company`; add `useCheckCrmClient(email, phone, cui)`; `CrmClient` type gains `company_name`/`cui`/`client_type`.
- `src/pages/Sales/TestDrive/DriverLicenseSection.tsx` — `CreateClientPanel`: "Persoană juridică" toggle → Company name + CUI; duplicate-match banner ("Client existent — folosește-l?").

---

## Phase 1 — Company + CUI capture

### Task 1.1: Backend — `cui` column + create route accepts company/CUI

**Files:**
- Modify: `jarvis/migrations/domains/schema_crm.py` (crm_clients column block)
- Modify: `jarvis/crm/repositories/client_repository.py:147` (`create`)
- Modify: `jarvis/foi_parcurs/routes/test_drive.py` (`api_create_crm_client`, ~line 230)

**Interfaces:**
- Produces: `crm_clients.cui TEXT`; `ClientRepository.create(..., cui=None)`; `POST /api/foi-parcurs/crm-clients` accepts `company_name`, `cui`, `is_company` and stores `client_type='company'` when `is_company`.

- [ ] **Step 1: Migration — add `cui` column (idempotent)** in `schema_crm.py`, next to the existing `email TEXT`/`company_name TEXT` block:

```python
cursor.execute('''
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='crm_clients' AND column_name='cui') THEN
            ALTER TABLE crm_clients ADD COLUMN cui TEXT;
        END IF;
    END $$;
''')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_cui ON crm_clients(cui)')
```

- [ ] **Step 2: Repo — add `cui` to `create()`** in `client_repository.py`. Add `cui=None` to the signature and include `cui` in the INSERT column list + VALUES + params tuple (mirror how `company_name` is already threaded).

- [ ] **Step 3: Route — accept company/CUI** in `api_create_crm_client` (`test_drive.py`). After the existing `display_name`/`phone` parsing:

```python
is_company = bool(data.get('is_company'))
company_name = (data.get('company_name') or '').strip() or None
cui = (data.get('cui') or '').strip() or None
```

Change the `_crm_client_repo.create(...)` call to pass `client_type='company' if is_company else 'person'`, `company_name=company_name`, `cui=cui`.

- [ ] **Step 4: Verify compile** — `python3 -m py_compile jarvis/foi_parcurs/routes/test_drive.py jarvis/crm/repositories/client_repository.py jarvis/migrations/domains/schema_crm.py` → no errors.

- [ ] **Step 5: Commit** — `git commit -m "crm: crm_clients.cui + create route accepts company_name/cui/client_type"`

### Task 1.2: Mobile — "Persoană juridică" toggle → Company name + CUI

**Files:**
- Modify: `src/hooks/useApi.ts` (`CreateCrmClientPayload`, `CrmClient`)
- Modify: `src/pages/Sales/TestDrive/DriverLicenseSection.tsx` (`CreateClientPanel`)

**Interfaces:**
- Consumes: `POST /api/foi-parcurs/crm-clients` fields from Task 1.1.
- Produces: `CreateClientPanel` sends `is_company`, `company_name`, `cui`.

- [ ] **Step 1: Types** — in `useApi.ts` add to `CreateCrmClientPayload`: `is_company?: boolean; company_name?: string; cui?: string`. Add to `CrmClient`: `company_name?: string | null; cui?: string | null; client_type?: string | null`.

- [ ] **Step 2: State + fields** — in `CreateClientPanel` add `const [isCompany, setIsCompany] = useState(false)`, `const [companyName, setCompanyName] = useState('')`, `const [cui, setCui] = useState('')`. Add a toggle row (checkbox) "Persoană juridică (firmă)". When `isCompany`, render two `Field`s: "Denumire firmă" (`companyName`) and "CUI" (`cui`, `inputMode="text"`).

- [ ] **Step 3: Payload** — in `handleCreate`'s `create.mutate({...})` add: `...(isCompany ? { is_company: true, company_name: companyName.trim() || undefined, cui: cui.trim() || undefined } : {})`.

- [ ] **Step 4: Build** — `npm run build && npx cap sync android` → `✓ built`, no TS errors.

- [ ] **Step 5: Commit + push** — `git commit -m "Test Drive: company/CUI toggle in client create" && git push origin main`

---

## Phase 2 — De-duplication (email/phone persons, CUI companies)

### Task 2.1: Backend — duplicate lookup + email unique guard

**Files:**
- Modify: `jarvis/migrations/domains/schema_crm.py` (partial unique index on email)
- Modify: `jarvis/crm/repositories/client_repository.py` (`find_duplicate`)
- Modify: `jarvis/foi_parcurs/routes/test_drive.py` (`GET /api/foi-parcurs/crm-clients/check`)

**Interfaces:**
- Produces: `ClientRepository.find_duplicate(email=None, phone=None, cui=None) -> dict|None`; `GET /api/foi-parcurs/crm-clients/check?email=&phone=&cui=` → `{ match: <client|null>, matched_on: 'email'|'phone'|'cui'|null }`.

- [ ] **Step 1: Non-unique lookup index** (soft guard — speeds the lookup, does NOT block inserts):

```python
cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_email_lower ON crm_clients (LOWER(email))')
```

- [ ] **Step 2: Repo — `find_duplicate`** in `client_repository.py` — return the first live (`merged_into_id IS NULL`) client matching, priority email → cui → phone:

```python
def find_duplicate(self, email=None, phone=None, cui=None):
    email = (email or '').strip().lower() or None
    phone = (phone or '').strip() or None
    cui = (cui or '').strip() or None
    if email:
        row = self.query_one(
            "SELECT * FROM crm_clients WHERE LOWER(email)=%s AND merged_into_id IS NULL LIMIT 1", (email,))
        if row: return dict(row) | {'matched_on': 'email'}
    if cui:
        row = self.query_one(
            "SELECT * FROM crm_clients WHERE cui=%s AND merged_into_id IS NULL LIMIT 1", (cui,))
        if row: return dict(row) | {'matched_on': 'cui'}
    if phone:
        row = self.query_one(
            "SELECT * FROM crm_clients WHERE phone=%s AND merged_into_id IS NULL LIMIT 1", (phone,))
        if row: return dict(row) | {'matched_on': 'phone'}
    return None
```

- [ ] **Step 3: Route — check endpoint** in `test_drive.py`:

```python
@foi_parcurs_bp.route('/api/foi-parcurs/crm-clients/check', methods=['GET'])
@login_required
def api_check_crm_client():
    m = _crm_client_repo.find_duplicate(
        email=request.args.get('email'),
        phone=(request.args.get('phone') or '').replace(' ', '').replace('-', ''),
        cui=request.args.get('cui'))
    return jsonify({'success': True, 'match': m, 'matched_on': (m or {}).get('matched_on')})
```

- [ ] **Step 4: Verify compile** — `python3 -m py_compile` the 3 files → no errors.

- [ ] **Step 5: Commit** — `git commit -m "crm: find_duplicate + /crm-clients/check + email partial-unique index"`

### Task 2.2: (removed — soft guard)

The create route does **not** auto-dedupe or block. All matching is surfaced to
the app via `GET /crm-clients/check` (Task 2.1); the consilier chooses to use the
existing client or create a new one. Nothing changes in `api_create_crm_client`.

### Task 2.3: Mobile — match-and-offer in the create form

**Files:**
- Modify: `src/hooks/useApi.ts` (`useCheckCrmClient`)
- Modify: `src/pages/Sales/TestDrive/DriverLicenseSection.tsx` (`CreateClientPanel`)

**Interfaces:**
- Consumes: `GET /api/foi-parcurs/crm-clients/check` (Task 2.1).
- Produces: a banner in `CreateClientPanel` — "Client existent: {name} — folosește-l?" with a button that calls `onCreated(existing, licenseNumber, licenseExpiry)` (selects it, no insert).

- [ ] **Step 1: Hook** — in `useApi.ts`:

```ts
export function useCheckCrmClient(email: string, phone: string, cui: string) {
  const enabled = !!(email.trim() || phone.trim() || cui.trim())
  return useQuery<{ match: CrmClient | null; matched_on: string | null }>({
    queryKey: ['crm-check', email, phone, cui],
    queryFn: () => apiFetch(`/api/foi-parcurs/crm-clients/check?email=${encodeURIComponent(email)}&phone=${encodeURIComponent(phone)}&cui=${encodeURIComponent(cui)}`),
    enabled,
    staleTime: 10_000,
  })
}
```

- [ ] **Step 2: Wire the banner** — in `CreateClientPanel`, debounce email/phone/cui (reuse `useDebouncedValue` pattern) and call `useCheckCrmClient`. When `data?.match` exists, render above the create button:

```tsx
{dupMatch && (
  <div className="rounded-xl bg-amber-50 p-3 text-xs space-y-2">
    <p>Client existent: <span className="font-semibold">{dupMatch.display_name || dupMatch.name}</span> ({matchedOnLabel}).</p>
    <button type="button" className="w-full rounded-xl bg-jarvis text-white py-2 font-medium"
      onClick={() => onCreated(dupMatch, licenseNumber.trim(), licenseExpiry.trim())}>
      Folosește clientul existent
    </button>
  </div>
)}
```

- [ ] **Step 3: Build** — `npm run build && npx cap sync android` → `✓ built`.

- [ ] **Step 4: Commit + push** — `git commit -m "Test Drive: offer existing client on email/phone/CUI match" && git push origin main`

---

## Phase 3 (optional, later) — Web merge tool for legacy duplicates

Not built now. Sketch: a web "Clients" admin list with a "possible duplicates" view (group by email/phone/cui), and a merge action that sets `merged_into_id` on the loser + repoints `foi_de_parcurs.client_id`. Uses the existing `crm_clients.merged_into_id`. Own spec when prioritized.

---

## Deploy order

1. Phase 1 backend (Task 1.1) → deploy dev→staging→main (has `cui` migration).
2. Phase 1 mobile (Task 1.2) → push jarvis-mobile-2 main (CI).
3. Phase 2 backend (2.1, 2.2) → deploy dev→staging→main (email index migration).
4. Phase 2 mobile (2.3) → push jarvis-mobile-2 main.

Each backend deploy: space staging/main pushes ≥30s; migrations are additive + idempotent.
