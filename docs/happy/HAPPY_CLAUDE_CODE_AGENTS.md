# Happy — Claude Code Orchestration Prompt (VS Code)

**Version:** 1.0 · **Target:** Claude Code running in the VS Code extension, repo root = `JARVIS`
**Companion document:** `docs/happy/HAPPY_MODULE_SPEC.md` (the spec — this file is the process)

---

## HOW TO USE THIS FILE

**Claude Code reads `CLAUDE.md`, not `AGENTS.md`.** Do not rename this file to `AGENTS.md` expecting it to auto-load — it will be silently ignored. This file is a *document Claude reads on instruction*, not a memory file.

Two supported ways to run it, in order of preference:

**A. Slash command (recommended).** `.claude/commands/happy.md` in this repo contains the bootstrap. In VS Code, type `/happy` in the Claude Code prompt box. Nothing loads into context until you invoke it, which keeps every unrelated session clean.

**B. Manual.** Open the `JARVIS` folder in VS Code, open the Claude Code panel, and paste the **BOOTSTRAP MESSAGE** below as your first message. Nothing else.

Either way, before you start: `git status` → must be on `staging` with a clean tree. Never start on `main`, never start on `feature/hub-chat-redesign`.

### BOOTSTRAP MESSAGE

```
Read docs/happy/HAPPY_CLAUDE_CODE_AGENTS.md completely before doing anything else.
Then read docs/happy/HAPPY_MODULE_SPEC.md completely.
Then read docs/CLAUDE.md.

Do not write a single line of application code yet.

Execute PHASE 0 (ASSESSMENT) exactly as specified:
  1. Run scripts/happy_assess.py and read its output.
  2. Verify every claim in HAPPY_MODULE_SPEC.md §3 against the actual code.
  3. Produce docs/happy/HAPPY_ASSESSMENT.md using the template in this file.
  4. Report the GO / NO-GO table and stop.

When Phase 0 is complete, ask me which implementation phase to begin.
```

---

## THE RULE THAT MATTERS MOST

**Phase 0 is not optional and not a formality.** The spec was written from a read of this repository, but a spec is a hypothesis about a codebase. Every assumption in §3 of the spec — the push category pipeline, the permissions v2 seeding pattern, the media proxy signature, the mobile JWT decorator, the Hub layout, the widget registry — is a place where a wrong assumption produces code that compiles, passes review, and fails in production.

Phase 0 converts hypotheses into verified facts and writes them down. Every later agent reads `HAPPY_ASSESSMENT.md` instead of re-deriving them. That single document is what stops fifteen sub-agents from making fifteen different guesses about the same function signature.

Cost of Phase 0: about four hours. Cost of skipping it: a rewrite somewhere in Phase 1, discovered in Phase 3.

---

## PHASE 0 — ASSESSMENT AGENT

**Identity:** `HAPPY-ASSESSOR`
**Model:** highest available reasoning tier. This phase is cheap and its errors are expensive.
**Authority:** read-only on all application code. May write **only** `docs/happy/HAPPY_ASSESSMENT.md`. May run read-only SQL. **May not create, modify or delete any table, column, file or migration.**

### 0.1 Automated inventory

Run the assessment script first. It is deterministic and it produces the raw material for the human-readable report.

```bash
python3 scripts/happy_assess.py --repo . --out docs/happy/HAPPY_ASSESSMENT_RAW.md
# with a database (read-only credentials preferred):
python3 scripts/happy_assess.py --repo . --db "$DATABASE_URL" --out docs/happy/HAPPY_ASSESSMENT_RAW.md
```

### 0.2 Manual verification checklist

For each row: read the actual file, record the **exact signature or DDL**, and mark the status. `ASSUMED` is not an allowed final value — resolve every row to `CONFIRMED`, `DIFFERENT` (with the real fact), or `MISSING`.

