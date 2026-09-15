# Cost Centers — dissociating invoice budgeting from the org structure

- **Date:** 2026-09-15
- **Branch:** `feature/cost-centers` (worktree `../JARVIS-cost-centers`, off `dev` @ `ddb4b5a66`)
- **Status:** Design — awaiting review
- **Author:** Sebastian + Claude (SDD)
- **Source data:** `centre cost firme grup AW 2026.xlsx` (6 sheets, one per group company, ~59 rows)

---

## 1. Problem

Two accounting processes are driven by **one** dimension today:

1. **Invoice budgeting / allocation** ("bugetare") — which cost bucket an invoice line hits.
2. **Responsable notification** — who gets emailed / in-app notified when an invoice is allocated.

Both read the same key: the four denormalised text columns
`allocations(company, brand, department, subdepartment)`, resolved **by name** against the
`structure_nodes` org tree (legacy `department_structure` as fallback).

The tightest coupling is a single call in the allocation write path — when an allocation is
saved without an explicit `responsible`, the responsible is auto-derived from the *same* path:

```
# jarvis/accounting/invoices/repositories/allocation_repository.py:130-142
if not responsible:
    responsible = StructureNodeRepository().find_responsable_by_path(
        alloc['company'], brand=..., department=..., subdepartment=...)
```

**Consequence:** in ~90% of cases the cost center equals the org department, so this works. In
~10% they legitimately differ, and because there is only one dimension you can encode only one
of them:
- allocate to the accounting-correct cost center → the wrong person is notified, or
- allocate to the responsible's department → the accounting/export is wrong.

## 2. Key discovery — the cost center already exists as `kostenstelle`

The codes in the Excel are the **`kostenstelle`** dimension JARVIS already uses on the
accounting/export side, not a new concept:

| Excel (this project) | Existing in code |
| --- | --- |
| `0211 → Masini noi VW PKW` | `bab_entries.kostenstelle = 211 → "VW PKW INTERN"` (`schema_controlling_bab.py:75`) |
| `0281 → IT`, `0291 → Conducere` | facturare `kostenstelle` → EuroFib xlsx column AJ (`generators/eurofib_xlsx.py`), `suppliers.kostenstelle_debit/credit` |

`kostenstelle` is **export-only today** — never linked to the org tree, allocation, or
notification. This project promotes it to a first-class Finance dimension that invoice budgeting
is allocated against.

**Format of record:** BAB stores `kostenstelle` as `INTEGER` (`211`). Finance / EuroFib use the
zero-padded string `0211`. This spec makes the **string `0211` canonical** (`cost_centers.code`);
comparison to BAB integers is a pad/strip at the boundary only.

## 3. Goals / non-goals

**Goals**
- A dedicated **Cost Center** dimension (per company, `code`='0211' string + name), seeded from
  the Excel, editable under Finance → "Centre de cost".
- Invoice budgeting keyed to a cost center (`allocations.cost_center_id`), **coexisting** with the
  org path.
- The 90% stays one-click via a default `cost_center → structure_node` map; the 10% is set
  independently.
- EuroFib/export kostenstelle sourced from the allocation's cost center.

**Non-goals (this phase set)**
- Planned budget amounts / budget-vs-actual per period (that is Phase 4, a separate decision).
- Changing responsable-notification logic or the org tree in any way.
- Touching the Sincron organigram, HR manager visibility, or accounting *visibility* scoping
  (`org_scope.py`) — all unchanged.

## 4. Locked decisions

1. Cost center **is** `kostenstelle`; stored canonically as string `0211`.
2. **Coexist** model — cost center is the budgeting key; the org path remains the notification key.
3. **Default map** `cost_center → structure_node` (maintained table) drives the 90% auto-fill; the
   10% divergence is an explicit, enumerable set.
4. Home: **Finance/Accounting**, admin-gated.
5. Backfill historical `Bugetata` invoices where department→cost-center is unambiguous; null +
   report the rest (non-destructive).
6. New allocations: cost center **optional** at first; becomes **required to reach `Bugetata`**
   only at a **later gate, once map coverage is proven** (not at end of Phase 2).
7. Ship **Phases 1–3**; Phase 4 decided later.
8. **Seed authority: in-app CRUD is the source of truth.** The Excel is a **one-time seed**;
   re-import is explicit/opt-in and must never clobber in-app edits.
9. **Default map: seed exact name-matches only.** `cost_center → structure_node` auto-created where
   names match unambiguously; accounting fills the remainder (incl. the ~10% divergences) in-app.
10. **Reinvoice lines: covered by the parent allocation's cost center** for now — no
    `cost_center_id` on `reinvoice_destinations` until a real split need appears.

