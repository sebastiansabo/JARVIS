# Happy — Internal Employee Engagement Module for JARVIS

**Version:** 1.0 · **Date:** 2026-08-23 · **Owner:** Sebastian Sabo
**Classification:** Internal Engineering — do not distribute
**Target repo:** `JARVIS` (branch `staging`) · **Stack:** Flask + PostgreSQL + React 19 SPA + Android APK (JWT)

---

## 0. Naming

**Happy.** Plain word, no acronym. Tagline where a subtitle is needed: *"Ce se întâmplă la noi."*

Rejected: *HAPPI* as a backronym — it reads as a misspelling of *Happy* in every Romanian-language screen and in every URL, and nobody will ever type the second P correctly. Also rejected: *Happy Hub* (collides with the existing `/app/hub` route), *Happenings*, *HappyPulse* (narrows the module to surveys).

| Layer | Identifier |
|---|---|
| Python package | `jarvis/happy/` |
| Flask blueprint | `happy_bp` |
| Web API prefix | `/api/happy` |
| Mobile API prefix | `/api/mobile/happy` |
| Postgres schema | `happy` |
| Migration file | `jarvis/migrations/domains/schema_happy.py` |
| React pages | `frontend/src/pages/Happy/` |
| Deep-link host | `com.jarvis.mobile2://happy/<kind>/<id>` |
| Permission module_key | `happy` |
| Push category slug | `happy_announce`, `happy_recognition`, `happy_pulse` |

Namespace verified free: zero tables, routes, blueprints or React modules in the repo use `happy`. The only existing occurrences are incidental prose and the "Happy Birthday / Happy {n}-year Work Anniversary" banners already rendered in `frontend/src/pages/Profile/index.tsx` — which are the moments feature this module absorbs, not a collision.

**Surface names inside the app**

| Surface | Name | Why not something warmer |
|---|---|---|
| Interstitial pop-up | **Spotlight** | it carries mandatory policy content; a cheerful label on a legal acknowledgement reads as manipulation |
| Dashboard / Hub banner | **Marquee** | |
| Peer recognition | **Praise** (`Aprecieri`) | |
| Surveys / eNPS | **Pulse** | |
| Admin console | **Happy Board** | |

**One risk, stated once.** "Happy" as the brand on a module that also delivers mandatory policy notices and salary-adjacent announcements is a tonal bet. In a bad quarter, management-branded cheer is the thing employees screenshot. The mitigation is already in the table above: *Happy* is the container and the app-drawer tile; the individual surfaces are named neutrally and factually. Never put the word "Happy" on an acknowledgement dialog or a survey intake screen.

---

## 1. Brutal truth: what the market data says you must NOT build

These are the four features every internal-engagement roadmap contains and that the evidence says will lose you money and trust. Read this before the data model.

**1. No named leaderboards.** Belo et al. ran a randomized field experiment on 188 leaderboards, n=3,762. The mere presence of a leaderboard produced **no significant engagement effect** (β=0.008 for login, 95% CI −0.02 to 0.04). The only real effect is defensive — people work to avoid being overtaken by the person below them (β=0.275, p<0.01) — which accrues to mid/upper ranks and does nothing for the bottom. Only 8% self-identify as competitive and they showed *reversed* patterns. The active ingredient is **performance feedback, not social comparison**. Ship personal streaks and personal trend lines. Ship no rankings.

**2. No "earn points for posting / reading / logging in."** Deci, Koestner & Ryan, 128 studies: expected, contingent tangible rewards move free-choice intrinsic motivation by **d = −0.36**. Unexpected rewards are neutral (d = +0.01). **Verbal recognition is the only manipulation that reliably increases intrinsic motivation: d = +0.33.** Therefore: mandatory written note on every kudos, no points for platform activity, surprise/spot awards only.

**3. No chrome-level coloured banner bar.** NN/g eye-tracking: the right rail drew 0.8% of fixations while occupying 25% of content area — a 33× under-attention ratio. Users have learned to ignore anything that *looks* like an ad: top-of-page bars, animation, coloured rectangles, text baked into images. A "must-read banner" styled as a bright bar at the top of the page is the single most ignorable placement available. Mandatory content goes **inline at the top of the feed, styled like content**.

**4. No individual read-receipt dashboards without legal cover.** Romanian Law 190/2018 Art. 5 imposes **four cumulative conditions** on employee monitoring: prior explicit information, documented and prevailing legitimate interest, **prior consultation of the union or employee representatives**, and subsidiarity — plus a **30-day retention cap** on the data. Law 367/2022 makes employee representatives mandatory at ≥10 employees, with RON 15,000–20,000 fines for failure to inform/consult. Per-person read receipts, acknowledgement timestamps and activity analytics are all monitoring. They are buildable — but only with the retention and consultation controls in §9 baked in from day one, not retrofitted.

**The strategic consequence:** Microsoft Viva Employee Communications is $2/user/month. Announcements-plus-a-feed is not a defensible product. The defensible surface is exactly the set of mechanics no vendor ships well: **acknowledgement with deadlines and escalation, comprehension checks, auto-inheritance of open must-reads by new joiners, native non-opener re-targeting, published anti-gaming rules, and EU-native anonymity tooling.** Happy is built around those six.

---

## 2. Market baseline — the numbers Happy is designed against

Targets, not aspirations. Every one of these becomes a KPI tile in Happy Board (§8).

| Metric | Market benchmark | Happy target (Y1) |
|---|---|---|
| Weekly active users / headcount | ≥60% good, <30% failing, 65% industry avg | **≥65%** |
| Read rate (opened + ≥8s dwell) | 77% avg (Workshop, 186M messages) | **≥75%** |
| Open rate, org <500 people | 73% median, 83% top quartile | **≥75%** |
| Acknowledgement within 7 days | *no vendor publishes a benchmark* | **≥85%**, residual escalated |
| Mandatory-read TTL | Simpplr: 90 days or indefinite | **90 days default, hard cap** |
| Comms frequency | 4–6/week peak; >10/week halves CTR (15%→7%) | **cap 5/week/user** |
| Push frequency | 2–3/week optimal; 3–6/week → 40% disable notifications | **cap 3/week/user, non-critical** |
| Active contributors | 5–20% of employees | **≥12%** |
| Mobile share of usage | 30–50% | **≥40%** |
| Session length | 9.5 min avg | not a target — vanity metric |
| Recognitions per employee per week | 1–2 with funded rewards; only 23% of employees feel meaningfully recognized | **≥1.0** |
| Recognition budget | modal 0.1–0.3% of payroll; ~$5–6/user/mo real spend | **0.15% of payroll** |
| Pulse participation | census 79%, pulse 67%; 70%+ = strong | **≥70%** |
| Pulse length | 3–10 questions, <5 min | **5 questions, weekly** |
| eNPS | global 14–32; size-adjusted ~30 under 250 employees | **≥30**, trend over absolute |
| Engagement context | Gallup: Romania **31% engaged** — 2nd in Europe vs EU avg 12%, global 20% | benchmark against 31%, not 12% |