| # | Claim to verify | Where to look | Record |
|---|---|---|---|
| 1 | `send_push_to_users` signature and whether `category` gates delivery | `core/notifications/push_service.py` | exact signature + how categories are resolved |
| 2 | Push categories: table name, columns, how quiet hours and rate limits are stored, how `critical` bypass is expressed | `core/notifications/push_service.py`, `migrations/domains/` | table + column list |
| 3 | Whether Happy can register new push categories without a migration | routes `/api/push-manager/categories` | yes/no + how |
| 4 | `notify_with_push` params, and whether `push_data` reaches the Android app as an FCM data payload | `core/notifications/notify.py` | exact signature |
| 5 | `public.notifications` DDL + whether `link` supports app-relative paths | `migrations/domains/schema_approvals.py` | DDL |
| 6 | `BaseRepository` API — `query_all` / `query_one` / `execute` / transaction helper | `core/base_repository.py` | exact methods + how transactions are opened |
| 7 | Migration entry point — how `schema_*.py` modules are called and in what order | `migrations/init_schema.py` | where `create_schema_happy` must be registered |
| 8 | Whether any `CREATE SCHEMA` already exists (the `hr` schema pattern) | `migrations/domains/schema_hr.py` | the exact idiom to copy |
| 9 | `permissions_v2` seeding idiom + how a **new** permission is added to existing DBs | `migrations/domains/schema_roles.py` | the `INSERT … ON CONFLICT DO NOTHING` block to copy |
| 10 | Permission-check decorator used on routes | `core/roles/decorators.py` | exact decorator name + args |
| 11 | Mobile JWT decorator + how the current user is resolved | `core/mobile/routes/_shared.py` | `jwt_required`, `_current_mobile_user` signatures |
| 12 | `/api/mobile/dashboard` response shape — exactly where a `happy` block can be added without breaking the Android client | `core/mobile/routes/dashboard.py` | current JSON keys |
| 13 | **Android client contract** — does the APK tolerate unknown JSON keys? Find the repo/source of the app | search repo + ask user | tolerant / strict; if strict, mobile changes need an app release |
| 14 | Media upload path — how a file gets into DO Spaces and what key format `/api/media/<key>` expects | `core/media/routes.py`, `boto3` usage | upload helper + key convention |
| 15 | Whether an image-resize/convert helper already exists | `core/services/image_compressor.py` | reuse or build |
| 16 | Deep-link scheme and the exact host/path grammar the Android app registers | `core/deeplink/routes.py` | `com.jarvis.mobile2://` paths in use |
| 17 | `users` targeting columns actually populated in production (not just present) | read-only SQL: null-rate per column | % non-null for company/brand/department/subdepartment/org_unit_id |
| 18 | Headcount and department size distribution — **does any department have <5 active users?** | read-only SQL | distribution; drives the pulse rollup rule |
| 19 | Dashboard widget registry — how a widget is declared, defaulted and toggled | `frontend/src/pages/Dashboard/widgets.tsx`, `types.ts`, `useDashboardPrefs.ts` | the registration shape |
| 20 | Hub right-column structure and where a Marquee slot can be inserted without touching unrelated JSX | `frontend/src/pages/Hub/index.tsx` (~line 400–470) | insertion point + line numbers |
| 21 | Frontend API client conventions — error envelope, unwrapping, TanStack Query key convention | `frontend/src/api/client.ts`, any `api/*.ts` | pattern to copy |
| 22 | shadcn components already installed: `dialog`, `drawer`/`sheet`, `badge`, `checkbox`, `progress`, `carousel` | `frontend/src/components/ui/` | present / must add |
| 23 | Theme tokens and whether dark mode is token-driven | `frontend/src/index.css`, `next-themes` usage | token names |
| 24 | i18n: is there a translation layer, or are strings hardcoded Romanian? | grep for `t(` / i18n libs | **this determines whether campaign content is single-locale or dual** |
| 25 | Background scheduler — how a nightly job is registered | `tasks/cleanup.py`, `apscheduler` usage | the registration idiom for the purge + refresh jobs |
| 26 | Test conventions: pytest fixtures for DB, vitest setup, Playwright base URL | `jarvis/conftest.py`, `frontend/src/test/`, `playwright.config.js` | how to write a Happy test |
| 27 | Whether `hr.events` has enough fields to auto-generate event campaigns | `migrations/domains/schema_hr.py` | fields present; note that `hr.events` has no time-of-day or location column |
| 28 | Any existing table or route already named `campaign`, `announcement`, `banner`, `kudos`, `pulse`, `digest` | `grep -rn` | collision risk |
| 29 | **Digest subsystem** — channel model, targeting granularity, post types, read-status semantics, and the service function that creates a post | `jarvis/chat/`, `migrations/domains/schema_digest.py`, `frontend/src/pages/Digest/` | the exact call Happy uses to publish a `feed` placement |
| 30 | **`digest_read_status` semantics** — confirm it is a channel-level watermark, not per-post | `schema_digest.py` | if per-post read tracking already exists, Happy's analytics layer shrinks |
| 31 | **`hr_dept_pulse_votes`** — who built it, is it live, is it covered by an information notice and employee-rep consultation | `schema_incremental.py` L2530, `grep -rn hr_dept_pulse_votes` | pre-existing Art. 5 exposure; must not contaminate Pulse's anonymity claim |
| 32 | Branch state — `git rev-parse --abbrev-ref HEAD` and `git status --porcelain` | — | **Phase 1 must not start on `feature/hub-chat-redesign` or a dirty tree** |

