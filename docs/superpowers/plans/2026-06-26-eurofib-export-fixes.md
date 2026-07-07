# EuroFib Export Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 bugs in the EuroFib XLSX export and add configurable venituri rules, text templates, contract-level accounting data card, and client konto validation on contract creation.

**Architecture:** New DB table `facturare_venituri_rules` for FINAL invoice account mapping (supplier × comanda prefix → cont + kostenstelle). Extend `facturare_konto_config` with `text_template`. Export route (`api_generate_eurofib`) gets rewritten to read firmennr from `companies`, konto debit from `crm_clients`, use correct dates, and handle STORNO s/h inversion. Frontend gets Settings UI extensions, a permanent "Date Contabile" card on contracts, and konto validation in the create contract modal.

**Tech Stack:** Python/Flask backend, PostgreSQL, openpyxl XLSX generation, React/TypeScript frontend with shadcn/ui

## Global Constraints

- All work on `dev` branch only
- Migration files go in `jarvis/accounting/facturare/migrations/` with sequential numbering (next: `006_`)
- Repository methods in `jarvis/accounting/facturare/repositories/invoice_storage_repository.py`
- API routes in `jarvis/accounting/facturare/routes_orders.py`
- Frontend uses shadcn/ui components (`Button`, `Card`, `Input`, `Select`, etc.)
- No tests exist for this module — skip TDD, verify manually via staging
- Commit after each task

---

### Task 1: DB Migration — venituri_rules table + text_template column

**Files:**
- Create: `jarvis/accounting/facturare/migrations/006_eurofib_venituri_rules.sql`

**Produces:**
- Table `facturare_venituri_rules` with columns: id, supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_at, updated_by
- Column `text_template` on `facturare_konto_config`
- Seed data for AW International (PKW/LNF) and AW Premium (Audi)
- Seed text_template defaults for existing konto_config rows

- [ ] **Step 1: Create migration file**

```sql
-- 006_eurofib_venituri_rules.sql
-- EuroFib venituri rules for FINAL invoices + text templates

-- ── Venituri rules table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facturare_venituri_rules (
    id              SERIAL PRIMARY KEY,
    supplier_id     INTEGER NOT NULL REFERENCES companies(id),
    comanda_prefix  VARCHAR(5) NOT NULL,
    konto_venituri  VARCHAR(20) NOT NULL,
    kostenstelle    VARCHAR(20) NOT NULL,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by      INTEGER REFERENCES users(id),

    CONSTRAINT uq_venituri_supplier_prefix UNIQUE (supplier_id, comanda_prefix)
);

-- Seed: AW International (id=10)
INSERT INTO facturare_venituri_rules (supplier_id, comanda_prefix, konto_venituri, kostenstelle)
VALUES
    (10, '5', '707127', '0215'),   -- PKW
    (10, '3', '707128', '0216')    -- LNF
ON CONFLICT DO NOTHING;

-- Seed: AW Premium (id=11)
INSERT INTO facturare_venituri_rules (supplier_id, comanda_prefix, konto_venituri, kostenstelle)
VALUES
    (11, '*', '707132', '0314')    -- Audi (wildcard)
ON CONFLICT DO NOTHING;

-- ── Text template column on konto_config ──────────────────────────
ALTER TABLE facturare_konto_config
    ADD COLUMN IF NOT EXISTS text_template VARCHAR(100);

-- Seed text templates for existing rows
UPDATE facturare_konto_config SET text_template = 'avans {model} {comanda}'
    WHERE invoice_type = 'INVOICE' AND text_template IS NULL;
UPDATE facturare_konto_config SET text_template = 'storno avans {model} {comanda}'
    WHERE invoice_type = 'STORNO' AND text_template IS NULL;
UPDATE facturare_konto_config SET text_template = '{model} {comanda}'
    WHERE invoice_type = 'FINAL' AND text_template IS NULL;
```

- [ ] **Step 2: Run migration on local dev DB**

Run: `psql postgresql://localhost/defaultdb -f jarvis/accounting/facturare/migrations/006_eurofib_venituri_rules.sql`
Expected: CREATE TABLE, INSERT 0 2, INSERT 0 1, ALTER TABLE, UPDATE statements succeed

- [ ] **Step 3: Verify tables**

Run: `psql postgresql://localhost/defaultdb -c "SELECT * FROM facturare_venituri_rules ORDER BY supplier_id, comanda_prefix"`
Expected: 3 rows (AW Intl PKW, AW Intl LNF, AW Premium Audi)

Run: `psql postgresql://localhost/defaultdb -c "SELECT supplier_id, invoice_type, text_template FROM facturare_konto_config"`
Expected: text_template populated for all existing rows

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/facturare/migrations/006_eurofib_venituri_rules.sql
git commit -m "feat(facturare): add venituri_rules table and text_template column for EuroFib export"
```

---

### Task 2: Repository — venituri rules + konto config extensions

**Files:**
- Modify: `jarvis/accounting/facturare/repositories/invoice_storage_repository.py` (add methods after line 181)

**Consumes:** Table `facturare_venituri_rules` and column `facturare_konto_config.text_template` from Task 1

**Produces:**
- `get_venituri_rules()` → list of all rules with supplier_name
- `upsert_venituri_rule(supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by)` → upserted row
- `delete_venituri_rule(rule_id)` → None
- `match_venituri_rule(supplier_id, nr_comanda)` → single rule dict or None
- Updated `get_konto_config()` to include `text_template`
- Updated `upsert_konto_config()` to accept and save `text_template`

- [ ] **Step 1: Add venituri rule methods**

Add after the existing `upsert_konto_config` method (after line 181):

```python
    # ── Venituri Rules ─────────────────────────────────────────────

    def get_venituri_rules(self):
        return self.query_all(
            """SELECT vr.*, comp.company AS supplier_name
               FROM facturare_venituri_rules vr
               JOIN companies comp ON comp.id = vr.supplier_id
               ORDER BY vr.supplier_id, vr.comanda_prefix""")

    def upsert_venituri_rule(self, supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by=None):
        return self.execute(
            """INSERT INTO facturare_venituri_rules (supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (supplier_id, comanda_prefix) DO UPDATE SET
                 konto_venituri = EXCLUDED.konto_venituri, kostenstelle = EXCLUDED.kostenstelle,
                 updated_at = now(), updated_by = EXCLUDED.updated_by
               RETURNING *""",
            (supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by), returning=True)

    def delete_venituri_rule(self, rule_id):
        self.execute("DELETE FROM facturare_venituri_rules WHERE id = %s", (rule_id,))

    def match_venituri_rule(self, supplier_id, nr_comanda):
        """Find the venituri rule for a supplier + order number.
        Tries prefix match first, then wildcard '*'."""
        nr_str = str(nr_comanda)
        rules = self.query_all(
            "SELECT * FROM facturare_venituri_rules WHERE supplier_id = %s ORDER BY comanda_prefix DESC",
            (supplier_id,))
        for rule in rules:
            if rule["comanda_prefix"] != "*" and nr_str.startswith(rule["comanda_prefix"]):
                return rule
        for rule in rules:
            if rule["comanda_prefix"] == "*":
                return rule
        return None
