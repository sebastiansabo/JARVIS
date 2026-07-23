# 360 Employee Evaluation Module — Claude Code Build Prompt

**How to use:** Copy `jarvis-360-module-spec.md` and `jarvis2 -360-indicators.json` into your Jarvis repo under `docs/360/`. Open Claude Code at the repo root, switch to **plan mode** (Shift+Tab), and paste everything below the line. Approve the Phase 0 plan before letting it write code.

---

You are building the **360 Employee Evaluation module** inside the existing Jarvis codebase. Two documents in this repo are the contract: `docs/360/jarvis-360-module-spec.md` (functional spec) and `docs/360/jarvis2-360-indicators.json` (metrics, events, thresholds). Read both fully before planning. Where this prompt and those files conflict, this prompt wins; where the existing codebase's conventions conflict with any of it, **the codebase's conventions win for technology and style, the spec wins for behavior**.

## 0. Prime directive — use Jarvis's current tech

Do not introduce a new framework, ORM, UI kit, auth system, queue, or design language. Phase 0 is discovery:

1. Map the stack: language/framework, database + migration tool, ORM/query layer, API style (REST/GraphQL/RPC), auth + role model, background jobs, notification/push/email infra, i18n approach, test framework, existing admin/backoffice patterns, existing hub layout/navigation, existing mobile app architecture (native/RN/Flutter/PWA) and its navigation + offline patterns.
2. Map reusable assets: existing user/org/team models, existing role definitions (find what maps to HR admin, manager, employee), existing components (tables, forms, charts, avatars, toasts), existing notification templates and rate limiting, existing audit logging.
3. Produce `docs/360/IMPLEMENTATION-MAP.md`: for every subsystem the spec needs, either the existing Jarvis component you will reuse or a one-line justification for building new. **Present this plan and wait for my approval before writing any code.**

If the repo lacks something the spec requires (e.g. no push infra), do not build a parallel system silently — list it in the map as a decision I need to make.

## 1. Surface placement (this overrides the spec's surface table)

- **Backend / admin backoffice → HR zone.** Everything the spec calls "HR Admin Hub" lives in the existing Jarvis admin area: cycle builder + dry-run validation, competency & template library (versioned, fork-on-edit), live progress dashboard with department completion, targeted nudges (rate-limited), decline queue with replacement suggestions, org analytics (aggregate-only, min-n 5), anonymity & retention policy console, audit log. HR admins never see response content — status only, enforced server-side.
- **Hub (web app) → Employee + Manager zone.** Role-gated sections of one module, using the hub's existing navigation:
  - *Employee:* my reviews to give (web variant of the evaluation flow), nomination picker, my report (radar self vs. others, gap chips, Johari quadrant, unattributed comment wall, trend), acknowledgment, development plan co-owned with manager.
  - *Manager:* team board (self-review status, reviewer counts, report status, debrief scheduled), calibration workspace (draft aggregates, 2σ single-rater outlier flags, required 300–1500 char summary comment — context only, never score edits), debrief mode, development plan co-authoring.
- **Mobile app → mirror of the hub zone (employee + manager), capture-optimized.** Same capabilities as the hub for employees and managers, plus the mobile-first evaluation flow from spec §6: inbox with time estimates, one competency per screen, anchored 1–5 + always-visible "Not observed", auto-advance, offline drafts (persist every tap, sync on reconnect, latest-per-question wins), one non-blocking comment nudge (<40 chars), voice dictation where the platform supports it, condensed results view, push notifications deep-linking to exact screens. Manager on mobile gets the team board and debrief-scheduling in read/act form; heavy analytics stay on hub/backend.

## 2. Non-negotiable behavior (server-enforced, not UI-enforced)

