# 360° Module — IMPLEMENTATION MAP (Phase 0 Discovery)

**Status:** Phase 0 — awaiting approval before any code · **Date:** 2026-07-23 · **Branch:** `dev`
**Contract:** `jarvis-360-claude-code-build-prompt.md` (wins on behavior) + `jarvis2-360-indicators.json` (metrics/events/thresholds). Codebase conventions win on tech & style.

> ✅ **Both contract docs present & read.** `jarvis-360-module-spec.md` (functional spec v1.0) is now in `docs/360/` and read in full; `jarvis2-360-indicators.json` too. **Surface confirmed** (prompt §1, user 2026-07-23): HR admin zone = **status-only** in the web platform; the employee + manager evaluation UX lives in the **web hub + mobile**. Branch: `dev` (per project workflow).

### Spec-derived model (exact objects, §3 of the spec)
`CompetencyLibrary→Competency` (name, definition, cluster, level_descriptors[]) · `FormTemplate` (competency_ids[], question_blocks[], rating_scale, **audience_variants**{self,manager,peer,upward,external}) · `QuestionBlock` (type: rating|behavioral_frequency|open_text|forced_choice, text_by_audience{}) · `ReviewCycle` (population_filter, timeline{nomination_start,review_start,review_end,calibration_end,release_at}, anonymity_policy, reminder_policy, status) · `Participant` (self_status, nomination_status, report_status) · `ReviewerAssignment` (relationship: self|manager|peer|direct_report|**external**, source, status) · `Response` (answers[], draft_payload, device — **encrypted at rest, keyed separately**) · `Report` (aggregates_by_relationship, gap_analysis, hidden_categories[], manager_summary) · `DevelopmentPlan`. Default scale **1–5 + "Not observed"**, configurable 1–5/1–7/frequency.

### MVP cut line (spec §12) — maps to the phases
**In MVP:** cycle builder · nomination + manager approval · mobile eval flow + offline drafts · anonymity engine · employee report w/ **Johari** · manager team board + summary · reminder engine · HR progress dashboard.
**Post-MVP (defer, schema-aware only):** external reviewers (magic-link) · calibration workspace · AI comment polish (reuse `ai_agent`) · collaboration-graph auto-suggest · org analytics beyond completion+heatmap · 9-box export · trend lines (needs ≥2 cycles).

---

## 1. Stack map (what JARVIS is)

| Concern | JARVIS today | Use for 360 |
|---|---|---|
| Language / framework | Python **Flask** (44 blueprints) + Gunicorn | New `evaluation360_bp` blueprint |
| DB / migrations | **PostgreSQL** (+pgvector); schema built by `migrations/domains/schema_*.py` via `init_db()` → `create_schema()` + `run_pending_migrations()` (version_manager) | New `schema_evaluation360.py` domain |
| Query layer | Raw SQL through `BaseRepository` (48 repos), no ORM | New repos extend `BaseRepository` |
| API style | **REST** (Flask blueprints, session `@login_required` web; JWT `@jwt_required` on `mobile_bp`) | REST endpoints, both auth paths |
| Auth + roles | `flask_login` sessions + JWT bridge; **`permissions_v2`** matrix (`check_permission_v2`), `role_name`, `is_superuser`, `is_hr_manager` | New `eval360.*` permission keys |
| Org / team | `core/organization/manager_utils`: `is_manager()`, `get_managed_employee_ids()`, `get_visible_tree()`; `structure_nodes`, `company_responsables` | Manager & direct-report derivation, peer pool |
| Background jobs | **APScheduler** (`tasks/*.py`, file-lock single-worker) | Aggregation job, overdue reminders, nudge scheduling |
| Notifications | `core/notifications/` — `notify.py` (in-app+email), `push_service.py`, `smart_service.py`; templates + repos | §9 matrix, nudges, deep-link push |
| Events / analytics | `core/telemetry/` → `telemetry_events` (`TelemetryRepository.insert_events`, JSON `properties`, `client_ts`) | Emit the 9 event families |
| Audit log | `EventRepository.log_event`; append-only `approval_audit_log` pattern | Anonymity/audit trail |
| Web hub | React **19** + Vite + Tailwind 4 + **shadcn/ui** + **recharts**; react-router 7, react-query, zustand; `Card/StatCard/DataTable/Tabs/Badge/PageHeader`, sidebar nav | Employee/Manager zone + HR dashboards |
| Mobile | **jarvis-mobile-2** (Capacitor 6, React 18 + Tailwind 4 + lucide + react-query + zustand); secureStore/Preferences, **speech-recognition**, **push-notifications**, barcode | Capture-optimized reviewer/employee/manager flow |
| i18n | **None** (inline RO/EN strings) | ⚠️ decision (P6) |
| Tests | Backend **pytest** (`tests/`, `conftest.py`) ✓; mobile **vitest** ✓; **web has no test runner** | Server-enforced §2 invariants → pytest; mobile → vitest |
| Encryption at rest | Not evident for app payloads (DB-level DO encryption only) | ⚠️ decision (spec §2.2 wants response payloads encrypted, keyed separately) |

---

## 2. Subsystem map (reuse vs build)

