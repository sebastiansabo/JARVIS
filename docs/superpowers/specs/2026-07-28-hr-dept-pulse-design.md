# HR Department Pulse — backend-aggregated 360 qualitative feedback (slice 2)

**Date:** 2026-07-28
**Status:** Approved (design)
**Scope:** `JARVIS` backend (new `hr_dept_pulse_votes` model + `/profile/api/dept-pulse` endpoints, Sincron-org aggregation & eligibility) **and** `jarvis-mobile-2` (rework the "Evaluare 360 calitativă" card: relabel, backend-backed votes, new "Statistici departament" tab). Ships in the same `2.0.x` mobile line; requires a JARVIS backend deploy.

## Problem

The mobile "Evaluare 360 calitativă" card
([Evaluation360Tab.tsx `RatingsSection`](../../../../jarvis-mobile-2/src/pages/HR/Evaluation360Tab.tsx)) rates a
**per-person subject on 5 competencies from 3 rater perspectives**
(self / peer / manager), 1–5 — but the ratings are **device-local**
(`useEvaluationStore`, `localStorage` key `jarvis2-evaluation-360`). They
never leave the phone, so:

- No one but the rater ever sees them; they cannot be aggregated.
- Rating an individual colleague/manager privately-on-device is low value — the
  card was assessed as "useless as-is."

The user's redesign turns it into a **shared department pulse**: keep the
familiar competency dial, but persist votes to the backend and roll them up per
**department** (scoped by the **Sincron organigram**) into an anonymous
aggregate everyone in the department can see and influence at any time.

## Goal (slice 2)

1. **Relabel** the `peer` rater perspective `Coleg → Colegi` (plural); keep
   `Autoevaluare` and `Manager`.
2. **Persist votes to the backend**, scoped to the voter's Sincron department
   node, **rolling** (latest vote per voter × perspective × competency counts —
   no month history).
3. **Add a "Statistici departament" tab** in the same card: an **anonymous**
   aggregate (average per perspective × competency + voter counts) for the
   viewer's department, **live** (recomputes as votes change).
4. **Eligibility** to vote on / see a department's pulse: department **members +
   their manager chain** (walk the Sincron `parent_id` upward).

**Later (phase 3, out of scope here):** generalize the "pulse" pattern to other
HR surfaces. Slice 2 proves it end-to-end on the 360 card first.

## Design

### Hierarchy resolution (Sincron organigram)

The Sincron org is a tree, already present:

- `sincron_org_nodes` (`id`, `company_id`, `parent_id`, `name`, `node_type`,
  `level` 1–6) — the department tree.
- `sincron_org_members` (`node_id`, `sincron_employee_id`, `company_name`,
  `role` ∈ `responsable` | `member`) — who sits in each node.
- `sincron_employees.mapped_jarvis_user_id` — links a JARVIS `users.id` to a
  Sincron employee (`sincron_employee_id` + `company_name`).

**A JARVIS user's department** is resolved:
`users.id` → `sincron_employees` (via `mapped_jarvis_user_id`, `is_active`) →
`sincron_org_members` (via `sincron_employee_id` + `company_name`) → `node_id`.
The user's **own department node** = a node where they are a `member` (fall back
to a node where they are a `responsable` if they are only a manager). A user may
map to more than one node; slice 2 uses the first by `level, node_id` as the
default and offers a picker (below) when there are several.

**Eligibility** — `eligible(user, node_id)` is true when either:
- `node_id` is one of the user's own member/responsable nodes, **or**
- `node_id` is a **descendant** of a node where the user is a `responsable`
  (the manager-chain-sees-down direction; a manager of a parent may vote on and
  view any department beneath them).

Descendants/ancestors are resolved with a recursive CTE over
`sincron_org_nodes.parent_id`. All endpoints enforce `eligible(...)` server-side
before returning or writing anything.

### Data model (new)

Table `hr_dept_pulse_votes` (public schema, alongside the `sincron_*` tables):

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `voter_user_id` | INTEGER | FK `users.id` |
| `department_node_id` | INTEGER | FK `sincron_org_nodes.id` |
| `perspective` | VARCHAR(20) | `self` \| `peer` \| `manager` (rater-role keys — unchanged) |
| `competency_key` | VARCHAR(40) | `communication` \| `teamwork` \| `initiative` \| `problemSolving` \| `professionalism` |
| `rating` | SMALLINT | `CHECK (rating BETWEEN 1 AND 5)` |
| `updated_at` | TIMESTAMPTZ | `DEFAULT NOW()` |

`UNIQUE (voter_user_id, department_node_id, perspective, competency_key)` — the
**rolling upsert** key: re-voting `UPDATE`s the same row, so a voter's latest
vote always counts and there is no history to accumulate. `ON DELETE CASCADE`
from both FKs so a removed user/node cleans up. Index on
`(department_node_id, perspective)` for the aggregate read.

