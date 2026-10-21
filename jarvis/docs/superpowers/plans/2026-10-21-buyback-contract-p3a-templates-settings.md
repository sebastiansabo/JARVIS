# BuyBack Contract P3a — Template store + Settings editor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let admins configure per-company×brand **purchase** and **consignment (depozit)** contract templates (legal body text with `{tokens}`), stored in a new table, edited in a **Settings → BuyBack → Contracte** zone, and pre-seeded from the three real AAP templates. No rendering yet (P3b).

**Architecture:** Mirror the Test-Drive contract-config pattern (`fp_contract_configs` + `contract_config_repository` + the `contract-configs` admin route + `ContractConfigSection` editor), adapted to BuyBack's per-company×brand×type model. New table `buyback_contract_templates`, a repo, an admin-gated GET/PUT route, a React editor (company switcher → one card per brand × {purchase, consignment}), and a seed that templatizes the three provided documents.

**Tech Stack:** Flask + raw psycopg2; React 19 + TS + Tailwind; pytest (localhost DB) + vitest.

**Spec:** `docs/superpowers/specs/2026-10-20-buyback-purchase-contract-design.md` (§4.2, §5)

## Global Constraints

- `document_type ∈ {'purchase', 'consignment'}`.
- Idempotent DDL (`CREATE TABLE IF NOT EXISTS`); unique `(company_id, brand_id, document_type)`.
- Route is **admin-only** (`current_user.can_access_settings`), mirroring `buyback/routes/settings.py::_require_admin`.
- Never f-string a user value into SQL; the upsert binds all values via `%s`; template `body_template`/`general_conditions` are stored verbatim (they are legal text, not SQL).
- Pre-seeded template text must preserve each brand's legal wording exactly; only deal-specific values become `{tokens}`. The user reviews the seeded text in the editor.
- Backend DB tests run with `DATABASE_URL=postgresql://localhost/defaultdb`.

## Token set (documented in the editor; the renderer in P3b substitutes these)

Shared: `{contract_number} {contract_date} {company_name} {company_address} {company_reg_no} {company_vat} {company_iban} {company_bank} {company_administrator} {advisor_name} {seller_name} {seller_address} {seller_cnp} {seller_ci} {seller_cui} {seller_reg_no} {seller_legal_rep} {brand} {model} {vin} {engine_no} {engine_capacity} {power_cp} {civ_no} {mileage} {first_registration}`
Purchase: `{price_eur} {price_ron} {price_words} {vat_note}`
Consignment: `{owner_price} {promo_price} {min_price} {commission} {deposit_months} {monthly_fee}`

## Review Focus

- **Unique constraint** — a second upsert for the same (company, brand, type) updates, not duplicates (Task 2 test).
- **Admin gate** — a non-admin GET/PUT is 403 (Task 3 test).
- **Blank/whitespace body** — stored as-is (nullable); no crash (Task 2 test).
- **Unknown document_type** — route rejects anything not in {purchase, consignment} (Task 3 test).
- **Seed idempotency** — re-running the seed doesn't duplicate or overwrite admin edits (Task 6 test).

---

### Task 1: `buyback_contract_templates` table

**Files:** Modify `jarvis/migrations/domains/schema_buyback.py`; Test `jarvis/tests/buyback/test_schema_buyback.py`.

- [ ] **Step 1: failing test**
```python
def test_buyback_contract_templates_table(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        create_schema_buyback(conn, cur); conn.commit()
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name='buyback_contract_templates'""")
        cols = {r[0] if not isinstance(r, dict) else r['column_name'] for r in cur.fetchall()}
        assert {'company_id','brand_id','document_type','title','body_template',
                'general_conditions','is_active'}.issubset(cols)
    finally:
        release_db(conn)
```
- [ ] **Step 2: run → FAIL** (`DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_schema_buyback.py -k contract_templates -q`)
- [ ] **Step 3: implement** — add to `create_schema_buyback` (after the hold/seller-id blocks):
```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_contract_templates (
            id BIGSERIAL PRIMARY KEY,
            company_id BIGINT NOT NULL,
            brand_id BIGINT,
            document_type VARCHAR(20) NOT NULL DEFAULT 'purchase',
            title VARCHAR(255),
            body_template TEXT,
            general_conditions TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by INTEGER, updated_by INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, brand_id, document_type)
        )
    ''')
```
- [ ] **Step 4: run → PASS** (full `test_schema_buyback.py`)
- [ ] **Step 5: commit** `feat(buyback): buyback_contract_templates table`