```

- [ ] **Step 2: Update get_konto_config to include text_template**

Change the existing `get_konto_config` method (line 166-171):

```python
    def get_konto_config(self):
        return self.query_all(
            """SELECT kc.*, comp.company AS supplier_name
               FROM facturare_konto_config kc
               JOIN companies comp ON comp.id = kc.supplier_id
               ORDER BY kc.supplier_id, kc.invoice_type""")
```

No change needed — `SELECT kc.*` already includes `text_template` since it's on the table now.

- [ ] **Step 3: Update upsert_konto_config to accept text_template**

Replace the existing method (lines 173-181):

```python
    def upsert_konto_config(self, supplier_id, invoice_type, konto_debit, konto_credit, centru_gestiune, text_template=None, updated_by=None):
        return self.execute(
            """INSERT INTO facturare_konto_config (supplier_id, invoice_type, konto_debit, konto_credit, centru_gestiune, text_template, updated_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (supplier_id, invoice_type) DO UPDATE SET
                 konto_debit = EXCLUDED.konto_debit, konto_credit = EXCLUDED.konto_credit,
                 centru_gestiune = EXCLUDED.centru_gestiune, text_template = EXCLUDED.text_template,
                 updated_at = now(), updated_by = EXCLUDED.updated_by
               RETURNING *""",
            (supplier_id, invoice_type, konto_debit, konto_credit, centru_gestiune, text_template, updated_by), returning=True)
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/facturare/repositories/invoice_storage_repository.py
git commit -m "feat(facturare): add venituri rules repository methods and text_template support"
```

---

### Task 3: API Routes — venituri rules CRUD + konto config text_template

**Files:**
- Modify: `jarvis/accounting/facturare/routes_orders.py` (add routes after line 873, update existing konto routes)

**Consumes:** Repository methods from Task 2

**Produces:**
- `GET /facturare/api/venituri-rules` → `{rules: [{id, supplier_id, supplier_name, comanda_prefix, konto_venituri, kostenstelle}]}`
- `PUT /facturare/api/venituri-rules` → upsert rules from `{items: [...]}`
- `DELETE /facturare/api/venituri-rules/<id>` → delete single rule
- Updated `GET /facturare/api/konto-config` to return `text_template`
- Updated `PUT /facturare/api/konto-config` to save `text_template`

- [ ] **Step 1: Add venituri rules GET endpoint**

Add after the `api_put_konto_config` function (after line 873):

```python
# ── Venituri Rules ───────────────────────────────────────────────

@facturare_bp.route("/facturare/api/venituri-rules")
@login_required
@handle_api_errors
def api_get_venituri_rules():
    if not _check_perm("view"):
        return error_response("Permission denied", 403)
    rows = _repo.get_venituri_rules()
    return jsonify({"rules": [
        {"id": r["id"], "supplier_id": r["supplier_id"], "supplier_name": r.get("supplier_name", ""),
         "comanda_prefix": r["comanda_prefix"], "konto_venituri": r["konto_venituri"],
         "kostenstelle": r["kostenstelle"]}
        for r in rows
    ]})


@facturare_bp.route("/facturare/api/venituri-rules", methods=["PUT"])
@login_required
@handle_api_errors
def api_put_venituri_rules():
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    items = data.get("items", [])
    for item in items:
        _repo.upsert_venituri_rule(
            supplier_id=item["supplier_id"], comanda_prefix=item["comanda_prefix"],
            konto_venituri=item["konto_venituri"], kostenstelle=item["kostenstelle"],
            updated_by=current_user.id,
        )
    return jsonify({"success": True, "count": len(items)})


