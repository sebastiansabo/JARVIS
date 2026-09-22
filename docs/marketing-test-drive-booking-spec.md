# Marketing Projects: Public Test-Drive Booking (design + brainstorm)

Status: proposal, not implemented. Date: 2026-09-22.

## 1. Verdict

Do not build a booking system. Build a thin public "slot layer" on top of what already exists.

Roughly 70% of the machinery is already in Jarvis and battle-tested:

| Need | Already exists | Where |
|---|---|---|
| Test-drive session with car, client, advisor, time, project, event | `foi_de_parcurs` rows, `route_type='TD'`, `status='PLANNED'`, columns `mkt_project_id`, `event_id`, `advisor_name`, `departure_datetime`, `return_datetime` | `foi_parcurs/routes/test_drive.py`, `migrations/domains/schema_incremental.py` |
| Car pool for test drives with lockouts and scheduled blocks | `fp_vehicles`, `fp_vehicle_blocks`, `lockout_*` | `foi_parcurs/repositories/vehicle_repository.py` |
| Car/time conflict detection | `FoiParcursRepository.find_conflicts(vin, frm, to)` | `foi_parcurs/repositories/foi_parcurs_repository.py:773` |
| No-show handling, advisor nudges | lifecycle cron flips PLANNED to MISSED after 8h grace, pushes the consilier | `tasks/foi_parcurs_sessions.py` |
| Staff calendar per car (day, week, month) | `CalendarTab` + shared `TimeGrid` | `frontend/src/pages/FoiParcurs/CalendarTab.tsx` |
| Activation at the event: signature, GDPR, odometer, PDF | `PUT /api/foi-parcurs/test-drive/<id>/activate` | `foi_parcurs/routes/test_drive.py:472` |
| HR event to marketing project bridge | `ProjectEventRepository.create_event_project`, `_ensure_event_project` | `marketing/repositories/event_repo.py` |
| Public, unauthenticated submit with rate limit, sanitizer, UTM capture | forms public routes | `forms/routes/public.py`, `forms/services/form_service.py` |
| Public React route outside the auth shell | `/f/:slug` | `frontend/src/App.tsx:175` |
| CRM client find-or-create from a form | `ClientRepository.find_by_phone`, `create_from_form` | `crm/repositories/client_repository.py` |
| Per-company GDPR text | `companies.gdpr_text` | `schema_core.py` |
| Signed one-click links in email (no login) | `make_action_token` / `read_action_token` | `core/approvals/action_token.py`, `core/deeplink/routes.py` |
| Email + push | `send_email`, `notify_with_push` | `core/services/notification_service.py`, `core/notifications/notify.py` |

What is missing, and is the actual work:

1. A **bookable inventory** concept: which cars, which days, which hours, which consilier, tied to a project. Today a session is created by staff one at a time.
2. A **public write path** into `foi_de_parcurs`. The create route is `@login_required` and reads `current_user`. The creation logic must be extracted into a service callable without a session.
3. A **race-safe slot guard**. `find_conflicts` is an application-level check. Two external people submitting the same slot within the same second will both pass it. Public traffic needs a database uniqueness constraint.
4. A **self-service confirm/cancel** flow for the external person.
5. Advisor identity. `advisor_name` is a free string. Bookings need a `user_id` so the consilier gets pushed, and so capacity per consilier can be enforced.

## 2. Why not the Forms module

Forms stores schemaless answer bags. It has no inventory, no uniqueness, no time. Its own code explicitly refuses the `test-drive` slug (`form_service._run_post_submit_hooks`). Reuse its patterns (IP rate limiter, `_sanitize_answers`, UTM filtering, `PublicForm.tsx` shell), not its tables.

One optional bridge: a booking page may reference a `form_id` for extra questions. The public page renders that schema with `FormRenderer` and stores the answers in `mkt_td_bookings.extra_answers`. That keeps "what do we ask" configurable without touching the booking core.

## 3. Data model

All new tables are marketing-owned (`mkt_` prefix) and live in `migrations/domains/schema_marketing.py`. A `foi_de_parcurs` session stays the operational record. The booking tables are the public-facing inventory and the audit of who booked what.