### 0.3 Required output — `docs/happy/HAPPY_ASSESSMENT.md`

```markdown
# Happy Phase 0 — Codebase Assessment
Date: <date> · Commit: <git rev-parse --short HEAD> · Branch: <branch>

## 1. GO / NO-GO
| Integration point | Status | Evidence (file:line) | Impact if wrong |
|---|---|---|---|
| Push pipeline reuse | GO / GO-WITH-CHANGES / NO-GO | | |
| Permissions v2 seeding | | | |
| Mobile payload extension | | | |
| Media upload + proxy | | | |
| Dashboard widget slot | | | |
| Hub slot | | | |
| Nightly job registration | | | |
| Digest reuse for the `feed` placement | | | |
| i18n strategy | | | |

## 2. Verified facts (the contract every later agent uses)
<one line per checklist row: exact signature / DDL / line reference>

## 3. Spec corrections required
<every place HAPPY_MODULE_SPEC.md is wrong about this codebase, with the correction>

## 4. Production data reality
- Active users: N
- Non-null rate: company X% · brand X% · department X% · subdepartment X% · org_unit_id X%
- Departments with <5 active users: <list> → pulse cohorts must roll up to <parent>
- Registered mobile devices: N (= the real ceiling on push reach)

## 5. Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|

## 6. Revised Phase 1 estimate
<days, with the delta from the spec's 8–10 and why>
```

### 0.4 Phase 0 exit criteria
- Zero rows left as `ASSUMED`.
- Every `NO-GO` has either a mitigation or an explicit escalation to the user.
- `HAPPY_MODULE_SPEC.md` §3 has been patched in place with any correction found.
- The report ends with a single sentence: *"Phase 1 may / may not begin."*

**Do not proceed past this point without the user saying so.**

### 0.5 Facts already established (verify, do not re-derive)

These came out of a first run of `scripts/happy_assess.py` on commit `39927b9ae`. Confirm each against the current commit, then treat as contract:

```
core/notifications/push_service.py:217
    send_push_to_users(user_ids, title, body, data=None, category='system', bypass_rules=False)
    -> bypass_rules=True IS the `critical` tier. Every use must write an audit row.

core/notifications/notify.py:75
    notify_with_push(user_ids, title, message=None, link=None, entity_type=None,
                     entity_id=None, type='info', push_data=None, category='system')

core/base_repository.py
    query_one(sql, params=None) | query_all(sql, params=None)
    execute(sql, params=None, returning=False) | execute_many(callback)
    -> NO transaction() helper. Use execute_many(callback) for atomic multi-statement work.

core/roles/decorators.py:8
    @v2_permission_required(module, entity, action)

core/mobile/routes/_shared.py:168,190
    @jwt_required · _current_mobile_user()

migrations: 232 tables declared across schemas public / hr / ai_agent.
Free namespaces: campaign, announcement, banner, kudos, happy, spotlight, marquee.
Collision: hr_dept_pulse_votes (non-anonymous, identifiable) — see spec §3.1.
Existing feed: digest_* (9 tables) + chat_bp at /api/chat and /api/digest — see spec §3.1.
```

---

## AGENT TEAM

Spawn as sub-agents. Each inherits this file and `HAPPY_ASSESSMENT.md`. Each reports in the fixed format below.

### 1. `HAPPY-DBA`
**Owns:** `jarvis/migrations/domains/schema_happy.py` and its registration in `init_schema.py`.
**Must:** copy the existing idempotency idiom exactly (`CREATE TABLE IF NOT EXISTS`, `DO $$ … information_schema` guards for `ALTER`). Every table from spec §7. Every index. The `CHECK` constraints — they are the anti-gaming rules, not decoration.
**Must not:** drop or rename anything. Use an ORM. Add a table not in the spec without MASTER approval.
**Verification:** run `init_schema` twice against a scratch DB; second run must be a clean no-op. Print `\dt happy.*` and diff against spec §7.

### 2. `HAPPY-BACKEND`
**Owns:** `jarvis/happy/` — `routes/`, `services/`, `repositories/`.
**Structure to follow (mirrors the rest of the repo):**
```
jarvis/happy/
├── __init__.py
├── routes/
│   ├── __init__.py          # happy_bp
│   ├── surface.py           # GET /api/happy/surface, POST /api/happy/events
│   ├── ack.py
│   ├── praise.py
│   ├── pulse.py
│   ├── prefs.py
│   ├── admin.py
│   └── mobile.py            # /api/mobile/happy/* — JWT
├── services/
│   ├── audience_resolver.py # rules -> happy.campaign_targets
│   ├── surface_resolver.py  # THE core primitive, spec §4
│   ├── frequency.py         # caps
│   ├── ack_service.py
│   ├── praise_service.py    # two-currency ledger, anti-gaming
│   ├── pulse_service.py     # anonymity engine
│   ├── delivery.py          # wraps core.notifications.notify
│   └── tokens.py            # impression_token mint/verify
├── repositories/
│   └── *.py                 # BaseRepository subclasses, raw SQL, %s params
└── jobs.py                  # refresh_targets, purge_events, rollup_stats, expire_points
```
**Hard rules:**
- Raw SQL with `%s` parameters. No f-string interpolation of any user value into SQL, ever.
- `surface_resolver` is pure and unit-testable: it takes `(user_context, placement, route, now)` and returns items. All I/O behind repository calls.
- Frequency capping calls the **existing** push pipeline for push; it only implements the *placement* caps itself.
- Every route has an explicit permission check. No route relies on "an admin wouldn't call this".
- No endpoint returns per-person engagement history. This is a spec-level prohibition (§9.4) and there is a test for it.
- **The `feed` placement publishes through the existing Digest service.** Do not create a channel model, a post model, a reaction model or a poll. Spec §3.1.
**Cannot without `HAPPY-DBA`:** any schema change.
**Cannot without `HAPPY-DPO`:** any endpoint that returns per-person data, any change to retention, any escalation channel.

