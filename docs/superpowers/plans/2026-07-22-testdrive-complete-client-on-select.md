# Test Drive — Complete Client Contact On Select — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After selecting a CRM client in the mobile Test Drive form, if the client is missing phone and/or email, prompt inline to fill them and persist to the CRM record; a missing phone blocks the form.

**Architecture:** New login-gated `PATCH /api/foi-parcurs/crm-clients/<id>` backend route reuses the existing `ClientRepository.update()` (phone/email already in its editable whitelist). The mobile `ClientPicker` exposes `email` on its type, renders an inline completion panel for missing fields after selection, PATCHes on save, and refreshes the selected client. The submit/draft/activate gate treats a phone-less selected client as incomplete.

**Tech Stack:** Flask (Python) + pytest backend; React + TypeScript + Vite + TanStack Query (Capacitor) frontend.

## Global Constraints

- Backend repo: JARVIS, branch `dev`. NEVER push to staging/main without explicit user confirmation.
- Frontend repo: jarvis-mobile-2, branch `main` (work on main directly).
- After ANY committed frontend code change: run `npm run build && npx cap sync android` in `/Users/sebastiansabo/Documents/Git/jarvis-mobile-2`.
- Phone validation regex (verbatim, already defined in `test_drive.py:14`): `^(07\d{8}|\+40\d{9}|004\d{10})$`. Strip spaces and dashes before matching.
- Phone error message (verbatim, matches existing create route): `Invalid phone. Must start with 07, +40, or 004`.
- Only email + phone are in scope. Do NOT touch address/CNP/other fields. Panel appears only when a field is empty (no editing of existing non-empty values).

---

### Task 1: Backend — `PATCH /api/foi-parcurs/crm-clients/<id>` route

**Files:**
- Modify: `jarvis/foi_parcurs/routes/test_drive.py` (add route after the create route ending at line 561)
- Test: `jarvis/tests/foi_parcurs/test_crm_client_update.py` (create)

**Interfaces:**
- Consumes: `_crm_client_repo` (module global, a `crm.repositories.ClientRepository`), `_PHONE_RE`, `login_required`, `jsonify`, `request`, `logger` — all already imported in `test_drive.py`.
- Uses `_crm_client_repo.update(client_id, data)` → returns the updated client dict, or `None` when no editable fields matched / the id does not exist.
- Produces: endpoint `PATCH /api/foi-parcurs/crm-clients/<int:id>` accepting JSON `{ phone?, email? }`, returning `{'success': True, 'client': <dict>}` on 200; `400` on bad/empty input; `404` when the client does not exist; `500` on repo error.

- [ ] **Step 1: Write the failing tests**

Create `jarvis/tests/foi_parcurs/test_crm_client_update.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


class FakeRepo:
    def __init__(self):
        self.calls = []
        self.existing = {1}

    def update(self, client_id, data):
        self.calls.append((client_id, data))
        if client_id not in self.existing:
            return None
        return {'id': client_id, 'phone': data.get('phone'), 'email': data.get('email')}


@pytest.fixture
def client(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(td_mod, '_crm_client_repo', fake)
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app._fake_repo = fake
    return app.test_client()


def test_update_phone_and_email(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1',
                     json={'phone': '0712 345-678', 'email': 'a@b.ro'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['client']['phone'] == '0712345678'  # spaces/dashes stripped
    assert body['client']['email'] == 'a@b.ro'


def test_update_email_only(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'email': 'x@y.ro'})
    assert r.status_code == 200
    # phone must NOT be part of the update when not supplied
    _, data = client.application._fake_repo.calls[-1]
    assert 'phone' not in data
    assert data['email'] == 'x@y.ro'


def test_update_invalid_phone(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'phone': '12345'})
    assert r.status_code == 400
    assert 'Invalid phone' in r.get_json()['error']


def test_update_empty_body(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={})
    assert r.status_code == 400


def test_update_unknown_id(client):
    r = client.patch('/api/foi-parcurs/crm-clients/999', json={'email': 'z@z.ro'})
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis && python -m pytest tests/foi_parcurs/test_crm_client_update.py -v`
Expected: FAIL — 404 for every route (route not registered yet).

- [ ] **Step 3: Implement the route**

In `jarvis/foi_parcurs/routes/test_drive.py`, immediately after the create route (after line 561), add:

