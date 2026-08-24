# Happy Phase 0 — Codebase Assessment

**Date:** 2026-08-23 · **Commit:** `d24b4cf85` · **Branch:** `staging`
**Method:** `scripts/happy_assess.py` (static inventory) + 32-row manual verification against live code + production data reality from the Aug-19 prod backup (`jarvis_prod_20260819_000252.dump`) restored read-only into a local scratch DB. No production DB was contacted.
**Assessor authority:** read-only on all application code; this file + `HAPPY_ASSESSMENT_RAW.md` + §3/§3.0/§3.1 spec patches are the only writes.

---

## 1. GO / NO-GO

| Integration point | Status | Evidence (file:line) | Impact if wrong |
|---|---|---|---|
| Push pipeline reuse | **GO-WITH-CHANGES** | `push_service.py:217`; `notify.py:75` | Categories/rate-limit tables unmanaged (no DDL/seed); `notify_with_push` double-sends; reach ~3%. Seed categories in `schema_happy`; call `send_push_to_users` directly. |
| Permissions v2 seeding | **GO** | `schema_roles.py:445-459`; `decorators.py:8` | Append an unconditional `INSERT … ON CONFLICT (module_key,entity_key,action_key) DO NOTHING` block (not the "if empty" seed). |
| Mobile payload extension | **NO-GO for Phase 1** (→ Phase 6) | mobile-2 repo has no `/api/mobile/dashboard` consumer; `dashboard.py:19-51` | App never reads the endpoint. Additive block is server-safe but invisible. Drop mobile from Phase 1. |
| Media upload + proxy | **GO-WITH-CHANGES** | `media/routes.py:24,52`; `spaces_service.py:41` | Add `private/happy/` to `_ALLOWED_PREFIXES`; key media `private/happy/…`. Build a Pillow resize/webp helper (none exists). |
| Dashboard widget slot | **GO** | `Dashboard/types.ts:19-27,70`; `Dashboard/index.tsx:73-81` | 3-file registration (catalog + component-map + component). `w:6` = full row. |
| Hub slot | **GO** | `Hub/index.tsx:408-409` | Insert `<MarqueeWidget placement="hub_card" />` between the right-column `<div>` (L408) and the Notifications `<Card>` (L409). |
| Nightly job registration | **GO** | `tasks/cleanup.py:136-145` (cron), `:76-84` (interval), `:44-58` (lock) | Add two `'cron'` jobs (`purge_events`, `refresh_targets`) with unique `id=`; file-lock guard already ensures single worker. |
| Digest reuse for the `feed` placement | **GO** | `chat/services/chat_service.py:130`; `schema_digest.py:44-58` | `ChatService().create_post(channel_id, user_id, content, post_type='announcement', author_name=…)`; store returned `id` on the campaign. |
| i18n strategy | **GO** (single-locale) | no i18n lib in `frontend/package.json`; strings hardcoded | Store `locale` on campaigns; author content as literal strings. No translation layer in Phase 1. |
| Audience targeting data quality | **GO-WITH-CHANGES** | scratch DB §8.2 | Only `company` (97%) is reliable. Phase 1 = company-first (+ `department` after cleanup). Others unusable as-is. |
| Pulse cohort viability | **NO-GO** (Phase 4, out of Phase 1) | scratch DB §8.3 | 37/46 depts <5 active; `org_unit_id` 0% → no parent to roll up to. Anonymity cohorts collapse to company. Revisit at Phase 4 with real hierarchy. |

**Net:** the Phase 1 MVP — a **web-only** surface engine (Spotlight + Marquee on Dashboard & Hub), **company-first** audience targeting, ack `click`, admin campaign CRUD + publish, permissions seed, and the 30-day purge job — is a GO. Mobile and multi-dimension targeting are corrected out of Phase 1; Pulse (Phase 4) is a data-headcount NO-GO to revisit later.

---

## 2. Verified facts (the contract every later agent uses)

