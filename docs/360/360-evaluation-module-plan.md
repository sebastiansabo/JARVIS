# JARVIS 360° Evaluation — Module Design Spec & Implementation Plan

**Status:** Draft for review · **Date:** 2026-07-23 · **Branch:** `dev` (spec stays off staging/main)
**Sources of truth (do not diverge):**
- `jarvis2-360-indicators.json` — the 22-indicator catalog, 9 events, conventions, families, implementation order.
- `jarvis2-360-indicators-handout.pdf` — the human map of the catalog.
- The **Cycle control center** mockup (HR dashboard, status-only, dark theme).

**Scope decisions (confirmed):** Full 360 (self + manager + peers + direct reports, nomination + n≥3 anonymity) · responses on **web + mobile** · **Phase 1 = one thin end-to-end loop** · spec + plan before code.

---

## 1. What we are building

An **HR-controlled zone** in the main JARVIS web platform — a new sidebar section **"360 Evaluations"** — where HR runs multi-rater evaluation *cycles*, *sets the indicators/templates*, and *sees statistics*. Reviewers respond on web **and** the JARVIS 2 mobile app. Employees read their own report.

**Hard invariant (from the spec + mockup):** HR/admin dashboards show **status and statistics only — never individual response content**, and **no category renders with n < 3** (B6, server-side gate, treated as a correctness bug not a metric). This is enforced at the API layer, not the UI.

The module is the survey-based program the catalog describes — distinct from the existing attendance-based `Employee360` drill-down, which stays as-is.

---

## 2. Domain model

### 2.1 Reviewer relationships (full 360)
`self · manager · peer · direct_report`. Peers are **nominated** (by participant and/or manager) and **HR-approved**; manager/reports are derived from the organigram (`get_managed_employee_ids`, `is_manager`). Category means use **equal weight per relationship** so a large peer group can't drown direct reports (catalog C2).

### 2.2 Anonymity & integrity
- Category rendered only when **n ≥ 3** (self & manager exempt, attributed at n=1) — catalog C1/B6.
- Reviewer load cap **≤ 8** (A6); participants need **≥ 3 eligible peers** (A7) — both are cycle **health checks** that gate state transitions.
- Submitted responses are **immutable**; drafts never count (conventions.immutability).
- `not_observed` is always excluded from every mean/count/σ (conventions.not_observed).

### 2.3 Cycle state machine
```
Draft ──▶ Nomination ──▶ Review(active) ──▶ Calibration ──▶ Released ──▶ Closed
```
- Windows: `nomination_end`, `review_end`, `release_at`.
- **Gates before transitions:** A7 (<3 eligible peers) blocks Draft→Nomination until resolved/waived; A6 (>8 load) blocks auto-approve; B6 anonymity is always enforced at render.
- Scores compute from **Calibration onward** (C1).

---

## 3. Data model (new Postgres domain: `schema_evaluation360`)

New `jarvis/migrations/domains/schema_evaluation360.py`, wired into `migrations/init_schema.py`. All tables prefixed `eval_`.

| Table | Purpose (key columns) |
|---|---|
| `eval_templates` | Named template. |
| `eval_template_versions` | **Immutable** version (template_id, version, published_at). Trends compare same competency **+ same template_version** only. |
| `eval_competencies` | (template_version_id, key, name, sort). |
| `eval_questions` | (competency_id, text, scale_min, scale_max, required). |
| `eval_indicators` | Per-cycle **thresholds/alerts** seeded from `jarvis2-360-indicators.json` (id, family, target, warn, refresh, surfaces, alert). HR "sets the indicators" by editing these. |
| `eval_cycles` | (name, template_version_id, state, nomination_end, review_end, release_at, created_by). |
| `eval_participants` | (cycle_id, subject_user_id). |
| `eval_assignments` | (cycle_id, subject_id, reviewer_id, relationship, state[`created/started/submitted/declined`], due_at). |
| `eval_responses` | (assignment_id, question_id, competency_id, rating **or** not_observed, comment). Immutable on submit. |
| `eval_aggregates` | Built at calibration: per (participant, competency, relationship) mean, n. Anonymity/gates applied here. |
| `eval_reports` | (cycle_id, participant_id, released_at, acknowledged_at, aggregate_json). |
| `eval_devplans` / `eval_devplan_goals` / `eval_checkins` | Outcome family (D). |
| `eval_events` | **Append-only** log of the 9 events — the substrate every indicator queries. |
| `eval_nudges` | `nudge.sent` log for rate-limiting (1/day/user). |

**Indicators are queries, not stored aggregates** (except `eval_aggregates` for report scores). Compute the 22 from `eval_events` + the tables above per the catalog formulas.

---

## 4. Events — emit first (catalog implementation_order #1)

Instrument these **before** any dashboard; backfill nothing:
```
assignment.created / .started / .submitted / .declined
report.released / .acknowledged
debrief.scheduled / .held
devplan.created / .checkin_completed
nudge.sent
```
Every event carries `ts` + `device`; answers ride only on `assignment.submitted`. A tiny `emit(event, payload)` helper writes to `eval_events`.

---

## 5. Indicators / statistics (the 22)

A pure module `evaluation360/indicators.py` maps each catalog id → a SQL/agg function over `eval_events` + tables, returning `{value, band, target, warn}`. Families:
- **A adoption** (A1–A7): completion, median time, mobile share, decline, overdue, reviewer load, peer eligibility.
- **B quality** (B1–B6): example rate, not-observed rate, outlier flag, leniency, drift, **anonymity (hard gate)**.
- **C scores** (C1–C5): category score, others composite, self–others gap, Johari, trend.
- **D outcomes** (D1–D4): debrief rate, ack rate, devplan activation, check-in completion.

