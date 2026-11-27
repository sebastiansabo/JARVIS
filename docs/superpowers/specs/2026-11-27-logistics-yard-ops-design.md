# Logistics (Yard Ops) Module — Design Spec

**Date:** 2026-11-27
**Status:** Draft (awaiting approval)
**Module location:** `jarvis/logistics/` · schema `jarvis/migrations/domains/schema_logistics.py` · frontend `jarvis/frontend/src/pages/Logistics/` · route `/app/service/logistics` (under **Service**)
**Reference data:** `Centralizator Logistica Audi si AAP.xlsx` (6 tabs, ~1,250 cars — the system this replaces)

---

## 1. Intent & Why

Autoworld runs a high-volume vehicle **logistics operation** today on a single fragile Excel file (`Centralizator Logistica Audi si AAP`): ~506 delivered exports, ~69 exports in progress, ~88 internal prep cars, ~27 display/demo cars, ~29 AAP customer deliveries, and a ~240-day cosmetics/RAR bay calendar. The spreadsheet is already failing: dates stored as free text, "SÂNNICOARĂ" leaking into the PDI-status column 371 times, statuses typed by hand, no alerting, no physical-location truth.

We are building **Logistics** as an **independent JARVIS app under Service** that owns its **own stock** — every vehicle in Autoworld's physical/logistics custody, whether or not it is a CarPark sales listing — and runs each car through its full physical journey: **gate-in → slot → inspection → work orders (PDI, cosmetică, RAR, remediere, baterie) → movements/transfers → gate-out/delivery**, with a live yard occupancy map and SLA-driven "next-in-line" notifications to drive **Time-to-Line** down.

It interconnects with CarPark by **VIN + order number**, but does not depend on it: most logistics cars (export B2B units, customer AAP cars) are not CarPark sales stock.

**Why now:** the spreadsheet can't scale, gives no real-time visibility across the three business lines (Intern/Display, AAP, Export), and loses money to coordination gaps (idle dwell time between prep stages, deliveries blocked on untracked payments, EVs discharging in storage).

---

## 2. Goals / Non-Goals / Anti-Goals

### Goals
1. **One structured car-in-logistics record** replacing all six spreadsheet tabs, keyed by VIN + order number.
2. **Pipelines as saved views** — Intern, Mașini Expunere, AAP, Export (în derulare / livrate) — over the same records, each with its own milestone set.
3. **Physical yard layer** — Location → Zone → Slot with capacity and a **live occupancy map** (AW, Sânnicoară, Athletic, extensible).
4. **Gate-in / gate-out** events capturing VIN, odometer, SoC%, photos, damage, slot assignment, and release gating.
5. **Work-order engine** — typed jobs (PDI, Cosmetică, RAR, Remediere daună, Intervenție baterie, Transport) with assignee (responsabil), target date/SLA, stage, and **next-in-line notification** when the prior step completes.
6. **Movements/transfers** between locations as transport orders (driver/carrier, gate pass, odometer in/out).
7. **Cosmetică/RAR bay capacity calendar** (replaces PROGRAMĂRI COSMETICĂ tab).
8. **Payment-gated delivery** for export (Încasare / Avans / Rest plată / Proformă), linked to JARVIS invoices.
9. **EV care** — next battery-intervention date, SoC% and odometer tracking, alerts before a unit discharges.
10. **CarPark interconnection** — two-way sync of location + readiness by VIN; work-order costs (Transport, ITP) post into CarPark's cost ledger for linked cars.
11. **Dashboards + alerts** — Time-to-Line, dwell per stage, yard occupancy vs capacity, overdue work orders, deliveries blocked on payment, EVs due for battery care.
12. **Migration** of the existing spreadsheet into the new model.

