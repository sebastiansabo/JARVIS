# Storno Split EuroFib — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Split EuroFib" button on STORNO invoices that creates per-car STORNO_SPLIT children in DB, used by EuroFib export instead of the parent.

**Architecture:** New enum value `STORNO_SPLIT` + link type `SPLITS`. Backend endpoint creates N split rows (1 per car) linked to parent. EuroFib export detects splits and uses them. Frontend adds split/delete buttons and expandable sub-rows.

**Tech Stack:** Python/Flask, PostgreSQL (enum types), React/TypeScript with shadcn/ui

## Global Constraints

- All work on `dev` branch
- Migration files in `jarvis/accounting/facturare/migrations/` (next: `007_`)
- No tests exist for this module — skip TDD, verify manually
- Commit after each task
- STORNO_SPLIT is an artefact for EuroFib only — hidden from main invoice lists
- `invoice_number` for splits: `parent_number * 100 + index` (1-indexed, up to 99 cars)
- EuroFib belegnummer for splits = parent's invoice_number (not the split's 9-digit number)

---

### Task 1: DB Migration — STORNO_SPLIT enum, SPLITS link type, relax CHECK

**Files:**
- Create: `jarvis/accounting/facturare/migrations/007_storno_split.sql`

**Produces:**
- `STORNO_SPLIT` value in `invoice_type_enum`
- `SPLITS` value in `invoice_link_type_enum`
- Relaxed CHECK on `invoice_number` (9 digits)

- [ ] **Step 1: Create migration file**

```sql
-- 007_storno_split.sql
-- Add STORNO_SPLIT invoice type and SPLITS link type for per-car EuroFib export

-- Add STORNO_SPLIT to invoice_type_enum
ALTER TYPE invoice_type_enum ADD VALUE IF NOT EXISTS 'STORNO_SPLIT';

-- Add SPLITS to invoice_link_type_enum
ALTER TYPE invoice_link_type_enum ADD VALUE IF NOT EXISTS 'SPLITS';

-- Relax invoice_number CHECK from 7 to 9 digits for split numbering
ALTER TABLE facturare_invoices DROP CONSTRAINT IF EXISTS ck_invoice_number_range;
ALTER TABLE facturare_invoices ADD CONSTRAINT ck_invoice_number_range
    CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 999999999));
```

- [ ] **Step 2: Run migration on local dev DB**

Run: `psql postgresql://localhost/defaultdb -f jarvis/accounting/facturare/migrations/007_storno_split.sql`
Expected: ALTER TYPE (x2), ALTER TABLE (x2)

- [ ] **Step 3: Commit**

```bash
git add jarvis/accounting/facturare/migrations/007_storno_split.sql
git commit -m "feat(facturare): add STORNO_SPLIT type, SPLITS link type, relax invoice_number to 9 digits"
```

---

### Task 2: Python models — add enum values

**Files:**
- Modify: `jarvis/accounting/facturare/models.py` (lines 36-54)

**Produces:**
- `InvoiceTypeEnum.STORNO_SPLIT = "STORNO_SPLIT"`
- `InvoiceLinkTypeEnum.SPLITS = "SPLITS"`

- [ ] **Step 1: Add STORNO_SPLIT to InvoiceTypeEnum**

In `models.py`, add after `FINAL = "FINAL"` (line 41):

```python
class InvoiceTypeEnum(str, Enum):
    PROFORMA = "PROFORMA"
    INVOICE = "INVOICE"
    STORNO = "STORNO"
    FINAL = "FINAL"
    STORNO_SPLIT = "STORNO_SPLIT"
```

- [ ] **Step 2: Add SPLITS to InvoiceLinkTypeEnum**

In `models.py`, add after `REPLACES = "REPLACES"` (line 54):

```python
class InvoiceLinkTypeEnum(str, Enum):
    REVERSES = "REVERSES"
    PRECEDES = "PRECEDES"
    REPLACES = "REPLACES"
    SPLITS = "SPLITS"
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/accounting/facturare/models.py
git commit -m "feat(facturare): add STORNO_SPLIT and SPLITS enum values"
```

---