Build-vs-buy comparator: $5–8/user/month platform for comms+engagement, plus $10–30/user/month if a rewards catalog is funded, plus $12k–75k one-off implementation. For 300 employees that is roughly €20–30k/year platform alone. Happy's payback case is that the surface engine (§4) is ~3 weeks of work against infrastructure you already own — auth, push, media, permissions, org hierarchy — and the reward catalog stays optional and unfunded at launch.

---

## 3. What already exists in JARVIS (verified against the repo)

Happy is an assembly job, not a greenfield build. Confirmed present:

| Capability | Location | How Happy uses it |
|---|---|---|
| Push pipeline w/ categories, quiet hours, per-user rate limit, critical bypass, TTL/priority | `core/notifications/push_service.py` L217 — `send_push_to_users(user_ids, title, body, data=None, category='system', bypass_rules=False)` | Happy registers 3 categories; **frequency capping is delegated here, not reimplemented**. `bypass_rules=True` is the `critical` tier — every use writes an audit row. **⚠ P0:** `push_notification_categories` & `push_rate_limit_log` have no migration DDL/seed; `notify_with_push` double-sends — see §3.0(4) |
| In-app notifications | `core/notifications/notify.py`, table `public.notifications`, `core/notifications/repositories/in_app_repo.py` | `notify_with_push()` fan-out for campaign delivery |
| FCM device registry | table `mobile_devices (user_id, device_id, push_token)` | push targeting |
| Deep links + mobile interstitial | `core/deeplink/routes.py`, scheme `com.jarvis.mobile2://` | `/go/happy/<id>` landing → app or web |
| Private media on DO Spaces + authed proxy | `core/media/routes.py` → `/api/media/<key>` | banner and campaign imagery. **⚠ P0:** proxy only serves `private/carpark/\|private/logos/\|private/foi-parcurs/damage/` — use `private/happy/…` + add the prefix; no resize/webp helper exists (build one) — see §3.0(3) |
| Permissions v2 matrix with scopes `deny/own/department/all` | `permissions_v2`, `role_permissions_v2`; decorator `core/roles/decorators.py` L8 — `@v2_permission_required(module, entity, action)` | all Happy admin gates |
| Org targeting dimensions on users | `users.company`, `.brand`, `.department`, `.subdepartment`, `.org_unit_id`, `.contract_status`, `.is_active` | audience resolver, zero new HR integration. **⚠ P0: only `company` (97%) is reliable** — `department` 65%, `brand` 13%, `subdepartment` 0%, `org_unit_id` 0%, `contract_status` 1 distinct value — see §3.0(1) |
| Org hierarchy | `department_structure`, `structure_nodes`, `structure_node_members` | manager-scoped analytics, cohort rollup |
| Hub (employee home) | `frontend/src/pages/Hub/index.tsx` — apps card, notifications card, punch card, bonus card | Marquee slot + Praise card + open-ack card |
| Dashboard widget grid | `frontend/src/pages/Dashboard/widgets.tsx` (`WidgetShell`) | Marquee widget + Praise widget |
| Mobile aggregated home | `core/mobile/routes/dashboard.py` → `/api/mobile/dashboard`, `/api/mobile/widget-data` | extend payload with `happy` block — **no new mobile round-trip**. **⚠ P0: the jarvis-mobile-2 app does not consume `/api/mobile/dashboard`** — additive block is invisible until the app is wired (Phase 6); drop from Phase 1 — see §3.0(2) |
| HR events | `hr.events`, `hr.event_bonuses` | event campaigns auto-generated from `hr.events` |
| Repo/service conventions | `core/base_repository.BaseRepository` — `query_one(sql, params)`, `query_all(sql, params)`, `execute(sql, params, returning=False)`, `execute_many(callback)`. **There is no `transaction()` helper** — multi-statement atomicity goes through `execute_many(callback)`, as `in_app_repo.create_bulk` does | all Happy repositories |
| Migrations | `migrations/domains/schema_*.py` called from `init_schema.py`, idempotent `CREATE TABLE IF NOT EXISTS` + `DO $$` guarded `ALTER` | `schema_happy.py` |
| Tests | `pytest jarvis/tests/`, `vitest` in frontend, Playwright at repo root | Happy test suite |

### 3.0 Phase 0 verification corrections (2026-08-23, commit `d24b4cf85`, branch `staging`)

Verified against live code and the Aug-19 production backup. Rows above are flagged **⚠ P0** where reality differs; full assessment in `HAPPY_ASSESSMENT.md`.

1. **Audience targeting is single-dimension in practice, not eight.** Active-user (n=269) column coverage: `company` 97%, `department` 65%, `brand` 13%, `subdepartment` 0% (1 row), `org_unit_id` 0% (0 rows), `contract_status` 100% but **1 distinct value**. Only `company` clears the 80% bar. **Phase 1 audience targeting is company-first**, with `department` as a secondary dimension pending a data-cleanup task; `brand`/`subdepartment`/`org_unit_id`/`contract_status` are not usable audience dimensions without HR data work. Keep `happy.campaign_audience` and the resolver 8-dimension-capable, but the authoring UI exposes only the populated dimensions.

2. **Mobile dashboard payload delivers nothing today.** The jarvis-mobile-2 app does **not** call `/api/mobile/dashboard` (only a doc-table mention; Home is built from other endpoints). Its client parses via a generic `res.json()` and tolerates unknown keys, so an additive `happy` block is server-safe but invisible until the app is wired. **Drop "mobile payload / mobile Marquee" from Phase 1** → Phase 6 (Android parity). `jwt_required` / `_current_mobile_user()` (`core/mobile/routes/_shared.py:168,190`) are the auth for a future dedicated `/api/mobile/happy/*`.

3. **Media proxy prefix + no resize helper.** `/api/media/<key>` (`core/media/routes.py:52`) only serves keys under `private/carpark/`, `private/logos/`, `private/foi-parcurs/damage/`. Happy media must be keyed `private/happy/…` and that prefix added to `_ALLOWED_PREFIXES`. Upload via `spaces_service.upload(data, key, content_type)`. `image_compressor.py` is **TinyPNG-only** (byte compression, no resize/convert/webp) — build a small Pillow helper (PIL is already a dependency; `carpark/routes/photos.py::_compress_jpeg` is the closest pattern).

4. **Push pipeline caveats.** `send_push_to_users(...)` and category-INSERT registration (`POST /api/push-manager/categories`, `notifications_bp`) are as described, but: (a) `push_notification_categories` and `push_rate_limit_log` have **no migration DDL and no seed** — they exist in prod only, so `schema_happy` (or a seed) must ensure the table + Happy's 3 categories rather than assume they exist; (b) `notify_with_push()` **double-sends** (one push without the data payload via `notify_users`, then one with it) and double-logs the rate limit — Happy's `delivery.py` must call `send_push_to_users(..., data=…)` directly, not wrap `notify_with_push`; (c) production push reach is **~3%** (10 devices / 8 users as of Aug-19, pre-dating the Aug-21 rollout — re-verify live). Push is not a launch KPI.