All confirmed against commit `d24b4cf85`. Zero rows remain `ASSUMED`.

1. **Push send** — `core/notifications/push_service.py:217` `send_push_to_users(user_ids, title, body, data=None, category='system', bypass_rules=False)`. `bypass_rules=True` skips global-kill/category-active/quiet-hours/rate-limit gating = the `critical` tier. FCM built at `:297-315`; `data=` → FCM **data** payload.
2. **Push gating storage** — quiet hours / global enable / global rate limit / default TTL / critical-bypass flag are key/value rows in `notification_settings` (`schema_misc.py:13`). Per-category `priority|max_per_hour|ttl_seconds|is_active|android_channel_id|is_builtin` live in `push_notification_categories`; per-user counters in `push_rate_limit_log`. **Both tables have NO migration DDL and no seed** (exist in prod only). Critical is `priority='critical'` + setting `push_quiet_hours_allow_critical='true'`.
3. **Register push category w/o migration** — YES: `POST /api/push-manager/categories` (`notifications/routes.py:248`, `notifications_bp`, admin-gated) → INSERT; cache invalidated. (Not on `push_bp`.) Caveat: table itself is unmigrated.
4. **In-app notify** — `core/notifications/notify.py:75` `notify_with_push(user_ids, title, message=None, link=None, entity_type=None, entity_id=None, type='info', push_data=None, category='system')`. **Bug:** it double-sends (via `notify_users` at `:89`→`:68`, then `:96`). Also `notify_user:25`, `notify_users:49`, `notify_node_cascade:103`. All write `public.notifications`.
5. **`public.notifications` DDL** — `schema_approvals.py:199-211`: `id, user_id FK, type, title, message, link, entity_type, entity_id, is_read, created_at`. `link TEXT` holds app-relative paths (`/app/…`) — confirmed by writers (`smart_service.py:109`, `notification_service.py:553`, `chat_service.py:182`).
6. **BaseRepository** — `core/base_repository.py`: `query_one(sql, params=None):45`, `query_all(sql, params=None):58`, `execute(sql, params=None, returning=False):71`, `execute_many(callback):100`. **No `transaction()`** — atomic multi-statement work via `execute_many(callback)` (sets `autocommit=False`, one commit/rollback).
7. **Migration entry point** — `migrations/init_schema.py`: domain builders imported L6-32, invoked L43-70 inside `create_schema()`. Register `create_schema_happy` import after `:32` and call it after `create_schema_incremental` (`:69`), before `run_pending_migrations` (`:70`). `create_schema_core`/`_roles` run first → FKs to `users`/`roles` are safe. Whole block re-runs on every `init_db()`.
8. **CREATE SCHEMA idiom** — `schema_hr.py:85`: `cursor.execute('CREATE SCHEMA IF NOT EXISTS hr'); conn.commit()`. Copy verbatim for `happy`.
9. **permissions_v2 seeding** — `schema_roles.py`: `permissions_v2` cols `module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order` UNIQUE`(module_key,entity_key,action_key)` (`:239`); `role_permissions_v2` cols `role_id, permission_id, scope permission_scope, granted` UNIQUE`(role_id,permission_id)` (`:258`); scope ENUM `('deny','own','department','all')` (`:231`). Add new perms via an **unconditional** `INSERT … ON CONFLICT DO NOTHING` migration block (pattern `:445-459`) — the "if empty" seed (`:270`) never touches existing DBs.
10. **Permission decorator** — `core/roles/decorators.py:8` `v2_permission_required(module, entity, action)`. Admin bypass via `is_admin`/`can_access_settings`; sets `g.permission_scope`; 401 unauth, 403 `{'success':False,'error':'Permission denied: m.e.a'}`.
11. **Mobile JWT** — `core/mobile/routes/_shared.py`: `jwt_required(f):168`, `_current_mobile_user():190` (`return request._jwt_user`), `_user_json(user):194`. HS256, `sub`=user id, access TTL 3600s.
12. **`/api/mobile/dashboard` shape** — `dashboard.py:9` (`@jwt_required`), returns top-level `stats`, `recent_invoices`, `recent_clients`, `upcoming_events`. Additive `happy` key is server-safe.
13. **Android client contract** — jarvis-mobile-2 does **not** consume `/api/mobile/dashboard` (only `android.md:461` doc mention). Client parses via generic `res.json()` (`src/services/api.ts:128`), no runtime schema validation → **tolerant** of unknown keys. Additive server keys need no app release.
14. **Media** — serve-only `/api/media/<path:key>` (`media/routes.py:52`, `@login_required`); key must start with `private/carpark/|private/logos/|private/foi-parcurs/damage/` (`:24`). Upload: `spaces_service.upload(data, key, content_type)` (`spaces_service.py:41`, boto3/DO Spaces, `ACL='private'`). Key style `private/<module>/…/<uuid>.<ext>`.
15. **Image helper** — `image_compressor.py` is TinyPNG byte-compression only (no resize/convert/webp). Real Pillow resize = `carpark/routes/photos.py:141 _compress_jpeg` (private). **Build** a shared helper (PIL already a dep).
16. **Deeplink** — `core/deeplink/routes.py`: scheme `com.jarvis.mobile2://approvals?request=<id>` (`:19`); web `/go/approval/<int:request_id>` (`:38`), `/go/approval/act` (`:81`); UA split on `_MOBILE_UA=('iphone','ipad','ipod','android')` (`:8,15`). `happy` host + `/go/happy/*` are free.
17. **Targeting coverage (active n=269)** — `company` 97% (15 distinct), `department` 65% (45), `brand` 13% (11), `subdepartment` 0% (1), `org_unit_id` 0% (0), `contract_status` 100% but **1 distinct value**. Only `company` ≥80%.
18. **Dept sizes** — 46 departments; **37 below min_group_size 5** (many singletons). With `org_unit_id` empty there is no hierarchy to roll up to except `company`.
19. **Widget registry** — `Dashboard/types.ts` `WidgetDef{id,name,icon,permission?,defaultLayout,defaultVisible,statCards}` (`:19`); catalog `WIDGET_CATALOG` (`:70` sample); component map + import `Dashboard/index.tsx:73-81` (id with no map entry renders null `:174`); toggle via `useDashboardPrefs.ts:105`. `COLS=6`.
20. **Hub slot** — `Hub/index.tsx`: right column `<div className="space-y-6">` opens `:408`; Notifications `<Card>` is first child `:409`. Insert between.
21. **API client** — `api/client.ts`: `request<T>` returns `response.json()` **without auto-unwrapping** (`:79`); modules unwrap `{key:[…]}` themselves. Error envelope `{error}`; `ApiError{status,data}`; 401→`/login`. TanStack keys are array/namespace-first (`['dashboard','recentInvoices']`); hooks live in pages/widgets, not `api/*.ts`.
22. **shadcn/ui** — present: dialog, sheet, badge, checkbox, progress, card, button, skeleton, tabs, select, textarea, avatar, separator (+ more). **Missing: `drawer`, `carousel`** — both avoidable (`Sheet` covers the mobile bottom-sheet; manual Marquee pager needs no carousel/embla).
23. **Theme** — `index.css` fully token-driven `oklch` vars in `:root` + `.dark` (`--background/-foreground/-card/-muted-foreground/-destructive/-border/-primary/-ring/…`); Tailwind 4 `@custom-variant dark`; `next-themes ^0.4.6`.
24. **i18n** — none (no i18next/react-intl). Strings hardcoded, mixed RO/EN; dates via `toLocaleString('ro-RO',…)`. → single-locale.
25. **Scheduler** — `tasks/cleanup.py`: `BackgroundScheduler(daemon=True):39`, `start_scheduler():61`, `fcntl.flock` single-worker lock `:44-58`. Cron idiom `:136-145`, interval idiom `:76-84` (`replace_existing=True, misfire_grace_time=300, coalesce=True`).
26. **Tests** — root `jarvis/conftest.py` mocks psycopg2 (no fixtures); repo-root `tests/conftest.py` = mock-only. **Real-DB fixtures live in per-subdir conftests** (`jarvis/tests/dept_pulse/conftest.py`, `hr_events/conftest.py`) via a probe/restore dance + `REAL_DB_AVAILABLE` against `postgresql://localhost/defaultdb`. New Happy tests → `jarvis/tests/happy/conftest.py` copying that pattern. vitest setup `frontend/src/test/setup.ts`; Playwright `baseURL` = staging URL (`playwright.config.js:30`).
27. **`hr.events`** — `schema_hr.py:93`: `id, name, start_date DATE, end_date DATE, company TEXT, brand TEXT, description, created_by, created_at`. **No time-of-day, no location** (spec correct); `company`/`brand` are free-text, not FKs. 31 rows in prod → event auto-generation viable (title + date-window + company/brand scope only).
28. **Route collisions** — `campaign|announcement|banner|kudos|spotlight|marquee|happy` free as blueprints/prefixes. **`pulse` partial:** `/api/dept-pulse` taken by `profile_bp` (`:933,986`). `/api/chat` + `/api/digest` taken (chat/digest).
29. **Digest** — `digest_channels.type ∈ {general,announcement,department}`, `is_private`; targets by `company_id | node_id (Sincron) | all` (`digest_channel_targets`); `digest_posts.type ∈ {post,announcement,poll}`, `is_pinned`, `parent_id/reply_to_id` threading. Publish: `ChatService.create_post(channel_id, user_id, content, post_type='post', parent_id=None, reply_to_id=None, poll_data=None, author_name=None)` (`chat_service.py:130`) → `digest_posts` INSERT (`chat_repository.py:306`) + auto-notify fan-out.
30. **`digest_read_status`** — channel-level watermark: `UNIQUE(channel_id,user_id)`, single `last_read_post_id` (`schema_digest.py:158`). **Not** per-post → Happy owns per-item read/impression analytics.
31. **`hr_dept_pulse_votes`** — `schema_incremental.py:2529`: `voter_user_id FK→users`, `department_node_id FK→sincron_org_nodes`, `perspective`, `competency_key`, `rating 1-5`, UNIQUE`(voter_user_id,department_node_id,perspective,competency_key)`. **Identifiable** per-person data; live backend, no UI, **no info notice/consultation found**. Anonymity presentation-only (`MIN_VOTERS=3`).
32. **Branch state** — `staging`, up to date with `origin/staging` (`d24b4cf85`). Tree carries only the untracked Happy setup files + a dirty `Conta_app` submodule pointer (unrelated). Clean enough to start; commit the Happy docs/scripts before Phase 1 code.