@facturare_bp.route("/facturare/api/venituri-rules/<int:rule_id>", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_venituri_rule(rule_id):
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    _repo.delete_venituri_rule(rule_id)
    return jsonify({"success": True})
```

- [ ] **Step 2: Update konto config GET to return text_template**

In `api_get_konto_config` (line 843-855), update the response dict to include text_template:

Change the dict comprehension inside `jsonify` to:

```python
    return jsonify({"configs": [
        {"supplier_id": r["supplier_id"], "supplier_name": r.get("supplier_name", ""),
         "invoice_type": r["invoice_type"], "konto_debit": r.get("konto_debit") or "",
         "konto_credit": r.get("konto_credit") or "", "centru_gestiune": r.get("centru_gestiune") or "",
         "text_template": r.get("text_template") or ""}
        for r in rows
    ]})
```

- [ ] **Step 3: Update konto config PUT to save text_template**

In `api_put_konto_config` (line 858-873), add `text_template` to the upsert call:

```python
        _repo.upsert_konto_config(
            supplier_id=item["supplier_id"], invoice_type=item["invoice_type"],
            konto_debit=item.get("konto_debit") or None, konto_credit=item.get("konto_credit") or None,
            centru_gestiune=item.get("centru_gestiune") or None,
            text_template=item.get("text_template") or None,
            updated_by=current_user.id,
        )
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py
git commit -m "feat(facturare): add venituri rules API and text_template to konto config"
```

---

### Task 4: Settings Tab UI — text_template column + venituri rules section

**Files:**
- Modify: `jarvis/frontend/src/pages/Accounting/Facturare/index.tsx`

**Consumes:** API endpoints from Task 3

**Produces:**
- `text_template` column in the existing Konto Config table
- New "Reguli Venituri Facturi Finale" card with editable table + Add Rule + Save

- [ ] **Step 1: Add text_template to KontoEntry interface and FIELD_LABELS**

At line 23-33, update the INVOICE_TYPES fields and add text_template:

```typescript
const INVOICE_TYPES = [
  { key: 'INVOICE', label: 'Advance', fields: ['konto_debit', 'konto_credit', 'centru_gestiune', 'text_template'] as const },
  { key: 'STORNO', label: 'Storno', fields: ['konto_debit', 'konto_credit', 'centru_gestiune', 'text_template'] as const },
  { key: 'FINAL', label: 'Final', fields: ['konto_debit', 'konto_credit', 'centru_gestiune', 'text_template'] as const },
] as const

const FIELD_LABELS: Record<string, string> = {
  konto_debit: 'Konto Debit',
  konto_credit: 'Konto Credit',
  centru_gestiune: 'Centru Gest.',
  text_template: 'Text Template',
}

interface KontoEntry {
  konto_debit: string
  konto_credit: string
  centru_gestiune: string
  text_template: string
}
```

- [ ] **Step 2: Update KontoSettingsTab defaults**

In the load callback (line 57), add text_template default:

```typescript
m[String(c.id)][t.key] = { konto_debit: '', konto_credit: '', centru_gestiune: '', text_template: '' }
```

And in the config mapping (line 63-66):

```typescript
m[sid][cfg.invoice_type] = {
  konto_debit: cfg.konto_debit || '',
  konto_credit: cfg.konto_credit || '',
  centru_gestiune: cfg.centru_gestiune || '',
  text_template: cfg.text_template || '',
}
```

- [ ] **Step 3: Update save function**

In the save function (line 90), include text_template in items:

```typescript
items.push({ supplier_id: parseInt(sid), invoice_type: type, ...entry })
```

This already spreads the full entry including text_template. No change needed.

- [ ] **Step 4: Adjust Input width for text_template**

In the table cell rendering (line 153), update the className condition:

```typescript
<Input className={`h-7 text-xs text-center ${f === 'text_template' ? 'w-32' : f === 'centru_gestiune' ? 'w-16' : 'w-20'}`}
  value={entry[f]} onChange={e => update(String(c.id), t.key, f, e.target.value)}
  placeholder={f === 'text_template' ? (t.key === 'INVOICE' ? 'avans {model} {comanda}' : t.key === 'STORNO' ? 'storno avans {model} {comanda}' : '{model} {comanda}') : undefined} />
```

- [ ] **Step 5: Add VenituriRulesSection component**

Add before the main `Facturare` component (before line 170):

```typescript
// ── Venituri Rules Section ─────────────────────────────────────

interface VenituriRule {
  id?: number
  supplier_id: string
  comanda_prefix: string
  konto_venituri: string
  kostenstelle: string
}

function VenituriRulesSection({ companies }: { companies: Company[] }) {
  const [rules, setRules] = useState<VenituriRule[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/facturare/api/venituri-rules')
      .then(r => r.ok ? r.json() : { rules: [] })
      .then(data => {
        setRules((data.rules || []).map((r: any) => ({
          id: r.id, supplier_id: String(r.supplier_id),
          comanda_prefix: r.comanda_prefix, konto_venituri: r.konto_venituri,
          kostenstelle: r.kostenstelle,
        })))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const updateRule = (idx: number, field: keyof VenituriRule, value: string) => {
    setRules(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const addRule = () => {
    setRules(prev => [...prev, { supplier_id: '', comanda_prefix: '', konto_venituri: '', kostenstelle: '' }])
  }

  const removeRule = async (idx: number) => {
    const rule = rules[idx]
    if (rule.id) {
      await fetch(`/facturare/api/venituri-rules/${rule.id}`, { method: 'DELETE' })
    }
    setRules(prev => prev.filter((_, i) => i !== idx))
  }

  const save = async () => {
    setSaving(true)
    const items = rules.filter(r => r.supplier_id && r.comanda_prefix && r.konto_venituri && r.kostenstelle)
      .map(r => ({ supplier_id: parseInt(r.supplier_id), comanda_prefix: r.comanda_prefix, konto_venituri: r.konto_venituri, kostenstelle: r.kostenstelle }))
    try {
      const res = await fetch('/facturare/api/venituri-rules', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })
      if (!res.ok) throw new Error('Failed to save')
      toast.success(`Saved ${items.length} rules`)
      load()
    } catch (err: any) { toast.error(err.message) }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin" /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">Reguli Venituri — Facturi Finale (supplier × prefix nr comandă → cont + kostenstelle)</h3>
        <div className="flex gap-2">
          <Button onClick={addRule} size="sm" variant="outline">+ Add Rule</Button>
          <Button onClick={save} disabled={saving} size="sm">
            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />} Save
          </Button>
        </div>
      </div>
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left px-3 py-2 font-medium">Supplier</th>
                <th className="text-left px-3 py-2 font-medium">Prefix Comandă</th>
                <th className="text-left px-3 py-2 font-medium">Cont Venituri</th>
                <th className="text-left px-3 py-2 font-medium">Kostenstelle</th>
                <th className="px-2 py-2 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule, idx) => (
                <tr key={idx} className="border-b hover:bg-muted/20">
                  <td className="px-2 py-1">
                    <select className="h-7 text-xs border rounded px-1 w-full" value={rule.supplier_id}
                      onChange={e => updateRule(idx, 'supplier_id', e.target.value)}>
                      <option value="">Select</option>
                      {companies.map(c => <option key={c.id} value={String(c.id)}>{c.company}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-1"><Input className="h-7 text-xs w-16" value={rule.comanda_prefix} placeholder="5, 3, *"
                    onChange={e => updateRule(idx, 'comanda_prefix', e.target.value)} /></td>
                  <td className="px-2 py-1"><Input className="h-7 text-xs w-20" value={rule.konto_venituri}
                    onChange={e => updateRule(idx, 'konto_venituri', e.target.value)} /></td>
                  <td className="px-2 py-1"><Input className="h-7 text-xs w-20" value={rule.kostenstelle}
                    onChange={e => updateRule(idx, 'kostenstelle', e.target.value)} /></td>
                  <td className="px-2 py-1">
                    <button onClick={() => removeRule(idx)} className="text-red-500 hover:text-red-700 text-xs">✕</button>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">No rules configured</td></tr>}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 6: Add VenituriRulesSection to Settings tab**

In the main `Facturare` component, find the TabsContent for "settings" (around line 207-210). It currently renders only `<KontoSettingsTab>`. Add VenituriRulesSection below it:

```typescript
<TabsContent value="settings" className="space-y-6">
  <KontoSettingsTab companies={companies} />
  <VenituriRulesSection companies={companies} />
</TabsContent>
```

- [ ] **Step 7: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/Facturare/index.tsx
git commit -m "feat(facturare): Settings tab — text_template column and venituri rules section"
```

---

### Task 5: Contract Modal — client konto validation + inline edit

**Files:**
- Modify: `jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx` (CreateContractDialog, around lines 150-194)

**Consumes:** `GET /api/crm/clients?name=...` (existing), `companies` prop with `eurofib_klient_id`

**Produces:** After selecting Customer + Supplier, shows konto status badge. If missing, shows inline input to add it. Saves via existing CRM edit endpoint.

- [ ] **Step 1: Ensure companies prop includes eurofib_klient_id**

In the parent component that fetches companies, the fetch call uses `/api/companies-vat`. Check that this endpoint returns `eurofib_klient_id`. If not, the companies-vat endpoint needs updating.

Check in `routes_orders.py` or `company_repository.py` — the `get_companies_with_vat()` query (which backs `/api/companies-vat`) already selects `eurofib_klient_id` from companies. Verify the Company interface in `index.tsx` includes it:

Update the `Company` interface (line 15-19 of `index.tsx`):

```typescript
interface Company {
  id: number
  company: string
  vat: string | null
  eurofib_klient_id: number | null
}
```

Also verify the `/api/companies-vat` endpoint returns this field. If it's a simple `SELECT id, company, vat FROM companies` query, add `eurofib_klient_id` to the select.

- [ ] **Step 2: Add konto validation state to CreateContractDialog**

Inside `CreateContractDialog` (line 150+), add state after existing state declarations:

```typescript
const [clientKonto, setClientKonto] = useState<{ status: 'unknown' | 'ok' | 'missing'; value: string }>({ status: 'unknown', value: '' })
const [kontoInput, setKontoInput] = useState('')
const [savingKonto, setSavingKonto] = useState(false)
```

- [ ] **Step 3: Add konto check effect**

Add after the state declarations:

```typescript
// Check client konto when customer + supplier are selected
useEffect(() => {
  if (!customerId || !supplierId) { setClientKonto({ status: 'unknown', value: '' }); return }
  const company = companies.find(c => String(c.id) === supplierId)
  const klientId = company?.eurofib_klient_id
  if (!klientId) { setClientKonto({ status: 'unknown', value: '' }); return }

  fetch(`/api/crm/clients/${customerId}`)
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data) { setClientKonto({ status: 'missing', value: '' }); return }
      const kdMap = data.eurofib_konto_debit as Record<string, number> | null
      const val = kdMap?.[String(klientId)]
      if (val) {
        setClientKonto({ status: 'ok', value: String(val) })
      } else {
        setClientKonto({ status: 'missing', value: '' })
      }
    })
    .catch(() => setClientKonto({ status: 'unknown', value: '' }))
}, [customerId, supplierId, companies])
```

- [ ] **Step 4: Add konto save handler**

```typescript
const saveClientKonto = async () => {
  if (!kontoInput.trim() || !customerId || !supplierId) return
  const company = companies.find(c => String(c.id) === supplierId)
  const klientId = company?.eurofib_klient_id
  if (!klientId) return

  setSavingKonto(true)
  try {
    // Fetch current client to get existing konto map
    const clientRes = await fetch(`/api/crm/clients/${customerId}`)
    const clientData = await clientRes.json()
    const kdMap = (clientData.eurofib_konto_debit as Record<string, number>) || {}
    kdMap[String(klientId)] = parseInt(kontoInput)

    await fetch(`/api/crm/clients/${customerId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ eurofib_konto_debit: kdMap }),
    })
    setClientKonto({ status: 'ok', value: kontoInput })
    toast.success('Konto saved')
  } catch { toast.error('Failed to save konto') }
  finally { setSavingKonto(false) }
}
```

- [ ] **Step 5: Add konto validation UI in the dialog**

In the Dialog JSX, after the Customer search field and before the Date field, add:

```tsx
{/* Konto validation */}
{customerId && supplierId && (
  <div className="space-y-1">
    {clientKonto.status === 'ok' && (
      <div className="flex items-center gap-2 text-xs text-green-600 bg-green-50 px-3 py-1.5 rounded">
        <span>✓</span>
        <span>Konto {companies.find(c => String(c.id) === supplierId)?.company}: <strong>{clientKonto.value}</strong></span>
      </div>
    )}
    {clientKonto.status === 'missing' && (
      <div className="space-y-1.5">
        <div className="text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded">
          ⚠ Konto debit lipsește pentru {companies.find(c => String(c.id) === supplierId)?.company}
        </div>
        <div className="flex gap-2">
          <Input className="h-7 text-xs w-28" placeholder="ex: 41214286" value={kontoInput}
            onChange={e => setKontoInput(e.target.value)} />
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={saveClientKonto} disabled={savingKonto}>
            {savingKonto ? 'Saving...' : 'Save Konto'}
          </Button>
        </div>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/Facturare/index.tsx jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx
git commit -m "feat(facturare): contract modal — client konto validation and inline edit"
```

---

### Task 6: Contract View — "Date Contabile" permanent card

**Files:**
- Modify: `jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx` (contract detail section)
- Modify: `jarvis/accounting/facturare/routes_orders.py` (new endpoint for accounting summary)

**Consumes:** `companies.eurofib_klient_id`, `crm_clients.eurofib_konto_debit`, `facturare_konto_config`, `facturare_venituri_rules`

**Produces:**
- `GET /facturare/api/contracts/<id>/accounting-summary` → JSON with all accounting data
- React card component showing the summary on every contract view

- [ ] **Step 1: Add backend endpoint**

Add to `routes_orders.py` after the venituri rules endpoints:

```python
@facturare_bp.route("/facturare/api/contracts/<int:contract_id>/accounting-summary")
@login_required
@handle_api_errors
def api_contract_accounting_summary(contract_id):
    """Return all accounting data relevant to a contract for display."""
    if not _check_perm("view"):
        return error_response("Permission denied", 403)

    contract = _repo.get_contract_by_id(contract_id)
    if not contract:
        return error_response("Contract not found", 404)

    # Supplier info (firmennr)
    supplier = _repo.query_one(
        "SELECT id, company, eurofib_klient_id FROM companies WHERE id = %s",
        (contract["supplier_id"],))

    # Customer konto debit
    customer = _repo.query_one(
        "SELECT id, display_name, eurofib_konto_debit FROM crm_clients WHERE id = %s",
        (contract["customer_id"],))

    firmennr = supplier.get("eurofib_klient_id") if supplier else None
    kd_map = customer.get("eurofib_konto_debit") if customer else None
    client_konto_debit = kd_map.get(str(firmennr)) if isinstance(kd_map, dict) and firmennr else None

    # Konto configs per invoice type
    konto_configs = {}
    for inv_type in ('INVOICE', 'STORNO', 'FINAL'):
        row = _repo.query_one(
            "SELECT konto_debit, konto_credit, centru_gestiune, text_template FROM facturare_konto_config WHERE supplier_id = %s AND invoice_type = %s",
            (contract["supplier_id"], inv_type))
        konto_configs[inv_type] = dict(row) if row else None

    # Venituri rules for this supplier
    venituri = _repo.query_all(
        "SELECT comanda_prefix, konto_venituri, kostenstelle FROM facturare_venituri_rules WHERE supplier_id = %s ORDER BY comanda_prefix",
        (contract["supplier_id"],))

    return jsonify({
        "firmennr": firmennr,
        "supplier_name": supplier["company"] if supplier else None,
        "customer_name": customer["display_name"] if customer else None,
        "client_konto_debit": client_konto_debit,
        "konto_configs": konto_configs,
        "venituri_rules": [dict(r) for r in venituri] if venituri else [],
    })
```

- [ ] **Step 2: Add AccountingCard component in ComenziTab.tsx**

Add a new component in `ComenziTab.tsx` (before the main export):

```tsx
function AccountingCard({ contractId }: { contractId: number }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/facturare/api/contracts/${contractId}/accounting-summary`)
      .then(r => r.ok ? r.json() : null)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [contractId])

  if (loading) return <div className="py-2"><Loader2 className="h-4 w-4 animate-spin" /></div>
  if (!data) return null

  const missing: string[] = []
  if (!data.firmennr) missing.push('Firmennr')
  if (!data.client_konto_debit) missing.push('Client Konto Debit')
  if (!data.konto_configs?.INVOICE) missing.push('Konto INVOICE')
  if (!data.konto_configs?.STORNO) missing.push('Konto STORNO')
  if (!data.konto_configs?.FINAL) missing.push('Konto FINAL')

  const Row = ({ label, value, warn }: { label: string; value: any; warn?: boolean }) => (
    <div className="flex justify-between text-xs py-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className={warn ? 'text-red-500 font-medium' : 'font-medium'}>{value ?? '—'}</span>
    </div>
  )

  return (
    <div className="border rounded-lg p-3 bg-muted/30 space-y-1">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold">Date Contabile</span>
        {missing.length > 0 && <span className="text-[10px] text-red-500 bg-red-50 px-1.5 py-0.5 rounded">⚠ {missing.length} lipsă</span>}
      </div>
      <Row label="Firmennr" value={data.firmennr} warn={!data.firmennr} />
      <Row label="Client" value={data.customer_name} />
      <Row label="Konto Debit Client" value={data.client_konto_debit} warn={!data.client_konto_debit} />
      {data.konto_configs?.INVOICE && <Row label="Konto Credit (Avans)" value={data.konto_configs.INVOICE.konto_credit} />}
      {data.konto_configs?.STORNO && <Row label="Konto Credit (Storno)" value={data.konto_configs.STORNO.konto_credit} />}
      {data.konto_configs?.FINAL && <Row label="Konto Credit (Final)" value={data.konto_configs.FINAL.konto_credit} />}
      {data.konto_configs?.INVOICE && <Row label="Centru Gestiune" value={data.konto_configs.INVOICE.centru_gestiune} />}
      {data.venituri_rules?.length > 0 && (
        <div className="pt-1 border-t mt-1">
          <span className="text-[10px] text-muted-foreground">Venituri FINAL:</span>
          {data.venituri_rules.map((r: any, i: number) => (
            <Row key={i} label={`Prefix ${r.comanda_prefix}`} value={`${r.konto_venituri} / KST ${r.kostenstelle}`} />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Render AccountingCard in the contract detail area**

Find the section in ComenziTab where the contract detail / anexa list is shown (where `drillContract` is displayed). Add `<AccountingCard contractId={drillContract.id} />` in the contract header area, visible when a contract is selected.

The exact location depends on the current layout — look for where `drillContract.contract_ref` is displayed and add the card nearby, for example:

```tsx
{drillContract && <AccountingCard contractId={drillContract.id} />}
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx
git commit -m "feat(facturare): permanent Date Contabile card on contract view"
```

---

### Task 7: Export Fix — firmennr, dates, and text template (Bugs 1, 2, 3-avans, 8-text)

**Files:**
- Modify: `jarvis/accounting/facturare/routes_orders.py` (lines 1265-1385, `api_generate_eurofib`)
- Modify: `jarvis/accounting/facturare/generators/eurofib_xlsx.py`
- Modify: `jarvis/accounting/facturare/config.py`
- Modify: `jarvis/accounting/facturare/models.py`

**Consumes:** `companies.eurofib_klient_id`, `facturare_konto_config.text_template`, Task 1-2 DB changes

**Produces:** Corrected EuroFib export with proper firmennr, invoice dates (not export dates), and configurable text template

- [ ] **Step 1: Add kostenstelle to EurofibConfig**

In `config.py`, update `EurofibConfig` (line 59-67):

```python
class EurofibConfig(BaseModel):
    klient: int
    konto_debit: int
    konto_credit: int
    belegart: str = "JVV"
    steuercode: str = "L00"
    fw_steuercode: str = "L00"
    text_template: str = "avans {model} {comanda}"
    brand_map: dict[str, str] = {}
```

No change needed — `text_template` already exists with a default. `kostenstelle` is per-line, not per-config.

- [ ] **Step 2: Add kostenstelle to OrderLine model**

In `models.py`, add `kostenstelle` field to `OrderLine` (line 12-28):

```python
@dataclass(frozen=True)
class OrderLine:
    """Single row from an Anexa xlsx — one vehicle order."""
    comanda: int
    model: str
    culoare: str
    list_price: float | None
    selling_price: float | None
    advance: float
    rest: float | None
    vin: str | None = None
    contract_ref: str | None = None
    anexa_ref: str | None = None
    start_no: int | None = None
    invoice_date: str | None = None
    qty: int = 1
    kurs: float | None = None
    storno_description: str | None = None
    kostenstelle: str | None = None
    konto_credit_override: str | None = None
```

- [ ] **Step 3: Update XLSX renderer to write kostenstelle and use text_template**

In `eurofib_xlsx.py`, update `_write_debit` (line 58-90) to write kostenstelle at column 36 (AJ) and use per-line konto_credit_override:

Add at end of `_write_debit` method, before the kurs_per comment:

```python
        if line.kostenstelle:
            ws.cell(row=r, column=36, value=line.kostenstelle)  # AJ kostenstelle
```

Add same to `_write_credit` method (line 92-125):

```python
        if line.kostenstelle:
            ws.cell(row=r, column=36, value=line.kostenstelle)  # AJ kostenstelle
```

Also update `_write_credit` to use `konto_credit_override` when present. Change line 106:

```python
        ws.cell(row=r, column=3, value=int(line.konto_credit_override) if line.konto_credit_override else cfg.eurofib.konto_credit)  # C konto
```

And update `_write_debit` gegenkonto (line 83):

```python
        ws.cell(row=r, column=16, value=int(line.konto_credit_override) if line.konto_credit_override else cfg.eurofib.konto_credit) # P gegenkonto
```

- [ ] **Step 4: Fix firmennr in route — read from companies table**

In `routes_orders.py`, in `api_generate_eurofib` (around line 1360-1373), replace the `klient=0` with a DB lookup:

```python
    # Get supplier firmennr (eurofib_klient_id)
    supplier_row = _repo.query_one(
        "SELECT eurofib_klient_id FROM companies WHERE id = %s",
        (contract["supplier_id"],))
    firmennr = supplier_row.get("eurofib_klient_id") if supplier_row else None
    if not firmennr:
        return error_response("Firmennr (eurofib_klient_id) not configured for this supplier. Check company settings.", 400)
```

Then use `firmennr` in the `EurofibConfig`:

```python
    eurofib=EurofibConfig(
        klient=firmennr,
        konto_debit=int(konto_row["konto_debit"]),
        konto_credit=int(konto_row["konto_credit"]),
        text_template=konto_row.get("text_template") or default_text_templates.get(inv_type_str, "{model} {comanda}"),
    ),
```

Add the defaults dict before the config construction:

```python
    default_text_templates = {
        'INVOICE': 'avans {model} {comanda}',
        'STORNO': 'storno avans {model} {comanda}',
        'FINAL': '{model} {comanda}',
    }
```

- [ ] **Step 5: Fix invoice date — strict issued_date, no fallback to today()**

Replace line 1314:

```python
    issued_date = inv_row.get("issued_date")
    if not issued_date:
        return error_response("Invoice has no issued date. Please set the issued date before exporting.", 400)
    if isinstance(issued_date, str):
        issued_date = date_type.fromisoformat(issued_date)
```

- [ ] **Step 6: Fix text template rendering in the route**

Update the text rendering in the render loop. Currently (around lines 1340-1353 for non-STORNO, and 1318-1339 for STORNO), the text is generated inside the renderer via `text_template.format(brand_short=..., comanda=...)`. But now the template uses `{model}` and `{comanda}` instead of `{brand_short}`.

In `eurofib_xlsx.py`, update the render methods (line 141-154 and 164-177). Change the text generation:

```python
            text = self.cfg.eurofib.text_template.format(
                model=line.model, comanda=line.comanda,
                brand_short=brand,  # keep for backwards compat
            )
```

This works because Python's `str.format` ignores extra kwargs but raises on missing ones. Since new templates use `{model}` and old ones use `{brand_short}`, passing both covers both cases.

- [ ] **Step 7: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py jarvis/accounting/facturare/generators/eurofib_xlsx.py jarvis/accounting/facturare/config.py jarvis/accounting/facturare/models.py
git commit -m "fix(facturare): EuroFib export — firmennr, strict issued_date, text template, kostenstelle column"
```

---

### Task 8: Export Fix — STORNO bugs (Bugs 3-storno, 4, 5, 6)

**Files:**
- Modify: `jarvis/accounting/facturare/routes_orders.py` (STORNO section of `api_generate_eurofib`, lines 1318-1339)
- Modify: `jarvis/accounting/facturare/generators/eurofib_xlsx.py` (s/h inversion for STORNO)

**Consumes:** `facturare_invoice_links` (REVERSES), `facturare_invoices` (original advance invoices)

**Produces:** Corrected STORNO export with: proper kurs_date from original advance, correct s/h (inverted), per-line invoice numbers, correct advance amounts

- [ ] **Step 1: Fix STORNO section in route — per-line invoice numbers and kurs from originals**

Replace the entire STORNO block (lines 1318-1339) in `api_generate_eurofib`:

```python
    if inv_type_str == "STORNO":
        # Get the original advance invoices that this storno reverses
        reversed_links = _repo.query_all(
            "SELECT source_invoice_id FROM facturare_invoice_links WHERE target_invoice_id = %s AND link_type = 'REVERSES'",
            (invoice_id,))
        reversed_inv_ids = [r["source_invoice_id"] for r in reversed_links] if reversed_links else []

        if not reversed_inv_ids:
            return error_response("STORNO has no linked reversed invoices", 400)

        reversed_invoices = _repo.query_all(
            "SELECT id, invoice_number, total_amount_eur, split_mode, kurs_applied, issued_date FROM facturare_invoices "
            "WHERE id IN ({}) ORDER BY sequence_number".format(",".join(["%s"] * len(reversed_inv_ids))),
            tuple(reversed_inv_ids))

        order_lines = []
        for ri in reversed_invoices:
            ri_total = float(ri["total_amount_eur"])
            ri_split = ri.get("split_mode") or "equal"
            ri_inv_no = ri.get("invoice_number") or ri["id"]
            # Kurs from the original advance invoice
            ri_kurs = float(ri["kurs_applied"]) if ri.get("kurs_applied") else kurs
            ri_issued = ri.get("issued_date")
            ri_kurs_date = (ri_issued - timedelta(days=1)) if ri_issued else kurs_date

            for car in lines:
                selling = float(car["selling_price_eur"])
                if ri_split == "proportional" and total_selling > 0:
                    car_amount = ri_total * (selling / total_selling)
                else:
                    car_amount = ri_total / max(len(lines), 1)
                order_lines.append(OrderLine(
                    comanda=int(car["nr_comanda"]) if car.get("nr_comanda") and str(car["nr_comanda"]).isdigit() else 0,
                    model=car.get("model", ""), culoare=car.get("culoare") or "",
                    list_price=float(car["list_price_eur"]), selling_price=selling,
                    advance=-car_amount, rest=None,
                    start_no=ri_inv_no,
                    kurs=ri_kurs,
                ))
```

Key changes:
- `start_no=ri_inv_no` — each line gets the invoice number from the **original** advance invoice, not the storno invoice
- `kurs=ri_kurs` — per-line kurs from the original advance invoice
- `car_amount = ri_total * (selling / total_selling)` — correctly uses the **advance total** from the reversed invoice, not the full selling price

- [ ] **Step 2: Fix kurs_date for STORNO in the route**

Update the `kurs_date` computation (around line 1355-1357). For STORNO, don't compute from `issued_date` — the per-line kurs is already set. But the global `cfg.fx.kurs_date` still needs a sensible default. Use the first reversed invoice's date:

```python
    # Compute kurs_date
    if inv_type_str == "STORNO" and reversed_invoices:
        # Use the first reversed invoice's date for the global kurs_date
        first_ri_date = reversed_invoices[0].get("issued_date")
        kurs_date = (first_ri_date - timedelta(days=1)) if first_ri_date else issued_date - timedelta(days=1)
    else:
        kurs_date = issued_date - timedelta(days=1)
```

- [ ] **Step 3: Fix s/h inversion for STORNO in the renderer**

In `eurofib_xlsx.py`, the issue is that for STORNO, the konto_config DB stores accounts in a way that when combined with the standard s/h logic, produces inverted results. The fix: add an `is_storno` flag and swap s/h.

Add `is_storno` parameter to the renderer. In `config.py`, add to `EurofibConfig`:

```python
class EurofibConfig(BaseModel):
    klient: int
    konto_debit: int
    konto_credit: int
    belegart: str = "JVV"
    steuercode: str = "L00"
    fw_steuercode: str = "L00"
    text_template: str = "avans {model} {comanda}"
    brand_map: dict[str, str] = {}
    is_storno: bool = False
```

In `eurofib_xlsx.py`, update `_write_debit` (line 71-72):

```python
        konto = cfg.eurofib.konto_credit if cfg.eurofib.is_storno else cfg.eurofib.konto_debit
        sh = "h" if cfg.eurofib.is_storno else "s"
        ws.cell(row=r, column=3, value=konto)          # C konto
        ws.cell(row=r, column=4, value=sh)              # D soll_haben
```

Update gegenkonto in `_write_debit` (line 83):

```python
        gegenkonto = cfg.eurofib.konto_debit if cfg.eurofib.is_storno else cfg.eurofib.konto_credit
        ws.cell(row=r, column=16, value=int(line.konto_credit_override) if line.konto_credit_override else gegenkonto)  # P gegenkonto
```

Update `_write_credit` (line 106-107):

```python
        konto = cfg.eurofib.konto_debit if cfg.eurofib.is_storno else cfg.eurofib.konto_credit
        sh = "s" if cfg.eurofib.is_storno else "h"
        ws.cell(row=r, column=3, value=konto)          # C konto
        ws.cell(row=r, column=4, value=sh)              # D soll_haben
```

- [ ] **Step 4: Set is_storno flag in the route**

In `routes_orders.py`, when building the EurofibConfig, set `is_storno`:

```python
    eurofib=EurofibConfig(
        klient=firmennr,
        konto_debit=int(konto_row["konto_debit"]),
        konto_credit=int(konto_row["konto_credit"]),
        text_template=konto_row.get("text_template") or default_text_templates.get(inv_type_str, "{model} {comanda}"),
        is_storno=(inv_type_str == "STORNO"),
    ),
```

- [ ] **Step 5: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py jarvis/accounting/facturare/generators/eurofib_xlsx.py jarvis/accounting/facturare/config.py
git commit -m "fix(facturare): STORNO export — correct kurs/date from original, s/h inversion, per-line invoice numbers"
```

---

### Task 9: Export Fix — FINAL invoice bugs (Bugs 3-final, 7, 8-kostenstelle)

**Files:**
- Modify: `jarvis/accounting/facturare/routes_orders.py` (FINAL section + non-STORNO block of `api_generate_eurofib`)

**Consumes:** `facturare_venituri_rules` via `_repo.match_venituri_rule()`, `facturare_invoices` for advance kurs lookup

**Produces:** Corrected FINAL export with: per-line konto_venituri from rules, kostenstelle column populated, kurs from integral advance invoice

- [ ] **Step 1: Fix FINAL kurs — use kurs from integral advance invoice**

In the route, after the STORNO block and within the else block (non-STORNO, lines 1340-1353), add FINAL-specific kurs logic:

```python
    else:
        # For FINAL: use kurs from the last advance invoice in this anexa
        if inv_type_str == "FINAL":
            last_advance = _repo.query_one(
                "SELECT kurs_applied, issued_date FROM facturare_invoices "
                "WHERE anexa_id = %s AND invoice_type = 'INVOICE' ORDER BY sequence_number DESC LIMIT 1",
                (anexa["id"],))
            if last_advance and last_advance.get("kurs_applied"):
                kurs = float(last_advance["kurs_applied"])
                adv_date = last_advance.get("issued_date")
                kurs_date = (adv_date - timedelta(days=1)) if adv_date else kurs_date

        order_lines = []
        for l in lines:
            selling = float(l["selling_price_eur"])
            if split_mode == "proportional" and total_selling > 0:
                car_advance = total_amount * (selling / total_selling)
            else:
                car_advance = total_amount / max(len(lines), 1)

            # For FINAL: look up venituri rule per line
            line_kostenstelle = None
            line_konto_credit = None
            if inv_type_str == "FINAL":
                nr_cmd = l.get("nr_comanda") or ""
                rule = _repo.match_venituri_rule(contract["supplier_id"], nr_cmd)
                if rule:
                    line_konto_credit = rule["konto_venituri"]
                    line_kostenstelle = rule["kostenstelle"]

            order_lines.append(OrderLine(
                comanda=int(l["nr_comanda"]) if l.get("nr_comanda") and str(l["nr_comanda"]).isdigit() else 0,
                model=l["model"], culoare=l.get("culoare") or "",
                list_price=float(l["list_price_eur"]), selling_price=selling,
                advance=car_advance, rest=selling,
                kostenstelle=line_kostenstelle,
                konto_credit_override=line_konto_credit,
            ))
```

- [ ] **Step 2: Update kurs_date computation for FINAL**

The kurs_date is already handled above (from the last advance invoice). Make sure the global config uses it:

```python
    if inv_type_str == "STORNO" and reversed_invoices:
        first_ri_date = reversed_invoices[0].get("issued_date")
        kurs_date = (first_ri_date - timedelta(days=1)) if first_ri_date else issued_date - timedelta(days=1)
    elif inv_type_str == "FINAL":
        # kurs_date already set above from last advance invoice
        pass
    else:
        kurs_date = issued_date - timedelta(days=1)
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py
git commit -m "fix(facturare): FINAL export — venituri rules per line, kostenstelle, kurs from advance"
```

---

### Task 10: Run migration on staging + manual verification

**Files:** No code changes

**Consumes:** All previous tasks

**Produces:** Working export on staging, verified against contabila's examples

- [ ] **Step 1: Run migration on staging**

```bash
PGPASSWORD="AVNS_xGqAdP95HvfqAj1AsUL" psql -h mkt-staging-do-user-24639451-0.k.db.ondigitalocean.com -p 25060 -U doadmin -d defaultdb --set=sslmode=require -f jarvis/accounting/facturare/migrations/006_eurofib_venituri_rules.sql
```

- [ ] **Step 2: Merge dev → staging and push**

```bash
git checkout staging
git merge dev --no-edit
git push origin staging
git checkout dev
```

Wait for staging deploy.

- [ ] **Step 3: Manual verification checklist**

On staging (https://mkt-app-922ou.ondigitalocean.app):

1. **Settings tab**: verify text_template column appears, venituri rules section shows 3 seed rules
2. **Contract view**: verify "Date Contabile" card appears with firmennr, konto debit, etc.
3. **Create contract modal**: select a client without konto → verify warning appears
4. **Export INVOICE**: download EuroFib XLSX → verify:
   - Column B (klient) = 139 or 140 (not 0)
   - Column E/G (dates) = issued_date (not today)
   - Column AF (kursdatum) = issued_date - 1 day
   - Column Q (text) = "avans {model} {comanda}" format
5. **Export STORNO**: verify:
   - Column D: s/h correctly swapped (419968 on h, client konto on s)
   - Column H: per-line invoice numbers from original advance
   - Column AF: kurs_date from original advance
   - Column M: advance amount (not full selling price)
6. **Export FINAL**: verify:
   - Column C/P: konto_venituri from rules (707127/707128/707132)
   - Column AJ: kostenstelle populated (0215/0216/0314)
   - Column AF/AG: kurs from integral advance invoice
   - Column Q: "{model} {comanda}" format

- [ ] **Step 4: Commit any hotfixes found during verification**