### Task 3: Repository — split CRUD methods

**Files:**
- Modify: `jarvis/accounting/facturare/repositories/invoice_storage_repository.py` (add after line 162)

**Consumes:** `create_invoice()` (line 112), `create_link()` (line 185), `delete_invoice()` (line 161)

**Produces:**
- `get_splits_for_invoice(invoice_id)` → list of STORNO_SPLIT rows linked via SPLITS
- `delete_splits_for_invoice(invoice_id)` → deletes all STORNO_SPLIT children and their links
- `has_splits(invoice_id)` → bool

- [ ] **Step 1: Add split query methods**

Add after `delete_invoice` method (after line 162):

```python
    # ── Storno Splits ──────────────────────────────────────────────

    def get_splits_for_invoice(self, invoice_id):
        """Get all STORNO_SPLIT children of a parent STORNO."""
        return self.query_all(
            """SELECT fi.* FROM facturare_invoices fi
               JOIN facturare_invoice_links fil ON fil.target_invoice_id = fi.id
               WHERE fil.source_invoice_id = %s AND fil.link_type = 'SPLITS'
               ORDER BY fi.sequence_number""",
            (invoice_id,))

    def has_splits(self, invoice_id):
        row = self.query_one(
            "SELECT EXISTS(SELECT 1 FROM facturare_invoice_links WHERE source_invoice_id = %s AND link_type = 'SPLITS') AS has",
            (invoice_id,))
        return row["has"] if row else False

    def delete_splits_for_invoice(self, invoice_id):
        """Delete all STORNO_SPLIT children and their links."""
        split_ids = self.query_all(
            "SELECT target_invoice_id FROM facturare_invoice_links WHERE source_invoice_id = %s AND link_type = 'SPLITS'",
            (invoice_id,))
        if split_ids:
            ids = [r["target_invoice_id"] for r in split_ids]
            ph = ",".join(["%s"] * len(ids))
            self.execute(f"DELETE FROM facturare_invoice_links WHERE source_invoice_id IN ({ph}) OR target_invoice_id IN ({ph})", tuple(ids + ids))
            self.execute(f"DELETE FROM facturare_invoices WHERE id IN ({ph})", tuple(ids))
```

- [ ] **Step 2: Commit**

```bash
git add jarvis/accounting/facturare/repositories/invoice_storage_repository.py
git commit -m "feat(facturare): add storno split repository methods"
```

---

### Task 4: Backend — POST split-eurofib endpoint

**Files:**
- Modify: `jarvis/accounting/facturare/routes_orders.py` (add new endpoint after venituri-rules section, ~line 1090)

**Consumes:**
- `_repo.get_invoice_by_id(id)` → invoice row dict
- `_repo.get_lines_by_anexa(anexa_id)` → list of line dicts with `id`, `selling_price_eur`, `nr_comanda`, `model`
- `_repo.has_splits(id)` → bool
- `_repo.create_invoice(...)` → new row
- `_repo.create_link(source, target, link_type)` → link row
- `_repo.query_all(sql, params)` → list of dicts
- `InvoiceTypeEnum.STORNO_SPLIT`, `InvoiceLinkTypeEnum.SPLITS`, `InvoiceLinkTypeEnum.REVERSES`
- `InvoiceStateEnum` from `models.py`

**Produces:**
- `POST /facturare/api/invoices/<id>/split-eurofib` → `{success, count, split_ids}`

- [ ] **Step 1: Add the split endpoint**

Add after the accounting-summary endpoint (around line 1090):