1. **Anonymity engine.** Min 3 submitted responses per relationship category or the category is merged/hidden; manager & self always attributed; comments unattributed and shuffled; policy locked once cycle enters `active`. This is a hard gate in the report-building code path with an audit trail — any render below threshold is a bug that blocks the render (indicator B6).
2. **Raw responses are radioactive.** No endpoint ever returns individual non-self, non-manager responses to anyone, including HR. All report reads are pre-aggregated server-side. Response payloads encrypted at rest, keyed separately from identity.
3. **Submissions are immutable.** Drafts are editable and autosaved (idempotent per question); submit is transactional and write-once.
4. **`not_observed` is excluded from every mean, count, and σ.**
5. **Scoring:** category score = mean of category ratings (n-gated); others composite = mean of category means, never pooled; gap = self − others; Johari split at 3.5/3.5 with |gap| ≥ 1.0 flag; no forced ranking; no auto performance rating; trends only on same competency + template version, else visible series break.
6. **Cycle state machine** exactly: `draft → nomination → active → calibration → released → closed → archived`, with the transition rules, defaults, and release policies (manager-gated default) from spec §5.
7. **Notifications** follow the spec §9 matrix; nudges rate-limited 1/day/user platform-wide; quiet hours respected.

## 3. Events and indicators

Instrument the nine event families from `jarvis2-360-indicators.json` (`assignment.created/started/submitted/declined`, `report.released/acknowledged`, `debrief.scheduled/held`, `devplan.created/checkin_completed`, `nudge.sent`) using Jarvis's existing event/analytics pipeline if one exists. Then implement the indicator families in this order: gates first (B6, C1's n≥3), A-family live during the first cycle (HR progress dashboard), C-family for reports, D-family for outcomes. **Do not implement B4, B5, C5 (cross-cycle) beyond schema — they need a second cycle of data; stub the UI with an honest empty state.**

## 4. Delivery plan — phased, each phase verified and committed

Work in this order; each phase ends with green tests, a self-review against §2, and a commit (or PR if the repo uses PRs). Do not start phase N+1 with phase N red.

- **P0 Discovery** → `IMPLEMENTATION-MAP.md`, my approval.
- **P1 Domain + DB.** Entities from spec §3 (CompetencyLibrary, FormTemplate, ReviewCycle, Participant, ReviewerAssignment, Response, Report, DevelopmentPlan) as migrations in the repo's migration tool. Unit tests for the state machine and scoring/aggregation functions — including anonymity gating, not-observed exclusion, mean-of-means, and the n=2 hide case.
- **P2 Cycle engine + HR backend zone.** Cycle builder, dry-run validation (A7 <3 peers, A6 load >8), nomination flow with manager approval + 48h auto-approve, assignment fan-out, progress dashboard, decline queue, nudge with rate limit. Integration tests on the full draft→released happy path plus decline/replacement.
- **P3 Capture.** Hub evaluation flow + mobile evaluation flow with offline drafts and idempotent autosave. Contract tests: draft autosave idempotency, submit immutability, resume mid-form.
- **P4 Reports.** Aggregation job, anonymity engine, employee report (radar, gaps, Johari, comments, hidden-category notices), manager calibration workspace + required summary, release policies, acknowledgment. Tests: B6 gate (attempt to render n=2 category must fail closed), outlier flag at 2σ, manager-gated release blocks until debrief scheduled.
- **P5 Outcomes + notifications.** Development plans, check-ins, notification matrix, D-family indicators.
- **P6 Hardening.** i18n pass on all user-visible strings, WCAG on web rating inputs, retention config, audit log coverage, load-test the aggregation job.

## 5. Working rules for you (Claude Code)

- Start every phase in plan mode; show the plan; implement only after approval.
- Reuse before you build; match the repo's naming, error handling, and test style — read neighboring code before writing new code.
- Every phase needs a verification gate that runs in CI: if the repo has no test for a behavior in §2, you write it. You are not done when the code compiles; you are done when the invariant tests pass and you have listed each §2 rule with the test that proves it.
- Never weaken an invariant to make a test pass. If an invariant is genuinely incompatible with existing Jarvis architecture, stop and surface the conflict with options — do not decide silently.
- Update `docs/360/IMPLEMENTATION-MAP.md` as decisions get made; it is the living record.
- Commit messages: `360: <phase> — <what>`. Keep diffs reviewable; split large phases into multiple commits.

Begin with Phase 0 now: explore the repository, then present the implementation map and the Phase 1 plan.