DDL lives in `jarvis/migrations/domains/schema_incremental.py` (idempotent
`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`, matching the
existing incremental-migration style).

### Backend endpoints (`core/profile/routes.py`)

Placed on the profile blueprint — the established mobile-HR surface (it already
serves `/profile/api/pontaje`, `/team-pontaje`, `/hr-events`,
`/sincron-timesheet`), and already in the mobile CORS allow-list for GET/POST
(no new methods → no `_mobile_cors` allow-methods change needed; **confirm during
implementation** per the known CORS-methods gotcha).

**`GET /profile/api/dept-pulse`** (optional `?department=<node_id>`)
- Resolves the caller's own department node when `department` is omitted; when
  present, requires `eligible(caller, department)` (else `403`).
- Returns the anonymous aggregate + the caller's own current votes + the list of
  departments the caller may view (for the picker):

```json
{
  "department": { "node_id": 42, "name": "Vânzări Audi", "company_id": 11 },
  "available_departments": [ { "node_id": 42, "name": "Vânzări Audi" }, ... ],
  "voter_count": 7,
  "min_voters": 3,
  "aggregate": [
    { "perspective": "peer", "competency_key": "communication",
      "avg": 4.2, "voters": 6 },
    ...
  ],
  "my_votes": [
    { "perspective": "self", "competency_key": "communication", "rating": 4 },
    ...
  ]
}
```

- Aggregate query (anonymous — no `voter_user_id` ever leaves the server):

```sql
SELECT perspective, competency_key,
       ROUND(AVG(rating)::numeric, 2) AS avg,
       COUNT(DISTINCT voter_user_id)  AS voters
FROM   hr_dept_pulse_votes
WHERE  department_node_id = %s
GROUP  BY perspective, competency_key;
```