### 3. `HAPPY-WEB`
**Owns:** `frontend/src/pages/Happy/`, `frontend/src/components/happy/`, `frontend/src/api/happy.ts`, `frontend/src/types/happy.ts`, plus **surgical** insertions into `pages/Dashboard/widgets.tsx` and `pages/Hub/index.tsx`.
**Components:**
```
components/happy/
├── SpotlightDialog.tsx      # desktop modal + mobile sheet, one component, useIsMobile
├── SpotlightProvider.tsx    # mounts once in App.tsx; owns route guards + surface query
├── MarqueeCard.tsx
├── MarqueeWidget.tsx        # Dashboard registration wrapper
├── AckPanel.tsx             # checkbox+confirm and quiz modes
├── OpenAcksCard.tsx         # Hub card: outstanding acknowledgements
├── PraiseComposer.tsx       # note >= 40 chars enforced client-side AND server-side
├── PraiseFeed.tsx
├── MyPraiseStreak.tsx       # personal trend only. No ranking. Ever.
└── PulseSheet.tsx           # anonymity notice ABOVE the first question
```
**Hard rules:**
- Existing shared components are **wrapped, never edited**: `Card`, `Button`, `Badge`, `Dialog`, `Sheet`, `Skeleton`, `EmptyState`, `MobileCardList`.
- No new npm dependency without MASTER approval. Everything in the spec is buildable with what is installed (`radix-ui`, `lucide-react`, `react-markdown`, `remark-gfm`, `@tanstack/react-query`, `sonner`, `tailwind-merge`).
- No `localStorage` for campaign content or ack state — the server owns that state. `usePersistedState` is acceptable only for pure UI preferences.
- Every visual value comes from spec §5.3 / §6.3. If the spec does not name a value, ask; do not invent.
- Dark mode: token-driven, verified in both themes before handoff.
- `npm run build` and `npm run test` exit 0 before handoff. No exceptions, no "will fix in the next pass".

### 4. `HAPPY-MOBILE`
**Owns:** `/api/mobile/happy/*` and the additive `happy` block inside `/api/mobile/dashboard`.
**Hard rules:** additive only — never rename or remove an existing key in the mobile payload. If Phase 0 found the Android client is strict about unknown keys, the block ships behind a `?v=2` query parameter and the change is coordinated with an app release. Produce a written API contract document for whoever builds the Android side; do not assume they read the Flask source.

### 5. `HAPPY-DPO` (privacy & security — blocking authority)
**Reviews every phase before QA. Can block a merge.**
Checklist, run against the actual diff:
- [ ] 30-day purge job exists, is registered with the scheduler, and has a test that inserts a 31-day-old row and asserts it is deleted
- [ ] `happy.pulse_responses` has no `user_id` and no column that can reconstruct one; `created_at` is `DATE` not `TIMESTAMP`
- [ ] pulse threshold settings are locked after launch (trigger or service-level guard) and are displayed to respondents before question 1
- [ ] cohort rollup fires for any unit below `min_group_size` — tested with a 3-person department
- [ ] no endpoint returns a per-person engagement history; dedicated test asserts this
- [ ] `compliance-export` is permission-gated and writes an audit row per call
- [ ] every `critical`-tier bypass of quiet hours / category prefs writes an audit row naming campaign and authoriser
- [ ] category-level notification prefs exist and are honoured in `delivery.py`
- [ ] the in-app transparency page exists and is linked from Spotlight and prefs
- [ ] no SQL injection surface: every query parameterised
- [ ] `impression_token` is signed, TTL-bounded, and verified server-side before any event is recorded
- [ ] no ranking of named employees exists anywhere in the API or the UI

### 6. `HAPPY-QA`
Writes tests **before** accepting a handoff, not after.
- pytest: `jarvis/tests/happy/` — resolver unit tests (targeting, caps, priority, state), ack idempotency, anti-gaming rules, anonymity rollup, purge job, permission 403s
- vitest: component render + interaction, both themes, mobile and desktop breakpoints
- Playwright: Spotlight appears exactly once per 24h; snooze × 3 converts to a Hub card; Marquee dismissal persists 7 days; ack survives a double-submit; nothing pops during a dirty form
- Coverage gate: ≥85% lines on `jarvis/happy/`
- Explicit adversarial tests: replayed `impression_token`; ack POST without a token; kudos to self; kudos with a 39-character note; 4th kudos to the same person in a month; pulse response from a 3-person department