---

## 3. Spec corrections required (patched in place)

Applied to `HAPPY_MODULE_SPEC.md` — see new §3.0 (items 1-5), §3.1 Phase 0 finding, and value fixes in §4/§7.1:

1. **§3 targeting row** — 8 dimensions → **`company`-first only**; `department` secondary after cleanup; `brand/subdept/org_unit/contract_status` unusable.
2. **§3 mobile row + §6.2 / §8 / §11 Phase 1 scope** — the app does not read `/api/mobile/dashboard`; **remove mobile Marquee/payload from Phase 1** (→ Phase 6).
3. **§3 media row + §4 + §7.1** — media keys `happy/…` would 403; corrected to `private/happy/…` (added `_ALLOWED_PREFIXES` requirement); flagged that no resize/webp helper exists (§6.5 is a build).
4. **§3 push row** — added the unmanaged-tables + `notify_with_push` double-send caveats; Happy must seed categories and call `send_push_to_users` directly.
5. **§6.2 widget registration** — corrected from "`widgets.tsx`" to the 3-file registration; added the exact Hub anchor (`Hub/index.tsx:408/409`).
6. **§3.1 `hr_dept_pulse_votes`** — added the confirmed identifiable/`sincron_org_nodes`/no-notice finding for the DPO.

No spec assumption was found to be a hard blocker; all corrections are design adjustments, not redesigns.

