# Jarvis 2.0 — 360° Employee Evaluation Module
## Product Specification v1.0

---

## 1. Purpose and Positioning

The 360 module gives every employee a multi-perspective performance signal — self, manager, peers, direct reports, and optionally external collaborators — and turns it into a development plan. It lives inside Jarvis 2.0 as a first-class module with two surfaces:

- **Mobile** — where feedback gets *given*. Optimized for completion speed: a reviewer finishes a full evaluation in under 4 minutes.
- **Hub (web)** — where feedback gets *orchestrated and consumed*. Role-based views for HR admins, managers, and employees.

Design principle: mobile is the capture surface, hub is the control and insight surface. Every feature is assigned to exactly one primary surface; duplication is deliberate and minimal.

---

## 2. Roles and Permissions

| Role | Capabilities |
|---|---|
| **HR Admin** | Create/configure cycles, manage competency library and form templates, override reviewer assignments, monitor progress, trigger nudges, control report release, org-level analytics, anonymity policy configuration |
| **Manager** | Approve/adjust reviewer nominations for direct reports, track team completion, view direct reports' released results, add manager summary comment, run calibration notes, create development plans |
| **Employee (subject)** | Nominate peer reviewers, complete self-review, view own released report, acknowledge report, co-own development plan |
| **Reviewer** | Complete assigned evaluations (peer / upward / downward), decline with reason |
| **External reviewer** (optional) | Complete a scoped form via magic-link, no Jarvis account required |

Permission rules of note: raw individual responses are never visible to anyone, including HR Admin (aggregate-only reporting); managers see only released reports, never in-flight responses; declines are visible to HR Admin with reason, to the subject only as "reviewer replaced."

---

## 3. Core Objects (Data Model)

**CompetencyLibrary** → Competency (id, name, definition, cluster, level_descriptors[], active)
**FormTemplate** (id, name, competency_ids[], question_blocks[], rating_scale, audience_variants{self, manager, peer, upward, external})
**QuestionBlock** (id, type: `rating | behavioral_frequency | open_text | forced_choice`, competency_id?, text_by_audience{}, required)
**ReviewCycle** (id, name, population_filter, template_id, timeline{nomination_start, review_start, review_end, calibration_end, release_at}, anonymity_policy, reminder_policy, status: `draft | nomination | active | calibration | released | closed | archived`)
**Participant** (cycle_id, employee_id, self_status, nomination_status, report_status)
**ReviewerAssignment** (id, cycle_id, subject_id, reviewer_id | external_email, relationship: `self | manager | peer | direct_report | external`, source: `self_nominated | manager_assigned | hr_assigned | auto_suggested`, status: `pending_approval | invited | in_progress | submitted | declined | replaced`)
**Response** (assignment_id, answers[], draft_payload, submitted_at, device: `mobile | web`) — encrypted at rest, keyed separately from identity
**Report** (participant_id, aggregates_by_relationship{}, gap_analysis, hidden_categories[], manager_summary?, released_at, acknowledged_at)
**DevelopmentPlan** (participant_id, goals[], linked_competencies[], check_in_dates[], status)

### Rating scale (default)
1–5 behavioral scale with anchored labels per competency level descriptor, plus **"Not observed"** (excluded from averages — critical for score integrity). Configurable per template: 1–5, 1–7, or frequency scale (Never → Always).

---

## 4. Anonymity Model (non-negotiable rules)

1. Minimum **3 submitted responses per relationship category** to show that category's breakdown. Below threshold, category is merged into "Others" or hidden.
2. Manager and self scores are always attributed (n=1 categories are inherently identifiable and both parties know it).
3. Open-text comments are displayed unattributed, shuffled, and never grouped by relationship when peer n < 3. Optional AI-rephrase pass (Jarvis assistant) to strip identifying style — off by default, cycle-level toggle.
4. HR Admin sees completion status per reviewer but never response content.
5. Anonymity policy is locked once the cycle enters `active` — no retroactive loosening.

---

## 5. Cycle Workflow

```
DRAFT → NOMINATION → ACTIVE → CALIBRATION → RELEASED → CLOSED → ARCHIVED
```