---

### Task 2: `ContractTemplateRepository`

**Files:** Create `jarvis/buyback/repositories/contract_template_repository.py`; Test `jarvis/tests/buyback/test_contract_template_repository.py`.

**Interfaces:** Produces `get_active(company_id, brand_id, document_type)`, `list_for_company(company_id)`, `upsert(company_id, brand_id, document_type, title, body_template, general_conditions, is_active, updated_by)`.

- [ ] **Step 1: failing test**
```python
import os
from buyback.repositories.contract_template_repository import ContractTemplateRepository

def test_upsert_is_unique_per_company_brand_type(require_real_db):
    repo = ContractTemplateRepository()
    cid = 963000 + int.from_bytes(os.urandom(2), 'big')
    repo.upsert(cid, 1, 'purchase', 'T1', 'body A', 'gc', True, 1)
    repo.upsert(cid, 1, 'purchase', 'T2', 'body B', 'gc2', True, 1)   # same key → update
    rows = [r for r in repo.list_for_company(cid) if r['brand_id'] == 1]
    assert len(rows) == 1 and rows[0]['title'] == 'T2' and rows[0]['body_template'] == 'body B'

def test_get_active_returns_only_active(require_real_db):
    repo = ContractTemplateRepository()
    cid = 964000 + int.from_bytes(os.urandom(2), 'big')
    repo.upsert(cid, 2, 'consignment', 'C', 'b', '', False, 1)
    assert repo.get_active(cid, 2, 'consignment') is None
    repo.upsert(cid, 2, 'consignment', 'C', 'b', '', True, 1)
    assert repo.get_active(cid, 2, 'consignment')['title'] == 'C'
```
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — `BaseRepository` subclass; `upsert` uses `INSERT ... ON CONFLICT (company_id, brand_id, document_type) DO UPDATE SET ... updated_at=NOW() RETURNING *`; `get_active` = `SELECT * WHERE company_id=%s AND brand_id=%s AND document_type=%s AND is_active=TRUE`; `list_for_company` = `SELECT * WHERE company_id=%s ORDER BY brand_id, document_type`. All values `%s`-bound.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(buyback): ContractTemplateRepository (upsert/get_active/list)`

---

### Task 3: Admin GET/PUT route

**Files:** Create `jarvis/buyback/routes/contract_templates.py` (+ register blueprint import in `buyback/__init__.py` if routes are auto-imported there — follow the existing pattern); Test `jarvis/tests/buyback/test_contract_templates_routes.py`.

**Interfaces:** `GET /api/buyback/contract-templates?company_id=<id>` → `{templates: [...]}`; `PUT /api/buyback/contract-templates/<brand_id>?company_id=<id>` body `{document_type, title, body_template, general_conditions, is_active}` → upsert. Both admin-only.

- [ ] **Step 1: failing tests** — admin GET returns `templates`; admin PUT upserts then GET reflects it; a non-admin PUT is 403; `document_type` not in {purchase,consignment} is 400. (Use the `client`/`as_role` harness; `as_role('Admin',1)` has `can_access_settings`; a plain role does not.)
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — mirror `buyback/routes/settings.py`: `_require_admin()`; GET calls `list_for_company`; PUT validates `document_type ∈ {purchase,consignment}` (400 otherwise) then `upsert(...)`. `_serialize` for dates.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(buyback): admin contract-template GET/PUT route`

---

### Task 4: API client + types

**Files:** Modify `jarvis/frontend/src/api/buyback.ts`, `jarvis/frontend/src/types/buyback.ts`; Test `jarvis/frontend/src/api/buyback.test.ts`.

