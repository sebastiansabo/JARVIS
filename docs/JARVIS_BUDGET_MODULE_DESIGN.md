# Jarvis Budget — Placement Decision & Module Design

**Status:** Decision proposal. Awaiting the source workbook for schema validation.
**Scope:** Where "Jarvis Budget" (annual sales budget / *refacut buget*, VW PKW Vanzari) is built, and how it is built.

---

## 0. Blocking input

The reference workbook `Copy of Refacut Buget VW PKW Vanzari an 2026 V1-11.12.2025.xls`
lives on a local machine and is not present in this repository or in the session
container. Every field-level statement in Section 4 is therefore **inferred from the
existing Controlling BAB structure**, not read from the file. Commit the workbook to
`docs/budget/` on this branch (or attach it) before the schema is treated as final.

What is *not* blocked by that gap: the placement decision. That is settled by the
codebase as it stands, below.

---

## 1. Brutal truth

Three things are true and they kill two of the three options outright.

**1. A separate app is a decision to rebuild the platform, not the budget.**
A budget app needs authentication, RBAC, multi-company scoping, an approval workflow
(a budget "refacut V1 / V2" *is* a versioned approval artifact), notifications, audit
trail, Excel import, an export engine, and a UI shell. All of it exists twice already —
in `jarvis/core/*` (2.0) and `jarvis/core/*` + `jarvis/primitives/*` (3.0, which ships
`approvals`, `workflows`, `notifications`, `forms`, `views`, `signatures`). The budget
logic itself is perhaps 15% of the work. A standalone module means paying 85% overhead
for the privilege of a second deploy pipeline you maintain forever.

**2. "Staging server so it's secure" is inverted.**
Staging is the *least* secure environment you own: looser secrets, experimental deploys,
weaker access control, no production alerting. Putting the annual sales plan there — the
single most commercially sensitive document a dealer group produces — and then opening a
network path from staging to the production database is a strictly worse posture than
putting it in production behind RBAC. Security for this comes from three things you
already have: permission-gated routes, a read-only Postgres role for cross-DB reads
(`MIGRATION_FROM_LEGACY.md` already specifies `jarvis3_migrator`), and tenant scoping.
Not from which droplet it runs on.

**3. The budget is the planning twin of a module you already shipped.**
`jarvis/accounting/controlling_bab/` + `schema_controlling_bab.py` already models exactly
this domain, with the *actuals* side seeded verbatim:

```
kostenstelle 211  VW PKW INTERN (retail)  Venit Sales realizat        707111,707116
                  VW PKW INTERN (retail)  Marjă Brută realizată       707111,707116,607111
                  VW PKW INTERN (retail)  Bonus trimestrial (importator) 609010
                  VW PKW INTERN (retail)  Venit Test Drive            707112
                  VW PKW INTERN (flote)   Venit Sales realizat         707110,707115
                  MARJA FINALĂ PKW        MARJA FINALĂ               (subtotal)
```

The workbook is the *plan* rows for the same cost centres, accounts and margin structure.
Building it as a disconnected app means duplicating the config engine
(`bab_report_config`, `bab_subtotal_refs`), the EUR-rate handling (`bab_eur_rates`, BNR
sync), the period locking (`locked_at`/`locked_by`), and the calculator — then
reconciling two divergent definitions of "Marjă Brută" for the rest of the company's life.
Budget without actuals on the same axis is a spreadsheet with extra steps.

**The real bottleneck is not this module.** In the last 30 days: 50 commits to JARVIS 2.0,
zero pushes to Jarvis-3.0 (last push 2026-08-17). The rewrite plan mandates a feature
freeze on 2.0 during Phase 1–2; the freeze is not holding. Every new module built in 2.0
lengthens the port backlog and pushes cutover further out. Jarvis Budget is a good
forcing function to resolve that — or it becomes the 55th blueprint in a monolith you
have already decided to retire.

---

## 2. Options, scored

| | A. Separate repo + droplet | B. New module in JARVIS 2.0 | C. Module in Jarvis-3.0 |
|---|---|---|---|
| Time to first usable version | 8–12 weeks | 3–4 weeks | 4–6 weeks |
| Auth / RBAC / approvals | rebuild | reuse | reuse (stronger primitives) |
| Actuals adjacency (BAB) | cross-DB, brittle | same DB, trivial | ETL via existing framework |
| Second deploy pipeline | yes, permanent | no | no |
| Sellable to other dealers | no | no | yes (multi-tenant, Store app) |
| Adds to 2.0→3.0 port backlog | n/a | yes | no |
| Violates the 2.0 feature freeze | n/a | yes | no |

