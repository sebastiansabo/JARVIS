# HUB Team Pontaje — Design

**Date:** 2026-07-15
**Status:** Approved (Approach A)

## Goal

Let a user who manages a team (organigram responsable / L0) see their **team's pontaje**
in the **HUB**, not just their own punches. Applies generically to any manager — including
users with the **Viewer** role, which is the immediate driver (user 312, Bogdan Paul-Dorin).

## Context / current state

- The HUB (`jarvis/frontend/src/pages/Hub/index.tsx` → `HubHrPanel`) shows a personal
  **Pontaje** tab (the logged-in user's own punches via `profileApi.getPontaje`), plus
  **Bonuses** and **Leave Permits**. Tabs are data-gated by an `availableTabs` array — a tab
  only appears when it has content.
- **Team-scoped pontaje already exists end-to-end**, but only on the **Profile** page:
  - Backend: `GET /profile/api/team-pontaje` (`core/profile/routes.py`) — gated by
    `is_manager(current_user.id)`, scoped via `get_managed_employee_ids()`, supports
    `mode=daily` and `mode=range`.
  - Frontend API: `profileApi.getTeamPontaje({ mode, start, end, ... })`.
  - Full UI: `TeamPontajePanel` in `Profile/index.tsx` (org-tree filter, daily/range toggle,
    punch drill-down).
- The team endpoint is gated on **`is_manager`, not `can_access_hr`**. The Viewer role
  (`can_access_hr = false`) can already call it if the user is a responsable. **No role or
  permission change is required.**

**Gap:** the team view is not surfaced in the HUB.

## Approach (A — compact new tab)

Add a **Team Pontaje** tab to `HubHrPanel`, matching the existing compact, data-gated tab
pattern. No backend change.

### Changes (single file: `Hub/index.tsx`)

1. Import the `Users` lucide icon.
2. Extend `HrSubTab`: add `'team-pontaje'`.
3. In `HubHrPanel`, pre-fetch team data for the selected month:
   ```ts
   const { data: teamData } = useQuery({
     queryKey: ['hub', 'team-pontaje', start, end],
     queryFn: () => profileApi.getTeamPontaje({ mode: 'range', start, end }),
   })
   const teamCount = teamData?.is_manager ? (teamData.summary?.length ?? 0) : 0
   ```
4. Push the tab when `teamCount > 0`:
   `tabs.push({ key: 'team-pontaje', label: 'Team Pontaje', icon: Users })`.
   (Reuses the same month navigator already in the panel.)
5. Render `{effectiveTab === 'team-pontaje' && <HubTeamPontajeContent year month />}`.
6. New component `HubTeamPontajeContent` — compact per-employee list mirroring
   `HubPontajeContent` styling:
   - fetch `getTeamPontaje({ mode: 'range', start, end })` (same queryKey → cache hit);
   - one row per employee: name, `days_present` days, net hours;
   - net hours = `((adjusted_total_duration_seconds ?? total_duration_seconds) −
     lunch_break_minutes*60*days_present) / 3600`, clamped at 0 (matches HR Pontaje formula);
   - color: green ≥ expected-ish, amber > 0, muted 0 (reuse existing thresholds);
   - header row: employee count + summed team hours;
   - empty/loading states like the other Hub content components.

### Out of scope (kept minimal / YAGNI)

- No org-tree node filter, no daily/range toggle, no punch drill-down in the HUB (those stay
  in the Profile `TeamPontajePanel` for the full view).
- No backend changes.
- No changes to the Viewer role, `can_access_hr`, or any permission.

## Data prerequisite (separate follow-up, not code)

For **Bogdan (user 312)** specifically to see a team, he must be assigned as a **responsable**
on an organigram node (`structure_node_members.role = 'responsable'`) or as an L0
`company_responsables` row. Today he manages nobody, so the tab correctly will not appear.
The *code* is generic and needs no per-user work; wiring Bogdan's actual team is a production
data change requiring the target node/company and the standard 2-confirmation rule.

## Testing / verification

- Manager with a team → **Team Pontaje** tab appears in HUB, lists team members with days +
  hours for the month; month nav updates data.
- Non-manager (no team) → tab does not appear (endpoint returns `is_manager: false`);
  existing personal tabs unchanged.
- Build passes: `npm run build` in `jarvis/frontend`.
