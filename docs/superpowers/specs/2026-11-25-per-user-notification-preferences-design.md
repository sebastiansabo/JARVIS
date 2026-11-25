# Per-User Notification Preferences — Multi-Channel Design

**Date:** 2026-11-25
**Status:** Awaiting approval (revised for 4-channel delivery)
**Module:** `jarvis/core/notifications`

## Intent & why

Today JARVIS has **no per-user notification preference**. The central helpers
`notify_user` / `notify_users` / `notify_with_push` / `notify_node_cascade`
(`core/notifications/notify.py`) *unconditionally* insert an in-app row **and**
fire a push for every recipient. The only gating is global/admin: the push
kill-switch, per-category `is_active`, quiet hours, and admin rate limits
(`core/notifications/push_service.py:235-265`). A user who doesn't want "chat"
pings or marketing noise has **no way to opt out**.

Separately, the only user-facing per-user control that exists today is a single
global boolean — `users.notify_on_allocation` — which governs *allocation
emails only* (the bespoke SMTP path in `core/services/notification_service.py`,
unrelated to `notify_*`).

This project gives each user control over **which categories reach them on which
channel**, across **four channels** — the in-app bell, push, **email**, and
**SMS** — while guaranteeing operationally critical signals always get through.
It also folds the legacy `notify_on_allocation` email flag into the new model.

## Decisions locked (2026-11-25)

| # | Decision | Choice |
|---|---|---|
| Channels | Which channels | **4**: in-app, push, email, SMS |
| Defaults | Posture before any toggle | in-app + push **ON**; email + SMS **opt-in (OFF)** per category |
| Mandatory | Scope of "truly unstoppable" (`approvals`, `system`) | **All four channels forced**, bypassing every admin gate *and* user prefs — including billed SMS |
| Email | Breadth | **All categories**, generic template (title + message + link) |
| SMS | Provider | **smsapi.com** (EU/RO), built with a mock mode + `SMSAPI_TOKEN` env |
| Legacy flag | `users.notify_on_allocation` | **Deprecate + migrate** into the new prefs; stage the column drop |

## Goals

- Each user controls notifications **per category** on **four independent
  channels**: in-app bell, push, email, SMS.