5. **Widget registration is three files, not one.** Adding `happy_marquee` touches `pages/Dashboard/types.ts` (catalog entry; `w:6` = full row), the `WIDGET_COMPONENTS` map + import in `pages/Dashboard/index.tsx`, and the component in `widgets.tsx` — not `widgets.tsx` alone. Hub slot anchor: insert `<MarqueeWidget placement="hub_card" />` between `Hub/index.tsx:408` (right-column `<div className="space-y-6">`) and `:409` (Notifications `<Card>`).

### 3.1 Already-built adjacencies — do not rebuild these

Phase 0 surfaced three existing subsystems the original design would have duplicated. The spec below is corrected for them.

**Digest — the internal feed already exists.** Tables `digest_channels` (types `general|announcement|department`, private flag), `digest_channel_members`, `digest_channel_targets` (targeting by `company_id` or org `node_id`, or `all`), `digest_posts` (types `post|announcement|poll`, pinning, threading), `digest_reactions`, `digest_polls` / `digest_poll_options` / `digest_poll_votes`, `digest_read_status`. Blueprint `chat_bp` is mounted at both `/api/chat` and `/api/digest`; React page at `frontend/src/pages/Digest`.

**Consequence — Happy does not build a feed, a channel model, a reaction model, or a poll.** The `feed` placement in §4 is implemented as *publishing a `digest_posts` row of type `announcement` into a target channel* and storing the resulting `post_id` on the campaign. Happy is the layer Digest lacks:

| Capability | Digest today | Happy adds |
|---|---|---|
| Audience targeting | channel-level, company or org node only | campaign-level, 8 dimensions, include/exclude, materialized per user |
| Read tracking | `digest_read_status` = **channel-level watermark** (`last_read_post_id`) | **per-item impression, ≥8s read, click, dwell** |
| Acknowledgement | none | click + comprehension quiz, deadline, escalation ladder |
| Frequency capping | none | per-user, per-placement, per-day and per-week |
| Interstitial / banner surfaces | none | Spotlight + Marquee |
| Analytics | none | reach funnel, rollups, hygiene alarms |
| New-joiner inheritance | none | yes |
| Retention controls | none | 30-day raw-event purge |

Add `happy.campaigns.digest_post_id INTEGER REFERENCES digest_posts(id) ON DELETE SET NULL` and, when `'feed' = ANY(placements)`, publish through the existing Digest service rather than a new one. Reactions and comments stay Digest's. Read/ack analytics stay Happy's.

**Chat.** `jarvis/chat/` is a live chat/DM subsystem under active redesign (`feature/hub-chat-redesign`). Happy must not touch it. It is a delivery channel at most, and not in Phase 1.

**`hr_dept_pulse_votes` — an existing, non-anonymous pulse.** Columns: `voter_user_id`, `department_node_id`, `perspective`, `competency_key`, `rating 1–5`, `UNIQUE (voter_user_id, department_node_id, perspective, competency_key)`. It stores a named employee's rating of a department. Two consequences:

1. **Naming collision.** Pulse uses schema `happy` and the table `happy.pulses`; there is no physical collision, but the two must be distinguished in the UI or users will not know which one is anonymous. Pulse ships with the anonymity notice on screen (§7.5); the existing feature must be relabelled so the difference is explicit.
2. **Pre-existing privacy exposure.** `hr_dept_pulse_votes` is identifiable rating data on a per-person basis and falls under Law 190/2018 Art. 5 exactly as described in §9. Phase 0 must report whether it is covered by an existing information notice and consultation. This is not Happy's bug, but Happy's DPO review is when it surfaces, and it should not be allowed to contaminate Happy's anonymity claims.

> **Phase 0 finding (2026-08-23):** confirmed identifiable — `hr_dept_pulse_votes.voter_user_id` FK → `users(id)`, `department_node_id` → `sincron_org_nodes(id)` (Sincron org node, **not** `structure_nodes`), `UNIQUE(voter_user_id, department_node_id, perspective, competency_key)` (`schema_incremental.py:2529`). Backend is **live** (`core/profile/routes.py` `GET/POST /api/dept-pulse`, `DeptPulseRepository`, tests in `jarvis/tests/dept_pulse/`) but has **no frontend consumer**, and **no information notice or consultation record was found** near the table or routes. Anonymity is presentation-only (a `MIN_VOTERS=3` aggregate floor). Route this pre-existing Art. 5 exposure to the DPO; Pulse (§7.5) must be visibly distinct from it.

**Missing and required (build):** campaign entity, audience resolver, surface resolver, ack/quiz, kudos ledger, pulse with anonymity thresholds, analytics rollups, admin console.

---

## 4. The surface engine — the core primitive

Everything visible to an employee comes from **one campaign entity** rendered into **one of five placements**. The client never decides what to show; the client asks the server for a surface and renders whatever comes back. This is the single most important architectural decision in the module: it makes frequency capping, targeting, ack-state and A/B behaviour server-side, testable, and identical between web and Android.

```
GET /api/happy/surface?placement=interstitial&route=/app/hub
        │
        ▼
 SurfaceResolver.resolve(user, placement, route)
        │
        ├─ 1. eligible campaigns  (status=live, now within [starts_at, ends_at], placement in placements)
        ├─ 2. audience match      (materialized happy.campaign_targets — O(1) index lookup)
        ├─ 3. state filter        (not acknowledged, not dismissed, snooze expired)
        ├─ 4. route guard         (placement allowed on this route; never mid-flow)
        ├─ 5. frequency cap       (happy.frequency_ledger — per placement, per day, per week)
        ├─ 6. priority sort       (critical > important > normal, then ack_deadline_at ASC, then created_at DESC)
        └─ 7. slice              (interstitial: 1 · dash_banner: 3 · hub_card: 5 · feed: 20)
```

**Contract (identical on web and mobile):**

```jsonc
{
  "placement": "interstitial",
  "items": [{
    "id": 412,
    "kind": "hr_announcement",           // hr_announcement|event|action|policy|survey|recognition
    "tier": "important",                  // critical|important|normal
    "kicker": "HR · Beneficii",
    "title": "Noul pachet de beneficii intră în vigoare pe 1 septembrie",
    "body_md": "…",                       // markdown, rendered with react-markdown + remark-gfm
    "summary": "Alegerea se face până pe 25 august.",
    "media": { "key": "private/happy/2026/08/benefits.webp", "url": "/api/media/private/happy/2026/08/benefits.webp",
               "w": 1200, "h": 400, "alt": "…" },
    "cta": { "label": "Alege pachetul", "href": "/app/forms/benefits-2026",
             "deeplink": "com.jarvis.mobile2://forms/benefits-2026" },
    "ack": { "mode": "quiz", "deadline_at": "2026-08-25T21:00:00Z",
             "questions": 3, "state": "pending" },
    "dismissible": false,
    "snooze_remaining": 2,
    "impression_token": "eyJhbGciOi…"     // signed, 10-min TTL, required to POST events
  }],
  "meta": { "capped": false, "next_eligible_at": null }
}
```