**1. Draft (HR Admin, hub).** Pick population (org filter: department, level, tenure), template, timeline, anonymity + reminder policy. Preview form in all audience variants. Dry-run validation: flags employees with <3 eligible peers, missing managers, open prior cycles.

**2. Nomination (5 business days default).** Employee nominates 3–8 peers; Jarvis auto-suggests based on collaboration graph (calendar/Slack/Jira signal, if connected) — suggestions ranked, never auto-confirmed. Manager approves/swaps within 48h; no action = auto-approve. HR can inject skip-level or cross-functional reviewers.

**3. Active (2 weeks default).** Assignments fan out. Mobile-first completion flow (§6). Reminder engine (§9). Manager and HR watch progress heatmaps — status only, never content.

**4. Calibration (optional stage, 1 week).** Managers see draft aggregates for their reports, add a required manager summary comment (300–1500 chars), flag statistical anomalies (single-rater outliers auto-flagged when a rating is >2σ from category mean). Calibration never edits scores — it contextualizes them.

**5. Released.** Reports released per policy: all-at-once, manager-gated (manager must schedule a debrief conversation before employee sees the report — recommended default), or rolling. Employee acknowledges receipt; acknowledgment unlocks development plan creation.

**6. Closed/Archived.** Cycle locks. Data feeds trend lines for next cycle. Retention policy applies (default: raw responses purged at 24 months, aggregates retained 5 years — configurable to local labor law).

---

## 6. Mobile Experience (capture surface)

### 6.1 Feedback Inbox
Home card: "You have 4 evaluations · ~14 min total." Each item shows subject, relationship, due date, estimated time, and progress. Sorted by due date; overdue pinned red.

### 6.2 Evaluation Flow — the 4-minute design
- **One competency per screen.** Anchored 1–5 tap targets (thumb-zone, bottom half of screen), "Not observed" always visible. Tap advances automatically after 400ms confirmation state.
- Behavioral anchor text shown *before* the scale, in the reviewer's language (i18n per user, not per cycle).
- **Open-text with voice dictation** and an AI polish assist ("tighten this comment" — reviewer approves final text; nothing auto-submitted).
- **Comment quality nudge**: comments under 40 chars or containing only adjectives get one inline prompt for a specific example ("What did they do?"). One nudge, never blocking.
- **Offline drafts**: every answer persisted locally on tap; syncs on reconnect; conflict rule = latest device wins per question.
- Resume exactly where you left off. Progress bar across top: `●●●○○○ 3/9`.
- Review-before-submit summary screen; edits jump back to the specific question.

### 6.3 Nomination on mobile
Swipe-based picker over auto-suggested peers (accept/reject), with search fallback. Requires 3–8 accepted.

### 6.4 My Results on mobile (read-only companion)
Released report in condensed form: overall by competency, self-vs-others gap chips, top strength, top growth area, comments feed. Full analytics and development planning deep-link to the hub. Report screens are **screenshot-watermarked** with viewer identity (deterrence, not prevention).

### 6.5 Push notifications
Assignment received · 3 days left · due today · report released · debrief scheduled · development check-in due. All deep-link to the exact screen. Quiet hours respected; max 1 nudge/day/user.

---

## 7. Hub Experience (orchestration + insight surface)

### 7.1 HR Admin Hub
- **Cycle builder** — wizard per §5 step 1, with dry-run validation report.
- **Competency & template library** — versioned; editing a template used by an active cycle forks a new version, never mutates in place.
- **Live progress dashboard** — completion % overall, by department, by relationship type; heatmap of laggard teams; one-click targeted nudge (rate-limited); reviewer decline queue with replacement suggestions.
- **Org analytics** (aggregate only, min-n 5 per slice) — competency heatmap by department, self-vs-others gap distribution, score distribution drift vs. prior cycles, leniency/severity index per department (mean given-score vs. org mean, surfaced for calibration hygiene, not shown per individual reviewer), 9-box feed (optional, exports rating axis to talent review).
- **Anonymity & retention policy console**; audit log of every admin action.