## 5. Data model

### 5.1 `cost_centers` (new)
```
cost_centers(
  id            SERIAL PK,
  company_id    INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  code          VARCHAR(8)  NOT NULL,     -- canonical zero-padded, e.g. '0211'
  name          VARCHAR(255) NOT NULL,    -- Denumire, e.g. 'Masini noi VW PKW'
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  display_order INTEGER NOT NULL DEFAULT 0,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(company_id, code)                -- code is unique PER company, not globally
)
```
Note: `0281/0291/0292` repeat across companies — hence the composite unique key, never `code`
alone.

### 5.2 `cost_center_structure_map` (new — the 90% bridge)
```
cost_center_structure_map(
  id              SERIAL PK,
  cost_center_id  INTEGER NOT NULL REFERENCES cost_centers(id) ON DELETE CASCADE,
  structure_node_id INTEGER REFERENCES structure_nodes(id) ON DELETE SET NULL,
  UNIQUE(cost_center_id)                  -- one default structure node per cost center
)
```
Purpose: when a user (or import) picks a cost center, suggest the department/responsable via the
mapped node. Nullable target so an unmapped cost center is allowed (the 10% or not-yet-mapped).
Directionality is cost_center → node (many cost centers may point at one node; a node may back
several cost centers).

### 5.3 `allocations.cost_center_id` (new column — additive)
```
ALTER TABLE allocations ADD COLUMN cost_center_id INTEGER
  REFERENCES cost_centers(id) ON DELETE SET NULL;   -- nullable, reversible
```
The existing `company/brand/department/subdepartment` + `responsible/responsible_user_id` columns
stay exactly as they are and keep driving notification. `cost_center_id` is the new **budgeting**
key. (`reinvoice_destinations` get **no** `cost_center_id` — reinvoiced lines inherit the parent
allocation's cost center, per decision 10.)

## 6. Resolution / data flow

### 6.1 Budgeting (Phase 2 target state)
```
User opens AllocationEditor for an invoice
  → picks Cost center (per company list from cost_centers)
      → if cost_center has a mapped structure_node:
            auto-fill brand/department/subdepartment + responsable  (90% one-click)
      → else:
            user fills the org path (for notification) manually        (10% / unmapped)
  → user may override the responsable independently of the cost center (10%)
  → save: allocations row carries BOTH cost_center_id (budget) AND org path (notify)
```

### 6.2 Notification (UNCHANGED)
```
allocation saved → notification_service.find_responsables_for_allocation(allocation)
  reads allocation['company'] + allocation['department']            # org path, not cost center
  → get_responsable_users_by_department (structure_nodes, fallback department_structure)
  → email (notification_service.py:536) + in-app (:549)
```
No file in `notification_service.py` / `structure_node_repository.py` changes.

### 6.3 EuroFib / export (Phase 3)
```
export kostenstelle = allocations.cost_center_id.code  ('0211')  when present
                    else supplier-level kostenstelle    (today's behaviour)  when null
```

## 7. Frontend

- **New:** Finance → **Centre de cost** section (admin-gated). Per-company table (code, name,
  active, mapped structure node), CRUD, "Import din Excel" / re-seed, and the default-map picker.
  Mirrors the existing `Settings/StructureTab.tsx` table idiom.
- **Changed:** `pages/Accounting/AllocationEditor.tsx` — add a **Cost center** select fed by a new
  `costCentersApi.list(companyId)`. On select, call the map to prefill org path + responsable
  (reusing the existing `getManager` auto-fill). Org-path selects remain, now pre-filled but
  editable. `LineItemAllocations.tsx` / `allocationUtils.ts` carry `cost_center_id` per line.
- **Unchanged:** everything under responsable resolution and the org endpoints used for
  notification.

## 8. Phased rollout

**Phase 0 — Validation & seed prep** *(no user-facing change)*
- Cross-check all ~59 Excel codes vs BAB `kostenstelle` (code + name); produce a reconciliation
  report: matched, Excel-only, BAB-only, name-mismatch.
- Freeze the seed dataset (canonical `code`='0211', per company).
- Draft the default `cost_center → structure_node` map; **enumerate the ~10% divergences** as an
  explicit list.

**Phase 1 — Cost Center dimension + Finance "Centre de cost"** *(standalone; zero invoice impact)*
- Migration: `cost_centers` + `cost_center_structure_map` + **one-time** Excel seed (in-app CRUD
  authoritative thereafter; re-import is opt-in and never clobbers edits).
- Repository + routes: list/CRUD/deactivate per company; opt-in import; get/set default map.
  Auto-seed the default map for **exact name-matches only**; accounting fills the rest in-app.
- Frontend Finance section. Admin-gated.

**Phase 2 — Attach cost center to allocations** *(the actual dissociation)*
- Migration: `allocations.cost_center_id` (nullable, additive).
- AllocationEditor cost-center picker + map-driven auto-fill; independent responsable override.
- Backfill `Bugetata` invoices where department→cost-center is unambiguous via the map; null +
  report the rest. Non-destructive.
- `cost_center_id` stays **optional** through Phase 2; a later gate (after coverage is proven)
  makes it required to reach `Bugetata`.
- Notification untouched.

**Phase 3 — EuroFib/export from the allocation's cost center**
- Export kostenstelle from `cost_center_id.code`, fallback to supplier-level when null.
- Report: `Bugetata` invoices missing a cost center.

**Phase 4 — *(optional/future)* planned budgets per cost center × period**
- `budget_plans` / `budget_values` keyed on `(company, cost_center, period)` — budget-vs-actual.
  Separate spec.

Phases 1–3 solve the 90/10 inconsistency. Each phase is independently shippable and reversible
(additive migrations, nullable columns, no destructive changes).

## 9. Edge cases & risks

- **Repeated codes across companies** — always resolve cost centers within a `company_id`; UI
  lists are per company. Enforced by `UNIQUE(company_id, code)`.
- **Code format drift** — `0211` (string) vs `211` (BAB int) vs any int coercion in facturare
  rules. Canonical = string; a single `cost_center_code_to_int()` / `_to_code()` helper is the only
  place conversion happens.
- **Unmapped cost centers (the 10%) & new hires' departments** — allowed; `cost_center_id` and org
  path are independent, so an unmapped cost center just means no auto-fill, never a block.
- **Backfill ambiguity** — where one department maps to several cost centers (or none), leave null
  and report; never guess.
- **Reinvoice destinations** — currently carry their own org path; whether they also need a cost
  center is deferred (Open Questions) so Phase 2 stays additive.
- **`company_responsables` has no DDL in the repo** (legacy table) — out of scope here but noted;
  unaffected by this change.

## 10. Testing

- Phase 0: reconciliation report reviewed by accounting before seeding.
- Phase 1: repo/route unit tests (per-company uniqueness, seed idempotency mirroring
  `tests/org/test_sincron_seed_idempotent.py`), import round-trip.
- Phase 2: allocation write carries `cost_center_id`; notification still resolves from org path
  (regression test asserting notification is unchanged when cost_center ≠ department); backfill
  dry-run report.
- Phase 3: EuroFib export golden-file test — kostenstelle from cost center when present, supplier
  fallback when null.

## 11. Resolved decisions (2026-09-15)

1. **Reinvoice destinations** — no own `cost_center_id`; reinvoiced lines inherit the parent
   allocation's cost center (revisit if a real split need appears).
2. **Seed authority** — **in-app CRUD is the source of truth.** Excel is a one-time seed; re-import
   is opt-in and never clobbers in-app edits.
3. **Default-map coverage** — Phase 1 auto-seeds the map for **exact name-matches only**;
   accounting fills the remaining (incl. the ~10% divergences) in-app.
4. **Required-ness timing** — `cost_center_id` stays optional through Phase 2 and becomes required
   to reach `Bugetata` only at a **later gate, once map coverage is proven**.

## 12. Key references (as-is code)

- Allocation schema: `jarvis/migrations/domains/schema_core.py:55` (`allocations`), `:241`
  (`structure_nodes`), `:99` (`department_structure`)
- The seam: `jarvis/accounting/invoices/repositories/allocation_repository.py:130-142`
- Budgeting orchestration: `jarvis/accounting/invoices/services/invoice_service.py:303-381`
- Auto-allocation on import: `jarvis/core/connectors/efactura/services/invoice_allocation_service.py:585,610-625,660`
- Responsable resolution: `jarvis/core/organization/repositories/structure_node_repository.py:247,279,321,384,424`
- Notification send: `jarvis/core/services/notification_service.py:28,416,463,536,549,572`
- Existing kostenstelle: `jarvis/migrations/domains/schema_controlling_bab.py:75`; EuroFib
  `jarvis/.../generators/eurofib_xlsx.py`; suppliers `core/suppliers/accounting_mapping.py`
- Budgeting UI: `jarvis/frontend/src/pages/Accounting/AllocationEditor.tsx`; org API
  `jarvis/frontend/src/api/organization.ts`; org routes `jarvis/core/organization/routes.py:78-157`
- Prior art (git-only, not in tree): `docs/JARVIS_BUDGET_MODULE_DESIGN.md` (commit `e0b4fda69`)