---

## 4. Production data reality (Aug-19 backup; re-verify live before launch)

- **Active users:** 269 (289 total).
- **Targeting non-null (active):** company **97%** · brand **13%** · department **65%** · subdepartment **0%** · org_unit_id **0%** · contract_status 100% but **1 distinct value**.
- **Departments <5 active:** **37 of 46** (many singletons) → pulse cohorts collapse to company; `org_unit_id` empty means no parent unit to roll up to.
- **Registered mobile devices:** **10 across 8 users = ~3% of active** = the real push ceiling. ⚠ Backup pre-dates the Aug-21 jarvis-2 push rollout — **re-check live** before treating push reach as final.
- **`hr.events`:** 31 rows, 2026-01-22 → 2026-08-13 → event auto-generation has enough volume.
- Expected tables all present (users, roles, notifications 11 251 rows, mobile_devices, permissions_v2 254, role_permissions_v2 1 464, department_structure 33, structure_nodes 105, hr.events 31, digest_channels 3, digest_posts 25, digest_read_status 42, hr_dept_pulse_votes 16).

---

## 5. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Audience targeting unusable beyond `company` | High (data confirmed) | High — narrows Phase 1 reach | Company-first targeting; open a `department`/`org_unit_id` data-cleanup task; keep resolver multi-dim-capable |
| `push_notification_categories` / `push_rate_limit_log` absent on fresh/staging DB | High (no DDL) | Medium — push send/registration breaks off-prod | `schema_happy` ensures the table + seeds Happy's 3 categories idempotently |
| `notify_with_push` double-send inflates delivery + rate counters | Certain (code path) | Medium — user annoyance, wrong metrics | `delivery.py` calls `send_push_to_users(..., data=…)` directly |
| Mobile scope assumed "free" in Phase 1 | Certain | Medium — schedule/expectation | Move mobile to Phase 6; Phase 1 is web-only |
| Push reach ~3% | Medium (may improve post-Aug-21) | Medium — push KPIs unreachable | Re-verify live; do not make push a launch KPI; lead with in-app surfaces |
| Pulse anonymity non-viable at current headcount | High (Phase 4) | High for Pulse only | Out of Phase 1; revisit at Phase 4 with real hierarchy + consultation |
| Pre-existing `hr_dept_pulse_votes` Art. 5 exposure | Exists now | High (legal) | DPO review; do not let it contaminate Pulse's anonymity claim |
| Media resize/webp helper must be built | Certain | Low | Extract/generalize `carpark _compress_jpeg`; PIL already present |

---

## 6. Revised Phase 1 estimate

Spec estimate: **8-10 days**. Revised: **8-10 days, web-only**, with scope shifted rather than grown:

- **Removed from Phase 1:** mobile payload / mobile Marquee (→ Phase 6) — nets ~1-1.5 days back.
- **Added to Phase 1:** `private/happy/` media prefix + a small Pillow resize/webp helper (~0.5 day); defensive `push_notification_categories` DDL/seed + `delivery.py` that avoids the double-send (~0.5 day); restrict authoring UI + audience resolver to populated dimensions (~0.5 day).
- **Net:** ~**8-9 days**, unchanged in magnitude, lower risk. First deliverable stays `surface_resolver.py` + its 12 unit tests before any UI.

---

**Phase 1 may begin:** web-only surface engine with company-first audience targeting, subject to the §3.0 corrections above. Mobile is deferred to Phase 6 and Pulse (Phase 4) is a headcount NO-GO to revisit; neither blocks Phase 1.