**HR Cycle control center = the mockup**, status-only: stat tiles (Reviews submitted %, Median time/review, Comments w/ example %, Declines pending), **Completion by department** bars (green, at-risk in orange), the **nudge** callout + action (rate-limited), and **Cycle health checks** table (A7 flagged, A6 overloaded, anonymity Locked·enforced). Built with existing `Card`/`StatCard`/recharts. Gates (B6, C1 n≥3) ship **before** any chart (implementation_order #2).

---

## 6. Screens

**Web — HR zone** (`pages/Hr/Evaluation360/`, new sidebar entry, `hr/evaluation-360/*`):
- **Cycles** list → **Cycle control center** (the mockup, status-only).
- **Cycle builder** (name, template version, population, timeline).
- **Template & Indicators editor** (competencies, questions, scales; per-cycle indicator thresholds seeded from the JSON).
- **Nominations / assignments** + health checks + one-click nudge.
- **Reports** (per participant; anonymity-gated) + release.

**Reviewer-facing (web + mobile):** the survey — per competency 1–5 (or not_observed) + optional comment; per relationship; **submit = immutable**. Mobile reuses the JARVIS 2 tab patterns; web reuses shadcn.

**Employee-facing:** *My report* — radar, Johari quadrant, self–others gap chips, acknowledge, dev plan + check-ins.

---

## 7. Permissions (`permissions_v2`)
- `eval360.admin` — manage cycles/templates/indicators; sees **status/stats only**.
- `eval360.respond` — reviewers, own assignments only.
- `eval360.report.view` — participants, own report after release.
- Manager calibration view: outlier context, **never** rater identity, never shown to subject.
API middleware strips response content from any admin-scoped endpoint (invariant §1).

---

## 8. Tech (reuse the existing stacks — no new frameworks)
- **Backend:** new `evaluation360_bp` Flask blueprint + repositories/services; schema domain; `eval_events`. Reuse `core/organization` (org hierarchy), `core/auth`, `permissions_v2`, notifications (nudges/emails).
- **Web:** React 19 + shadcn/ui + **recharts** (dashboard), react-query, zustand — matches the platform.
- **Mobile:** extend `jarvis-mobile-2` (React 18 + Tailwind v4 + lucide + react-query) with the reviewer survey + my-report; the existing `HR → 360` tab becomes the entry point.

---

## 9. Phased plan

### Phase 1 — Thin end-to-end loop (this deliverable)
One minimal but **complete** cycle for a small population, proving the whole pipe:
1. **Schema (subset):** `eval_cycles, eval_participants, eval_assignments, eval_responses, eval_events, eval_reports, eval_aggregates` + a single seeded template (a few competencies, 1–5 scale).
2. **Backend blueprint:** create cycle (Draft→active) with population; auto-build assignments (self + manager + nominated peers + reports); emit `assignment.created`; **respond → submit** (immutable, emits `.started/.submitted`); build `eval_aggregates` with the **n≥3 anonymity gate**; release report (`report.released`).
3. **Indicators (minimum viable set):** A1 completion, A2 median time, A4 decline, A5 overdue, B1 example rate, **B6 anonymity gate**, C1 category score, C2 others composite, C3 self–others gap, C4 Johari.
4. **Web:** Cycle control center (stat tiles + completion-by-department + health checks, matching the mockup) + minimal cycle-create + reports list.
5. **Reviewer survey on web + mobile** → submit.
6. **Employee report** (radar + gap chips, anonymity-gated) read-only.
- **Acceptance:** HR creates a cycle → reviewers respond on web **and** mobile → the control center stats move in real time → a participant opens an **anonymity-gated** report with radar + gaps. Backend unit tests for scoring + anonymity + the A/B/C indicator queries; a seed script for a demo cycle.

### Phase 2 — Breadth & governance
Full nomination/approval workflow; health-check **gating** of state transitions (A6/A7); all remaining **A + B** indicators (B2 not-observed, B3 outlier, B4 leniency, B5 drift); manager **calibration** workspace; org analytics surfaces.

### Phase 3 — Outcomes (D family)
Debrief scheduling/tracking (D1), acknowledgments (D2), dev plans + goals + check-ins (D3/D4); nudge + alert wiring (rate-limited, digests).

### Phase 4 — Trend & polish
Template **versioning** + cross-cycle **trend series** (C5, same competency + version only, explicit series breaks); exports; full mobile parity; accessibility + theme polish.

---

## 10. Risks & invariants to hold
- **Anonymity (B6)** and **HR-never-sees-content** are correctness invariants, enforced server-side — a breach blocks render and pages engineering.
- **Immutability** of submitted responses.
- **Equal-weight relationship composite** (C2) — don't pool responses.
- **Trend integrity** — only same competency + template version; else render an explicit series break.
- Gates and the n≥3 display rule ship **before** any chart (implementation_order).

---

## 11. Open questions for you
1. **Rating scale** — 1–5 (matches mobile tab + Johari 3.5 split), or a different anchor set?
2. **Population source** — whole company, by company/department, or a hand-picked list per cycle for Phase 1?
3. **Peer nomination in Phase 1** — allow real nomination now, or hard-wire self+manager+reports and defer peer nomination to Phase 2 (keeps the thin loop thinner)?
4. **Cycle cadence** — quarterly (Q3 2026 as in the mockup) the default, with custom windows allowed?