```python
@facturare_bp.route("/facturare/api/invoices/<int:invoice_id>/split-eurofib", methods=["POST"])
@login_required
@handle_api_errors
def api_split_storno_eurofib(invoice_id):
    """Split a STORNO into per-car STORNO_SPLIT children for EuroFib export."""
    from .models import InvoiceTypeEnum, InvoiceStateEnum, InvoiceLinkTypeEnum
    from decimal import Decimal, ROUND_HALF_UP
    import json as _json

    if not _check_perm("add"):
        return error_response("Permission denied", 403)

    inv = _repo.get_invoice_by_id(invoice_id)
    if not inv:
        return error_response("Invoice not found", 404)
    if inv["invoice_type"] != "STORNO":
        return error_response("Only STORNO invoices can be split", 400)
    if _repo.has_splits(invoice_id):
        return error_response("This STORNO already has splits. Delete them first to re-split.", 400)

    # Get target line_ids
    raw_line_ids = inv.get("line_ids")
    if isinstance(raw_line_ids, str):
        raw_line_ids = _json.loads(raw_line_ids)

    anexa_id = inv["anexa_id"]
    all_lines = _repo.get_lines_by_anexa(anexa_id)
    all_line_id_set = {l["id"] for l in all_lines}
    target_line_ids = raw_line_ids if raw_line_ids else sorted(all_line_id_set)

    if len(target_line_ids) <= 1:
        return error_response("Cannot split a single-car STORNO", 400)

    # Get reversed advance invoices (parent's REVERSES links)
    reversed_links = _repo.query_all(
        "SELECT source_invoice_id FROM facturare_invoice_links WHERE target_invoice_id = %s AND link_type = 'REVERSES'",
        (invoice_id,))
    reversed_inv_ids = [r["source_invoice_id"] for r in reversed_links] if reversed_links else []

    reversed_invoices = []
    if reversed_inv_ids:
        ph = ",".join(["%s"] * len(reversed_inv_ids))
        reversed_invoices = _repo.query_all(
            f"SELECT id, invoice_number, total_amount_eur, line_ids, kurs_applied FROM facturare_invoices WHERE id IN ({ph})",
            tuple(reversed_inv_ids))

    # Build line price map
    line_map = {l["id"]: l for l in all_lines}
    line_prices = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in all_lines}

    # Calculate per-car share from reversed advances
    parent_number = inv.get("invoice_number") or inv["id"]
    parent_kurs = Decimal(str(inv["kurs_applied"])) if inv.get("kurs_applied") else Decimal("1")
    ONE = Decimal("0.01")

    split_ids = []
    for idx, lid in enumerate(target_line_ids):
        car_share = Decimal("0")
        for ri in reversed_invoices:
            ri_raw = ri.get("line_ids")
            if isinstance(ri_raw, str):
                ri_raw = _json.loads(ri_raw)
            ri_lines = set(ri_raw) if ri_raw else all_line_id_set
            covered_total = sum(line_prices.get(x, Decimal("0")) for x in ri_lines)
            if covered_total and lid in ri_lines:
                car_share += (line_prices.get(lid, Decimal("0")) / covered_total * Decimal(str(abs(float(ri["total_amount_eur"]))))).quantize(ONE, rounding=ROUND_HALF_UP)

        split_number = parent_number * 100 + (idx + 1)
        split_row = _repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.STORNO_SPLIT,
            invoice_state=InvoiceStateEnum(inv.get("invoice_state", "DRAFT")),
            sequence_number=idx + 1,
            total_amount_eur=-car_share,
            total_amount_ron=(-car_share * parent_kurs).quantize(ONE, rounding=ROUND_HALF_UP),
            kurs_applied=inv.get("kurs_applied"),
            invoice_number=split_number,
            issued_date=inv.get("issued_date"),
            intocmit_de=inv.get("intocmit_de"),
            notes=f"Split {idx + 1}/{len(target_line_ids)} of storno {parent_number}",
            created_by=current_user.id,
            line_ids=[lid],
        )

        # Link parent → split
        _repo.create_link(
            source_invoice_id=invoice_id,
            target_invoice_id=split_row["id"],
            link_type=InvoiceLinkTypeEnum.SPLITS,
        )
        # Copy parent's REVERSES links to split
        for ri in reversed_invoices:
            _repo.create_link(
                source_invoice_id=ri["id"],
                target_invoice_id=split_row["id"],
                link_type=InvoiceLinkTypeEnum.REVERSES,
            )

        split_ids.append(split_row["id"])

    return jsonify({"success": True, "count": len(split_ids), "split_ids": split_ids})
```

- [ ] **Step 2: Add delete-splits endpoint**

Add right after the split endpoint:

```python
@facturare_bp.route("/facturare/api/invoices/<int:invoice_id>/splits", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_storno_splits(invoice_id):
    """Delete all STORNO_SPLIT children of a STORNO."""
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    inv = _repo.get_invoice_by_id(invoice_id)
    if not inv or inv["invoice_type"] != "STORNO":
        return error_response("Not a STORNO invoice", 400)
    _repo.delete_splits_for_invoice(invoice_id)
    return jsonify({"success": True})
```

- [ ] **Step 3: Add GET splits endpoint** (for frontend to fetch split details)

```python
@facturare_bp.route("/facturare/api/invoices/<int:invoice_id>/splits")
@login_required
@handle_api_errors
def api_get_storno_splits(invoice_id):
    """Get STORNO_SPLIT children with car details."""
    if not _check_perm("view"):
        return error_response("Permission denied", 403)
    import json as _json
    splits = _repo.get_splits_for_invoice(invoice_id)
    result = []
    for s in splits:
        raw = s.get("line_ids")
        if isinstance(raw, str):
            raw = _json.loads(raw)
        result.append({
            "id": s["id"], "invoice_number": s["invoice_number"],
            "sequence_number": s["sequence_number"],
            "total_amount_eur": float(s["total_amount_eur"]),
            "line_ids": raw or [],
        })
    return jsonify({"splits": result})
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py
git commit -m "feat(facturare): add split-eurofib, get-splits, delete-splits endpoints"
```

---

### Task 5: EuroFib export — detect and use splits

**Files:**
- Modify: `jarvis/accounting/facturare/routes_orders.py` (in `api_generate_eurofib`, around line 1628)

**Consumes:**
- `_repo.has_splits(invoice_id)` → bool
- `_repo.get_splits_for_invoice(invoice_id)` → list of STORNO_SPLIT rows
- `EurofibXlsxRenderer.render_multi_to_bytes(batches)` (already exists in eurofib_xlsx.py)

**Produces:** When exporting a STORNO with splits, uses split rows instead of parent. belegnummer = parent's invoice_number.

- [ ] **Step 1: Add split detection at the top of the STORNO block**

In `api_generate_eurofib`, find the STORNO block (line ~1628: `if inv_type_str == "STORNO":`). Add split detection right after the type check, BEFORE the existing storno logic:

```python
    if inv_type_str == "STORNO":
        # Check if this storno has per-car splits — if so, export those instead
        if _repo.has_splits(invoice_id):
            from .generators.eurofib_xlsx import EurofibXlsxRenderer
            splits = _repo.get_splits_for_invoice(invoice_id)
            parent_inv_no = inv_row.get("invoice_number") or inv_row["id"]

            # Build one batch per split, each reusing the same config but with its own lines
            batches = []
            for split in splits:
                # Re-run the single-invoice eurofib build helper for each split
                split_cfg, split_lines = _build_eurofib_config_for_invoice(split["id"], _repo)
                # Override belegnummer to parent's number
                for sl in split_lines:
                    object.__setattr__(sl, 'start_no', parent_inv_no)
                batches.append((split_cfg, split_lines))

            xlsx_bytes = EurofibXlsxRenderer.render_multi_to_bytes(batches)

            cust_row = _repo.query_one("SELECT display_name FROM crm_clients WHERE id = %s", (contract["customer_id"],))
            cust_name = (cust_row["display_name"] if cust_row else "").replace(" ", "_")
            dl_name = f"EuroFib_{cust_name}_{parent_inv_no}_storno_split.xlsx"

            return send_file(io.BytesIO(xlsx_bytes), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name=dl_name)

        # ... existing storno logic continues below (no splits case)
```

- [ ] **Step 2: Extract _build_eurofib_config_for_invoice helper**

The existing code at lines ~1580-1765 builds a `(JobConfig, [OrderLine])` for a single invoice. There's already a helper for batch export (`_build_single_invoice_eurofib` around line 1820+). Check if it exists; if so, reuse it. If not, extract the common logic into a helper function that both the single and batch export can call.

Look for the existing `_build_single_invoice_eurofib` function (used by `api_generate_eurofib_daily`). It already returns `(cfg, order_lines)`. Reuse it directly:

```python
            for split in splits:
                split_cfg, split_lines = _build_single_invoice_eurofib(split["id"])
                for sl in split_lines:
                    object.__setattr__(sl, 'start_no', parent_inv_no)
                batches.append((split_cfg, split_lines))
```

Note: `_build_single_invoice_eurofib` is a nested function inside `api_generate_eurofib_daily`. It needs to be either extracted to module level or the split logic placed inside the daily endpoint's scope. The cleanest approach: extract it to a standalone function at module level that takes `invoice_id` and `_repo` as params.

- [ ] **Step 3: Filter STORNO_SPLIT from main invoice queries**

In `get_invoices_by_anexa` (repository line 135-138), add a WHERE clause to exclude STORNO_SPLIT:

```python
    def get_invoices_by_anexa(self, anexa_id):
        return self.query_all(
            "SELECT * FROM facturare_invoices WHERE anexa_id = %s AND invoice_type != 'STORNO_SPLIT' ORDER BY created_at",
            (anexa_id,))
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/accounting/facturare/routes_orders.py jarvis/accounting/facturare/repositories/invoice_storage_repository.py
git commit -m "feat(facturare): EuroFib export uses splits when available, hide STORNO_SPLIT from main queries"
```

---

### Task 6: Frontend — Split button, sub-rows, delete button

**Files:**
- Modify: `jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx`

**Consumes:**
- `POST /facturare/api/invoices/{id}/split-eurofib` → `{success, count}`
- `GET /facturare/api/invoices/{id}/splits` → `{splits: [...]}`
- `DELETE /facturare/api/invoices/{id}/splits` → `{success}`

**Produces:**
- "Split EuroFib" button on STORNO rows (visible when no splits exist and >1 car)
- Expandable sub-rows under STORNO showing splits
- "Delete Splits" button (visible when splits exist)

- [ ] **Step 1: Add Scissors icon import**

At line 6, add `Scissors` to the lucide-react imports:

```typescript
import {
  Plus, FileText, Loader2, ChevronRight, ChevronDown, Copy,
  Search, CheckCircle2, Ban, Pencil, Check, X,
  Trash2, Download, Archive, FileSpreadsheet, ArrowUpDown, ArrowUp, ArrowDown,
  Scissors,
} from 'lucide-react'
```

- [ ] **Step 2: Add split state and handlers**

In the main ComenziTab component, add state for tracking which stornos have splits:

```typescript
const [stornoSplits, setStornoSplits] = useState<Record<number, any[]>>({})
const [splittingId, setSplittingId] = useState<number | null>(null)
const [expandedSplits, setExpandedSplits] = useState<Set<number>>(new Set())

const loadSplits = async (invoiceId: number) => {
  const res = await fetch(`/facturare/api/invoices/${invoiceId}/splits`)
  if (res.ok) {
    const data = await res.json()
    setStornoSplits(prev => ({ ...prev, [invoiceId]: data.splits || [] }))
  }
}

const handleSplit = async (invoiceId: number) => {
  setSplittingId(invoiceId)
  try {
    const res = await fetch(`/facturare/api/invoices/${invoiceId}/split-eurofib`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'Failed')
    toast.success(`Created ${data.count} splits`)
    await loadSplits(invoiceId)
    setExpandedSplits(prev => new Set(prev).add(invoiceId))
  } catch (err: any) { toast.error(err.message) }
  finally { setSplittingId(null) }
}

const handleDeleteSplits = async (invoiceId: number) => {
  if (!confirm('Delete all splits for this STORNO?')) return
  try {
    const res = await fetch(`/facturare/api/invoices/${invoiceId}/splits`, { method: 'DELETE' })
    if (!res.ok) throw new Error('Failed')
    toast.success('Splits deleted')
    setStornoSplits(prev => { const n = { ...prev }; delete n[invoiceId]; return n })
    setExpandedSplits(prev => { const n = new Set(prev); n.delete(invoiceId); return n })
  } catch (err: any) { toast.error(err.message) }
}
```

- [ ] **Step 3: Load splits when storno is visible**