```python
@foi_parcurs_bp.route('/api/foi-parcurs/crm-clients/<int:id>', methods=['PATCH'])
@login_required
def api_update_crm_client(id):
    """Login-gated partial update of a CRM client's contact details (phone/email)
    from the mobile Test Drive form, so a consilier can complete a selected
    client's missing contact info without full CRM access."""
    data = request.get_json(silent=True) or {}
    update_data = {}

    if 'phone' in data:
        phone = (data.get('phone') or '').strip()
        phone_clean = phone.replace(' ', '').replace('-', '')
        if not _PHONE_RE.match(phone_clean):
            return jsonify({
                'success': False,
                'error': 'Invalid phone. Must start with 07, +40, or 004',
            }), 400
        update_data['phone'] = phone_clean

    if 'email' in data:
        update_data['email'] = (data.get('email') or '').strip()

    if not update_data:
        return jsonify({'success': False, 'error': 'phone or email required'}), 400

    try:
        client = _crm_client_repo.update(id, update_data)
    except Exception as e:
        logger.exception('Failed to update CRM client %s from Test Drive form', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500

    if client is None:
        return jsonify({'success': False, 'error': 'Client not found'}), 404
    return jsonify({'success': True, 'client': client})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis && python -m pytest tests/foi_parcurs/test_crm_client_update.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/foi_parcurs/routes/test_drive.py jarvis/tests/foi_parcurs/test_crm_client_update.py
git commit -m "feat(foi-parcurs): PATCH crm-clients/<id> to complete phone/email

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Frontend — expose `email` on `CrmClient` + `useUpdateCrmClient` hook

**Files:**
- Modify: `src/hooks/useApi.ts` (`CrmClient` interface ~line 1007; add hook after `useCreateCrmClient` ~line 1106)

**Interfaces:**
- Consumes: `apiFetch`, `useMutation`, existing `CrmClient` / `CreateCrmClientResponse` types.
- Produces:
  - `CrmClient.email?: string | null` field (backend `search` already returns it via `SELECT c.*`; the normalizer passes the whole object through, so only the type needs it).
  - `useUpdateCrmClient()` → `useMutation` whose `mutationFn` takes `{ id: number | string; phone?: string; email?: string }` and returns `Promise<CrmClient | undefined>`. Sends only the provided keys.

- [ ] **Step 1: Add `email` to the `CrmClient` interface**

In `src/hooks/useApi.ts`, in the `CrmClient` interface (line 1007), add the field after `phone`:

```typescript
export interface CrmClient {
  id: number | string;
  display_name?: string | null;
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  company_name?: string | null;
  cui?: string | null;
  client_type?: string | null;
  // Driving license kept on the client for reuse (front-end checks expiry).
  driver_license_number?: string | null;
  driver_license_expiry?: string | null;
}
```

(No change to `normalizeCrmClients` — it returns the whole object, so `email` is already present at runtime once typed.)

- [ ] **Step 2: Add the `useUpdateCrmClient` hook**

In `src/hooks/useApi.ts`, immediately after `useCreateCrmClient` (after line 1106), add:

```typescript
/** Partial update of a CRM client's contact details via the login-gated
 *  foi-parcurs endpoint. Sends only the keys provided. Returns the updated
 *  client. */
