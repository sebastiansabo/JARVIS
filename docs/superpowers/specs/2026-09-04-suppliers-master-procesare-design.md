# Suppliers Master + "Procesare" Resolution Console — Design

**Date:** 2026-09-04
**Branch:** `feature/suppliers-master` (off `staging`)
**Status:** Design approved (in-chat). Phase 1 scope. Awaiting spec review → implementation plan.

---

## 1. Problem

"Supplier" (furnizor) identity is fragmented across the app with **no foreign keys** —
everything is glued by fragile string matching:

| Representation | Location | Key it carries |
|---|---|---|
| `suppliers` master (DMS) | `jarvis/dms/` — `suppliers` table | `cui`, `nr_reg_com`, IBAN, ANAF sync |
| `invoices.supplier` (free text) | AP invoices | **name only — no CUI column** |
| `efactura_invoices.partner_name` / `partner_cif` | e-Factura inbound | `partner_cif` |
| `efactura_supplier_mappings.partner_name` | e-Factura allocation config | `partner_cif`, `kod_konto`, dept/brand |
| `vendor_mappings` | bank statements | regex → `matched_supplier` |

### Evidence (local DB, illustrative but structurally representative)
- e-Factura → invoices "link" (`jarvis_invoice_id`) is tautological: `invoices.supplier` is
  *copied* from `partner_name` on send-to-module
  (`core/connectors/efactura/services/invoice_allocation_service.py:306-307,418-419`).
- Of 8 distinct e-Factura partners, **0** match a `efactura_supplier_mappings` row by name.
  One — `Porsche Romania s.r.l.` (RO9997007) — has a mapping with the **same CUI** but a
  different spelling (`PORSCHE ROMANIA SRL`), so the name-keyed join **misses it** and the
  dept/brand/konto allocation silently never applies. This is the canonical failure case.
- DMS suppliers ↔ e-Factura partners share **0** CUIs; DMS suppliers ↔ e-Factura-origin
  invoices match only **3 of 61** by name.

**Conclusion:** CUI is the only reliable identity, and it is present everywhere *except* on
`invoices` itself. We need a single supplier master keyed on stable identifiers, plus a
resolver, plus a human console ("Procesare") to confirm the matches the resolver can't make
confidently.

## 2. Goals / Non-goals

**Goals (Phase 1)**
- One shared supplier master, keyed by **CUI → Nr. Reg. Com → Ref. No → name** (tiered).
- Robust, normalization-aware resolver shared by Accounting and e-Factura.
- Alias capture so every confirmed spelling variant auto-resolves thereafter.
- Per-supplier **AP EuroFib posting config** (Firmennr, Konto Debit, Konto Credit ×3, Centru Gestiune).
- A "Procesare" Accounting sub-tab: worklist of unresolved suppliers + master management.
- Bind e-Factura invoices to the master **now** (they carry CUI). Invoices resolve by
  name/alias only (resolve-on-read).

**Non-goals (deferred to Phase 2)**
- `invoices.supplier_id` column + backfill of existing 448 invoices.
- Capturing supplier CUI at manual/AI invoice entry.
- Folding `statements.vendor_mappings` into the worklist.
- Touching AR `facturare_konto_config` (stays separate — it is keyed by *issuing companies*,
  a different ledger side).

## 3. Locked decisions

1. **Master origin:** promote the existing DMS `suppliers` table (do **not** create a 4th
   table). Keep the DMS Suppliers page working on the same table.
2. **Binding strategy:** resolve-on-read first. e-Factura + DMS bind by CUI now; invoices by
   name/alias until Phase 2.
3. **Procesare role:** resolution console (worklist + master console), not just CRUD.
4. **Konto fields ownership:** AP furnizori posting (booking incoming supplier invoices into
   EuroFib). Separate from AR `facturare_konto_config`.
5. **Ref. No:** added as an identity tier for external/foreign suppliers with no RO CUI.
6. Resolver/repository live in **`core/suppliers/`** (shared).
7. Phase-1 worklist scope = **e-Factura + invoices** only.
8. Procesare master console is **global** (all companies); the DMS Suppliers page stays
   company-filtered.

## 4. Data model (all additive; idempotent DDL in `jarvis/migrations/domains/`)

### 4.1 `suppliers` — new columns (existing table, `schema_incremental.py:1350`)

Identity / normalization:
- `cui_normalized TEXT` — digits-only canonical of `cui` (`RO9997007` → `9997007`).
  **Partial unique index** `WHERE cui_normalized IS NOT NULL`.
- `nr_reg_normalized TEXT` — canonical of `nr_reg_com` (uppercase, collapse separators).
  Indexed, **non-unique** (can legitimately repeat historically).
- `ref_no TEXT` — external reference for foreign/no-CUI suppliers. Indexed.

AP EuroFib posting block:
- `firmennr TEXT`
- `konto_debit TEXT`
- `konto_credit_avans TEXT`
- `konto_credit_storno TEXT`
- `konto_credit_final TEXT`
- `centru_gestiune TEXT`

Normalized columns are maintained in the repository on every write (not DB triggers), so the
canonical logic lives in one place with the resolver.

### 4.2 `supplier_aliases` — new table

```
supplier_aliases(
  id SERIAL PK,
  supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
  alias_name TEXT,
  alias_cui_normalized TEXT,
  source TEXT,              -- 'efactura' | 'invoice' | 'manual' | 'import'
  created_by INT REFERENCES users(id),
  created_at TIMESTAMP DEFAULT now()
)
```
Indexes on `alias_cui_normalized` and `LOWER(alias_name)`. Every confirmed match in Procesare
writes an alias so the same raw string auto-resolves next time.

### 4.3 `efactura_invoices` — new FK