```
mkt_projects 1 ── n mkt_td_booking_pages 1 ── n mkt_td_booking_cars 1 ── n mkt_td_slots 1 ── 0..1 mkt_td_bookings 1 ── 1 foi_de_parcurs
                                          1 ── n mkt_td_booking_windows
```

### mkt_td_booking_pages (the "open link")

| column | notes |
|---|---|
| id, project_id FK mkt_projects, company_id FK companies | one company per page; the session's `company_id` comes from here |
| event_id FK hr.events NULL | optional; prefills date range and tags every session with `event_id` |
| slug TEXT UNIQUE | public URL `/td/<slug>` |
| status | `draft`, `open`, `closed` |
| opens_at, closes_at TIMESTAMP | registration window. Outside it the page renders "closed" |
| min_lead_minutes INT default 120 | slots starting sooner than this are hidden |
| slot_minutes INT default 30, buffer_minutes INT default 0 | defaults for windows |
| max_bookings_per_phone INT default 1 | anti-hoarding |
| access_code TEXT NULL | optional invite-only gate |
| confirm_mode | `auto` (booked = confirmed) or `manual` (staff confirms; slot held) |
| require_license BOOLEAN | ask for licence number on the public form |
| form_id FK forms NULL | optional extra questions |
| title, intro, thank_you, branding JSONB | public copy |
| notify_user_ids INT[] | staff to email on each booking |
| created_by, created_at, updated_at, deleted_at | |

### mkt_td_booking_cars

| column | notes |
|---|---|
| id, page_id FK | |
| fp_vehicle_id FK fp_vehicles | the pool that sessions require. `carpark_vehicles` is stock, not the demo fleet |
| display_name, photo_url, description | public-facing; never expose VIN or plate |
| sort_order, is_active | |
| UNIQUE (page_id, fp_vehicle_id) | |

### mkt_td_booking_windows

Staff intent: "Car X, Saturday 10:00 to 17:00, 30-minute slots, consilier Y."

| column | notes |
|---|---|
| id, page_id FK, car_id FK NULL | NULL car means every active car on the page |
| day DATE, start_time TIME, end_time TIME | |
| slot_minutes, buffer_minutes NULL | override page defaults |
| advisor_user_id FK users NULL | consilier for slots generated from this window |
| capacity INT default 1 | reserved for a future "2 people per slot" case; v1 keeps 1 |

### mkt_td_slots (materialized)

Generated from windows on save. Regeneration is idempotent and never deletes a slot that has a booking.

| column | notes |
|---|---|
| id, page_id FK, car_id FK, window_id FK | |
| starts_at, ends_at TIMESTAMP | Bucharest wall clock, naive, same convention as `foi_de_parcurs` |
| advisor_user_id FK users NULL | copied from window |
| status | `open`, `held`, `booked`, `blocked` |
| booking_id FK mkt_td_bookings NULL | |
| UNIQUE (car_id, starts_at) | the race guard |

Why materialize: a `UNIQUE` row plus `SELECT ... FOR UPDATE` is the only race-safe guard. Computing slots on the fly from windows leaves the double-booking check in Python.

### mkt_td_bookings

| column | notes |
|---|---|
| id, page_id FK, slot_id FK UNIQUE | |
| fp_session_id FK foi_de_parcurs NULL | set when the PLANNED session is created |
| crm_client_id FK crm_clients | find by phone, else create |
| name, phone (E.164), email, license_number NULL | snapshot |
| gdpr_consent_at, gdpr_text_hash, marketing_consent BOOLEAN | consent evidence with text version |
| extra_answers JSONB | from optional form |
| utm JSONB, ip INET, user_agent | |
| status | `pending`, `confirmed`, `cancelled`, `no_show`, `completed` |
| cancel_token TEXT UNIQUE | random 32 bytes, hashed at rest |
| created_at, confirmed_at, cancelled_at, cancelled_by (`client`, `staff`, `system`) | |

## 4. Flows

### Staff (marketing user), inside the project