- **Anonymity floor:** `voter_count` = `COUNT(DISTINCT voter_user_id)` for the
  department. When `voter_count < min_voters` (**3**), `aggregate` is returned
  **empty** (the client shows "statistici disponibile de la 3 voturi") so a
  single vote can never be de-anonymised. `my_votes` is always returned (it's the
  caller's own data). The `min_voters` value is a backend constant surfaced to
  the client so the copy stays in sync.

**`POST /profile/api/dept-pulse`** — upsert one of the caller's votes:

```json
{ "department_node_id": 42, "perspective": "peer",
  "competency_key": "communication", "rating": 4 }
```

- Requires `eligible(caller, department_node_id)` (else `403`); validates
  `perspective`, `competency_key`, and `rating` ∈ 1..5 against fixed allow-lists
  (else `400`). `rating: 0`/`null` **deletes** the caller's vote for that
  (perspective, competency) — mirrors the card's "tap the lit dot again to
  clear" behaviour.
- Upsert: `INSERT ... ON CONFLICT (voter_user_id, department_node_id,
  perspective, competency_key) DO UPDATE SET rating = EXCLUDED.rating,
  updated_at = NOW()`.
- Returns `{ "ok": true }`. The mobile client refetches `GET` to update the
  aggregate.

A thin `DeptPulseRepository` (`core/profile/repositories/`) owns the SQL
(resolution, eligibility, aggregate, upsert/delete) behind the route, per the
routes → repository convention.

### Mobile card rework (`jarvis-mobile-2`)

**Relabel (immediate, independent):** in
[evaluationStore.ts](../../../../jarvis-mobile-2/src/stores/evaluationStore.ts)
`RATER_ROLES`, the `peer` label becomes `Colegi`.

**The card becomes department-scoped, two-tabbed.** Rework `RatingsSection`
(rename to `DeptPulseCard`) into a self-contained card driven by the backend, no
longer a per-`subject` device-local widget. It renders **once** in the user's own
"Rezultatele mele" view (not per team-member drill-down — a department pulse is
not per person). Card title stays **"Evaluare 360 calitativă"**; a segmented
control at the top switches two tabs:

1. **"Evaluează"** — the existing perspective selector (Autoevaluare / **Colegi**
   / Manager) × 5 competencies × 1–5 dial, unchanged in look. The dots reflect
   the caller's **own** votes from `my_votes`; tapping a dot `POST`s the vote
   (tap the lit value again to clear → `rating: 0`). The `X/100` header keeps
   showing the caller's own `qualitativeScore` over their submitted ratings.
   When the caller has no Sincron department, the tab shows a "nu ești asociat
   unui departament Sincron" empty state and the dial is disabled.

2. **"Statistici departament"** — the anonymous aggregate for the department:
   per competency, the **average** (with the same band colouring) under each
   perspective, plus a **voter count** per perspective ("din N") and an overall
   department voter count. Below the floor (`voter_count < min_voters`) it shows
   "Statistici disponibile de la 3 voturi (acum: N)". A **department picker**
   (from `available_departments`) appears only when the caller may view more than
   one department (managers with descendants); otherwise the header just names
   the department.

**Footnote** updated: no longer "salvată doar pe acest dispozitiv." New copy,
e.g. *"Evaluare calitativă la nivel de departament — anonimă, agregată din
Autoevaluare, Colegi și Manager. Poți actualiza oricând."*

**Data layer:** two hooks in
[useApi.ts](../../../../jarvis-mobile-2/src/hooks/useApi.ts) — `useDeptPulse(department?)`
(`GET`, React-Query) and `useSubmitDeptPulseVote()` (`POST`, invalidates the
`useDeptPulse` query on success). Types mirror the JSON above.

**Retire device-local storage:** `Evaluation360Tab.tsx` is the **only** consumer
of `evaluationStore.ts` (verified by grep). Once `DeptPulseCard` no longer reads
`useEvaluationStore`, **relocate** the two constants it defines that are still
needed — `COMPETENCIES` and `RATER_ROLES` (with `peer` relabelled `Colegi`) —
into `src/lib/evaluation.ts` (where the other 360 pure logic already lives and is
tested), then **delete `src/stores/evaluationStore.ts` outright** (the Zustand
store, its `localStorage` persistence key `jarvis2-evaluation-360`, and the
`subject`-scoped helpers `subjectKey`/`getRating`/`ratedValues`/`setRating`/
`clearSubject` all go with it). `qualitativeScore` and `scoreBand` already live in
`src/lib/evaluation.ts`, and `BAND` is a local const in `Evaluation360Tab.tsx` —
both untouched. The new card computes its own `X/100` by passing the caller's
`my_votes` ratings (a `number[]`) straight into `qualitativeScore`, so the
removed `ratedValues` helper is not needed.

### Pure logic (testable)

Extract the aggregate/eligibility-independent shaping into pure functions so they
can be unit-tested without a device or DB:

- Backend: `resolve_department(user_id)`, `eligible_dept_nodes(user_id)`,
  `is_eligible(user_id, node_id)`, and the aggregate row-shaping — tested against
  a seeded Sincron org fixture (nodes + members + a mapped user) on
  **localhost/defaultdb** (never staging/prod).
- Mobile: a small `src/lib/deptPulse.ts` mapping the `GET` payload to the tab
  view-model (per-perspective competency rows, floor gating) — Vitest-covered.

## Edge cases

- **User not mapped to any Sincron node** → `GET` returns `department: null`;
  card shows the "no department" empty state; `POST` is not offered.
- **User maps to multiple nodes** → default to first by `level, node_id`;
  managers get the picker.
- **Anonymity floor** (`< 3` voters) → aggregate suppressed, `my_votes` still
  shown, explanatory copy.
- **Clearing a vote** (`rating: 0`) deletes the row; if it was the department's
  only vote for that cell, the aggregate cell disappears.
- **Manager voting on a descendant department** → allowed by `eligible(...)`;
  their vote lands in that department's pool, under the perspective they pick.
- **Ineligible department in `?department=` / `POST`** → `403`, client surfaces a
  non-blocking banner.
- **Stale org membership** (Sincron re-sync moved the user) → resolution is live
  per request; old votes remain attached to the old `department_node_id` (rolling
  model tolerates this; no migration of past votes).

## Testing

- Backend `pytest` (localhost DB, seeded Sincron fixture): resolution,
  eligibility (member vs manager-chain vs ineligible → 403), rolling upsert
  (re-vote updates same row), delete-on-zero, anonymity floor (2 voters →
  aggregate empty, 3 → present), aggregate averages & distinct voter counts.
  Never touches staging/prod DB.
- Mobile: `deptPulse.ts` Vitest (payload → view-model, floor gating, empty
  states). Card verified via `tsc` + existing `vitest` + `npm run build` +
  `npx cap sync android` (repo convention — components aren't render-tested).
- Manual device pass: rate under each perspective → aggregate updates; second
  account in same department pushes voter count to 3 → stats appear; manager sees
  descendant departments in the picker; unmapped user sees empty state.

## Out of scope

- Phase 3 HR-wide generalization of the pulse pattern (other HR surfaces).
- Month-over-month history (explicitly rolling/current).
- Showing individual votes or voter identities (anonymous only).
- Any change to the objective 360 score, the 360 cycle/report backend, the
  scoring formulas, or the web HUB.
- Editing the Sincron organigram itself (consumed read-only here).

## Sequencing

Backend first (table + endpoints + tests, deployed to staging → prod on `dev`→
staging→main per the strict git workflow), then the mobile card consuming the
live endpoints, shipped in the next `2.0.x` APK. This design doc stays on `dev`
and is dropped before any staging/main merge (per repo convention: no SDD docs on
staging/main).
