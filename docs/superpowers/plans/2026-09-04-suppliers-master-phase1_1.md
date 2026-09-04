# Suppliers Master — Phase 1.1: per-company Table 2, mapping fn, EuroFib export, import, tenant+period gating

**Goal:** Make the supplier master tenant-gated (per-company konto = "Table 2"), add inline-edit/add/import (Excel + e-Factura), a config-driven invoice→accounting mapping function, and a batch EuroFib export (MEDLINE format) gated by company + period (monthly/weekly/range).

**Branch:** feature/suppliers-master (worktree /Users/sebastiansabo/Documents/Git/JARVIS-suppliers-master). Builds on Phase 1 (identity master, resolver, suppliers_bp, Procesare page).

## Global constraints
- Same as Phase 1: BaseRepository (%s params, execute_many for atomic), idempotent DDL in schema_incremental.py, correct perm helper, `api` client no auto-unwrap, tests with mocked psycopg2, `cd jarvis/frontend && npm run build` must pass.
- **Never hardcode account numbers** — all fixed accounting values come from Table 2 config.
- **Account codes / cost centers / steuercode are STRINGS** — preserve leading zeros (e.g. "0393").
- Safe migration order: child table already added (0d41c4dea, non-destructive); drop the flat konto cols on `suppliers` LAST (Batch D), after code no longer references them.

---

## Data model — "Table 2" = `supplier_konto_config` (per company)

Already created (Batch A): `supplier_konto_config(id, supplier_id FK, company_id FK, konto_debit, konto_credit, klient, gegenkonto_debit, gegenkonto_credit, kostenstelle_debit, kostenstelle_credit, extbeleg_debit, extbeleg_credit, created_by, created_at, updated_at, UNIQUE(supplier_id, company_id))`.

**Batch B adds** (idempotent guarded ALTER): `steuercode TEXT`, `text_template TEXT`, `belegart TEXT`.

Column semantics:
- `konto_debit/konto_credit/klient/gegenkonto_debit/gegenkonto_credit/kostenstelle_debit/kostenstelle_credit` — fixed EuroFib values (strings).
- `extbeleg_debit/extbeleg_credit` — **source directives**: value `'invoice_number'` → emit the invoice number; empty → emit "".
- `steuercode` — VAT code string (e.g. "621").
- `text_template` — booking text; may contain `{invoice_number}`/`{supplier}` placeholders, else literal.
- `belegart` — document type (e.g. "JC"); credit line uses as-is, debit line lower-cased.

---

## Mapping function — `core/suppliers/accounting_mapping.py`

Config-driven; implements the user's exact rules. Pure + unit-tested.

```python
def map_invoice_to_accounting_fields(invoice: dict, config: dict) -> dict:
    """invoice: {supplier, supplier_id?, invoice_number, invoice_date, due_date,
       net_amount, vat_amount, gross_amount}. config: a supplier_konto_config row for the
       invoice's company. Returns the 9 accounting fields. Raises ValueError if config missing
       or config.supplier_id != invoice.supplier_id."""
```

Rules (verbatim intent):
- If no Table 2 config → raise `ValueError("No Table 2 config for supplier <id>")` (do NOT guess).
- If `config['supplier_id']` is provided and `invoice.get('supplier_id')` is provided and they differ → raise `ValueError` (config must belong to the detected supplier).
- Fixed fields copied from config, coalescing None→"": `klient, konto_debit, konto_credit, gegenkonto_debit, gegenkonto_credit, kostenstelle_debit, kostenstelle_credit`.
- `extbeleg_credit` = `invoice['invoice_number']` if `config.get('extbeleg_credit') == 'invoice_number'` else "".
- `extbeleg_debit` = `invoice['invoice_number']` if `config.get('extbeleg_debit') == 'invoice_number'` else "".
- All outputs are strings; never invent values; empty config field → "".

Output dict keys exactly: `konto_debit, konto_credit, klient, gegenkonto_debit, gegenkonto_credit, kostenstelle_debit, kostenstelle_credit, extbeleg_debit, extbeleg_credit`.

Reference example (must pass as a test): config `{klient:'140', konto_credit:'40102793', konto_debit:'628701', gegenkonto_credit:'628701', gegenkonto_debit:'', kostenstelle_debit:'0393', kostenstelle_credit:'', extbeleg_credit:'invoice_number', extbeleg_debit:''}`, invoice number `'17278'` → `{konto_debit:'628701', konto_credit:'40102793', klient:'140', gegenkonto_debit:'', gegenkonto_credit:'628701', kostenstelle_debit:'0393', kostenstelle_credit:'', extbeleg_debit:'', extbeleg_credit:'17278'}`.

---

## EuroFib export — MEDLINE format (`core/suppliers/eurofib_export.py`)

56-column xlsx. Header row (col 0 is an unnamed marker column), verbatim:
`"", klient, konto, soll_haben, buchdatum, belegart, belegdatum, belegnummer, betrag, steuercode, steuerbetrag, fwcd, fwbetrag, fw_steuercode, fwsteuerbetrag, gegenkonto, text, brutto_netto, nettotage, valuta, leistung, leistung_von, leistung_bis, zuordnung, extbeleg, valuta_beginn, sktage1, skproz1, sktage2, skproz2, freigabe, kursdatum, kurs, kurs_per, kurs_fix, kostenstelle, kostentraeger, mengen_kz, mengen_stuck, zession, scannummer, ueberw_banr, nb_code, mahncode, opo_info, skonto_basis, skonto_fwbasis, kost_variator, kost_variator_k, skonto, skonto_fw, vb_factoring, kurs_steuer, kundendaten, vertreter, uid`