`impression_token` is a signed short-lived token minted by the resolver. Event POSTs are rejected without it. This prevents client-side inflation of read/ack analytics — which matters because those numbers will be used in a legally-consequential compliance report.

---

## 5. SPEC A — Spotlight (the HR pop-up)

### 5.1 Purpose
One high-salience, low-frequency interruption for content that genuinely cannot be missed: policy changes with a legal deadline, benefits enrolment windows, mandatory training, safety notices, major company announcements. Not for events. Not for recognition. Not for surveys.

### 5.2 Placement and trigger rules — non-negotiable

| Rule | Value | Rationale |
|---|---|---|
| Eligible routes | `/app/hub`, `/app/dashboard`, mobile home tab **only** | never interrupt a task in progress |
| Blocked contexts | any form in a dirty state, any modal already open, check-in/punch flow, approval decision flow, invoice editor, first 3s after app mount | interruption during a transaction is the #1 driver of reflexive dismissal |
| Max per session | 1 | |
| Max per user per 24h | 1 for `normal`/`important`; `critical` may add **1 more, max 2/day absolute**, and every critical show writes an audit row | Teams priority-message pattern, bounded |
| Max per user per 7 days | 3 | derived from the 4–6/week comms optimum |
| Cooldown after dismissal | 24h snooze; max 3 snoozes | |
| After 3rd snooze | campaign converts to a **persistent Hub card** and stops interrupting | preserves reach without escalating annoyance |
| Past `ack_deadline_at`, still unacknowledged | becomes non-dismissible **on `/app/hub` only** — never on mobile home, never on Dashboard | contains the blocking behaviour to one surface |
| Never shown | on first login after password reset, during onboarding wizard, on any `/public/*` route | |

### 5.3 Visual specification

Anti-banner-blindness rules apply: **content-styled, not ad-styled. No animation. No gradient. No full-bleed brand colour block. No text baked into the image.**

**Desktop / tablet ≥768px — centered modal**

| Property | Value |
|---|---|
| Overlay | `bg-background/80 backdrop-blur-sm`, no fade longer than 150ms |
| Container | shadcn `Dialog`, `max-w-[560px]`, `rounded-2xl`, `border`, `shadow-lg`, `bg-card` |
| Padding | `p-0` on container; content `px-6 py-5` |
| Media | optional, top, full-width, `aspect-[3/1]`, `object-cover`, `rounded-t-2xl`. Max 1200×400, WebP, ≤200 KB |
| Kicker | `text-xs font-medium uppercase tracking-wide text-muted-foreground`, format `{ICON} {Module} · {Category}`, lucide icon 14px |
| Tier chip | `critical` → `Badge variant="destructive"` "Obligatoriu"; `important` → `Badge variant="secondary"`; `normal` → no chip |
| Title | `text-lg font-semibold leading-snug`, **max 64 chars**, 2 lines max, no truncation — enforce at authoring time |
| Body | `text-sm text-muted-foreground`, markdown via `react-markdown` + `remark-gfm`, **max 600 chars visible**, overflow → "Citește tot" expands in place (no navigation) |
| Deadline strip | shown only when `ack.deadline_at` set: `Clock` icon 14px + `Termen: 25 august, 21:00` + relative `(în 2 zile)`; turns `text-destructive` at <24h |
| Primary CTA | `Button` full-width on mobile, auto on desktop. Label from campaign, **max 24 chars** |
| Ack control | see §5.4 |
| Secondary | `Button variant="ghost"` — `Mai târziu` (snooze) — hidden when `dismissible:false` |
| Close X | top-right `Button variant="ghost" size="icon"`, **hidden when `dismissible:false`** |
| Footer meta | `text-xs text-muted-foreground` — `Publicat de {author} · {relative date}` |

**Mobile <768px — bottom sheet**

| Property | Value |
|---|---|
| Container | `Drawer`/`Sheet side="bottom"`, `rounded-t-3xl`, `max-h-[88vh]`, internal scroll |
| Grabber | 36×4px `bg-muted` pill, `mt-3` |
| Media | `aspect-[16/9]` |
| CTA | full-width, `h-12`, sticky to sheet bottom with `border-t bg-card` when content scrolls |
| Safe area | `pb-[env(safe-area-inset-bottom)]` |
| Gesture | swipe-down = snooze, **disabled** when `dismissible:false` |

**Android (native APK)** — same contract, `BottomSheetDialogFragment`, `skipCollapsed=true`, `isCancelable = dismissible`, Material3 tokens mapped to the same palette. Consumes `/api/mobile/happy/surface`.

### 5.4 Acknowledgement modes

| `ack_mode` | Behaviour |
|---|---|
| `none` | CTA closes. Impression + click logged. |
| `click` | CTA is a labelled confirmation — `Am citit și am înțeles` — with an explicit `Checkbox` above it that must be ticked to enable the button. A single unticked click is not an acknowledgement in any audit that matters. |
| `quiz` | **Comprehension check.** 1–5 single-choice questions rendered after the body. Wrong answer → inline reveal of the correct one + forced re-selection (no penalty, no score shown to the user). Ack recorded only when all questions are correct. **Reporting is aggregate + per-question accuracy only — never per-person answers.** This is both the GDPR-safe design and the market's rarest feature. |

**Escalation ladder for unacknowledged mandatory campaigns:**

| T+ | Action | Channel |
|---|---|---|
| 0 | Spotlight + in-app notification | app |
| 48h | Re-surface (snooze reset once) + push, category `happy_announce` | app + push |
| 5 days | Email to employee | email |
| 7 days | Email to employee **and** direct manager (resolved via `department_structure`), naming only the employee, no read history | email |
| `deadline_at` | Non-dismissible on `/app/hub` + one `critical`-category push (bypasses quiet hours) | app + push |
| `deadline_at + 3d` | Compliance export row for HR; no further employee-facing escalation | report |

Every step is configurable per campaign and every step off the default writes an audit row. Escalation past step 4 requires `happy.campaigns.escalate` permission.

### 5.5 New-joiner inheritance
Any campaign with `ack_mode != 'none'` and `status='live'` is **automatically assigned to users created after publication** whose attributes match the audience rules, at the nightly `happy_refresh_targets` job and on first login. Simpplr is the only vendor that ships this. It is ~30 lines of SQL and it is the difference between a compliance record that holds up and one that does not.

### 5.6 Accessibility
`role="alertdialog"` for `critical`, `role="dialog"` otherwise; `aria-modal="true"`; focus trapped, first focus on the title, restored on close; Esc = snooze, never ack; full keyboard path to ack; `prefers-reduced-motion` kills the 150ms transition; contrast ≥4.5:1 in both themes; all imagery has meaningful `alt` (decorative → `alt=""`).

---

## 6. SPEC B — Marquee (the dashboard banner)