### Non-Goals
- Not a sales/pricing/publishing system — that's CarPark. Logistics never lists or prices a car for sale.
- Not a replacement for Foi de Parcurs (trip/driver logging) or the DMS order system — it references orders, doesn't own them.
- Not an accounting system — it links to invoices for payment status; it does not issue them.
- Not a route-optimization / carrier-TMS for third-party haulage (the industry's "FVL transport planning"). We record transport orders; we don't optimize fleets.

### Anti-Goals (failure even if it technically works)
- **Contaminating CarPark** with non-sales cars, or coupling the two so a change in one breaks the other.
- Recreating the spreadsheet's free-text chaos (statuses must be enumerated, dates must be real dates).
- A yard map so rigid that staff abandon it — slot assignment must be **optional** and adoptable gradually.
- Double data entry — if a car is both in CarPark and Logistics, its shared facts sync; staff never type them twice.

---

## 3. Constraints

- **JARVIS monolith**: single Flask/gunicorn app, one shared Postgres, React/Vite frontend, deployed on DigitalOcean (two services off branch HEADs). Reuse existing plumbing; do not stand up a separate service/DB.
- **Schema pattern**: `init_db()`-on-import domain schema file `schema_logistics.py` added to the domain registry; idempotent `CREATE TABLE IF NOT EXISTS`. Never app-import to run it.
- **Multi-tenant**: JARVIS is Company × Brand. Logistics tables carry `company_id` (and brand where relevant) for tenant isolation, consistent with CarPark.
- **Reuse, don't rebuild**: CRM (clients), Invoices/e-Factura (payment status), Notifications (4-channel prefs), Approvals, Organization (companies/brands), Users + `role_permissions_v2` (roles/permissions).
- **Romania domain**: first-class support for RAR (+ interval orar), nr. roșii (temporary plates), ETB, înmatriculare, impunere primărie, plate-holder (AW / Arval / Ayvens / BLRO).
- **Frontend error shape**: fetch-client `ApiError = {status,data,message}` (no `.response`); use `e?.data?.error || e?.message`.
- **Git workflow**: dev → staging → main FF-promotion; no plans/secrets committed to staging/prod; code review before commit; show commit SHA.

---

## 4. Approaches Considered

**Approach A — Logistics owns its own stock, linked to CarPark by VIN. ✅ CHOSEN.**
Own schema (`logistics_*`): `logistics_vehicles` (stock; nullable `carpark_vehicle_id` + VIN link), locations/zones/slots, movements (gate events + transfers), work orders, flows. Reuses shared JARVIS services (CRM, Invoices, Notifications, Org, Users). When a VIN exists in both apps, **location + readiness sync both ways**; work-order costs can post into CarPark's cost ledger.
*Trade-off accepted:* a thin sync contract to maintain and minor duplication of core vehicle attributes (VIN, model, plate).
*Why:* genuinely independent (own stock, own schema), does not contaminate CarPark, leverages the monolith's shared plumbing.

**Approach B — One shared vehicle record; Logistics as an operational layer on `carpark_vehicles`.** *Rejected.*
Reuse CarPark's vehicle table as the single identity for all cars incl. export/AAP; add only ops tables. No duplication, but **pollutes CarPark with hundreds of non-sales cars**, drags its tenant/permission model into Logistics, kills the independent-app requirement, and tightly couples the two.

**Approach C — Separate standalone service (own DB/deploy), API integration only.** *Rejected.*
Maximum isolation, but JARVIS is a single app on one shared DB; duplicating auth/org/deploy isn't worth the marginal benefit.

---

## 5. Domain Model (from the real data)

Every row in the spreadsheet is a **car in a flow**. Decoded entities:

- **LogisticsVehicle** — the stock unit. VIN (serie șasiu), model (autoturism), order no. (nr. comandă), plate, flow, client, salesperson (vânzător), billing center (centru de facturare), company/brand, optional `carpark_vehicle_id`, EV fields (SoC%, next battery date), current location/zone/slot, current status, plate-holder (suport nr).
- **Flow / Pipeline** — INTERN, MASINI_EXPUNERE, AAP, EXPORT. Determines which milestones apply and which board the car shows on.
- **Location → Zone → Slot** — physical hierarchy with capacity (AW, Sânnicoară, Athletic).
- **GateEvent** — gate-in (sosire) / gate-out (livrare/ieșire): odometer, SoC%, photos, damage snapshot, slot assignment, release-gate result.
- **Movement / Transfer** — between locations; transport order with driver/carrier, gate pass, odometer in/out.
- **WorkOrder** — typed job (PDI, COSMETICA, RAR, NR_ROSII, ETB, INMATRICULARE, IMPUNERE_PRIMARIE, REMEDIERE_DAUNA, INTERVENTIE_BATERIE, TRANSPORT) with assignee, scheduled date, target/SLA, stage, result; some are **appointments** (RAR interval orar, cosmetică bay slot).
- **DamageRecord** — observation, responsabil remediere, estimated fix date, status.
- **PaymentGate** (export) — Încasare / Avans / Rest plată / Proformă, linked to invoice(s); blocks gate-out until satisfied.
- **Client** — B2B export accounts (TA Trading, Auto Kombi, AT Rent, Gierse…) and AAP customers → **CRM**.
- **BayCalendar** — daily capacity for Cosmetică / RAR / Test (PROGRAMĂRI COSMETICĂ).

---

## 6. Data Model (tables)

> Columns below are the spine; builder may add indexes/audit columns per JARVIS norms (`created_by`, `created_at`, `updated_at`, soft-delete `deleted_at`). All tenant tables carry `company_id` (+ `brand` where relevant).

### `logistics_vehicles` (the stock)
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| company_id | INT NOT NULL | tenant |
| brand | VARCHAR(50) | e.g. AUDI |
| vin | VARCHAR(17) NULL | indexed; CarPark link key. **Nullable** — INTAKE_PLANNED/IN_TRANSIT cars may have no VIN yet; backfilled on arrival |
| order_no | VARCHAR(50) | nr. comandă — **the stable identity key**; links to `facturare` order lines (`cod_comanda`) when present |
| plate | VARCHAR(20) | current plate |
| model | VARCHAR(120) | autoturism |
| carpark_vehicle_id | INT NULL FK → carpark_vehicles | set when also a CarPark car |
| client_id | INT NULL FK → crm_clients | export B2B / AAP customer |
| flow | VARCHAR(24) | INTERN / MASINI_EXPUNERE / AAP / EXPORT |
| status | VARCHAR(32) | enumerated (see §7) |
| current_location_id | INT NULL FK → logistics_locations | |
| current_zone_id | INT NULL FK → logistics_zones | |
| current_slot_id | INT NULL FK → logistics_slots | **optional** |
| plate_holder | VARCHAR(16) | AW / ARVAL / AYVENS / BLRO |
| salesperson_user_id | INT NULL FK → users | vânzător |
| billing_center | VARCHAR(80) | centru de facturare |
| is_ev | BOOLEAN DEFAULT FALSE | |
| soc_percent | SMALLINT NULL | last known State of Charge |
| next_battery_date | DATE NULL | următoarea intervenție baterie |
| odometer_km | INT NULL | |
| arrived_at | DATE NULL | data sosire AW |
| transport_ordered_at | DATE NULL | data comandă/solicitare transport |
| est_delivery_at | DATE NULL | data estimată livrare |
| delivered_at | DATE NULL | |

**Identity & dedup:** primary identity is `order_no` (present from intake, before a VIN exists). VIN is the *CarPark link* key and is backfilled at gate-in. Migration dedups by `order_no` first, VIN second. A car with neither is rejected to a review queue.

### `logistics_locations` / `logistics_zones` / `logistics_slots`
- `logistics_locations`: id, company_id, name, code (AW/SNN/ATH), type (compound/showroom/bodyshop/partner), capacity, address, city, is_active.
- `logistics_zones`: id, location_id, name, code, capacity.
- `logistics_slots`: id, zone_id, code (row/slot label), is_occupied, current_vehicle_id NULL. **Slot-level optional** — occupancy map degrades gracefully to location+zone.

### `logistics_gate_events`
id, vehicle_id FK, company_id, kind (`IN`/`OUT`), occurred_at, location_id, slot_id NULL, odometer_km, soc_percent, photo_ids JSONB, damage_summary TEXT, release_gate_ok BOOLEAN NULL (gate-out), handover_to VARCHAR, created_by.

### `logistics_movements` (transfers)
id, vehicle_id FK, company_id, from_location_id, to_location_id, status (`PLANNED`/`IN_TRANSIT`/`ARRIVED`/`CANCELLED`), carrier_name, driver_name, gate_pass_ref, odometer_out, odometer_in, requested_at, departed_at, arrived_at, created_by.

### `logistics_work_orders`
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| vehicle_id | INT FK | |
| company_id | INT | |
| type | VARCHAR(28) | PDI / COSMETICA / RAR / NR_ROSII / ETB / INMATRICULARE / IMPUNERE_PRIMARIE / REMEDIERE_DAUNA / INTERVENTIE_BATERIE / TRANSPORT |
| stage | VARCHAR(20) | PLANNED / IN_PROGRESS / DONE / BLOCKED / CANCELLED |
| assignee_user_id | INT NULL FK → users | responsabil |
| scheduled_at | TIMESTAMP NULL | appointment start (RAR, cosmetică) |
| slot_window | VARCHAR(20) NULL | interval orar RAR |
| target_at | DATE NULL | SLA due date |
| completed_at | TIMESTAMP NULL | data efectuat |
| result | TEXT NULL | |
| blocks_delivery | BOOLEAN DEFAULT FALSE | gate-out dependency |
| carpark_cost_posted | BOOLEAN DEFAULT FALSE | synced into CarPark cost ledger |
| sequence | SMALLINT | order within the flow's template (defines "next-in-line") |
| depends_on_wo_id | INT NULL FK → self | prior step that must be DONE before this starts |
| auto_generated | BOOLEAN DEFAULT FALSE | created from the flow template at intake |

**Work orders are template-driven.** Each flow has a milestone template that **auto-creates its work orders at intake** with `sequence` and `depends_on_wo_id` set, so "next-in-line" is deterministic (the lowest-`sequence` open WO whose dependency is DONE). Templates (derived from the data, builder to validate):
- **AAP:** PDI → RAR → NR_ROSII → ETB → INMATRICULARE → IMPUNERE_PRIMARIE → (delivery)
- **EXPORT:** PDI → COSMETICA → (payment gate) → delivery
- **INTERN / MASINI_EXPUNERE:** PDI → COSMETICA → INTERVENTIE_BATERIE (recurring for EVs)
Coordinators can add/remove/reorder WOs on a specific car; the template is the default, not a cage.

### `logistics_damage` 
id, vehicle_id FK, company_id, description, responsabil_user_id, est_fix_date, status (`OPEN`/`IN_PROGRESS`/`RESOLVED`), photo_ids JSONB, created_by, created_at.

### `logistics_payment_gates` (export)
id, vehicle_id FK, company_id, incasare_status, avans_amount, rest_amount, proforma_issued BOOLEAN, facturare_invoice_ids JSONB (FK → **`facturare_invoices`** — the sales-invoice system, ADVANCE/PROFORMA/FINAL + PAID; **not** the generic budget `invoices` table), is_cleared BOOLEAN (computed), cleared_at.
*Clearance rule (default):* gate clears when the FINAL `facturare` invoice for the order is `PAID` (equivalently rest plată ≤ 0). Hard-block vs override policy → Open Decision §14.8.

### `logistics_bay_calendar`
id, company_id, date, bay_type (`COSMETICA`/`RAR`/`TEST`), capacity, notes. Appointments reference work orders via `scheduled_at`.

### `logistics_vehicle_history` (audit/event log)
id, vehicle_id, company_id, event_type, old_value JSONB, new_value JSONB, user_id, created_at — drives dwell-time/Time-to-Line analytics and status history.

---

## 7. Lifecycle & Statuses

Canonical status set (enumerated — no free text):

```
INTAKE_PLANNED → IN_TRANSIT → ARRIVED → INSPECTION → PREP (work orders open)
   → READY → DELIVERY_PLANNED → DELIVERED
                 ↘ BLOCKED (damage open / payment pending)   [overlay flag, not a dead end]
```

- Per-flow milestone sets map onto this spine (e.g. AAP adds RAR → nr. roșii → ETB → înmatriculare between PREP and READY; EXPORT adds the payment gate before DELIVERED).
- `BLOCKED` is an **overlay** (reason-coded: damage / payment / parts), not a terminal status, so a car can be "in PREP but blocked on payment".
- Time-to-Line = `delivered_at − arrived_at` (and a "ready" variant = `READY reached − arrived_at`). Dwell per stage derived from `logistics_vehicle_history`.

---

## 8. CarPark Interconnection (the sync contract)

- **Link:** `logistics_vehicles.carpark_vehicle_id` + VIN match. At gate-in a helper resolves "is this VIN a CarPark car?" and offers to link.
- **No cross-module writes (project rule: modules own their tables).** Logistics **never** writes `carpark_*` directly. CarPark exposes a service entrypoint (e.g. `carpark.logistics_sync.apply(vin|carpark_vehicle_id, payload)`); Logistics calls it, CarPark decides what to persist. Reverse direction is a CarPark→Logistics call or a subscribed event.
- **What syncs & who wins (precedence):**
  | Field | Owner / source of truth | On conflict |
  |---|---|---|
  | Commercial status (LISTED/RESERVED/SOLD) | CarPark | CarPark wins; Logistics never sets it |
  | Physical location | Logistics (gate events/movements) | Logistics wins |
  | Readiness signal (READY) | Logistics | advisory → CarPark may flip `READY_FOR_SALE` |
  | Odometer | Logistics gate events | proposed to CarPark, applied via its **existing odometer ratchet** (never decreases) |
  | Work-order costs (Transport, ITP) | Logistics | posted into `carpark_vehicle_costs` via CarPark service, idempotent (`carpark_cost_posted`) |
- **Existing-importer reconciliation:** CarPark already imports `docs/centralizator AAP.xlsx` → `carpark_vehicles`. Migration must **re-link to those existing rows by VIN/order_no, not re-create them**, and the two importers must be reconciled (see Open Decision §14.7).
- **Isolation:** sync is a thin module (`jarvis/logistics/carpark_sync.py`) calling CarPark's service; Logistics works fully with `carpark_vehicle_id = NULL`.

---

## 9. Notifications, Alerts & KPIs

- **Next-in-line** (the Time-to-Line driver): when a work order completes, notify the assignee of the next open work order for that car (reuse Notifications 4-channel prefs).
- **Overdue** work orders (past `target_at`), **deliveries blocked on payment**, **EVs due for battery care** (`next_battery_date` approaching / low SoC), **aged dwell** (car in a stage beyond threshold).
- **Dashboards:** Time-to-Line (target 3–5 days), dwell per stage, yard occupancy vs capacity per location, overdue WO count, blocked-on-payment list, EV care due.

---

## 10. Permissions, Tenancy, Surfaces

- **Roles** (via `role_permissions_v2`): Logistics Coordinator (full), Technician (own work orders: PDI/Cosmetică/RAR/Remediere/Baterie), Gate Operator (gate-in/out + movements), Viewer. Permission key family `can_access_logistics`, `logistics_manage`, `logistics_gate`, `logistics_work`.
- **Tenancy:** scoped by `company_id` (+ brand), same pattern as CarPark's tenant-isolation fix.
- **Surfaces:** Web (pipelines/boards, yard map, work-order queue, calendar, dashboards). **Mobile (jarvis-mobile-2)** for gate-in/out, work-order status updates, and damage photo capture — the field surfaces.

---

## 11. Migration

- One-off importer `jarvis/logistics/scripts/import_centralizator.py` mapping the six tabs → `logistics_vehicles` + child rows, normalizing text dates and splitting the leaked PDI/location column.
- **Import active rows first** (Intern, Expunere, AAP, Export în derulare); EXPORT LIVRATE (~506) imported as historical/archive for Time-to-Line baselines.
- Dedup by VIN; link to CarPark where VIN matches.

---

## 12. Phasing (build order; detailed in the plan)

1. **Core stock + pipelines** — `logistics_vehicles`, flows, statuses, boards, CRUD, migration of active rows. (Replaces the spreadsheet.)
2. **Work-order engine + notifications** — typed WOs, SLA, next-in-line, overdue alerts, bay calendar, damage, EV care.
3. **Physical yard layer** — locations/zones/slots, gate-in/out, occupancy map, movements/transfers.
4. **Payment gating + CarPark sync + dashboards** — invoice link, release gate, two-way sync, cost posting, KPIs.
5. **Mobile** — gate-in/out + work-order updates on jarvis-mobile-2.

---

## 13. What's Left to the Builder

- Exact indexes, audit columns, API route shapes, and React component structure (follow CarPark/Voucher precedents).
- Precise permission-key wiring in `role_permissions_v2`.
- Enum value finalization for work-order types / statuses against any flow not fully represented in the sample.
- Photo storage reuse (same pipeline as CarPark photos).

---

## 14. Open Decisions

### Calls I made (confirm or correct)
1. **Tenancy:** schema is multi-company/brand from day one, seeded with Audi/Autoworld (not Audi-hardcoded).
2. **Clients:** reuse **CRM** (`crm_clients`) for export B2B accounts and AAP customers, not a Logistics-local client table.
3. **Payment source:** gate reads **`facturare`** (sales invoices, ADVANCE/PROFORMA/FINAL + PAID), not the generic budget `invoices` table; manual flags allowed only when no `facturare` order exists.
4. **Slots:** Location → Zone → Slot modeled, but **slot assignment is optional**; occupancy map works at location+zone level until you map slots.
5. **Mobile:** gate-in/out + work-order updates are **Phase 5**, not first release.
6. **Migration scope:** active rows first; ~506 archived exports imported as historical baseline only.
7. **Sync direction:** no cross-module writes — Logistics calls a CarPark-owned service; precedence table in §8; odometer respects CarPark's ratchet.
8. **Work orders:** template-driven auto-generation per flow with explicit `sequence`/`depends_on_wo_id` (§6).
9. **Movements vs Foi de Parcurs:** `logistics_movements` stays a lightweight standalone record (carrier/driver/gate-pass/odometer). An **optional** link to a Foi de Parcurs session is deferred to post-Phase-3, only for self-propelled staff drives — car-carrier transfers never need one. *(Flagged so double-entry stays an explicit, bounded choice.)*
10. **EV care:** `next_battery_date` is entered manually or computed from last `INTERVENTIE_BATERIE` + a configurable interval; SoC alert threshold is configurable (default 30%).

### Needs your decision (changes the build — see questions)
- **D1 — Where AAP & export cars live.** CarPark already imports AAP cars into `carpark_vehicles`. Are AAP/export cars genuinely CarPark sales stock (link & keep), or purely logistics (Logistics owns them; CarPark stops importing them)? Decides whether migration reconciles-and-links or de-duplicates-and-moves, and how literally "don't pollute CarPark" holds.
- **D2 — Payment-gated gate-out policy.** Hard block until `facturare` FINAL is PAID, with Coordinator override? Soft warning only? Hard block with no override? Decides gate-out UX + permission wiring.

---

## Appendix A — Source spreadsheet columns (ground truth)

Source file: `Centralizator Logistica Audi si AAP.xlsx` (in the user's Downloads, **not in the repo** — copy into `docs/` or point the importer at a configured path before running migration). Six tabs, decoded headers:

- **INTERN** (~88 rows): Nr crt · Nr comanda · Client · Autoturism · Serie sasiu (VIN) · Data comanda transport · Data sosire AW · Data PDI planificata · Data PDI efectuat · Data estimata livrare solicitata · Data urmatoarei interventii (Baterie) · Suport numar (AW/Arval/Ayvens/BLRO) · Obs/Daune/Reparatii · Responsabil remediere · Vanzator
- **AAP** (~29 rows): Nr crt · Client · Autoturism · Serie sasiu · Data comanda transport · Data sosire AW · Data programare RAR · Interval orar RAR · Data programare nr rosii · Data programare ETB · Data estimata livrare la client · Obs/Daune/Reparatii · Responsabil · Centru de facturare · Vanzator
- **EXPORT IN DERULARE** (~69 rows): Nr crt · COMANDA · CLIENT · MODEL · S.S (VIN) · INCASARE · DATA SOLICITARE TRANSPORT · DATA SOSIRE AW · LOCATIE DESCARCARE · STATUS PDI · PROGRAMARE INMATRICULARE · DATA LIVRARE EXTERN · OBSERVATII/DAUNE · Data estimativa remediere · Responsabil dauna · IMPUNERE PRIMARIE · PRET ACHIZITIE BRUT · DATA INCASARE EFECTIVA · Incasat efectiv · Plata la Poro realizat · Data livrare transport extern · NOT
- **EXPORT LIVRATE** (~506 rows): NR.CRT. · COMANDA · CLIENT · MODEL · S.S · DATA SOLICITARE TRANSPORT · DATA SOSIRE AW · LOCATIE DESCARCARE · STATUS PDI · DATA LIVRARE EXTERN · PROGRAMARE INMATRICULARE · AVANS · REST PLATA · PROFORMA REST PLATA DA/NU
- **MASINI EXPUNERE** (~27 rows): Nr crt · Nr comanda · PREGATIRE · Client · Autoturism · Serie sasiu · Data sosire AW · Data PDI planificata · Data PDI efectuat · Data estimata livrare solicitata · Data urmatoarei interventii (Baterie) · Suport numar · Obs/Daune/Reparatii · Responsabil remediere · Vanzator
- **PROGRAMARI COSMETICA AUDI** (~240 day-rows): Data · Tip programare (TEST / COSMETICA / C.O / WEEKEND / RAR / RAR (2 AUTO)) · Detalii

**Data-quality notes for the importer:** dates are stored as free text in mixed formats (e.g. `07.04.2026`, `AW 06.03.2026`, `9.11`); `DATA SOSIRE AW` and `STATUS PDI` columns have location values ("SANNICOARA") leaking in (371×); PDI status is free text ("EFECTUAT", "in lucru", "?"); EV notes appear inline ("SoC 60%", "Peste 10 km"). Expect ~15–20% rows needing a review queue, not clean import.

## Appendix B — Pre-existing related code (builder: reconcile, don't duplicate)

- `jarvis/carpark/services/import_service.py` — existing `CentralizatorImporter` loading `docs/centralizator AAP.xlsx` (sheet AUDI, ~149 rows) into `carpark_vehicles`. Overlaps this module's migration — see D1.
- `jarvis/accounting/facturare/` — sales invoicing (`facturare_invoices`: DRAFT/ISSUED/PAID, ADVANCE/PROFORMA/FINAL, keyed by `cod_comanda`). Authoritative payment source for §8/§14.3.
- `jarvis/foi_parcurs/` — trip/driver/odometer logging. Related to `logistics_movements` — see §14.9.
- `jarvis/carpark/` — `carpark_locations`, `carpark_vehicle_costs`, status lifecycle incl. `IN_TRANSIT`/`TRANSFERRED`/`AT_BODYSHOP`, odometer ratchet. Link target per §8.