### 7.2 Manager Hub
- **Team board** — each report: self-review status, reviewer completion n, report status, debrief scheduled y/n.
- **Calibration workspace** — draft aggregates, outlier flags, required summary comment, side-by-side with prior cycle.
- **Debrief mode** — presentation view of a report for the 1:1 conversation (no raw comments visible on projected view until manager toggles them).
- **Development plan co-authoring** — goals linked to lowest-gap competencies; Jarvis suggests goal templates from the competency library; check-ins auto-scheduled to calendar.

### 7.3 Employee Hub
- **My report** — full interactive version: radar chart (self vs. each relationship category that clears min-n), competency drill-down with anchor descriptors, comment wall, trend vs. previous cycles, hidden-category notices ("Peer breakdown hidden: fewer than 3 responses").
- **Johari-style quadrant** — competencies plotted by self-score vs. others-score: Confirmed strengths / Blind spots / Hidden strengths / Agreed growth areas. This single view is the product's core value moment.
- **My development plan** — goals, check-ins, progress; visible to manager.
- **My reviews to give** — same inbox as mobile, web form variant.

---

## 8. Scoring & Aggregation Rules

- Category score = mean of submitted ratings, "Not observed" excluded; category displayed only when n ≥ anonymity threshold.
- Overall "Others" score = mean of category means (not pooled responses) so a large peer group doesn't drown out direct reports.
- Gap = self − others; |gap| ≥ 1.0 flags Johari placement.
- No forced ranking, no auto-derived performance rating. Export to talent review is an explicit HR action with its own audit entry.
- Trend lines computed only on same-competency, same-scale comparisons; template version changes break the trend line visibly rather than silently comparing different questions.

## 9. Reminder Engine

| Trigger | Channel | Timing |
|---|---|---|
| Assignment created | Push + email | Immediate |
| No start | Push | T+3 days |
| 50% window elapsed, not submitted | Push | Midpoint |
| Due in 48h | Push + email | T−2 days |
| Overdue | Email + manager digest | T+1 day, then every 3 days, max 3 |
| HR manual nudge | Push | Rate-limited: 1/day/user |

## 10. API Sketch (module boundary)

```
POST   /cycles                       POST /cycles/{id}/transition
GET    /cycles/{id}/progress         POST /cycles/{id}/nudge
POST   /cycles/{id}/nominations      PATCH /nominations/{id}/approve
GET    /me/assignments               PATCH /assignments/{id}/decline
PUT    /assignments/{id}/draft       POST  /assignments/{id}/submit
GET    /me/report/{cycleId}          POST  /reports/{id}/acknowledge
GET    /teams/{id}/board             POST  /reports/{id}/manager-summary
POST   /participants/{id}/dev-plan   GET   /org/analytics?slice=...
```

Draft autosave endpoint is idempotent per question (mobile offline sync). Submit is transactional and immutable. All report reads are pre-aggregated server-side — clients never receive raw responses.

## 11. Non-functional

- **Privacy/compliance**: GDPR-ready (relevant for Romania/EU): purpose limitation, retention config, right-to-erasure workflow (subject erasure removes their reports; reviewer erasure de-links identity, keeps anonymized ratings where n-threshold still holds, else deletes).
- **Security**: response payloads encrypted at rest with key separation from identity tables; audit log on all admin/report accesses.
- **Performance**: mobile flow usable on 3G; drafts local-first. Report render < 1.5s p95.
- **i18n**: form text per audience *and* per locale; RTL support.
- **Accessibility**: WCAG 2.2 AA; rating scales operable by keyboard and screen reader on web.

## 12. MVP Cut Line

**In MVP:** cycle builder, nomination + manager approval, mobile evaluation flow with offline drafts, anonymity engine, employee report with Johari quadrant, manager team board + summary comment, reminder engine, HR progress dashboard.

**Post-MVP:** external reviewers, calibration workspace, AI comment polish/rephrase, collaboration-graph auto-suggestions, org analytics beyond completion + heatmap, 9-box export, trend lines (needs ≥2 cycles of data anyway).

## 13. Success Metrics

- Reviewer completion rate ≥ 90% by deadline (industry baseline ~70–80%)
- Median time per evaluation ≤ 4 min on mobile
- % of comments containing a specific example ≥ 60%
- % of released reports with debrief held within 14 days ≥ 80%
- % of employees with an active development plan 30 days post-release ≥ 70%
