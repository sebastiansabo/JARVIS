# Field Sales Tenant Isolation (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.
> **Workspace:** isolated git worktree at `/Users/sebastiansabo/Documents/Git/JARVIS-fs-tenant` on branch `fs-tenant-build` (off `dev`); ff-merge to `dev` at finish. All subagents work in that path.

**Goal:** Make Field Sales tenant/company-scoped — every visit & client belongs to a company, all lists filter by a selected company, and the Hub panel's company selector auto-defaults to the user's own company (locked if single, switchable for managers/admins).

**Architecture:** Nullable `company_id` (FK `companies.id`) on `kam_visit_plans` + `client_profiles` (Task 1, DONE), backfilled from each KAM's `users.company_id`. New `GET /api/field-sales/companies` returns the companies the user may see + default. Existing list endpoints gain a `company_id` filter. The web Hub panel gains a company selector threaded into all queries.

**Tech Stack:** Flask/psycopg2; React + TanStack Query + Tailwind; Vitest. This is Phase 1; Phase 2 (add-info-during-visit) builds on it.

## Global Constraints
- Work in the worktree on `fs-tenant-build`. Additive schema only. No table drops.
- Company model: **default** = `users.company_id`. **Allowed**: Admin role → all `companies`; else `company_responsables.company_id` for the user UNION `users.company_id`; if empty → `[users.company_id]`. Single allowed company → selector **locked**.
- Backfill (Task 1, done): `kam_visit_plans.company_id` = the KAM's `users.company_id`; `client_profiles.company_id` = assigned KAM's company, else the client's most-recent visit's company, else NULL.
- Filtering: when `company_id` supplied, filter (`visits` by `kam_visit_plans.company_id`, `clients` by `client_profiles.company_id`). NULL-company rows excluded under a company filter; visible to Admins in the unfiltered view.
- Reuse `_get_current_user()`, `_is_manager()`, `_has_permission()` from `field_sales/routes/_shared.py`. No raw SQL in route bodies (repo methods).
- Romanian UI; iOS sizing; reuse DrivingCalendar/HubDrivingPanel selector styling. Tests PRISTINE (RTL waitFor). Run from `jarvis/frontend`: `npx vitest run <p>`, `npx tsc --noEmit`. Backend parse: `python3 -c "import ast;ast.parse(open('jarvis/field_sales/routes/<f>.py').read())"`. Do NOT `npm run build` in task commits; commit source only. Commit hook prints a repo-wide report — ignore its pre-existing failures.

## Tasks
### Task 1 (DONE — committed dev 361b3bba0): company_id columns + backfill
Applied to localhost (14/14 visits, 7/15 profiles). In `fs-tenant-build` history via dev base.

### Task 2: companies endpoint + tag visit company on create
- `get_allowed_companies(user_id, is_admin)` repo method: Admin → all companies; else companies in `company_responsables` for user UNION user's own company; fallback to own.
- Route `GET /api/field-sales/companies` (`@field_sales_required`) → `{ success, companies:[{id,company}], default_company_id: user.company_id }`.
- `api_create_visit`: set `visit_data['company_id']` = the resolved KAM's `users.company_id`; `VisitRepository.create()` INSERTs `company_id`.
- Verify parse. Commit `feat(field-sales): companies endpoint + tag visit company on create`.

### Task 3: company_id filter on list endpoints
- Optional `company_id` on `get_by_kam_and_date`, `get_team_visits`, client search (append `AND <t>.company_id = %s`).
- Thread `request.args.get('company_id', type=int)` into `visits/today`, `visits/mine`, `manager/overview`, `clients/search`.
- Commit `feat(field-sales): company_id filtering on visit/client list endpoints`.

### Task 4: web API company-scoping wrappers
- `getFieldSalesCompanies()`; optional `companyId` on `getTodayVisits`, `getMyVisits`, `searchClients`, `getManagerOverview` (append `company_id` when >0).
- TDD tests; tsc clean. Commit `feat(field-sales): web api company scoping wrappers`.

### Task 5: Hub company selector + threading
- Company selector (DrivingCalendar style) fed by `getFieldSalesCompanies()`; init from `default_company_id` (persist `usePersistedState('hub-fs-company',0)`, override to default when 0 or persisted id not in allowed list); single allowed → locked label.
- Thread `companyId` into every field-sales query key + call (today/upcoming/search/calendar).
- Tests: defaults to default_company_id; single-company → locked; switching refetches with new company_id. Keep existing tests green (mock returns one company → locked). Commit `feat(field-sales): Hub company selector defaulting to user company + query threading`.

### Task 6: full verification + final review
- tsc clean; full `npx vitest run` green pristine; `npm run build` ok then revert build artifacts.
- Backend `ast.parse` on changed files.
- Final whole-branch review over the Phase-1 range; then ff-merge `fs-tenant-build` → `dev`.

## Self-Review
Schema+backfill (T1 done); companies endpoint+default+create-tag (T2); filters (T3); web wrappers (T4); selector+threading (T5); verify+merge (T6). Backfill idempotent; filters exclude NULL-company under a filter; company_id nullable so inserts safe; no raw SQL in routes.