When the anexa detail loads, check each STORNO invoice for splits:

```typescript
// In the useEffect that loads anexa detail, after invoices are loaded:
for (const inv of detail.invoices) {
  if (inv.invoice_type === 'STORNO') {
    loadSplits(inv.id)
  }
}
```

- [ ] **Step 4: Add Split/Delete buttons to STORNO invoice row**

In the invoice row rendering (around line 1842), after the existing EuroFib button, add:

```tsx
{inv.invoice_type === 'STORNO' && (inv.line_ids?.length || detail.lines.length) > 1 && (
  <>
    {!stornoSplits[inv.id]?.length ? (
      <Button variant="ghost" size="icon" className="h-5 w-5" title="Split EuroFib (per car)"
        disabled={splittingId === inv.id}
        onClick={async (e) => { e.stopPropagation(); await handleSplit(inv.id) }}>
        {splittingId === inv.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Scissors className="h-3 w-3 text-violet-500" />}
      </Button>
    ) : (
      <>
        <Button variant="ghost" size="icon" className="h-5 w-5" title="Toggle splits"
          onClick={(e) => { e.stopPropagation(); setExpandedSplits(prev => { const n = new Set(prev); n.has(inv.id) ? n.delete(inv.id) : n.add(inv.id); return n }) }}>
          {expandedSplits.has(inv.id) ? <ChevronDown className="h-3 w-3 text-violet-500" /> : <ChevronRight className="h-3 w-3 text-violet-500" />}
        </Button>
        <Button variant="ghost" size="icon" className="h-5 w-5" title="Delete splits"
          onClick={async (e) => { e.stopPropagation(); await handleDeleteSplits(inv.id) }}>
          <Trash2 className="h-3 w-3 text-red-400" />
        </Button>
      </>
    )}
  </>
)}
```

- [ ] **Step 5: Add expandable sub-rows for splits**

After the STORNO invoice row `</tr>`, add split sub-rows:

```tsx
{inv.invoice_type === 'STORNO' && expandedSplits.has(inv.id) && stornoSplits[inv.id]?.map((split, si) => {
  const carLine = detail.lines.find(l => split.line_ids?.includes(l.id))
  return (
    <tr key={`split-${split.id}`} className="border-b border-violet-100 bg-violet-50/30 text-[10px]">
      <td className="px-3 py-1 pl-12 text-violet-600">
        Split {split.sequence_number}
      </td>
      <td className="px-2 py-1 text-violet-600 font-mono">{split.invoice_number}</td>
      <td className="px-2 py-1 text-muted-foreground" colSpan={2}>
        {carLine ? `${carLine.model} — ${carLine.nr_comanda}` : `Line ${split.line_ids?.[0]}`}
      </td>
      <td className="px-2 py-1 text-right font-mono">{fmtEur(split.total_amount_eur)}</td>
      <td colSpan={2}></td>
    </tr>
  )
})}
```

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx
git commit -m "feat(facturare): Split EuroFib button on STORNO with expandable sub-rows"
```

---

### Task 7: Run migration on staging + manual verification

**Files:** No code changes

- [ ] **Step 1: Run migration on staging**

```bash
PGPASSWORD="<REDACTED-STAGING-DB-PASSWORD>" psql -h mkt-staging-do-user-24639451-0.k.db.ondigitalocean.com -p 25060 -U doadmin -d defaultdb --set=sslmode=require -f jarvis/accounting/facturare/migrations/007_storno_split.sql
```

- [ ] **Step 2: Merge dev → staging and push**

```bash
git checkout staging && git merge dev --no-edit && git push origin staging && git checkout dev
```

- [ ] **Step 3: Manual verification on staging**

1. Navigate to a contract with a STORNO invoice (>1 car)
2. Verify "Split EuroFib" button appears (scissors icon, violet)
3. Click split → verify splits created, expandable sub-rows show
4. Download EuroFib from the STORNO → verify it uses split data (per-car lines, belegnummer = parent nr)
5. Delete splits → verify sub-rows disappear, split button returns
6. Verify main invoice list does NOT show STORNO_SPLIT entries