### 6.1 Purpose
Ambient, non-blocking promotion of internal events and calls to action: team events, training sign-ups, blood drives, open enrolment, referral programmes, survey invitations, deadline reminders. Advertises; never blocks.

### 6.2 Placements
1. **Dashboard** — first cell of the `react-grid-layout` widget grid, full row width, above all other widgets. Registered as widget id `happy_marquee` in `frontend/src/pages/Dashboard/widgets.tsx`, default-enabled, user-hideable via `CustomizeSheet`.
2. **Hub** — top of the right-hand column in `frontend/src/pages/Hub/index.tsx`, above the Notifications card.
3. **Mobile home** — first card below the greeting; data arrives inside the existing `/api/mobile/dashboard` payload as a `happy.marquee[]` block. **No extra request.**

Explicitly *not* placed in the app chrome, the sidebar, or a sticky top bar. See §1.3.

### 6.3 Visual specification

| Property | Desktop | Mobile |
|---|---|---|
| Container | `Card` — `rounded-xl border bg-card`, **no gradient, no coloured fill** | same |
| Height | 128px fixed | 88px (text-only) / 176px (with media, stacked) |
| Layout | `flex` — media 33% left, content 67% right | stacked: media top `aspect-[3/1]`, content below |
| Media | `object-cover`, `rounded-l-xl`, 1200×400 source | `rounded-t-xl` |
| Kicker | lucide icon 14px + `text-xs uppercase tracking-wide text-muted-foreground` | same |
| Title | `text-base font-semibold`, **max 56 chars**, 1 line, `truncate` | `text-sm`, 2 lines `line-clamp-2` |
| Body | `text-sm text-muted-foreground`, **max 110 chars**, 1 line `truncate` | hidden |
| Date chip | `Badge variant="outline"` — `24 sep · 18:00` when `event_at` present | same |
| CTA | `Button size="sm"` right-aligned, label ≤20 chars | full-width `size="sm"` below text |
| Dismiss | `X` ghost icon, top-right, appears on hover (desktop) / always (mobile) | |
| Pager | when >1 item: `‹ 1/3 ›` bottom-right, `text-xs`. **Manual only — no autoplay, no carousel timer.** | swipe horizontally, dots |
| Empty state | widget renders `null` and collapses its grid row — never an empty card | |
| Skeleton | `Skeleton` at exact final height to prevent layout shift | |

### 6.4 Behaviour
- Max 3 items. Selection and ordering come from the surface resolver (§4), never from the client.
- Dismiss persists **7 days** per item per user (`happy.campaign_state`), then the item may return once if still live. Second dismissal is permanent for that user.
- Click → `POST /api/happy/events {type:'click'}` then navigate. Web uses `href`, Android uses `deeplink`.
- Impression logged once per item per session (deduped by `impression_token`).
- Dwell tracked with `IntersectionObserver` at ≥50% visibility; **≥8 seconds counts as a read** — this is the industry read-rate definition and the metric Happy reports.
- Events auto-generate: a nightly job creates `normal`-tier draft Marquee campaigns from `hr.events` rows starting within 14 days, targeted to `company`/`brand` matching the event row. Drafts, never auto-published — a human presses publish.

### 6.5 Authoring constraints enforced server-side
Reject on save, do not truncate at render: title ≤56 chars (Marquee) / ≤64 (Spotlight), body ≤110 (Marquee) / ≤600 (Spotlight), CTA label ≤20/24, image ≤200 KB after conversion, image aspect within 2.5:1–3.5:1, `alt` text required and ≥10 chars, `ends_at` required and ≤90 days from `starts_at`.

---

## 7. Data model

Schema `happy`. All DDL in `jarvis/migrations/domains/schema_happy.py`, idempotent, following the existing `CREATE TABLE IF NOT EXISTS` + `DO $$ ... information_schema` guard convention.

### 7.1 Campaigns & delivery

```sql
CREATE SCHEMA IF NOT EXISTS happy;

CREATE TABLE IF NOT EXISTS happy.campaigns (
    id              SERIAL PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    kind            TEXT NOT NULL,              -- hr_announcement|event|action|policy|survey|recognition
    tier            TEXT NOT NULL DEFAULT 'normal',   -- critical|important|normal
    placements      TEXT[] NOT NULL,            -- {interstitial,dash_banner,hub_card,feed,push,email}
    locale          TEXT NOT NULL DEFAULT 'ro',
    kicker          TEXT,
    title           TEXT NOT NULL,
    summary         TEXT,
    body_md         TEXT,
    media_key       TEXT,                       -- DO Spaces key under private/happy/…, served via /api/media/<key>
    media_alt       TEXT,
    cta_label       TEXT,
    cta_href        TEXT,
    cta_deeplink    TEXT,
    event_at        TIMESTAMPTZ,                -- for event campaigns
    ack_mode        TEXT NOT NULL DEFAULT 'none',     -- none|click|quiz
    ack_deadline_at TIMESTAMPTZ,
    dismissible     BOOLEAN NOT NULL DEFAULT TRUE,
    escalation      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'draft',    -- draft|scheduled|live|paused|archived
    starts_at       TIMESTAMPTZ,
    ends_at         TIMESTAMPTZ,                -- REQUIRED at publish; <= starts_at + 90 days
    digest_post_id  INTEGER REFERENCES public.digest_posts(id) ON DELETE SET NULL,  -- set when 'feed' in placements
    source_type     TEXT,                       -- hr_event|manual|pulse|system
    source_id       INTEGER,
    created_by      INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    approved_by     INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_happy_campaigns_live
    ON happy.campaigns (status, starts_at, ends_at) WHERE status = 'live';
CREATE INDEX IF NOT EXISTS idx_happy_campaigns_placements
    ON happy.campaigns USING GIN (placements);

-- Declarative audience rules (authoring representation)
CREATE TABLE IF NOT EXISTS happy.campaign_audience (
    id          SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    mode        TEXT NOT NULL,        -- include|exclude
    dimension   TEXT NOT NULL,        -- company|brand|department|subdepartment|org_unit|role|contract_status|user
    value       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_happy_audience_campaign ON happy.campaign_audience(campaign_id);

-- Materialized resolved audience. Refreshed at publish + nightly (new-joiner inheritance).
CREATE TABLE IF NOT EXISTS happy.campaign_targets (
    campaign_id INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (campaign_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_happy_targets_user ON happy.campaign_targets(user_id);

-- Per-user per-campaign UI state (dismissals, snoozes). Not analytics.
CREATE TABLE IF NOT EXISTS happy.campaign_state (
    campaign_id     INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    snooze_count    SMALLINT NOT NULL DEFAULT 0,
    snoozed_until   TIMESTAMPTZ,
    dismiss_count   SMALLINT NOT NULL DEFAULT 0,
    dismissed_until TIMESTAMPTZ,
    first_seen_at   TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (campaign_id, user_id)
);
```

### 7.2 Acknowledgement & comprehension

