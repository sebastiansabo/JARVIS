# Public Test-Drive Booking — Design Spec

Date: 2026-09-22
Status: APPROVED 2026-09-22 (§13 defaults locked). Not implemented — implementation plan next.
Author: brainstorm + code-grounded pressure-test (see §11 for verification provenance).

## 1. Goal & scope

Let a marketing **event** publish a public, unauthenticated link where a
prospect picks a **specific car** and an available **time slot**, submits
name/phone/email, and receives an **email** confirm/cancel link. On confirm,
the system creates the existing operational record — a `foi_de_parcurs`
test-drive row in `PLANNED` status — assigned to a real consilier. Staff run
the drive at the event through the **existing** activation flow (signature,
GDPR, odometer, PDF).

This is **not** a booking engine. It is a thin public *slot layer* over the
`foi_de_parcurs` machinery. `foi_de_parcurs` stays the operational record; the
new `mkt_td_*` tables are public-facing inventory + booking audit.

### MVP scope (locked)

- **One event**, one company, one focused link. Leans on the existing HR-event
  ↔ marketing-project bridge (`event_id` → `mkt_project_id`).
- Customer picks a **specific car**.
- Consilier is set as a **per-car default** when staff add cars to the page,
  and can be **manually (re)assigned per planned session** afterward. Advisor
  resolves to a real `user_id` (fixes today's silent-no-push gap).
- Customer confirm/cancel is by **email link** (SMS deferred — see §9).

### Explicitly out of scope (YAGNI cuts, revisit later)

- Always-on / whole-fleet booking (no event anchor).
- SMS / WhatsApp channel (design keeps a provider-agnostic seam; §9).
- Staff "manual confirm" mode — the customer's email click *is* the
  confirmation.
- `form_id` extra-questions bridge (a JSONB column is reserved but unused).
- Per-car window overrides (windows are page-level in MVP).
- Access-code / invite-only gate (optional column reserved, not built).
- Any modification to `foi_de_parcurs` schema or an exclusion constraint on it
  (§4.2 explains why we avoid it).

## 2. Corrections to the original brainstorm (grounded in code)

The pressure-test found the original doc understated the work in specific ways.
This spec supersedes it. Key corrections carried through the design:

| Original claim | Reality (verified) | Design consequence |
|---|---|---|
| TD row = `PLANNED` | `PLANNED` only for a **draft**; a *live* submit lands as `FILLED` and fires PDF + real customer email | Public bookings create the FP row as `PLANNED` only; signature/PDF/email stay with staff activation. |
| `find_conflicts` is the guard | It is a non-locking `SELECT` **and is not called in the TD insert transaction at all** | We add our own race guard (§4) and re-check availability at commit. |
| No-show cron: 8h grace, pushes consilier | Grace is **6h** (`GRACE_HOURS`); advisor resolved by `LOWER(users.name)=LOWER(advisor_name)`, **no `user_id` FK** — push **silently drops** if the name doesn't match | We assign a real user and set `advisor_name = users.name` so the existing cron notifies. |
| Forms module refuses `test-drive` slug | Only a **comment + no-op**; a `test-drive` slug form would be publicly submittable | We do **not** reuse Forms tables; we build a dedicated public blueprint. |
| Reuse public rate limiter | It is a **per-worker in-memory dict**, resets on deploy, IP from **spoofable** `X-Forwarded-For` | We add a **DB-backed** rate limit (§7). |
| Reuse action tokens for customers | Built for **internal approver user-ids** gated by `ApprovalEngine` | We add a dedicated **booking** token (§5) for external customers. |
| CRM `find_by_phone` / `create_from_form` | **Exact** phone match, no normalization; `crm_clients` is **global, no `company_id`** | Normalize to E.164 before lookup; treat client as global (existing behavior). |
| `send_email` reaches customers | Yes (plain `smtplib`), but appends `global_cc` unless `skip_global_cc=True` | Customer emails set `skip_global_cc=True`. |

## 3. Architecture overview

Units, each with one purpose and a defined interface:

```
Staff (authed)                         Public (anonymous)
──────────────                         ──────────────────
Booking-page admin  ──creates──▶  mkt_td_booking_pages
  add cars + advisor ──▶ mkt_td_booking_cars (default_advisor_user_id)
  set hours          ──▶ mkt_td_booking_windows
        │
        ▼  slot materialization service
   mkt_td_slots  (pre-materialized grid, per car × window)
        │                                   ▲
        │                          GET /api/td/pages/<slug>  (avail = slots
        │                            filtered by live 3-way check, §4.3)
        │                                   │
        │                          POST …/bookings  ──▶ mkt_td_bookings
        │                            (status=pending_confirm, slot_id,
        │                             partial-unique race guard §4.1)
        │                                   │ send email (skip_global_cc)
        │                                   ▼
        │                          GET/POST /td/confirm?token=…
        │                            advisory lock + 3-way recheck (§4.3)
        │                                   │
        └──────────────────────────▶  foi_de_parcurs (route_type='TD',
                                          status='PLANNED', advisor_name=user.name)
                                            │
   Staff Hub: reassign advisor,            │  existing no-show cron (6h grace),
   run activation (existing flow) ◀────────┘  existing activate route
```

New backend units:
- `marketing/repositories/td_booking_repository.py` — CRUD for the `mkt_td_*`
  tables + the partial-unique claim.
- `marketing/services/td_slot_service.py` — materialize slots, compute live
  availability (the 3-way reconciliation).
- `marketing/services/td_booking_service.py` — submit / confirm / cancel
  orchestration (the session-less create path).
- `core/approvals/booking_token.py` — signed customer confirm/cancel token.
- `core/messaging/` — provider-agnostic `send_customer_message()` seam (email
  today; SMS adapter later).
- `foi_parcurs` reuse: `FoiParcursRepository.create_from_td_form`,
  `find_conflicts`, `get_open_session`; `VehicleRepository.get_lock_by_vin`.

New public blueprint: `marketing/routes/td_public.py` (NO `@login_required`).
New staff routes: `marketing/routes/td_admin.py`
(`@v2_permission_required('marketing', …)`).

New frontend: public route `/td/:slug` (outside the auth shell, mirroring
`/f/:slug`) → `PublicTdBooking.tsx`; staff config UI inside the marketing module.

## 4. The hard part: race safety & availability

### 4.1 Public-vs-public race — partial unique index

Slots are **pre-materialized** rows in `mkt_td_slots`. A booking references a
slot. The race guard is a **partial unique index** on the booking:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_mkt_td_active_booking_per_slot
  ON mkt_td_bookings (slot_id)
  WHERE status IN ('pending_confirm', 'confirmed');
```

Two prospects submit the same slot in the same second → both `INSERT` →
Postgres serializes; one wins, the other raises `UniqueViolation` (SQLSTATE
23505) → the route returns **409 "slot just taken"**. On cancel/expire the
booking leaves the active set, so the index frees the slot for rebooking.
No application-level check-then-insert window.

### 4.2 Why NOT an exclusion constraint on `foi_de_parcurs`

`btree_gist` is installed and an `EXCLUDE USING gist` would be the textbook
non-overlap guard. We deliberately avoid it here because:
1. `foi_de_parcurs` almost certainly **already contains overlapping rows**
   (nothing has ever prevented them) — adding the constraint would **fail** to
   create against existing data.
2. `foi_de_parcurs` DDL is in the **protected** `migrations/domains/` set.
3. It would only cover `route_type='TD'` rows unless broadened, and broadening
   risks staff workflows.

The partial-unique-on-a-new-table approach gets the same safety without
touching the operational table.

### 4.3 Cross-system availability — the 3-way reconciliation

A slot can be free in `mkt_td_slots` yet the car actually busy in
`foi_de_parcurs` (a colleague booked it manually, or it's locked/blocked).
Availability for a car+time is the **AND of three existing checks**:

1. `FoiParcursRepository.find_conflicts(vin, frm, to)` — overlapping open TD
   sessions (already excludes `MISSED` and past-6h-grace `PLANNED`).
2. `VehicleRepository.get_lock_by_vin(vin)` — manual lockout ∪ active
   scheduled-block window (`fp_vehicle_blocks`).
3. `FoiParcursRepository.get_open_session(vin)` — the single-open-session rule.

Plus a `min_lead_minutes` floor and the slot being unbooked. This runs in
**two** places:
- **At read time** (`GET …/pages/<slug>`): filter the materialized slot grid so
  the public only sees genuinely-free slots.
- **At confirm time**, inside a **per-VIN advisory lock**
  (`pg_advisory_xact_lock(hashtext(vin))`), re-run all three immediately before
  inserting the `foi_de_parcurs` row. If the car became unavailable, fail the
  confirm gracefully (booking → `conflict`, notify staff, offer rebook). The
  advisory lock serializes the public confirm against a concurrent staff insert
  on the same VIN.

## 5. Booking lifecycle & token flow

Status machine on `mkt_td_bookings.status`:

```
                 submit                 email click (confirm)
   (none) ─────────────▶ pending_confirm ─────────────▶ confirmed ──▶ (staff activation → FILLED → COMPLETED, existing flow)
                              │  │                          │
              expires_at ◀────┘  └───── email click (cancel)│──── cancel ──▶ cancelled
              (cleanup task)        cancel ─────────────────┘
                    │                                         │
                    ▼                                         ▼
                 expired                                   cancelled
             (slot freed)                            (slot freed + FP row hard-deleted if PLANNED)
```

Key timing decisions:
- The **`foi_de_parcurs` row is created at confirm**, not at submit. Unconfirmed
  / spam bookings never touch the operational table; they just hold a slot until
  `expires_at`, then a cleanup task releases them.
- The email click is **loose ownership proof** for the contact channel.

**Token** (`core/approvals/booking_token.py`) mirrors the proven
`action_token.py` pattern (`itsdangerous.URLSafeTimedSerializer`,
`current_app.secret_key`):
- `make_booking_token(booking_id, action)` — `action ∈ {'confirm','cancel'}`,
  salt `'td-booking-action'`.
- `read_booking_token(token, max_age)` — `max_age` = time until slot start (cap
  a few days). Expired/forged → 410.
- **GET renders a confirm page (never mutates)** — mail-scanner-safe, mirroring
  the existing deeplink pattern. **POST mutates.**

## 6. Data model (all in `migrations/domains/schema_marketing.py`)

New `mkt_td_*` tables. Prefix verified free (no collision). Conventions copied
from existing `mkt_*` tables: `SERIAL PRIMARY KEY`, inline `REFERENCES`,
named `CHECK`/`UNIQUE`, `created_at/updated_at/deleted_at`, `IF NOT EXISTS`,
separate `CREATE INDEX` statements, partial indexes `WHERE deleted_at IS NULL`.
`foi_de_parcurs` is **not** altered.

### mkt_td_booking_pages
| column | type | notes |
|---|---|---|
| id | SERIAL PK | |
| project_id | INT REFERENCES mkt_projects(id) ON DELETE CASCADE | the marketing project |
| company_id | INT NOT NULL REFERENCES companies(id) | the session's company; **server-bound** |
| event_id | INT REFERENCES hr.events(id) | prefills date range; tags every FP row |
| slug | TEXT UNIQUE NOT NULL | public URL `/td/<slug>` |
| status | TEXT DEFAULT 'draft' CHECK IN ('draft','open','closed') | |
| opens_at, closes_at | TIMESTAMPTZ | registration window |
| min_lead_minutes | INT DEFAULT 120 | hide slots sooner than this |
| slot_minutes | INT DEFAULT 30 | default slot length |
| buffer_minutes | INT DEFAULT 0 | gap between slots |
| max_bookings_per_contact | INT DEFAULT 1 | anti-hoarding (by phone+email) |
| access_code | TEXT NULL | reserved, unused in MVP |
| title, intro, thank_you | TEXT | public copy |
| notify_user_ids | INT[] DEFAULT '{}' | staff emailed on each booking |
| created_by | INT REFERENCES users(id) | |
| created_at, updated_at, deleted_at | TIMESTAMPTZ | |

### mkt_td_booking_cars
| column | type | notes |
|---|---|---|
| id | SERIAL PK | |
| page_id | INT NOT NULL REFERENCES mkt_td_booking_pages(id) ON DELETE CASCADE | |
| vehicle_id | INT | fp_vehicles.id (advisory; fp_vehicles not FK-clean) |
| vin | TEXT NOT NULL | the identity `find_conflicts` keys on |
| default_advisor_user_id | INT REFERENCES users(id) | **per-car default consilier** |
| sort_order | INT DEFAULT 0 | |
| is_active | BOOLEAN DEFAULT TRUE | |
| created_at, updated_at | TIMESTAMPTZ | |
| UNIQUE (page_id, vin) | | one entry per car per page |

### mkt_td_booking_windows
| column | type | notes |
|---|---|---|
| id | SERIAL PK | |
| page_id | INT NOT NULL REFERENCES mkt_td_booking_pages(id) ON DELETE CASCADE | |
| window_date | DATE NOT NULL | a day within the event |
| start_time, end_time | TIME NOT NULL | opening hours that day |
| slot_minutes | INT NULL | optional override of page default |
| created_at | TIMESTAMPTZ | |

### mkt_td_slots (pre-materialized grid)
| column | type | notes |
|---|---|---|
| id | SERIAL PK | |
| page_id | INT NOT NULL REFERENCES mkt_td_booking_pages(id) ON DELETE CASCADE | |
| car_id | INT NOT NULL REFERENCES mkt_td_booking_cars(id) ON DELETE CASCADE | |
| vin | TEXT NOT NULL | denormalized for fast availability checks |
| starts_at, ends_at | TIMESTAMPTZ NOT NULL | |
| status | TEXT DEFAULT 'open' CHECK IN ('open','blocked') | display hint only; truth = bookings + live 3-way |
| created_at | TIMESTAMPTZ | |
| UNIQUE (car_id, starts_at) | | idempotent re-materialization |

### mkt_td_bookings
| column | type | notes |
|---|---|---|
| id | SERIAL PK | |
| page_id | INT NOT NULL REFERENCES mkt_td_booking_pages(id) | |
| slot_id | INT NOT NULL REFERENCES mkt_td_slots(id) | |
| car_id | INT NOT NULL REFERENCES mkt_td_booking_cars(id) | |
| customer_name | TEXT NOT NULL | |
| customer_phone_e164 | TEXT NOT NULL | normalized before store |
| customer_email | TEXT NOT NULL | confirm channel |
| crm_client_id | INT NULL | set at confirm (find-or-create) |
| foi_de_parcurs_id | INT NULL | set at confirm; the operational record |
| advisor_user_id | INT REFERENCES users(id) | car default, staff-overridable |
| status | TEXT DEFAULT 'pending_confirm' CHECK IN ('pending_confirm','confirmed','cancelled','expired','conflict','completed','no_show') | |
| expires_at | TIMESTAMPTZ NOT NULL | pending_confirm TTL |
| confirmed_at, cancelled_at | TIMESTAMPTZ | |
| extra_answers | JSONB DEFAULT '{}'::jsonb | reserved (form bridge), unused MVP |
| utm | JSONB DEFAULT '{}'::jsonb | captured + sanitized |
| ip, user_agent | TEXT | abuse forensics |
| created_at, updated_at | TIMESTAMPTZ | |

Indexes: `uq_mkt_td_active_booking_per_slot` (partial, §4.1);
`idx_mkt_td_bookings_page`, `_status`, `_contact (customer_phone_e164, customer_email)`
for rate limiting; `idx_mkt_td_slots_page_car`, `_starts_at`.

## 7. Public endpoint hardening

The public blueprint is genuinely anonymous — none of the trust the existing
`@login_required` route relied on is present, so:

- **Server-bind everything from the slug.** `company_id`, the allowed car set,
  and the advisor come from `mkt_td_booking_pages` / `mkt_td_booking_cars` rows
  looked up by slug — **never** from the request body. The body carries only
  contact fields and a chosen `slot_id` (validated to belong to the page).
- **DB-backed rate limit** replacing the in-memory dict: count
  `mkt_td_bookings` by `(customer_phone_e164, customer_email)` and by `ip` in a
  rolling window, plus enforce `max_bookings_per_contact`. Durable across
  workers and deploys.
- **Registration window & lead time:** reject submits when the page is not
  `open` or outside `[opens_at, closes_at]`, or when the slot is under
  `min_lead_minutes`.
- **Sanitize** free-text (reuse the `html.escape` approach from
  `form_service._sanitize_answers`) and **filter UTM** to a tracked allowlist.
- **Phone normalization to E.164** before `crm.find_by_phone` (reuse the
  existing foi_parcurs phone country-code → E.164 normalizer) so dedup works.
- **Customer emails**: `send_email(..., skip_global_cc=True)`.

## 8. Endpoints

Public (`marketing/routes/td_public.py`, no auth):
- `GET  /api/td/pages/<slug>` → page config + cars + **available** slots
  (materialized grid filtered by the live 3-way check + lead time + open
  bookings).
- `POST /api/td/pages/<slug>/bookings` → validate, rate-limit, insert
  `pending_confirm` booking under the partial-unique guard, send confirm email.
  Returns 201 (check-your-email) / 409 (slot taken) / 422 / 429.
- `GET  /td/confirm?token=…`, `POST /api/td/bookings/confirm` → confirm page +
  mutation (advisory lock + 3-way recheck + create FP `PLANNED`).
- `GET  /td/cancel?token=…`, `POST /api/td/bookings/cancel` → cancel page +
  mutation (soft-cancel + hard-delete PLANNED FP row).

Staff (`marketing/routes/td_admin.py`, `@v2_permission_required('marketing', …)`):
- CRUD booking pages; add/remove cars with `default_advisor_user_id`; define
  windows; `open`/`close` a page; trigger slot (re)materialization.
- List bookings for a page; **reassign advisor** on a session (updates
  `mkt_td_bookings.advisor_user_id` **and** `foi_de_parcurs.advisor_name` so the
  no-show cron notifies the right user).

Also register CORS/allow-methods for any new methods (mobile CORS gotcha noted
in project memory — not mobile here, but the same app-level allow-list applies).

## 9. Notification channel (email now, SMS-ready)

`core/messaging/send_customer_message(contact, subject, body_html, body_text)`
is a thin seam. MVP implementation = `send_email(..., skip_global_cc=True)`.
The seam exists so an SMS/WhatsApp adapter can be dropped in later without
touching the booking service. **There is no SMS provider in JARVIS today** —
adding one is net-new infra (provider account, credentials, sender-ID, cost);
deferred by decision.

Staff notification on each booking reuses `notify_with_push(notify_user_ids,…)`
and/or an internal `send_email`. The **advisor** is notified through the
existing no-show cron because we set `advisor_name = users.name` for a real
user; optionally push immediately on confirm too.

## 10. Cancel & deletion model

- Customer cancel (or staff cancel): set `mkt_td_bookings.status='cancelled'`,
  `cancelled_at=now` — **fully audited in the new table**.
- If a `foi_de_parcurs` PLANNED row was already created (post-confirm),
  hard-`DELETE` it via the existing `delete_contract` primitive — mirroring the
  existing PLANNED-only discard route. (There is no soft-delete on
  `foi_de_parcurs`; we accept parity with current behavior and keep the audit
  trail on `mkt_td_bookings`.)
- The partial-unique index frees the slot automatically once the booking leaves
  the active set.
- A small cleanup task expires `pending_confirm` bookings past `expires_at`
  (frees their slots). The existing 6h-grace no-show cron already handles
  confirmed-but-no-show TD rows correctly (no `created_by` dependency).

## 11. Testing

- **Unit:** slot materialization skips busy/locked slots (mock the 3-way
  check); availability filter; `booking_token` make/read incl. expiry &
  tamper; phone→E.164; rate-limit counting.
- **Integration (DB):**
  - Concurrent double-submit on one slot → exactly one 201, one 409
    (two threads / two connections; assert the partial-unique guard).
  - Confirm creates a `foi_de_parcurs` row with `route_type='TD'`,
    `status='PLANNED'`, `advisor_name` matching the car's default user.
  - Cancel deletes the PLANNED FP row and frees the slot (rebook succeeds).
  - Confirm when the car went busy (seed a conflicting FP row) → booking
    `conflict`, no FP row created.
  - Expired `pending_confirm` → slot freed by cleanup task.
- **Security:** body cannot override `company_id`/car/advisor; page-closed and
  out-of-window submits rejected; rate limit trips.

## 12. Provenance (what was verified against code)

Every claim in §2 and the reuse surfaces were verified read-only in
`JARVIS/jarvis` on 2026-09-22. Anchors:
`foi_parcurs/routes/test_drive.py` (create `:163`, activate `:472`),
`foi_parcurs/repositories/foi_parcurs_repository.py` (`find_conflicts` `:772`,
`create_from_td_form` `:476`, `delete_contract` `:370`, `get_open_session`
`:802`), `foi_parcurs/session_lifecycle.py` (`GRACE_HOURS=6` `:12`),
`tasks/foi_parcurs_sessions.py` (no-show + name-match push),
`foi_parcurs/repositories/vehicle_repository.py` (`get_lock_by_vin` `:379`),
`core/services/notification_service.py` (`send_email` `:70`, `is_smtp_configured`
`:57`, `global_cc` `:133`), `core/approvals/action_token.py`,
`core/deeplink/routes.py`, `forms/routes/public.py` (in-memory rate limiter),
`forms/services/form_service.py` (`_sanitize_answers`, test-drive no-op comment),
`crm/repositories/client_repository.py` (`find_by_phone` exact `:89`,
`create_from_form` `:311`), `migrations/domains/schema_marketing.py`
(`mkt_projects` `:11`, conventions), `migrations/domains/schema_incremental.py`
(`foi_de_parcurs` cols; `mkt_project_id`/`event_id` plain BIGINT; `btree_gist`
`:3518`), `migrations/domains/schema_hr.py` (`hr.events` `:124`),
`marketing/repositories/event_repo.py` (`create_event_project` `:23`),
`foi_parcurs/routes/test_drive.py` (`_ensure_event_project` `:74`).

## 13. Resolved defaults (locked 2026-09-22)

Left open at draft, now fixed. Each is overridable during plan review.

1. **Rate limits:** page `max_bookings_per_contact` default **1**; global guard
   **3 pending/confirmed bookings per contact (phone+email) per rolling 24h**
   and **8 submit attempts per IP per rolling hour**.
2. **TTLs:** `pending_confirm` `expires_at` = **45 minutes**. Confirm-token
   `max_age` = **min(time-until-slot-start, 7 days)**; cancel-token valid until
   slot start.
3. **Admin home:** the booking-page admin lives in the **Driving Hub / Foi de
   Parcurs module** (it already owns vehicles, advisors, the calendar). The
   marketing project/event is referenced via `event_id`, not managed there.
4. **Advisor visibility:** the consilier is **not shown on the public page** —
   surfaced to staff only.
5. **Vehicle identity:** cars are keyed by **`vin`**; adding a car to a page
   **requires a non-empty VIN** on its `fp_vehicles` row (block otherwise).
```
