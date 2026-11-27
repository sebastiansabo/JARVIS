# JARVIS Parc — Logistics Yard-Ops App — Design & Flow

**Date:** 2026-11-27
**Status:** Draft (awaiting approval)
**Product:** **JARVIS Parc** — an **independent** logistics / yard-operations app for Autoworld România's Audi & Audi Approved :plus (AAP) team.
**Supersedes framing of:** `2026-11-27-logistics-yard-ops-design.md` (kept as domain background; that draft assumed a monolith module — this one is the real target: a standalone app fed by jarvis-alpha).
**Data analyzed:** `Centralizator Logistica Audi si AAP.xlsx` (6 tabs, ~1,250 cars) + the working prototype screens (Azi, Kanban, Parc, Calendar, Setări).

---

## 1. What this is

JARVIS Parc replaces the fragile `Centralizator` Excel with a structured app that runs every car through its **physical journey** inside the park: arrival → reception → prep/work → ready → handover. It is an **independent application** with its **own stock** (every car in Autoworld's custody, Audi + AAP), and it **receives its feed from jarvis-alpha** — the disponent/DMS that already knows orders and transport status. jarvis-alpha *pushes* events; JARVIS Parc *consumes* them into a vehicle register and a task board.

The prototype already validated the UX. This spec makes it real and buildable.

### Two things stay strictly separated (the key insight)
- **Etapă Parc** — the car's *physical* stage: `În tranzit → În pregătire → În stoc → Expunere`.
- **Predare** — *handover readiness*, a separate axis: a car can be **În stoc** yet **blocked for release**. Handover (Predare) is always a **deliberate employee action**, never auto-triggered by the feed.

---

## 2. Architecture & integration

```
jarvis-alpha (DMS / disponent)                 JARVIS Parc (independent app)
  orders, transport status, ETA   ──push──▶   POST /api/intake/events
                                               GET  /api/intake/mapping  (published rule map)
                                                        │
                                               Mapping rules (Setări → Reguli)
                                                        │  translate event → actions
                                                        ▼
                                          ┌───────────────────────────┐
                                          │  Vehicle register (Parc)  │
                                          │  Task board (Kanban)      │
                                          │  Vehicle history (audit)  │
                                          └───────────────────────────┘
```

- **Independent deployment, own database.** No shared schema with jarvis-alpha or the Flask monolith. The only coupling is the intake contract.
- **Intake is event-driven and idempotent.** jarvis-alpha delivers events "even with the app closed" (queued/retried). Each event carries an **order reference** (identity) and a **monotonic timestamp/sequence** (ordering).
- **Mapping rules are editable** in `Setări → Reguli` (prototype's "Reguli Dispo"): e.g. event `Transport in derulare` → *create vehicle + open a Recepție task*; event `ETA actualizat` → *update that task's deadline*. Rules are versioned (`Rev. N`) and can run in `Simulare`.
- **"Dispo" was a placeholder name in the prototype** — the real source is jarvis-alpha. Endpoint names use `/api/intake/*`; the UI label becomes **Sincronizare jarvis-alpha**.

### Intake semantics (the acceptance test, verbatim from requirements)
1. **Idempotent create:** the same `Transport in derulare` event for an order, delivered **twice**, yields **one** vehicle row and **one** Recepție card (dedup by order reference).
2. **ETA update:** an `ETA actualizat` event updates the **same** card's due time — no second card.
3. **Confirmed state is authoritative over intake:** after a human confirms reception (bay, VIN…), a later **older** event must **not** overwrite the confirmed bay/location. Ordering guard = event timestamp/sequence + "confirmed fields win."
4. **Handover is separate:** the feed never sets Predare; only an employee action does.

---

## 3. Core domain model

| Entity | Purpose | Key fields |
|---|---|---|
| **Vehicle** (Parc register) | the stock unit | order_ref (AW-####, identity), vin (nullable until reception), model, plate, destinatie (flow), location_id, position_id (bay), etapa_parc, predare, eta, arrived_at, is_ev, soc_percent, next_battery_date, condition, keys_count |
| **Task** (Kanban card) | a unit of work on a car | title/action, type (Recepție/Îngrijire/Programare/Documente/Predare), vehicle_id, location_id, position_id, assignee (responsabil), due_at, status (coloană), block_reason, block_next_action, measured_result (JSON), source_event_id |
| **Location → Position** | physical yard map | location (name, code), position (bay code: A-01, Rampă 1, Atelier…) |
| **Destinație / Flow** | intended use | `Intern`, `AAP`, `Export`, `Expunere` — drives which checklist applies |
| **Checklist (per destinație)** | required steps before ready/handover | destinatie, items[] |
| **Program de îngrijire** | recurring custody care | name (Baterie 12V, Încărcare tracțiune), interval_days, unit (V, %), requires_measured_result, approval_state |
| **Mapping rule** | event → actions | trigger_code, actions (create/update), rev, mode (Simulare/Activ), is_active |
| **Intake event** (log) | every received event | order_ref, code, payload, event_ts/seq, received_at, result (created/updated/ignored-stale/duplicate) |
| **Vehicle history** (audit) | every state change | vehicle_id, event_type, old→new, actor, at |

### Enumerations (from the data)
- **Etapă Parc:** `În tranzit`, `În pregătire`, `În stoc`, `Expunere`.
- **Predare (readiness):** `În așteptare`, `Pregătit de predare`, `Blocat`, `Predat`.
- **Destinație:** `Intern`, `AAP`, `Export`, `Expunere`.
- **Task status (Kanban columns):** `De făcut`, `În lucru`, `Blocat`, `Finalizat`.
- **Task type:** `Recepție`, `Îngrijire`, `Programare`, `Documente`, `Predare`.
- **Responsabil (owner group):** `Logistică`, `Vânzări`, `Service` (+ named users).

---

## 4. Surfaces

### 4.1 Parc — one row per vehicle (flat register)
- **Columns:** Vehicul · Comandă · Locație · Poziție · Destinație · **Etapă Parc** · **Predare** · VIN. Compact, **sortable**.
- **Search:** VIN, order, model, or plate. **Filters:** locație, destinație, etapă, stare predare (readiness). `Resetează`.
- **Etapă Parc and Predare render as separate columns/badges** so "În stoc but Blocat for release" is visible at a glance.
- Row click → **Fișa mașinii** (detail: timeline/history, tasks, checklist, costs/care, documents). Back **restores filters + sort**.
- **Mobile:** `Vehicul` column stays pinned/visible; the rest scroll horizontally.

### 4.2 Kanban (Panou de lucru) — one card per task
- **Columns:** `De făcut` · `În lucru` · `Blocat` · `Finalizat` (with counts).
- **Card:** action · vehicle model · order ref · location + bay · responsabil · due time · type badge · `Mută` menu.
- **Create** tasks (`Activitate nouă`). **Drag** on desktop; **Mută** dropdown on mobile. **Search** by vehicle/order; **filter** by locație + responsabil.
- **Move rules (workflow gates — enforced, logged to history):**
  - → **Blocat** requires a **responsible person** for resolution **and a next action** (prototype shows "Vânzări · Solicită certificatul de conformitate").
  - **Recepție → Finalizat** opens **Confirmă recepția**; the task completes only after the operator confirms **VIN, actual location, bay, keys, condition** — which then populate the Vehicle's confirmed fields.
  - **Îngrijire / battery checks** require a **measured result** (e.g. 12 V reading, SoC %) before Finalizat.
  - Every move writes a **vehicle history** entry.

### 4.3 Azi — landing dashboard (stays the home page)
- Stat cards: `Activități de azi`, `Mașini în custodie`, `Programări azi`, `Mașini cu blocaje`.
- `Activitate în lucru` hero (continue current task) · `Agenda zilei` (today's tasks, tabs Toate/De făcut/În lucru/Blocat) · `Situația parcului` (etapă breakdown) · `Programări azi`.

### 4.4 Calendar
- Week/day view of `Rezervări, deplasări și disponibilitate`; appointments (e.g. `Recondiționare AAP · Service · Atelier`, `Programare RAR · Logistică · RAR`) tied to tasks; `Programare nouă`; resource filter.

### 4.5 Setări (admin)
- **Reguli** (mapping rules, versioned, Simulare/Activ) · **Sincronizare jarvis-alpha** (connection, published mapping, event log) · **Locații** (locations + positions/bays) · **Utilizatori** (users + roles) · **Checklisturi** (per destinație) · **Îngrijire** (custody care programs, intervals, approval).

---

## 5. Tech & deployment (decided)

- **Independent module inside the Flask JARVIS monolith** — `jarvis/logistics/` (mirrors `jarvis/carpark/`: `repositories/`, `routes/`, `services/`). Own schema `jarvis/migrations/domains/schema_logistics.py` (registered, `init_db()`-on-import, idempotent). React frontend under `jarvis/frontend/src/pages/Logistics/` + `jarvis/frontend/src/api/logistics.ts`. Blueprint prefix `/api/logistics/*`.
- **"Independent"** here means its **own schema and logic** (never writes other modules' tables), while **reusing shared plumbing**: Postgres (shared DB, `company_id`-scoped), auth + `role_permissions_v2` (`can_access_logistics`), Notifications (4-channel), Users, CRM/Invoices where linked.
- **jarvis-alpha feed** arrives at the Flask blueprint `POST /api/logistics/intake/events` (published rule map at `GET /api/logistics/intake/mapping`).
- **Testing:** pytest under `jarvis/tests/logistics/` — run with the **repo venv python**, never bare `python3` (circular-import trap).
- Deploys with the monolith (dev → staging → main FF-promotion). No separate service.

---

## 6. Phasing (each phase = its own plan)

1. **Spine (Plan #1, detailed):** schema + intake API (idempotent create, ETA update, stale-event guard) + Parc register + Kanban board + the three enforced move-gates + vehicle history. Proves the jarvis-alpha integration and satisfies the §2 acceptance test.
2. **Setări editors:** Reguli (rule builder + Simulare), Locații, Checklisturi, Utilizatori/roles, Sincronizare panel.
3. **Îngrijire scheduler:** recurring care programs (Baterie 12V/14z, Tracțiune/7z), measured-result capture, due alerts, approval.
4. **Azi dashboard + Calendar:** aggregates and appointments.
5. **Fișa mașinii:** full vehicle detail (timeline, documents, costs, care).

---

## 7. Decisions locked

- **Home:** independent module in the Flask JARVIS monolith (`jarvis/logistics/`) — §5. *(Decided 2026-11-27.)*
- **Execution:** subagent-driven (fresh implementer + fresh reviewer per task).
- **Handover (Predare):** separate axis from physical stage; always a manual employee action — §1.