```sql
-- Compliance record. Legal basis = contract/legal obligation, NOT monitoring.
-- Retained per the document-retention policy, not the 30-day analytics cap.
CREATE TABLE IF NOT EXISTS happy.acknowledgements (
    id              SERIAL PRIMARY KEY,
    campaign_id     INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    method          TEXT NOT NULL,        -- click|quiz
    surface         TEXT NOT NULL,        -- interstitial|hub_card|feed|email
    attempts        SMALLINT DEFAULT 1,
    UNIQUE (campaign_id, user_id)
);

CREATE TABLE IF NOT EXISTS happy.quiz_questions (
    id           SERIAL PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    position     SMALLINT NOT NULL,
    prompt       TEXT NOT NULL,
    options      JSONB NOT NULL,          -- ["a","b","c"]
    correct_index SMALLINT NOT NULL,
    CHECK (position BETWEEN 1 AND 5)
);

-- AGGREGATE ONLY. No user_id. Ever.
CREATE TABLE IF NOT EXISTS happy.quiz_question_stats (
    question_id   INTEGER PRIMARY KEY REFERENCES happy.quiz_questions(id) ON DELETE CASCADE,
    attempts      INTEGER NOT NULL DEFAULT 0,
    first_correct INTEGER NOT NULL DEFAULT 0
);
```

### 7.3 Analytics — the retention-sensitive layer

```sql
-- RAW EVENTS. 30-day hard retention (Law 190/2018 Art. 5). Purged nightly.
CREATE TABLE IF NOT EXISTS happy.campaign_events (
    id           BIGSERIAL PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    surface      TEXT NOT NULL,
    event_type   TEXT NOT NULL,     -- impression|read|click|dismiss|snooze|ack|push_sent|push_open
    dwell_ms     INTEGER,
    platform     TEXT,              -- web|android
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_happy_events_campaign_day
    ON happy.campaign_events (campaign_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_happy_events_purge ON happy.campaign_events (created_at);

-- ROLLUP. Survives the purge. No user_id — aggregate by cohort only.
CREATE TABLE IF NOT EXISTS happy.campaign_daily_stats (
    campaign_id  INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
    day          DATE NOT NULL,
    cohort_key   TEXT NOT NULL DEFAULT 'all',   -- 'all' | 'dept:Vanzari' | 'company:AutoWorld'
    targeted     INTEGER NOT NULL DEFAULT 0,
    reached      INTEGER NOT NULL DEFAULT 0,    -- ≥1 impression
    read_8s      INTEGER NOT NULL DEFAULT 0,
    clicked      INTEGER NOT NULL DEFAULT 0,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    dismissed    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (campaign_id, day, cohort_key)
);

-- Frequency governor. Feeds the resolver's cap check.
CREATE TABLE IF NOT EXISTS happy.frequency_ledger (
    user_id     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    placement   TEXT NOT NULL,
    shown_count SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day, placement)
);
```

### 7.4 Recognition (Praise)

Two-currency model, copied from the only implementation with published mechanics.