export function useUpdateCrmClient() {
  return useMutation({
    mutationFn: async (
      vars: { id: number | string; phone?: string; email?: string },
    ): Promise<CrmClient | undefined> => {
      const body: Record<string, string> = {};
      if (vars.phone !== undefined) body.phone = vars.phone;
      if (vars.email !== undefined) body.email = vars.email;
      const res = await apiFetch<CreateCrmClientResponse>(
        `/api/foi-parcurs/crm-clients/${vars.id}`,
        { method: 'PATCH', body: JSON.stringify(body) },
      );
      return res?.client;
    },
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx tsc --noEmit`
Expected: no new errors from `useApi.ts`.

- [ ] **Step 4: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/hooks/useApi.ts
git commit -m "feat(test-drive): expose CrmClient.email + useUpdateCrmClient hook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Frontend — inline completion panel + gate change in `ClientPicker`

**Files:**
- Modify: `src/pages/Sales/TestDrive/New.tsx` (the `missing` object line 280; the `ClientPicker` selected-branch lines 984–1003; imports)

**Interfaces:**
- Consumes: `useUpdateCrmClient` (Task 2), `CrmClient.email` (Task 2), existing `inputClass`, `cn`, `_PHONE_RE`-equivalent client-side check, `onSelect`.
- Produces: `ClientPicker`, when a client is selected but missing phone and/or email, renders inputs for the missing field(s) + a Save button; on save calls `useUpdateCrmClient` then `onSelect(updated)`. Gate `missing.client` becomes truthy when no client is selected OR the selected client has no phone.

- [ ] **Step 1: Change the gate to require phone on the selected client**

In `src/pages/Sales/TestDrive/New.tsx`, change line 280 from:

```typescript
    client: !selectedClient,
```

to:

```typescript
    // A selected client with no phone is incomplete: the completion panel in
    // ClientPicker must be filled (phone is mandatory) before the form is valid.
    client: !selectedClient || !selectedClient.phone,
```

(This propagates automatically to `draftMissing.client` at line 306 and, via `draftMissing`, to `activateMissing`.)

- [ ] **Step 2: Add a client-side phone regex constant near the top of the file**

In `src/pages/Sales/TestDrive/New.tsx`, add near the other module-level constants (e.g. just above `function ClientPicker`):

```typescript
/** Mirrors the backend _PHONE_RE (test_drive.py): 07xxxxxxxx / +40xxxxxxxxx /
 *  004xxxxxxxxxx, after stripping spaces and dashes. */
const PHONE_RE = /^(07\d{8}|\+40\d{9}|004\d{10})$/;
```

- [ ] **Step 3: Render the completion panel in the selected branch**

In `ClientPicker`, replace the entire selected-branch (lines 984–1003, the `if (selected) { return (...) }` block) with:

```tsx
  if (selected) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-2 rounded-xl bg-card px-3.5 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{selected.display_name || selected.name || `Client #${String(selected.id)}`}</p>
            {selected.phone && <p className="text-xs text-muted-foreground">{selected.phone}</p>}
            {selected.email && <p className="text-xs text-muted-foreground truncate">{selected.email}</p>}
          </div>
          <button
            type="button"
            onClick={() => {
              onSelect(null);
              setTerm('');
            }}
            className="text-xs text-jarvis font-medium shrink-0 touch-target"
          >
            Schimbă
          </button>
        </div>
        {(!selected.phone || !selected.email) && (
          <ClientContactPanel selected={selected} onUpdated={onSelect} invalid={invalid} />
        )}
      </div>
    );
  }
```

- [ ] **Step 4: Add the `ClientContactPanel` component**

In `src/pages/Sales/TestDrive/New.tsx`, add immediately after the `ClientPicker` function (after line 1074):

```tsx
/** Inline "complete the client's contact details" panel shown under a selected
 *  client that is missing phone and/or email. Phone is required (blocks the
 *  form via the gate); email is optional. On save, PATCHes the CRM client and
 *  hands the refreshed record back via onUpdated. */
function ClientContactPanel({
  selected,
  onUpdated,
  invalid,
}: {
  selected: CrmClient;
  onUpdated: (client: CrmClient) => void;
  invalid?: boolean;
}) {
  const needPhone = !selected.phone;
  const needEmail = !selected.email;
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const updateMutation = useUpdateCrmClient();

  const save = async () => {
    setError(null);
    const vars: { id: number | string; phone?: string; email?: string } = { id: selected.id };
    if (needPhone) {
      const clean = phone.replace(/[\s-]/g, '');
      if (!PHONE_RE.test(clean)) {
        setError('Telefon invalid. Trebuie să înceapă cu 07, +40 sau 004.');
        return;
      }
      vars.phone = clean;
    }
    if (needEmail && email.trim()) {
      vars.email = email.trim();
    }
    try {
      const updated = await updateMutation.mutateAsync(vars);
      if (updated) onUpdated(updated);
    } catch {
      setError('Salvarea a eșuat. Încearcă din nou.');
    }
  };

  return (
    <div className={cn('rounded-xl bg-card px-3.5 py-3 space-y-2', invalid && 'ring-2 ring-destructive')}>
      <p className="text-xs text-muted-foreground">
        Completează datele de contact ale clientului{needPhone ? ' (telefonul este obligatoriu)' : ''}.
      </p>
      {needPhone && (
        <input
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="Telefon (07... / +40... / 004...)"
          className={inputClass}
        />
      )}
      {needEmail && (
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email (opțional)"
          className={inputClass}
        />
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      <button
        type="button"
        onClick={save}
        disabled={updateMutation.isPending}
        className="w-full rounded-xl bg-jarvis text-white text-sm font-medium py-2.5 px-3 touch-target active:scale-[0.98] transition-transform disabled:opacity-60"
      >
        {updateMutation.isPending ? 'Se salvează...' : 'Salvează datele clientului'}
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Ensure `useUpdateCrmClient` is imported**

In `src/pages/Sales/TestDrive/New.tsx`, add `useUpdateCrmClient` to the existing import from `../../../hooks/useApi` (the same import statement that brings in `useCrmClientSearch` / `useCreateCrmClient`). Verify by searching:

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && grep -n "useUpdateCrmClient\|useCreateCrmClient" src/pages/Sales/TestDrive/New.tsx`
Expected: both names appear in the import block.

- [ ] **Step 6: Typecheck + build**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 7: Commit + Capacitor sync**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/New.tsx
git commit -m "feat(test-drive): complete client phone/email inline after select

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
npx cap sync android
```

---

### Task 4: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Serve the app locally**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run dev`
Open the Test Drive → "Test Drive nou" form.

- [ ] **Step 2: Verify each case**

- Search + select a client that has **no phone** → the completion panel shows a phone input; the Client section stays red / submit blocked until a valid phone is saved. Enter `12345` → inline "Telefon invalid" error, no save. Enter `0712345678` → saves, panel collapses, phone shows on the card, gate clears.
- Select a client with a phone but **no email** → panel shows only the email input, labelled optional; leaving it empty and NOT saving does NOT block submit (gate is phone-only). Entering an email + save persists and shows it on the card.
- Select a **complete** client (has phone + email) → no panel, gate clear immediately.

- [ ] **Step 3: Confirm persistence**

After saving a phone for a previously phone-less client, clear the selection ("Schimbă"), search the same client again, and confirm the newly saved phone now appears in the search result row (proves the DB was updated).

---

## Notes for the executor

- The backend search endpoint already returns `email` (it selects `c.*`); no backend search change is needed — only the mobile `CrmClient` type was missing the field.
- Do NOT push JARVIS `dev` to staging/main, and do NOT merge without explicit user confirmation. The frontend `main` push will trigger the APK CI — that is expected, but confirm with the user before relying on the published APK.