Per invoice → **2 rows** (v1 single-VAT), all account codes as strings, blanks left empty:

**Credit line (Haben):** col0=`"x"` (new-doc marker), klient=`config.klient`, konto=`config.konto_credit`, soll_haben=`"h"`, buchdatum=invoice_date, belegart=`config.belegart` (upper), belegdatum=invoice_date, belegnummer=invoice_number, betrag=**gross_amount**, gegenkonto=`config.gegenkonto_credit`, text=resolved `config.text_template`, brutto_netto=`"N"`, valuta=due_date, extbeleg=(invoice_number if config.extbeleg_credit=='invoice_number' else ""), kostenstelle=`config.kostenstelle_credit`.

**Debit line (Soll):** col0="", klient="" (or config.klient — MEDLINE sample leaves blank; use ""), konto=`config.konto_debit`, soll_haben=`"s"`, buchdatum=invoice_date, belegart=`config.belegart.lower()`, belegdatum=invoice_date, belegnummer=invoice_number, betrag=**net_amount**, steuercode=`config.steuercode`, steuerbetrag=**vat_amount**, gegenkonto=`config.gegenkonto_debit`, kostenstelle=`config.kostenstelle_debit`, extbeleg=(invoice_number if config.extbeleg_debit=='invoice_number' else "").

Dates formatted as the sample (`YYYY-MM-DD` / Excel date). Amounts numeric (2 decimals). **Assumption (v1):** one net+VAT pair per invoice; invoices with >1 VAT rate are SKIPPED and returned in a `skipped[]` list with a reason (surface in the UI — no silent drop). The second sample row (defaults row) is NOT emitted.

---

## Repository & routes

`SupplierMasterRepository` (extend) + a `KontoConfigRepository` (new, or same file):
- `get_konto(supplier_id, company_id) -> dict|None`; `upsert_konto(supplier_id, company_id, **fields, created_by)` (INSERT ... ON CONFLICT (supplier_id, company_id) DO UPDATE).
- `list_master(company_id, search)` — LEFT JOIN `supplier_konto_config` ON supplier_id AND company_id, so each row carries that company's konto (or nulls).
- Worklist (company + period): `unresolved_efactura(company_id, start, end)` (filter `company_id` + `issue_date` range); `unresolved_invoice_suppliers(company_name, start, end)` (filter `allocations.company = company_name` + `invoice_date` range). Resolve the company_name from companies(id).
- Import Excel: parse rows (openpyxl) → for each, resolve/create identity (CUI→NrReg→Ref→name via SupplierResolver) → `upsert_konto` for company_id.
- Import e-Factura: for company_id, bulk create master identity rows from that company's e-Factura partners (keyed by CUI) not already in the master.
- Export: for company_id + period, select invoices in range with a resolvable supplier that has Table 2 → mapping fn + betrag/dates/steuercode/text/belegart → build xlsx.

Routes (`suppliers_bp`, all `_check_supplier_perm(...)`, all require `company_id`):
- `GET  /api/suppliers?company_id=&search=` (list incl. that company's konto)
- `GET/PUT /api/suppliers/<id>/konto?company_id=` (Table 2 get/upsert; PUT = edit action)
- `GET  /api/suppliers/worklist?company_id=&start_date=&end_date=`
- `POST /api/suppliers/import?company_id=` (multipart xlsx/csv) → {created, updated, skipped[]}
- `POST /api/suppliers/import-efactura?company_id=` → {created, skipped[]}
- `GET  /api/suppliers/export?company_id=&start_date=&end_date=` → MEDLINE xlsx download {or JSON with skipped[] + a download token}

---

## Frontend (Procesare)

- **Company selector** (required) + **Period selector** (This month / This week / custom range via DateField mode="range") at the top; both scope worklist + export; company scopes konto.
- **Master tab:** inline-edit identity (CUI/NrReg/Ref) + the Table 2 konto/steuercode/text/belegart cells (PUT konto per selected company) — click cell → input → save on blur; **Add supplier** form (POST); **Import** menu → Excel/CSV upload + "From e-Factura"; **Export** button → downloads the MEDLINE xlsx for the selected company+period (toast the skipped count).
- **Worklist tab:** filtered by company + period.
- Update `MasterSupplier` type: konto fields become a nested `konto` object (per selected company) incl. steuercode/text_template/belegart; add import/export/konto methods to `api/suppliers.ts`.

---

## Batches
- **A** (done): child table.
- **B (backend):** ALTER add steuercode/text_template/belegart; mapping fn + tests; konto repo (get/upsert, list join); worklist company+period; import (excel+efactura); export generator + tests; routes. 
- **C (frontend):** company+period selectors, inline-edit, add, import, export.
- **D (cleanup):** drop flat konto cols from `suppliers`; restart :5056; verify end-to-end.