**Interfaces:** `buybackApi.listContractTemplates(companyId)`, `buybackApi.putContractTemplate(companyId, brandId, data)`; type `BuybackContractTemplate`.

- [ ] **Step 1: failing test** — `listContractTemplates(3)` GETs `/api/buyback/contract-templates?...company_id=3`; `putContractTemplate(3, 5, {...})` PUTs `/api/buyback/contract-templates/5?...company_id=3`.
- [ ] **Step 2: run → FAIL** (`npx vitest run src/api/buyback.test.ts`)
- [ ] **Step 3: implement** the two methods (follow the `getConfig`/`updateConfig` style) + the TS type.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(buyback-ui): contract-template api client + type`

---

### Task 5: Settings "Contracte" editor (company switcher → brand×type cards)

**Files:** Create `jarvis/frontend/src/pages/Settings/BuyBackContractsSection.tsx`; wire it into the BuyBack settings area (where `BuyBackTab` is rendered — add a "Contracte" sub-tab/section next to the notification config); Test `jarvis/frontend/src/pages/Settings/BuyBackContractsSection.test.tsx`.

**Interfaces:** Consumes `buybackApi.listContractTemplates/putContractTemplate` + the company's active brands (reuse the existing brands source used by the BuyBack settings/company switcher). Renders, per active brand, a **Purchase** card and a **Consignment** card: `title` input, `body_template` textarea, `general_conditions` textarea, `is_active` switch, Save button, and a collapsible **token reference** panel listing the tokens from this plan's token set.

- [ ] **Step 1: failing test** (mock `buybackApi`): renders the section heading "Contracte" and, for a brand with a seeded purchase template, shows its title in an input + a "Salvează" button.
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** the component (company switcher reused from the parent; `useQuery(listContractTemplates)`; group results by brand_id×document_type; an editable card per (brand, type) with a `useMutation(putContractTemplate)` Save; a `<details>` token palette).
- [ ] **Step 4: run → PASS**; then `cd jarvis/frontend && npm run build` clean.
- [ ] **Step 5: commit** `feat(buyback-ui): Settings Contracte editor (brand×type cards)`

---

### Task 6: Seed the three provided templates (templatized)

**Files:** Create a seed in `schema_buyback.py` (idempotent, `WHERE NOT EXISTS`, after the table) OR a dedicated `buyback/seed_contract_templates.py` invoked from init — follow whichever matches `fp_contract_configs`' seed; Test `jarvis/tests/buyback/test_contract_template_seed.py`.

Content: templatize the three `~/Downloads` documents — **Contract achiziție DWA** + **Antecontract Volvo** (`purchase`) and **Contract de depozit International** (`consignment`) — replacing deal-specific values (names, VIN, prices, dates, reg numbers) with the plan's `{tokens}`, keeping each brand's legal boilerplate verbatim. Resolve company_id/brand_id from the `companies`/brands tables (DWA→Autoworld NEXT, Volvo→Autoworld Prestige, depozit→Autoworld International — confirm the exact brand_ids at implement time; **Ruling** + ledger if a mapping is ambiguous).

- [ ] **Step 1: failing test** — after `create_schema_buyback`, `ContractTemplateRepository().get_active(<international_company>, <vw_brand>, 'consignment')` returns a row whose `body_template` contains `{owner_price}` and `{commission}`; a purchase seed contains `{price_eur}` and `{seller_name}`. Re-running `create_schema_buyback` keeps exactly one row per key (idempotent).
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** the idempotent seed (guarded `WHERE NOT EXISTS (company_id, brand_id, document_type)` so admin edits are never overwritten).
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(buyback): seed AAP purchase + depozit contract templates`

---

## Done-when

- Admins can open **Settings → BuyBack → Contracte**, pick a company, and edit per-brand purchase/consignment templates; the three provided templates appear pre-seeded (token-ized) for review.
- `DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/ -q` green; `cd jarvis/frontend && npm run build` clean; BuyBack vitest green.
- P3b then adds the renderer (tokens → PDF) + the "Generează contract" button + delivery.