### 7. `HAPPY-PERF`
- `/api/happy/surface` p95 < 80 ms at 500 users. It is called on every Hub and Dashboard mount — it is the hottest new endpoint in the app.
- `EXPLAIN ANALYZE` the resolver query; it must use `idx_happy_targets_user`, never a sequential scan on `campaign_targets`.
- Marquee must not shift layout: `Skeleton` at the exact final height.
- `campaign_events` write path must be fire-and-forget and must never block a render.
- Nightly `refresh_targets` must complete in <60s at 1,000 users × 50 live campaigns.

---

## REPORT FORMAT (every agent, every handoff)

```
[AGENT-NAME REPORT]
Phase: <n> | Task: <description>
Files created: <path (lines)>
Files modified: <path — what changed>
Tables/columns touched: <or "none">
Endpoints added: <METHOD /path — permission>
Tests: <count, path, pass/fail>
Build: npm run build <exit code> | pytest <n passed, n failed>
Spec deviations: <none | what and why>
Blockers: <none | description>
Handoff to: <agent>
```

---

## MASTER STATUS TABLE

Maintained by the orchestrator, updated after every handoff.

```
PHASE | AGENT          | STATUS         | BLOCKER
------+----------------+----------------+---------------------------
0     | ASSESSOR       | ⏳ PENDING      | —
1     | DBA            | ⏳ WAITING      | blocked on Phase 0
1     | BACKEND        | ⏳ WAITING      | blocked on DBA
1     | WEB            | ⏳ WAITING      | blocked on BACKEND endpoints
1     | DPO            | ⏳ WAITING      | —
1     | QA             | ⏳ WAITING      | —
```

Phase N+1 does not begin until Phase N is green on **both** QA and DPO. Conflicts between agents are resolved with file:line evidence; DPO wins any tie involving personal data; QA wins any tie involving correctness; escalate to the user only for business decisions.

---

## NON-NEGOTIABLE PROJECT RULES (from `docs/CLAUDE.md`)

- Branch `staging`. Merging to `main` requires **double explicit confirmation** from the user.
- Before any push: `npm run build` (zero errors) → `pytest tests/ -x -q` (green) → `git status` (no untracked source) → `python3 -m py_compile jarvis/app.py`.
- Never drop or rename a table without `grep -r "<table>" jarvis/` first.
- Target the React frontend. Do not touch Jinja2 templates.
- Backend wraps responses in an envelope; the frontend unwraps. Follow the existing convention.
- macOS dev port is **5001**, not 5000.
- When asked for a plan, produce only a plan. Do not start implementing.

---

## THE FIRST THING TO BUILD IN PHASE 1

Not the pop-up. Not the banner. **`surface_resolver.py` and its unit tests**, with an in-memory fake repository. Targeting, capping, state filtering and priority ordering are the entire difficulty of this module; the UI is a rendering of whatever it returns. If the resolver is right, both surfaces on both platforms are straightforward. If it is wrong, every surface is wrong in a different way and you will debug it four times.

Build it, test it against the twelve cases below, and only then render anything:

1. user not in audience → empty
2. user in audience, campaign not yet started → empty
3. campaign ended → empty
4. already acknowledged → empty
5. snoozed, snooze not expired → empty
6. snoozed 3×, still live → returns for `hub_card`, not for `interstitial`
7. two eligible, one `critical` → critical first
8. two eligible same tier → earlier `ack_deadline_at` first
9. daily cap reached, next is `normal` → empty, `meta.next_eligible_at` set
10. daily cap reached, next is `critical` → returned, cap overridden, audit row written
11. route is `/app/accounting` → empty for `interstitial`, populated for `dash_banner` only if that route hosts one
12. user created after publication, matches audience → included (new-joiner inheritance)