```sql
CREATE TABLE IF NOT EXISTS happy.value_tags (
    id       SERIAL PRIMARY KEY,
    slug     TEXT UNIQUE NOT NULL,
    label_ro TEXT NOT NULL,
    label_en TEXT NOT NULL,
    icon     TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order SMALLINT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS happy.wallets (
    user_id            INTEGER PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    giveable_balance   INTEGER NOT NULL DEFAULT 0,   -- expires monthly, cannot be self-redeemed
    giveable_period    CHAR(7) NOT NULL,             -- 'YYYY-MM'
    redeemable_balance INTEGER NOT NULL DEFAULT 0,   -- earned, never expires
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS happy.kudos (
    id          SERIAL PRIMARY KEY,
    from_user   INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    to_user     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    value_tag_id INTEGER REFERENCES happy.value_tags(id) ON DELETE SET NULL,
    note        TEXT NOT NULL,                      -- CHECK length >= 40
    points      INTEGER NOT NULL DEFAULT 0,
    visibility  TEXT NOT NULL DEFAULT 'company',    -- company|department|private
    period      CHAR(7) NOT NULL,
    flagged     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (from_user <> to_user),
    CHECK (char_length(note) >= 40)
);
CREATE INDEX IF NOT EXISTS idx_happy_kudos_to ON happy.kudos(to_user, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_happy_kudos_period ON happy.kudos(period, from_user);

CREATE TABLE IF NOT EXISTS happy.point_ledger (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    bucket      TEXT NOT NULL,          -- giveable|redeemable
    delta       INTEGER NOT NULL,
    reason      TEXT NOT NULL,          -- monthly_grant|expiry|kudos_sent|kudos_received|redemption|adjustment
    kudos_id    INTEGER REFERENCES happy.kudos(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS happy.kudos_flags (
    id         SERIAL PRIMARY KEY,
    kudos_id   INTEGER NOT NULL REFERENCES happy.kudos(id) ON DELETE CASCADE,
    rule       TEXT NOT NULL,           -- reciprocity|burst|duplicate_text|deadline_dump|cap_exceeded
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Economy rules (configurable, these are the defaults):**

| Rule | Default | Source of the number |
|---|---|---|
| Monthly giveable allowance | 100 points | market default |
| Point value | 1 point = 0.5 RON, unfunded at launch | |
| Giveable expiry | last day of month, 23:59 Europe/Bucharest | removes hoarding |
| Redeemable expiry | none | |
| Manager top-up | +25 points × direct reports | scales budget to span of control |
| Self-award | impossible by schema | `CHECK (from_user <> to_user)` |
| Mandatory note | ≥40 characters | verbal recognition d=+0.33; a note is the mechanism |
| Mandatory value tag | yes | ties recognition to stated company values |
| Points for platform activity (posting, reading, logging in) | **zero, ever** | expected contingent rewards d=−0.36 |

**Published anti-gaming rules** — no vendor documents these; publishing them in-app is itself the trust feature:
1. Max **3 kudos to the same recipient per giver per month**; 4th is blocked with an explanation.
2. **Reciprocity detector** — if A→B and B→A exceed 4 exchanges in 60 days, both are flagged and points on the excess are voided pending HR review.
3. **Burst detector** — >8 kudos from one giver in 60 minutes flags the batch.
4. **Duplicate-text detector** — Levenshtein similarity >0.9 against that giver's last 10 notes → rejected at submit with "scrie ceva specific".
5. **Deadline-dump detector** — >50% of a giver's monthly allowance spent in the final 48h of the month flags the batch for review (points still land; the pattern is reported).
6. **No leaderboards.** The only rankings that exist are `top value tags this month` (aggregate) and the user's **own** streak/trend.

### 7.5 Pulse (surveys / eNPS)

The anonymity architecture is the whole product here. **`happy.pulse_responses` has no `user_id` column and no foreign key that can reconstruct one.**

```sql
CREATE TABLE IF NOT EXISTS happy.pulses (
    id                   SERIAL PRIMARY KEY,
    slug                 TEXT UNIQUE NOT NULL,
    title                TEXT NOT NULL,
    cadence              TEXT NOT NULL,      -- weekly|biweekly|monthly|quarterly|adhoc
    question_count       SMALLINT NOT NULL DEFAULT 5,
    -- Anonymity settings: LOCKED once status leaves 'draft'. Enforced by trigger.
    min_group_size       SMALLINT NOT NULL DEFAULT 5,
    min_comment_group    SMALLINT NOT NULL DEFAULT 10,
    indirect_protection  BOOLEAN NOT NULL DEFAULT TRUE,
    settings_locked_at   TIMESTAMPTZ,
    status               TEXT NOT NULL DEFAULT 'draft',
    opens_at             TIMESTAMPTZ,
    closes_at            TIMESTAMPTZ,
    created_by           INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS happy.pulse_questions (
    id        SERIAL PRIMARY KEY,
    pulse_id  INTEGER NOT NULL REFERENCES happy.pulses(id) ON DELETE CASCADE,
    position  SMALLINT NOT NULL,
    prompt_ro TEXT NOT NULL,
    prompt_en TEXT,
    qtype     TEXT NOT NULL,     -- likert5|enps|single|open
    driver    TEXT               -- manager|recognition|growth|alignment|workload|wellbeing|ambassadorship
);

-- Invite list: exists ONLY to send and to remind. Deleted at pulse close.
CREATE TABLE IF NOT EXISTS happy.pulse_invites (
    pulse_id  INTEGER NOT NULL REFERENCES happy.pulses(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    responded BOOLEAN NOT NULL DEFAULT FALSE,   -- boolean only; never joined to responses
    PRIMARY KEY (pulse_id, user_id)
);

-- NO user_id. cohort_key is coarse and validated to have >= min_group_size members
-- BEFORE any row is written; otherwise it is rolled up to the parent unit.
CREATE TABLE IF NOT EXISTS happy.pulse_responses (
    id         BIGSERIAL PRIMARY KEY,
    pulse_id   INTEGER NOT NULL REFERENCES happy.pulses(id) ON DELETE CASCADE,
    cohort_key TEXT NOT NULL,
    answers    JSONB NOT NULL,     -- {"q1":4,"q2":9,"q3":"..."}
    created_at DATE NOT NULL DEFAULT CURRENT_DATE   -- DATE, not timestamp: no time-of-day fingerprint
);
CREATE INDEX IF NOT EXISTS idx_happy_pulse_resp ON happy.pulse_responses(pulse_id, cohort_key);
```

**Rules:**
- Defaults: reporting minimum **5**, comments minimum **10**, indirect-identification protection **on**. These are the published EU norms and Viva Glint's defaults.
- Thresholds are **immutable after launch** and are **shown to the respondent before they answer**, on the intake screen. Both are trust features and both are cheap.
- Cohort assignment happens server-side at submit: the user's department is checked against live headcount; if the unit has fewer than `min_group_size` active members, `cohort_key` is set to the parent unit. The narrow value is never written.
- `created_at` is a `DATE`. A timestamp plus a small team is a re-identification vector.
- Participation is reported as **a count and a rate**, never a name list. `pulse_invites` is dropped at close.
- Cadence-to-length mapping: weekly = 5 questions, bi-weekly = 10, monthly = 20. Never exceed.
- eNPS is never shipped alone; it is always rendered next to its driver breakdown.

### 7.6 Notification preferences

```sql
-- Category-level consent. OS push permission is NOT valid GDPR consent for
-- non-operational categories (ePrivacy Art. 5(3) + EDPB 2/2023).
CREATE TABLE IF NOT EXISTS happy.user_prefs (
    user_id            INTEGER PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    allow_announce     BOOLEAN NOT NULL DEFAULT TRUE,   -- operational, Art. 6(1)(b)
    allow_recognition  BOOLEAN NOT NULL DEFAULT TRUE,
    allow_pulse        BOOLEAN NOT NULL DEFAULT TRUE,
    allow_social       BOOLEAN NOT NULL DEFAULT TRUE,   -- birthdays, anniversaries
    digest_only        BOOLEAN NOT NULL DEFAULT FALSE,
    quiet_start        TIME DEFAULT '20:00',
    quiet_end          TIME DEFAULT '08:00',
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

`critical`-tier campaigns bypass `allow_*` and quiet hours. Every bypass writes an audit row naming the campaign and the authorising admin. That audit trail is what makes the bypass defensible.

---

## 8. API surface

All web routes session-authenticated via Flask-Login and gated on `permissions_v2`. All mobile routes JWT-authenticated via the existing `@jwt_required` decorator in `core/mobile/routes/_shared.py`. **One service layer, two transports.**

### 8.1 Employee-facing

| Method | Path | Notes |
|---|---|---|
| GET | `/api/happy/surface?placement=&route=` | the resolver (§4). Cached 30s per user per placement. |
| POST | `/api/happy/events` | `{impression_token, type, dwell_ms?}`. Rejected without a valid token. |
| POST | `/api/happy/campaigns/<id>/ack` | `{method, answers?}`. Idempotent. |
| POST | `/api/happy/campaigns/<id>/snooze` | server enforces max 3 |
| POST | `/api/happy/campaigns/<id>/dismiss` | |
| GET | `/api/happy/feed?cursor=` | paged campaign feed + kudos + moments |
| GET | `/api/happy/inbox` | open acknowledgements for this user, sorted by deadline |
| GET | `/api/happy/praise/wallet` | own balances + expiry countdown |
| POST | `/api/happy/praise/kudos` | validates note length, tag, caps, anti-gaming |
| GET | `/api/happy/praise/received?cursor=` | own received kudos |
| GET | `/api/happy/praise/me` | own streak + own 12-week trend. **No peer comparison.** |
| GET | `/api/happy/pulse/current` | current open pulse + the anonymity notice text |
| POST | `/api/happy/pulse/<id>/respond` | idempotent per user per pulse via `pulse_invites.responded` |
| GET/PUT | `/api/happy/prefs` | category consent |
| GET | `/api/mobile/happy/surface` | JWT twin of the resolver |
| — | `/api/mobile/dashboard` **(extend)** | add `happy: {marquee:[], open_acks:n, kudos_unseen:n}` — no new round-trip |
| GET | `/go/happy/<id>` | deep-link landing, reuses `core/deeplink/routes.py` UA split |

### 8.2 Admin (Happy Board)

| Method | Path | Permission |
|---|---|---|
| GET/POST/PUT | `/api/happy/admin/campaigns[/<id>]` | `happy.campaigns.edit` |
| POST | `/api/happy/admin/campaigns/<id>/publish` | `happy.campaigns.publish` |
| POST | `/api/happy/admin/campaigns/<id>/preview-audience` | returns **count + cohort breakdown only, never a name list** |
| POST | `/api/happy/admin/campaigns/<id>/escalate` | `happy.campaigns.escalate` — audited |
| GET | `/api/happy/admin/campaigns/<id>/stats` | rollups only; raw events never exposed via API |
| GET | `/api/happy/admin/campaigns/<id>/compliance-export` | `happy.compliance.export` — the ack list, the one legitimate per-person export, audited |
| GET/POST | `/api/happy/admin/pulses[/<id>]` | `happy.pulse.manage` |
| GET | `/api/happy/admin/pulses/<id>/results` | threshold-enforced; suppressed cohorts return `{suppressed:true, reason:'below_min_group_size'}` |
| GET | `/api/happy/admin/praise/flags` | `happy.praise.moderate` |
| GET | `/api/happy/admin/health` | the KPI board of §2 |

### 8.3 Permissions to seed in `permissions_v2`

```
happy.campaigns.view       (scope: own|department|all)
happy.campaigns.edit
happy.campaigns.publish
happy.campaigns.escalate
happy.compliance.export
happy.pulse.manage
happy.pulse.results        (scope: department|all)
happy.praise.moderate
happy.praise.grant         (manual point adjustments)
happy.admin                (settings, categories, value tags)
```

---

## 9. Legal & governance — mandatory, not optional

This section is a build requirement. Skipping it is the fastest way to turn an engagement module into a labour-inspection finding.

### 9.1 Romanian Law 190/2018 Art. 5 — four cumulative conditions
Individual-level impressions, read events, acknowledgement timestamps and activity analytics are **employee monitoring**. All four must hold:

1. **Prior explicit information.** Ship an in-app "Cum funcționează Happy" page listing exactly what is recorded, for how long, and who can see it. Link it from the Spotlight footer and the prefs screen. Written before launch, not after.
2. **Documented legitimate interest.** Produce a written LIA (legitimate interest assessment) covering the compliance purpose of acknowledgement records. Store it with the DPO file.
3. **Prior consultation of employee representatives.** Law 367/2022 makes representatives mandatory at ≥10 employees; failure to inform/consult carries RON 15,000–20,000. Consultation happens **before launch**, is minuted, and the minutes are attached to the LIA.
4. **Subsidiarity.** Document why less intrusive measures (email-only, no receipts) do not meet the compliance need.

Plus: **30-day retention cap** on `happy.campaign_events`. Enforced by a nightly `DELETE` job, not by policy prose. `happy.acknowledgements` is retained longer under a separate legal basis (compliance record) and that distinction is written into the privacy notice.

### 9.2 Push notifications
OS-level permission prompts are **not** valid GDPR consent for non-operational categories — they do not distinguish categories and carry no withdrawal path. Hence `happy.user_prefs` with per-category toggles and in-app withdrawal. Operational announcements ride Art. 6(1)(b)/(f); recognition and social ride the toggle. Note that the legitimate-interest balance is explicitly contingent on **frequency and app design** — over-notifying does not merely annoy people, it erodes the legal basis. This is the second, independent reason for the caps in §5.2.

### 9.3 Pulse
DPA in place with any sub-processor; EU data residency; participation voluntary and never tracked per person beyond the boolean; purpose and anonymity thresholds disclosed **before** the first question; thresholds immutable after launch.

### 9.4 Hard prohibitions in code
- No API returns a per-person read/impression history to anyone, including admins. Only `compliance-export` returns per-person acknowledgement state, and only under its own permission, and every call is audited.
- No endpoint ranks named employees by any engagement metric.
- No manager-facing screen shows an individual's activity, only their team's aggregate against the min-group-size threshold.

---

## 10. Metrics — Happy Board

Every tile compares against §2. Computed from `campaign_daily_stats`, never from raw events.

**Reach funnel per campaign:** Targeted → Reached (≥1 impression) → Read (≥8s dwell) → Clicked → Acknowledged. Rendered as a horizontal funnel with absolute numbers and percentages, sliced by cohort (never by person).

**Org health, weekly:** WAU/headcount · Read rate 7-day rolling · Open-ack backlog (count + oldest) · Contributor/Participant/Observer split · Kudos per employee per week · Pulse participation · eNPS trend + driver deltas · Push opt-out rate (leading indicator of over-sending; alarm at >12%).

**Communicator hygiene alarms:**
- >5 campaigns/user/week scheduled → publishing blocked with an explanation, override requires `happy.admin`.
- Read rate <50% on a campaign with >100 targets → flag to author with the title-length and send-time diagnostics.
- Ack rate <60% at deadline−48h → auto-suggest escalation step.
- Any cohort below min group size in a pulse report → suppressed and labelled, never silently merged.

---

## 11. Delivery plan

| Phase | Scope | Est. | Ships value |
|---|---|---|---|
| **0 — Assessment** | Automated codebase + DB assessment, assumptions verified or corrected, go/no-go per integration point | 0.5 day | de-risks everything below |
| **1 — Surface engine (MVP)** | `schema_happy` (campaigns, audience, targets, state, events, daily_stats, frequency_ledger), audience + surface resolvers, Spotlight, Marquee (Dashboard + Hub + mobile payload), ack `click`, admin campaign CRUD + publish, permissions seed, 30-day purge job | 8–10 days | **This alone is the product.** Everything else is expansion. |
| **2 — Compliance depth** | `ack_mode='quiz'`, escalation ladder, new-joiner inheritance, compliance export, audit log | 4–5 days | the market differentiator |
| **3 — Praise** | wallets, kudos, ledger, value tags, anti-gaming rules, Hub + mobile cards, personal streak | 6–7 days | |
| **4 — Pulse** | pulses, anonymity engine, cohort rollup, eNPS + drivers, threshold-enforced reporting | 6–7 days | |
| **5 — Board** | full analytics console, hygiene alarms, benchmark comparisons | 3–4 days | |
| **6 — Android parity** | native Spotlight bottom sheet, Marquee card, Praise send flow, deep links | 5 days | mobile share target of 40% |

**Cut line for the MVP: Phase 1 only.** Announcements that reach the right people, at a capped frequency, with measurable read and acknowledgement, on web and mobile. Ship it, measure it against §2 for four weeks, then decide whether Praise or Pulse comes next based on what the read rate and the open-ack backlog actually say.

---

## 12. Definition of done (applies to every phase)

- `cd jarvis/frontend && npm run build` → exit 0, zero TypeScript errors
- `cd jarvis/frontend && npm run test` → all vitest green
- `pytest jarvis/tests/ -x -q` → all green, Happy suite ≥85% line coverage on `jarvis/happy/`
- `python3 -m py_compile jarvis/app.py` → clean
- Migration is idempotent: run `init_schema` twice against a fresh DB, second run is a no-op
- No table dropped or renamed; `grep -r "<table>" jarvis/` run before any destructive change
- Playwright e2e: Spotlight shows once and only once per 24h; Marquee dismiss persists 7 days; ack is idempotent under double-submit
- Every new endpoint has an explicit permission check and a test that asserts 403 without it
- `happy.campaign_events` purge job verified: insert a 31-day-old row, run job, assert zero rows
- No endpoint anywhere returns a per-person engagement history — asserted by a dedicated test