1. Open project, new tab **Test Drive** in `pages/Marketing/ProjectDetail.tsx` next to Events.
2. Create booking page. If the project has a linked HR event, dates prefill from it and `event_id` is set.
3. Add cars from the company's `fp_vehicles` pool (`document_type='sales'`, active, not archived). Cars locked or blocked for the event dates show a warning and are excluded from generation.
4. Add windows per car or for all cars. Pick a consilier per window from the users directory (same source as `FoiParcurs/useUsersDirectory.ts`). Optionally restrict to project members.
5. Save generates slots. The grid shows per car per day: open, booked (name), blocked (staff session or vehicle block).
6. Publish sets `status='open'`. Copy link, QR code for the stand.
7. Bookings list with confirm, cancel, reassign consilier, and a link to the session in Foi de Parcurs.

### External person

1. `GET /td/<slug>` renders the page (public React route next to `/f/:slug`).
2. Pick a car. `GET .../availability?car_id=&day=` returns slots with `open|taken` only. Never names.
3. Pick a slot, fill name, phone, email, GDPR checkbox, optional licence, optional extra form.
4. `POST .../book`. On success: thank-you page, email with details, ICS attachment and a cancel link.
5. Cancel link: `GET /td/cancel?token=` with a confirm page, then `POST`. Frees the slot and cancels the PLANNED session.

### Server, on book (single transaction)

1. Rate limit by IP (reuse `forms/routes/public.py` limiter). Honeypot field must be empty.
2. Validate page is `open`, now inside `[opens_at, closes_at]`, project status `active`, event not ended.
3. Validate phone against the existing `_PHONE_RE`, email format, GDPR checked.
4. `SELECT ... FROM mkt_td_slots WHERE id=%s FOR UPDATE`. Require `status='open'`, `starts_at > now + min_lead`.
5. Cross-check `find_conflicts(vin, starts_at, ends_at)` and vehicle lock/blocks. This catches a staff session created in Foi de Parcurs on the same car outside the slot grid.
6. Count bookings for this phone on this page. Reject over `max_bookings_per_phone`.
7. `crm_clients`: `find_by_phone`, else `create_from_form`.
8. Insert `mkt_td_bookings`, update slot to `booked`.
9. Create the PLANNED session through a new `foi_parcurs/services/session_service.create_planned_td(...)` extracted from the route body (lines 300 to 430 of `test_drive.py`). Payload: `company_id`, `vin`, `client_id`, `departure_datetime`, `return_datetime = starts_at + slot_minutes`, `advisor_name` resolved from `advisor_user_id`, `mkt_project_id`, `event_id`, `source='public_booking'`, `gdpr_consent=True`.
10. Commit. Then, outside the transaction: email the client, `notify_with_push` the consilier, email `notify_user_ids`, log `mkt_project_activity` (`td_booked`).

Unique violation or conflict at step 4 or 5 returns 409 with "slot just taken" and the client refreshes availability.

### Keeping booking and session in sync

Session is the source of truth for what happened. Booking mirrors it:

| session event | booking |
|---|---|
| activated (FILLED) | `confirmed` stays; show "arrived" |
| returned (COMPLETED) | `completed` |
| cron flips to MISSED | `no_show`, slot freed only if the page is still open and slot is still in the future (it never is, so slot stays `booked` for history) |
| staff deletes PLANNED draft | `cancelled` by staff, slot `open` |
| staff reschedules session | booking keeps `slot_id`; slot flagged `moved`, availability recomputed from session times |

Implement as small hooks in the existing routes (`delete`, `reschedule`, `activate`, `return`) guarded by `source='public_booking'`, plus a nightly reconcile in `tasks/foi_parcurs_sessions.py`.

## 5. The "certain conditions" gate, explicit

A slot is bookable only when all of these hold:

- page `status='open'` and now within `opens_at..closes_at`
- project `status='active'` (pausing the project closes the link)
- HR event, if set, has not ended
- car is active on the page, not locked, not inside an active `fp_vehicle_blocks` window
- slot `status='open'`, `starts_at >= now + min_lead_minutes`
- `find_conflicts` returns nothing for the car and time
- phone under `max_bookings_per_phone` for this page
- `access_code` matches, when set

Everything else (which cars, which hours, which consilier) is data on the page, so marketing changes it without a deploy.

## 6. Where it lives

Backend, all under `jarvis/marketing/`:

- `repositories/td_booking_repo.py` (pages, cars, windows, slots, bookings; slot generation)
- `services/td_booking_service.py` (gate checks, book transaction, cancel, sync hooks, notifications)
- `routes/td_booking_admin.py` (login + `mkt_permission_required('project','edit')`)
- `routes/td_booking_public.py` (no auth; mounted at `/marketing/public/td/...`, mirrors `forms/routes/public.py`)
- `foi_parcurs/services/session_service.py`: `create_planned_td()` extracted from the route so both the route and the booking service call it

Frontend:

- `pages/Public/TestDriveBooking.tsx` at route `/td/:slug` (add next to `/f/:slug` in `App.tsx`)
- `pages/Marketing/tabs/TestDriveTab.tsx` (page config, cars, windows, slot grid, bookings)
- `api/marketing.ts` and `types/marketing.ts` additions

Schema: append to `migrations/domains/schema_marketing.py`. No changes to `foi_de_parcurs` except allowing `source='public_booking'` if a check constraint exists.

Permissions: reuse `marketing.project.edit` for config and `marketing.project.view` for reading bookings. A dedicated `td_booking` entity can be seeded later if a narrower role is needed.

## 7. KPIs for the project

The Marketing module already has `mkt_kpi_definitions` and deal sources. Add a `td_bookings` source that computes per project:

- bookings created
- confirmed
- showed (session reached FILLED)
- completed
- converted (session `led_to_sale` or a CRM deal on the client within 90 days)

This makes the event measurable inside the same project that paid for it.

## 8. Brainstorm: options beyond v1

- **Kiosk mode.** Same public page with `?kiosk=1`: no email, big buttons, resets after submit. A tablet at the stand becomes a walk-in register.
- **QR per car.** `/td/<slug>?car=<id>` printed on the windscreen card. Scanning lands directly on that car's slots.
- **Waitlist.** When a car is full, collect phone and notify on cancellation. Cheap once the cancel hook exists.
- **Round-robin consilier.** Windows with no advisor pick the project member with the fewest bookings that day.
- **Manual confirm mode.** Slot held for 24h, staff confirms or releases. Useful for VIP events.
- **Reminder.** T-24h and T-2h email via the existing scheduler. SMS has no provider in Jarvis today, so email or nothing in v1.
- **Consilier calendar.** Push confirmed sessions to Google Calendar via the existing connector layer.
- **Multi-event reuse.** "Duplicate page" copies cars and windows shifted to new dates.
- **Deposit or card hold.** Out of scope; no payment provider in the platform.

## 9. Risks and decisions taken

- **Timezone.** `foi_de_parcurs` stores Bucharest wall clock as naive timestamps. Slots use the same convention. Do not introduce UTC here.
- **Privacy on the public API.** Availability returns only times and a boolean. Car list returns `display_name` and photo, never VIN or plate.
- **Consent evidence.** Store the GDPR text hash and timestamp and IP on the booking. The company text lives in `companies.gdpr_text`.
- **Abuse.** IP limiter, honeypot, phone uniqueness per page. Add Cloudflare Turnstile behind an env flag only if abuse appears; do not block v1 on it.
- **Advisor as string.** Bookings and slots carry `advisor_user_id`; the session gets `advisor_name` resolved from `users.name`. This is the same mapping the existing form does.
- **Staff bookings off-grid.** A consilier can still create a session for the same car in Foi de Parcurs. Step 5 of the book transaction respects that. The reverse direction (staff session created while a public booking exists) is already protected by `find_conflicts` in the existing route.

## 10. Delivery plan

| phase | scope | estimate |
|---|---|---|
| 0 | Extract `create_planned_td()` service from the route, keep route behavior identical, tests | 0.5 day |
| 1 | Schema, repo, slot generation, admin routes, TestDriveTab (cars, windows, slot grid, publish) | 2 days |
| 2 | Public route + page, book transaction, email with cancel link, consilier push, activity log | 2 days |
| 3 | Sync hooks (delete, reschedule, activate, return, MISSED), bookings list actions, KPI source | 1 day |
| 4 | QR, kiosk mode, duplicate page, reminders | 1 day |

Total v1 (phases 0 to 3): about 5.5 working days.

## 11. Open decisions for the owner

1. `confirm_mode` default: `auto` is recommended. Manual confirm halves conversion at events.
2. One booking per phone per page, or per car per page? Recommended: per page. People who want two cars talk to the consilier.
3. Should the public page require an `access_code` for closed events? Field is in the schema either way; default off.