**A is rejected.** It maximises cost and minimises reuse. The only argument for it —
isolation — is better served by RBAC inside an existing platform.

**B is the tactical answer.** Fastest path to a working tool, sits next to BAB actuals in
one database, ships on the pipeline that actually deploys today. Its cost is strategic:
it adds a module to the codebase you are trying to retire.

**C is the correct answer**, on one condition below.

---

## 3. Recommendation

**Build `budget` as an installable module in Jarvis-3.0.**

Rationale beyond the table:

- **It is a product, not an internal tool.** The VW/importer budget refactoring workbook
  is standardised across the dealer network. Every dealership in the Jarvis SaaS pipeline
  refills the same structure every year in Excel, by hand, badly. In 3.0 it is a Store app
  with `tenant_id` scoping from day one. In 2.0 it is an Autoworld-only feature.
- **The approval workflow is free.** `V1 – 11.12.2025` in the filename is version 1 of a
  submitted plan. That is `jarvis/primitives/approvals` + `workflows`: dealer submits,
  controller reviews, GM approves, version is frozen, next revision forks from it. In 2.0
  this maps to `core/approvals`; in 3.0 it maps with tenant isolation and a proper state
  machine.
- **Sales actuals are already modelled in 3.0.** `jarvis/modules/carsale` (`sale_deals`,
  `sale_bonuses`, `sale_offers`, delivery tracking, centralizator margins) is the unit-level
  actuals source. Budget-vs-actual at unit granularity — plan 40 Golf in March, delivered 31 —
  requires exactly this, and 2.0 has no equivalent.
- **The module scaffold exists.** `manifest.py` + `models.py` + `repository.py` + `service.py`
  + `schemas.py` + `routes.py` + `api.py`, `PermissionSpec`, `require_module_enabled`,
  `INSTALLABLE_MODULE_IDS`. Copy `carsale`, change the nouns.

### The condition

3.0 must be the platform you actually ship to. If the next 30 days look like the last 30
(50:0 in favour of 2.0), option C produces a module nobody uses. Resolve that first, in
writing, with a date. If the honest answer is "2.0 is the platform through 2026", then
build option B — but build it *as a port candidate*: schema and service layer written so
that the 3.0 port is mechanical, not a rewrite.

---

## 4. Module design

Module id `budget`. Placement `jarvis/modules/budget/` in Jarvis-3.0.
Schema below is the inferred shape; validate against the workbook before migration.

### 4.1 Grain

The budget grain is `(tenant, company, cost_centre, brand/segment, indicator, period_month)`.
This deliberately mirrors `bab_entries` (`company_id`, `kostenstelle`, `konto`, `saldo1`)
so plan and actual join without translation.

Unit-volume rows (cars per model per month) are a **second grain**, not the same table:
`(tenant, company, cost_centre, model/variant, channel, period_month) -> units, avg_price,
avg_margin`. Value rows are derived from unit rows where the workbook derives them, and
entered directly where it does not. Which rows are derived is the single most important
thing the workbook will tell us.

### 4.2 Tables

```
budget_plans          -- one per (company, year, scenario); versioned
  id, tenant_id, company_id, year, scenario, version, label,
  status (draft|submitted|approved|frozen|superseded),
  parent_version_id, currency, eur_rate, created_by, approved_by,
  approved_at, frozen_at

budget_config_rows    -- the plan-side twin of bab_report_config
  id, tenant_id, company_id, sort_order, cost_centre, group_name,
  item_label, row_type (input|sum|subtotal|derived), konto_refs,
  formula, actuals_binding   -- FK/expr resolving to bab indicator

budget_values         -- value grain
  id, plan_id, config_row_id, period_month (1..12), amount, currency, note

budget_volume_lines   -- unit grain
  id, plan_id, cost_centre, channel (retail|flote|test_drive),
  model_code, model_label, period_month, units,
  avg_sale_price, avg_gross_margin, avg_importer_bonus

budget_assumptions    -- drivers: EUR rate, bonus %, discount %, mix
  id, plan_id, key, label, value, unit, applies_to

budget_revisions      -- audit: who changed what, when, from which version
```