- **Default posture is behaviour-preserving:** in-app + push default **on**
  (today's behaviour); email + SMS default **off** (opt-in) so nobody gets an
  email flood or a surprise SMS bill on rollout.
- **Critical/operational categories are protected and unstoppable** — `approvals`
  and `system` always deliver on **all four** channels, shown locked in the UI,
  not mutable by the user and not stoppable by admin gates.
- A **canonical category registry** whose slugs match what the code emits, so
  preferences (and the existing admin per-category push controls) bind correctly.
- Email becomes a **general channel** for any category (generic template), not
  just the hard-wired allocation email.
- SMS is a **new, live channel** via smsapi.com, with a mock mode for dev/test.
- The legacy `notify_on_allocation` email opt-out is **migrated** into the new
  prefs with zero behaviour change, then its column retired in a later step.

## Non-goals

- Commits-Digest email preferences (separate system; see the digest design).
- Admin/global notification config — the existing `NotificationsTab` and
  `notification_settings` behaviour is unchanged.
- Realtime delivery / SSE — that is Project #4, designed separately.
- Per-channel scheduling or per-user quiet hours (quiet hours stay global, and
  mandatory categories bypass them entirely — see below).
- A phone-number collection campaign (operational follow-up; see Constraints).

## Anti-goals (failure even if it "works")

- **Anyone goes silent on rollout** because a default flipped. in-app + push stay
  on; allocation email stays on for everyone it reaches today.
- **A surprise SMS bill or email flood** because a broadcast/info category
  emailed or texted everyone by default. Email + SMS are opt-in.
- **A user mutes a category they're accountable for** (approvals/system) — those
  are mandatory and un-mutable.
- **A preference that looks set but doesn't bind** because its slug doesn't match
  the emitted category (the bug the registry fix prevents).
- **Allocation emails silently stop** because email defaults to off — the
  migrated `allocation` category must default email-**on** (see migration).

## Constraints

- Postgres + Flask backend; React/TS web; Capacitor mobile (`jarvis-mobile-2`).
- **The `notifications` table already has a `category` column** (verified live —
  the earlier draft said it didn't). The in-app gate still filters recipients
  *before* insert using the `category` argument; it does not need to read the
  stored column.
- `send_push_to_users(user_ids, …, category=…, bypass_rules=False)` is the single
  push choke point. `bypass_rules=True` (admin test sends) must keep skipping all
  gating. Mandatory categories behave like an implicit `bypass_rules` for the
  gate pipeline (but still resolve to real recipients).
- **SMS is greenfield** — no provider, no sending code exists. smsapi.com
  integration is net-new: REST client, `SMSAPI_TOKEN`, RO phone normalization
  (`+40`), per-message cost, and a mock mode mirroring `EFACTURA_MOCK_MODE`.
- **Phone coverage is 11/297 users.** SMS reaches ~4% until phones are collected;
  email reaches all 297. This does not block the build but bounds SMS usefulness.
- **Cost/operational warning (mandatory = all four):** every `approvals`/`system`
  event sends a **billed SMS + an email** to every recipient, un-opt-out-able and
  un-gateable. An admin's push kill-switch and quiet hours will **not** stop
  mandatory push either (incl. at night). This is an explicit, accepted trade-off.
- Prod category rows exist and are partly mismatched (see registry); prod data
  changes run only through the normal migration/backfill path (2-confirm for prod).

## The design

### 1. Category registry (foundational — lands first)

The code emits **19** category slugs (verified):
`system, approvals, chat, digest, smart_alert, hr_attendance, hr_course_expiry,
field_sales, ticketing, marketing, carpark, buyback, performance, accounting,
test_drive, happy_announce, bnr_feed_down, fp_scheduled_block, fp_vehicle_expiry`
— plus one **new** slug introduced by this project: **`allocation`** (the
migrated allocation-email channel).

Prod `push_notification_categories` holds **6** builtin rows; three slugs don't
match what the code emits (verified live — all `is_active=true`, no custom rate
limits except `smart_alert.max_per_hour=3`):

| prod slug (today) | emitted slug (code) | priority | channel |
|---|---|---|---|
| `approval` | `approvals` | high | approval_notifications |
| `attendance` | `hr_attendance` | high | attendance_notifications |
| `message` | `chat` | normal | message_notifications |
| `digest` | `digest` ✅ | low | digest_notifications |
| `smart_alert` | `smart_alert` ✅ (max 3/hr) | normal | smart_notifications |
| `system` | `system` ✅ | critical | system_notifications |

Because the lookup is `get_category(slug)` and the slug never matches for the
mismatched three, their admin per-category settings **silently never apply**.
Backfill (idempotent, additive, via the normal migration path — **not** a manual
prod edit):

1. **Rename** the three legacy slugs to canonical — preserves each row's id and
   admin-tuned settings: `approval→approvals`, `attendance→hr_attendance`,
   `message→chat`.
2. **Upsert** the full canonical set (19 + `allocation`) as `is_builtin = TRUE`
   with `ON CONFLICT (slug) DO NOTHING`, with Romanian display names and sensible
   defaults. Only *adds* missing categories; existing rows untouched.

`approvals` and `system` are flagged **mandatory** (and `priority='high'`/
`'critical'`). Exact display-name/priority/grouping table is a build detail.

> ⚠️ This backfill changes prod category rows on the next deploy. Idempotent and
> additive (rename + insert-if-missing), but call it out at deploy time.

### 2. New table: `user_notification_preferences` (four channels)

```sql
CREATE TABLE IF NOT EXISTS user_notification_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_slug TEXT NOT NULL,
    in_app_enabled BOOLEAN,   -- NULL = use category default
    push_enabled   BOOLEAN,
    email_enabled  BOOLEAN,
    sms_enabled    BOOLEAN,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_notif_pref UNIQUE (user_id, category_slug)
);
CREATE INDEX IF NOT EXISTS idx_user_notif_pref_user
    ON user_notification_preferences(user_id);
```

- Columns are **nullable**; `NULL` means "inherit the category default". Only an
  explicit user choice writes a non-NULL value. This keeps the table small and
  lets defaults differ per channel/category without per-user backfill.
- Lives in a notifications migration domain (`schema_approvals.py` alongside the
  other notification tables, or a dedicated section), `IF NOT EXISTS`.

### 3. Per-category channel defaults (the heart of the model)

A code-level `CHANNEL_DEFAULTS` map (not stored per user) gives the effective
value when a user's row/column is NULL:

| Category class | in_app | push | email | sms |
|---|---|---|---|---|
| **Default** (most of the 19) | on | on | **off** | **off** |
| **`allocation`** (migrated, email-only today) | off | off | **on** | off |
| **Mandatory** (`approvals`, `system`) | on (forced) | on (forced) | on (forced) | on (forced) |

Effective value = mandatory? → forced on; else user row value if non-NULL; else
`CHANNEL_DEFAULTS[category][channel]`. This preserves today's behaviour exactly
(in-app+push for everything; allocation email for everyone) while making email/
SMS opt-in for the broadcast categories.

### 4. Gate placement (four gates + mandatory bypass)

A shared `preference_filter(user_ids, category, channel)` helper returns the
subset of users who should receive `category` on `channel`:

- If `category in MANDATORY_CATEGORIES` → return **all** `user_ids` unchanged
  (no query, forced on).
- Else one indexed query over the bounded recipient set, applying the
  `CHANNEL_DEFAULTS` + NULL-inheritance logic:
  ```sql
  SELECT user_id, <channel>_enabled
  FROM user_notification_preferences
  WHERE category_slug = %s AND user_id = ANY(%s);
  ```
  Users with an explicit `FALSE` are dropped; users with `TRUE` or no row follow
  the category default.

Applied at four points:

- **In-app** — `core/notifications/notify.py`: filter recipients on
  `channel='in_app'` **before** insert, in `notify_user/notify_users/
  notify_with_push/notify_node_cascade` (via the shared helper).
- **Push** — `core/notifications/push_service.py:send_push_to_users`: after the
  existing global/`is_active`/quiet-hours/rate-limit pipeline and only when
  `bypass_rules=False`, filter on `channel='push'`. **Mandatory categories
  short-circuit the entire pipeline** (treated like `bypass_rules`): they skip
  kill-switch, `is_active`, quiet hours, and rate limits — truly unstoppable.
- **Email** — new generic email send plumbed into the `notify_*` path (see §5),
  filter on `channel='email'`; mandatory forces send.
- **SMS** — new SMS send plumbed into the `notify_*` path (see §6), filter on
  `channel='sms'`; mandatory forces send.

### 5. Email channel (generic, all categories, opt-in)

- Reuse the existing SMTP sender `core/services/notification_service.send_email`.
- A new `notify.py`-level step: after in-app insert + push, for the recipients
  who pass the `email` gate, send a **generic email** (subject = title, body =
  message + a link button to `link`). A single reusable template — most
  `notify_*` calls only carry title/message/link, which renders fine.
- Default **off** for all categories except `allocation` (on) and mandatory
  (forced). So broadcast/info categories only email users who opted in.
- Fire-and-forget, never blocks the request (same pattern as push).

### 6. SMS channel (smsapi.com, live, opt-in)

- New module `core/notifications/sms_service.py`: a thin smsapi.com REST client
  (`send_sms_to_users(user_ids, body, category=…, bypass_rules=False)`),
  mirroring `push_service` structure.
- Config via env: `SMSAPI_TOKEN`, `SMSAPI_FROM` (sender ID), and `SMS_MOCK_MODE`
  (mirrors `EFACTURA_MOCK_MODE`) so dev/test never hit the real API or incur cost.
- **Phone normalization:** read `users.phone`, normalize to E.164 `+40…`; skip
  users with no/invalid phone (logged, not an error). Only 11/297 reachable today.
- Gated by the `sms` channel filter; default **off** everywhere except mandatory
  (forced). Respects a per-category rate-limit reuse of `push_rate_limit_log`
  pattern if needed (build detail).
- **Cost:** each send is billed. Mandatory categories bill unconditionally —
  surfaced at deploy time.

### 7. Deprecate + migrate `notify_on_allocation`

Today: `notify_allocation()` (SMTP) filters recipients by
`is_active AND notify_on_allocation`. Live data: **0 users are FALSE** (243
active + 54 inactive, all TRUE), so migration writes **zero opt-out rows**.

Steps:
1. Introduce the `allocation` category (email default **on**, in-app/push/sms
   **off** — exactly today's email-only behaviour).
2. Repoint `notification_service.notify_allocation` to check the new `email`
   preference for `category='allocation'` instead of `users.notify_on_allocation`.
3. Backfill: for any user with `notify_on_allocation=FALSE`, write a row
   `(user, 'allocation', email_enabled=FALSE)`. (None exist today → no-op, but
   the migration is written to be correct if that changes before deploy.)
4. **Stage the column drop:** stop writing/reading `notify_on_allocation` in app
   code and frontend (UsersTab switch → the new prefs surface), but **leave the
   column in place** this release. Drop it in a dedicated later cleanup once all
   ~7 references (routes, user_repository create/update, structure_node_repository,
   models, frontend types, UsersTab, NotificationsTab) are confirmed migrated —
   per the repo's "create replacement first, migrate refs, then remove" rule.

### 8. API (per-user, `current_user.id`-scoped) — settles Q4

- `GET /notifications/api/preferences` →
  ```json
  {
    "categories": [
      {"slug":"chat","name":"Mesaje","group":"Comunicare","mandatory":false}, …
    ],
    "preferences": {
      "chat": {"in_app":true,"push":true,"email":false,"sms":false}, …
    },
    "mandatory": ["approvals","system"],
    "channels": ["in_app","push","email","sms"]
  }
  ```
  `preferences` returns **effective** values (mandatory forced-on, NULL columns
  resolved against `CHANNEL_DEFAULTS`) so the client renders without knowing the
  default rules. Mandatory categories are flagged and rendered locked-on.
- `POST /notifications/api/preferences` → upsert
  `{category_slug, in_app_enabled, push_enabled, email_enabled, sms_enabled}` for
  the current user (any channel omitted = leave NULL/unchanged). **Rejects** any
  mandatory slug (409/422). Scoped strictly to `current_user.id`.

Added to the existing `notifications_bp` next to the current user
`/notifications/api/*` endpoints (not the admin `_require_admin` ones).

### 9. Web UI (ship first)

A **"Notificări"** preferences card on the user's own settings/profile page
(distinct from the admin `Settings/NotificationsTab`, which stays global-only).
Categories grouped; each row shows **four toggles** (in-app / push / email / SMS).
Mandatory categories render all four locked-on with an explanation. SMS toggles
show a subtle "necesită număr de telefon" hint when the user has no phone on file.
Reads/writes the two endpoints via a small `api/notificationPreferences.ts`
client + a react-query hook. The legacy `notify_on_allocation` switch in UsersTab
is removed in favour of this surface.

### 10. Mobile (follow-up)

A settings screen in `jarvis-mobile-2` hitting the same endpoints, in the next APK
bundle. Out of scope for the first PR; the API is designed for it.

## Rollout / ordering

1. **Registry backfill** (rename + upsert canonical set incl. `allocation`).
2. **Table** `user_notification_preferences` + `CHANNEL_DEFAULTS` + shared gate
   helper (no behaviour change yet: defaults reproduce today's delivery).
3. **Gates** wired into notify.py + push_service (in-app + push).
4. **Email channel** generic send + gate.
5. **SMS channel** smsapi.com client (mock-mode first) + gate.
6. **Migrate** `notify_on_allocation` → `allocation` category; repoint
   `notify_allocation`; remove the UsersTab switch (column kept).
7. **API** GET/POST preferences.
8. **Web UI** Notificări card.
9. (Later) mobile screen; (later) drop `notify_on_allocation` column.

## What's left to the builder

- Final **Romanian display names + grouping** for the 20 categories and any
  non-`normal` priorities.
- Exact **location of the user settings/profile page** to host the web card.
- Whether SMS needs its own per-category rate-limit (reuse `push_rate_limit_log`
  pattern) to bound cost on noisy categories (recommended for non-mandatory).
- smsapi.com specifics: sender-ID registration, RO phone validation rules,
  error/`DLR` handling, and the exact env var names.
- Whether to add a short-TTL cache for the per-user pref lookup (start without).

## Test coverage

- Gate unit tests per channel: default-on (in-app/push), default-off
  (email/sms), explicit opt-out respected, NULL-inherits-default, mandatory forces
  all four + bypasses admin gates, `bypass_rules` still skips.
- Registry backfill idempotency (rename preserves id/settings; re-run no-ops).
- `notify_on_allocation` migration: email behaviour unchanged for all users;
  opt-out (if any) maps to `allocation` email off.
- SMS: mock-mode send, phone normalization/skip-no-phone, cost-path not hit in
  tests.
- API authz: a user can only read/write their own prefs; mandatory slug rejected.
