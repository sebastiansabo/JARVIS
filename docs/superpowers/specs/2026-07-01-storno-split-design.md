# Storno Split EuroFib — Design Spec

**Date:** 2026-07-01
**Module:** Facturare (Comenzi Externe)
**Trigger:** Need to split cumulated storno invoices (10 cars in 1 storno) into per-car entries for EuroFib accounting import

---

## Context

When a cumulated storno invoice reverses an advance for multiple cars (e.g., 10 cars), the EuroFib export currently produces one entry per car using the storno's total split equally/proportionally. The accountant needs the ability to split a storno into individual per-car invoices for separate EuroFib import, while keeping the original storno intact as the parent.

### Key files
- **Storno creation:** `jarvis/accounting/facturare/services/invoice_state_machine.py` (L214-316)
- **Storno route:** `jarvis/accounting/facturare/routes_orders.py` (L733-755)
- **EuroFib export:** `jarvis/accounting/facturare/routes_orders.py` (L1575-1765)
- **XLSX renderer:** `jarvis/accounting/facturare/generators/eurofib_xlsx.py`
- **Frontend:** `jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx`
- **Models:** `jarvis/accounting/facturare/models.py`

---

## 1. DB Schema Changes

### 1a. New invoice type: STORNO_SPLIT

Add `STORNO_SPLIT` to the invoice type enum (both DB and Python `InvoiceTypeEnum`).

STORNO_SPLIT is an artefact used only for EuroFib export. It does not appear in the main invoice list. It is always a child of a STORNO parent.

### 1b. New link type: SPLITS

Add `SPLITS` to `InvoiceLinkTypeEnum`. Links parent STORNO → child STORNO_SPLIT.

Direction: `source_invoice_id = parent STORNO`, `target_invoice_id = child STORNO_SPLIT`.

### 1c. Relax invoice_number CHECK constraint

Current: `CHECK (invoice_number >= 1 AND invoice_number <= 9999999)` (7 digits)

New: `CHECK (invoice_number >= 1 AND invoice_number <= 999999999)` (9 digits)

Reason: split numbering = `parent_number * 100 + index`. A 7-digit parent (9103292) produces 9-digit splits (910329201).

### 1d. No unique constraint changes needed

`uq_anexa_storno` only applies to `invoice_type = 'STORNO'`. STORNO_SPLIT is a different type, so no conflict.

---

## 2. Split Creation Logic

### Endpoint
`POST /facturare/api/invoices/<invoice_id>/split-eurofib`

### Preconditions
- Invoice must be type STORNO
- Invoice must not already have splits (check invoice_links for SPLITS)
- Invoice must have line_ids with more than 1 car (no point splitting a single car)

### Algorithm
Given parent STORNO with `line_ids = [131, 132, ..., 159]` (29 cars):

1. Fetch all cars (lines) from `facturare_anexa_lines` for those line_ids
2. Fetch reversed advance invoices via `facturare_invoice_links WHERE target_invoice_id = parent AND link_type = 'REVERSES'`
3. For each car (sorted by line_id):
   - Calculate share: sum of `(advance_total * car_selling / covered_selling)` across all reversed advances
   - Create STORNO_SPLIT row:
     - `invoice_type = 'STORNO_SPLIT'`
     - `anexa_id = parent.anexa_id`
     - `invoice_number = parent.invoice_number * 100 + (idx + 1)` (1-indexed)
     - `total_amount_eur = -share` (negative)
     - `total_amount_ron = -share * parent.kurs_applied`
     - `kurs_applied = parent.kurs_applied`
     - `issued_date = parent.issued_date`
     - `intocmit_de = parent.intocmit_de`
     - `line_ids = [car_id]` (single car)
     - `sequence_number = idx + 1`
     - `invoice_state = parent.invoice_state`
   - Create link: `source = parent.id, target = split.id, link_type = 'SPLITS'`
   - Copy parent's REVERSES links to each split (so split also knows which advances it reverses)

### Response
`{success: true, count: N, split_ids: [...]}`

---

## 3. EuroFib Export Behavior

### Detection
In `api_generate_eurofib`, after loading the invoice:
- If `invoice_type == 'STORNO'`: check if splits exist (`SELECT id FROM facturare_invoice_links WHERE source_invoice_id = invoice_id AND link_type = 'SPLITS'`)
- If splits exist: redirect to batch export using splits
- If no splits: export as current (unchanged)

### Per-split export
Each STORNO_SPLIT produces 1 debit/credit pair in XLSX:
- **belegnummer** (col H) = parent's `invoice_number` (NOT the split's 9-digit number)
- **fwbetrag** (col M) = split's `total_amount_eur` (per-car share, negative)
- **kurs** (col AG) = split's `kurs_applied` (inherited from parent)
- **extbeleg** (col Y) = car's `nr_comanda`
- All other columns: same as current storno export logic

### Batch rendering
Use `EurofibXlsxRenderer.render_multi_to_bytes()` (already exists) or iterate splits through the standard renderer in sequence.

---

## 4. Frontend UI

### Split button
On the invoice detail / document items list, when viewing a STORNO invoice:
- Show button **"Split EuroFib"** (icon: Split/Scissors)
- Only visible if: `invoice_type === 'STORNO'` AND no existing splits AND `line_ids.length > 1`
- On click: POST to `/facturare/api/invoices/{id}/split-eurofib`
- On success: toast + reload

### Split visibility
STORNO_SPLIT invoices do NOT appear in the main invoice list.

They appear as expandable sub-rows under the parent STORNO, showing:
- Split number (91032921, 91032922, ...)
- Car model + nr_comanda
- Amount (per-car share)
- EuroFib download button per split (optional, for individual re-export)

### Delete splits
Button **"Delete Splits"** on parent STORNO (visible only when splits exist):
- Deletes all STORNO_SPLIT children and their links
- Allows re-splitting if amounts change

---

## 5. What does NOT change

- STORNO creation flow — unchanged
- STORNO PDF rendering — unchanged (uses parent, not splits)
- Main invoice list — STORNO_SPLIT filtered out
- INVOICE / FINAL / PROFORMA export — unchanged
- facturare_konto_config — unchanged
- facturare_venituri_rules — unchanged

---

## 6. Summary of changes per file

| File | Changes |
|---|---|
| **Migration** | Add STORNO_SPLIT to enum, SPLITS to link enum, relax CHECK to 9 digits |
| **models.py** | Add `STORNO_SPLIT` to `InvoiceTypeEnum`, `SPLITS` to `InvoiceLinkTypeEnum` |
| **routes_orders.py** | New endpoint POST split-eurofib, update EuroFib export to detect/use splits |
| **invoice_storage_repository.py** | Methods: get_splits, delete_splits, create_split |
| **ComenziTab.tsx** | Split button on STORNO, expandable sub-rows, delete splits button |
| **DocumentItemsTab.tsx** | Filter out STORNO_SPLIT from main list (if shown there) |