**Reuse (existing JARVIS asset):**
- **Roles → 360 roles:** HR admin = `can_access_hr`/`is_hr_manager` (+ new `eval360.admin`); Manager = `is_manager()` org-responsable; Employee = authenticated user. Reuse `permissions_v2`.
- **Manager / direct reports / visible tree:** `get_managed_employee_ids()`, `is_manager()`, `get_visible_tree()`.
- **Notifications & push:** `core/notifications/notify.py` + `push_service.py` for the §9 matrix, deep-link pushes, emails.
- **Event emission:** `telemetry_events` for the 9 families (lightweight analytics substrate); **domain tables remain the source of truth** for state.
- **Audit trail:** mirror `approval_audit_log` (append-only) for anonymity-gate + admin-access audit.
- **Scheduler:** `tasks/` + APScheduler for aggregation, overdue reminders, nudge windows.
- **Web components:** shadcn `Card/StatCard/DataTable/Tabs/Badge/PageHeader/EmptyState` + **recharts** (radar, bars). Sidebar entry pattern (`Sidebar.tsx`) + HR tab registration (`pages/Hr/index.tsx`).
- **Mobile capture primitives:** react-query hooks + `apiFetch`, zustand-persist for **offline drafts**, `secureStore`, `@capacitor-community/speech-recognition` for **voice**, `@capacitor/push-notifications` for **deep-link push**. The existing `HR → 360` tab becomes the entry point.
- **Rate limiter (partial):** `core/utils/api_helpers.RateLimiter` (in-memory) for cheap per-request limits.

**Build new (justified):**
- **`schema_evaluation360` domain + repos/services** — no existing competency/cycle/assignment/response/report entities.
- **Anonymity + aggregation engine** (`evaluation360/aggregation.py`, `anonymity.py`) — the n≥3 gate, mean-of-means, not-observed exclusion, Johari/gap; nothing equivalent exists. Pure, pytest-covered.
- **Indicator query layer** (`evaluation360/indicators.py`) — the 22 catalog indicators as queries; thresholds seeded from the JSON.
- **DB-backed nudge rate-limiter** — existing `RateLimiter` is **in-memory** (resets on restart, per-worker), incompatible with "1/day/user platform-wide." Build a small `eval_nudges`-backed limiter. *(decision below)*
- **Response-at-rest encryption** — spec §2.2 wants response payloads encrypted, keyed separately from identity; no app-layer field encryption exists today. *(decision below)*

---

## 3. Open decisions (need your call — not deciding silently)

*Resolved: ✅ functional spec provided & read · ✅ surface confirmed (HR status-only; UX in hub+mobile).*

1. **Response encryption at rest (§2.2 / §11)** — spec explicitly wants response payloads encrypted with key separation from identity. Options: full app-layer field encryption now (new key management), or DO disk encryption + strict access control + the "raw responses never returned" API gate for MVP, with field encryption in P6 hardening. *(Recommend: MVP = gate + access control; P6 = field encryption. Your call, since the spec names it non-functional-critical.)*
2. **Nudge rate-limit** — build the DB-backed 1/day/user limiter now (recommended, small) vs. defer. Existing `RateLimiter` is in-memory and can't do platform-wide.
3. **i18n (§11 wants per-audience + per-locale + RTL)** — introduce a lightweight i18n layer, or ship RO-only for MVP and add i18n in P6? *(Recommend RO-only MVP; i18n P6 — matches current app.)*
4. **Web invariant tests** — critical §2 invariants are **server-side → pytest** (fine). OK to not add a web test runner now, keeping mobile on vitest?

---

## 4. Phase plan (per prompt §4) & the immediate next step

- **P0 Discovery** ✅ this doc → **your approval**.
- **P1 Domain + DB (next):** `schema_evaluation360` migration for CompetencyLibrary, FormTemplate (versioned, fork-on-edit), ReviewCycle, Participant, ReviewerAssignment, Response, Report, DevelopmentPlan + `eval_events`. **Pure functions + pytest** for the state machine (`draft→nomination→active→calibration→released→closed→archived`) and scoring/aggregation — **incl. anonymity gating, not-observed exclusion, mean-of-means, and the n=2 hide case** (fail-closed). No UI yet.
- **P2** Cycle engine + HR backend zone (builder, dry-run A6/A7, nomination + 48h auto-approve, fan-out, progress dashboard = the mockup, decline queue, nudge). Integration tests draft→released + decline/replace.
- **P3** Capture — hub + mobile evaluation flow, offline drafts, idempotent autosave, submit immutability. Contract tests.
- **P4** Reports — aggregation job, anonymity engine, employee report (radar/gap/Johari/comments/hidden-category notices), manager calibration + required 300–1500 char summary, release policies, acknowledgment. Tests: **B6 n=2 must fail closed**, 2σ outlier, manager-gated release.
- **P5** Outcomes + notifications — dev plans, check-ins, §9 matrix, D-family indicators.
- **P6** Hardening — i18n, WCAG rating inputs, retention, audit coverage, load-test aggregation.

**Indicator order (per §3):** gates first (**B6**, C1 n≥3) → **A-family** live in cycle 1 → **C-family** reports → **D-family** outcomes. **B4/B5/C5 (cross-cycle): schema only + honest empty-state UI** (need a 2nd cycle).

**§2 invariant → test ledger** (filled as we build; each rule must have a proving test): anonymity n≥3 fail-closed · raw responses never returned · submit immutable/idempotent draft · not_observed excluded · mean-of-means (not pooled) · Johari 3.5 + |gap|≥1.0 · state-machine transitions · nudge 1/day/user + quiet hours.

---

## 5. Recommendation
Approve Phase 0 and let me start **P1 (Domain + DB + pure-logic pytest)** — it's the safe foundation, no UI, fully test-gated, and it's where the non-negotiable invariants (anonymity, scoring, state machine) get proven before anything renders. In parallel I need your calls on the **Open decisions (§3)**, especially #1 (functional spec) and #6 (surface confirmation).