- `supplier_id INT NULL REFERENCES suppliers(id) ON DELETE SET NULL`.
  Set at resolution time. Safe — e-Factura rows carry `partner_cif`.

### 4.4 `invoices` — **no change this phase** (protected table; Phase 2 adds `supplier_id`).

## 5. Resolver (`core/suppliers/`)

```
SupplierResolver.resolve(name, cui=None, nr_reg=None, ref_no=None)
    -> { supplier_id, confidence: 'high'|'medium'|'low'|'none', method }
```

Tiered match (first hit wins):
1. `cui_normalized` exact ......................... high  (`method='cui'`)
2. `nr_reg_normalized` exact ...................... high  (`method='nr_reg'`)
3. `ref_no` exact ................................ high  (`method='ref_no'`)
4. `supplier_aliases` (cui or normalized name) ... high  (`method='alias'`)
5. normalized-name exact on master ............... medium(`method='name_exact'`)
6. `pg_trgm` fuzzy name ≥ threshold .............. low   (`method='fuzzy'`)  → worklist
7. no hit ........................................ none                       → worklist

- `high` → auto-link (write `efactura_invoices.supplier_id`; no human needed).
- `medium`/`low`/`none` → surface in the Procesare worklist for a decision.
- Normalization helpers (`normalize_cui`, `normalize_nr_reg`) are pure functions with unit
  tests. The Porsche case is a required fixture (same CUI, different name → resolves high via
  cui tier, not fuzzy).

## 6. Procesare tab

**Route:** `/app/accounting/procesare` (lazy component), sidebar item under Accounting,
guarded by `can_access_accounting` (outer) + `V2Guard permKey="suppliers.master.view"`.

### 6.1 Worklist view
- Data: e-Factura partners + invoice suppliers whose resolver result is not `high`.
- Each row: raw name / CUI / source, and the resolver's **ranked candidate matches**.
- Actions per row: **Link to existing** · **Merge** · **Create new master** · **Ignore**.
  - Link/Create writes a `supplier_aliases` row (+ sets `efactura_invoices.supplier_id`).
  - Merge folds a duplicate master into a survivor (repoints aliases + efactura FKs).
- After action the row disappears (resolves to `high` next pass).

### 6.2 Master console view
- Global, searchable list of master suppliers.
- Edit master incl. identity fields + the **AP konto posting block**.
- Reuse existing DMS supplier endpoints for **ANAF auto-fill / sync** (no rebuild):
  `POST /api/dms/suppliers/<id>/auto-fill`, `/sync-anaf`, `/sync-anaf-batch`.
- Drill into a supplier → linked invoices (`GET /api/dms/suppliers/<id>/invoices`, extended to
  also match via aliases) + e-Factura docs (via `supplier_id`).

## 7. API surface (new, under `core/suppliers/` blueprint; correct permission helper)

- `GET  /api/suppliers` — master list (search, paginate).
- `GET  /api/suppliers/<id>` — detail incl. konto block + aliases + linked docs.
- `POST /api/suppliers` — create master.
- `PUT  /api/suppliers/<id>` — update (identity + konto block).
- `POST /api/suppliers/<id>/aliases` — add alias.
- `POST /api/suppliers/merge` — merge dup into survivor.
- `GET  /api/suppliers/worklist` — unresolved e-Factura + invoice suppliers with candidates.
- `POST /api/suppliers/resolve` — apply a worklist decision (link/create/ignore).

**Permission:** new V2 entity `suppliers.master.{view,edit,merge,resolve}`. The route helper
MUST read `perm.get("has_permission")` / `perm.get("has_explicit_entry")` — NOT the
`routes_orders.py:203` dict-truthiness anti-pattern (`if perm is not None`), which is a known
broken-access-control bug in this codebase.

## 8. Backfill / rollout

- **DDL:** additive, idempotent (`CREATE TABLE IF NOT EXISTS`, guarded `ALTER` in
  `information_schema` `DO $$` blocks) in `jarvis/migrations/domains/schema_*.py`.
- **Populate normalized columns** for existing `suppliers` rows in the same migration
  (`UPDATE ... SET cui_normalized = regexp_replace(...)`).
- **Initial e-Factura link pass:** a one-off resolve over existing `efactura_invoices` setting
  `supplier_id` where the resolver returns `high`. Non-high rows appear in the worklist.
- No invoice rows are mutated in Phase 1.

## 9. Testing

- Unit: `normalize_cui`, `normalize_nr_reg` (RO prefix, whitespace, punctuation).
- Unit: `SupplierResolver` tiers incl. the Porsche fixture (same CUI / different name → high),
  fuzzy-threshold boundary, no-hit → worklist.
- Integration: worklist decision writes alias + efactura `supplier_id`; merge repoints
  aliases + FKs; DMS Suppliers page still lists on the same table.
- Frontend: Procesare worklist actions, master edit incl. konto block, `npm run build` clean.

## 10. Risks

- **CUI normalization must be exact-once** or the fragility returns. Single source (repo).
- **Merge** must repoint every reference (aliases, efactura `supplier_id`) atomically
  (`execute_many` callback — there is no `transaction()` helper in this codebase).
- Reusing DMS endpoints couples Procesare to DMS routes; acceptable (same table), revisit if
  DMS suppliers is later moved under `core/`.
- Global master console vs company-filtered DMS page is an intentional divergence — document it
  in the UI so it isn't read as a bug.

## 11. Phase 2 (out of scope — recorded for continuity)

- `invoices.supplier_id INT NULL REFERENCES suppliers(id)`.
- Backfill 448 invoices by CUI → Nr.Reg → Ref.No → name.
- Capture supplier CUI at manual/AI invoice entry (AI parser already extracts VAT).
- Optionally fold `statements.vendor_mappings` into the worklist.