`scenario` covers `base` / `stretch` / `refacut` — the filename says *refacut* (revised),
so revision-of-a-revision is a first-class case, not an edge case.

### 4.3 Services

- `ImportService` — parse the workbook. Reuse the shape of
  `accounting/controlling_bab/parser.py` (column mapping, tolerant numeric coercion) and
  `bugetare/invoice_parser.py` (LLM-assisted mapping when the layout drifts year to year).
  Import must be idempotent and produce a diff against the current version, never a blind
  overwrite.
- `CalculationService` — pure, no DB, mirroring `controlling_bab/calculator.py`. Formula
  and subtotal resolution config-driven, so the 2027 workbook is a config change.
- `VarianceService` — plan vs actual. In 3.0: actuals from `carsale` (units, realised
  margin) plus BAB indicator values ported by ETL. Outputs per period: absolute variance,
  %, YTD cumulative, run-rate to year end.
- `ApprovalBinding` — plan submit/approve/freeze wired to `primitives/approvals`.
  A frozen version is immutable; a new revision forks it.
- `ExportService` — back to the importer's Excel layout. Non-negotiable: the importer
  will keep asking for the file.

### 4.4 Permissions

```
budget.plan.view      read plans, variance, exports
budget.plan.manage    create/edit draft plans, import workbooks
budget.plan.approve   approve and freeze a version
budget.config.manage  edit config rows, formulas, actuals bindings
```

### 4.5 Actuals bridge (the only cross-system concern)

3.0 application code never reads the legacy database at runtime —
`MIGRATION_FROM_LEGACY.md` is explicit and it is the right rule. So:

- A scheduled job under `jarvis/modules/budget/data_migration/` reads `bab_uploads` /
  `bab_entries` through the read-only `jarvis3_migrator` role and lands them in a 3.0
  `budget_actuals_bab` table, keyed `(company, year, month, cost_centre, konto)`.
- Progress tracked in `migration_progress`; idempotent, resumable.
- Only locked BAB periods (`bab_uploads.locked_at IS NOT NULL`) are ingested. An unlocked
  period is not a closed month and must not appear as actual.
- After 2.0 cutover the job is deleted and the source becomes native 3.0 tables. Nothing
  else changes.

This is one nightly read-only job — not a live cross-database join, not a network path
from a staging app into the production database.

### 4.6 Phasing

| Phase | Deliverable | Exit criterion |
|---|---|---|
| 0 | Workbook committed and mapped to the schema above | Every column has a home or an explicit "drop" decision |
| 1 | Schema + import + read-only plan view | The 2026 workbook round-trips: import → view → export, values identical |
| 2 | Editing, versioning, approvals | A revision can be created, submitted, approved, frozen |
| 3 | BAB actuals ETL + variance | Plan-vs-actual for closed 2026 months matches manual calculation |
| 4 | Unit-grain volumes + carsale actuals | Units delivered vs planned, per model per month |
| 5 | Multi-tenant hardening, Store listing | A second dealer can self-install and import their own workbook |

Phase 1 is the honest test. If the workbook does not round-trip byte-for-byte on values,
the model is wrong and no amount of UI fixes it.

---

## 5. What is explicitly rejected

- **A separate droplet.** Second pipeline, second secret store, second auth surface, second
  on-call target. No compensating benefit.
- **A separate repository.** Same, plus a permanent version-skew problem against the
  primitives it depends on.
- **Staging-hosted with a production database connection.** Weakest environment, strongest
  data. Inverted risk.
- **Rebuilding a config/formula engine.** `bab_report_config` + `bab_subtotal_refs` +
  `calculator.py` is the pattern. Reuse the shape.

---

## 6. Open decisions

1. **Platform commitment.** Is 3.0 the deployment target for new modules starting now?
   A date, in writing. Everything else follows from this.
2. **Grain authority.** Are value rows derived from unit rows, or entered independently
   and reconciled? The workbook decides; nothing else can.
3. **Scope of "Vanzari".** PKW retail + flote + test drive only, or the full margin
   structure including aftersales cost centres?
4. **Multi-company.** Is a plan per legal entity, or one plan spanning entities with
   cost-centre splits?
5. **Importer round-trip.** Is the exported file required to be byte-compatible with the
   importer's template, or is a JARVIS-native layout acceptable?
