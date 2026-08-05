# Repoint manager/team visibility to the Sincron organigram

**Date:** 2026-07-29
**Status:** Approved (design)
**Scope:** `JARVIS` backend — rewrite the 3 functions in `core/organization/manager_utils.py` so the manager/team hierarchy (L1–L5) is sourced from the **Sincron organigram** (`sincron_org_nodes` / `sincron_org_members`) instead of the JARVIS structure tree (`structure_nodes` / `structure_node_members`). L0 (whole-company) is unchanged. Developed on branch `feature/team-sincron-org` (isolated from `dev`).

## Problem

JARVIS has **two independent org trees**:
- `structure_nodes` / `structure_node_members` / `company_responsables` — the JARVIS hierarchy the manager/team functions read today.
- `sincron_org_nodes` / `sincron_org_members` — the **Sincron organigram** the user maintains (and that Department Pulse already uses).

The "team" surfaces show a team derived from the JARVIS tree, which disagrees with the Sincron organigram the user manages (99 vs 74 nodes; 314 vs 322 members). The user wants "my team" to conform to the Sincron organigram.

The three functions in `core/organization/manager_utils.py` are the single choke point — all ~10 team consumers call them:
- HR Pontaje (`/profile/api/team-pontaje`), 360 module (nomination / report / dev-plan services), Time Bank, Field Sales (tasks/visits), HR Events/Organigram, BioStar, Connecteam (Învoiri "De aprobat").

## Goal

Rewrite the 3 functions so the **team tree (L1–L5) comes from the Sincron organigram**, keeping their exact signatures and return shapes so **no consumer changes**. **L0 stays exactly as-is** (`company_responsables` → whole company).

## Non-goals (explicit)

- **Accounting is out of scope and untouched.** The Accounting/invoice module scopes visibility through its **own** `core/utils/org_scope.py` (`get_org_scope` / `build_allocation_org_filter`), which has **zero** references to these functions and does not import `manager_utils`/`hr_utils`. Accounting keeps using the JARVIS `structure_nodes` tree. Verified 2026-07-29. (Consequence, accepted: HR uses Sincron, Accounting uses the JARVIS tree — two sources by design.)
- **No feature flag** — clean swap (user decision).
- **Org completeness is not addressed here.** The Sincron organigram is currently a flat operational map missing the upper management layer (see "Known impact"); the user has chosen to proceed against it as-is. Editing/completing the organigram is a separate effort.

## Design

### The mapping (structure → Sincron)

| JARVIS today | Sincron equivalent |
|---|---|
| `structure_nodes` (`id`, `parent_id`, `company_id`, `level`) | `sincron_org_nodes` — same columns |
| `structure_node_members.role = 'team'` | `sincron_org_members.role = 'member'` |
| `structure_node_members.role = 'responsable'` | `sincron_org_members.role = 'responsable'` |
| `structure_node_members.user_id` (direct FK to users) | `sincron_org_members` → `sincron_employees` (join on `sincron_employee_id` + `company_name`, `is_active`) → `mapped_jarvis_user_id` (one extra hop) |

Every recursive descent is over `sincron_org_nodes.parent_id` (same shape as the JARVIS tree). The **only** structural difference is the member→user hop through `sincron_employees.mapped_jarvis_user_id`. The rewrite stays in `manager_utils.py`'s existing raw-`get_db()`/cursor style (no new repository) to match the file.

### `is_manager(user_id) -> bool` (unchanged contract)

`True` if the user is a Sincron `responsable` **or** in `company_responsables` (L0):

```sql
-- (a) Sincron responsable via mapped user
SELECT 1 FROM sincron_org_members som
JOIN sincron_employees se
  ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
LIMIT 1;
-- (b) L0 (unchanged)
SELECT 1 FROM company_responsables WHERE user_id = %s LIMIT 1;
```

### `get_managed_employee_ids(user_id, node_id=None) -> [user_id]` (unchanged contract)

**With `node_id`** — that Sincron node + descendants → `member`s → mapped users, excluding self:

```sql
WITH RECURSIVE descendants AS (
    SELECT id FROM sincron_org_nodes WHERE id = %s
    UNION ALL
    SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
)
SELECT DISTINCT se.mapped_jarvis_user_id
FROM descendants d
JOIN sincron_org_members m ON m.node_id = d.id AND m.role = 'member'
JOIN sincron_employees se
  ON se.sincron_employee_id = m.sincron_employee_id AND se.company_name = m.company_name
WHERE se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE
  AND se.mapped_jarvis_user_id <> %s;
```

**Without `node_id`** — union of L0 (unchanged) + Sincron tree descent, deduped:

```sql
-- L0 (UNCHANGED): whole company
SELECT DISTINCT u.id
FROM company_responsables cr
JOIN users u ON u.company_id = cr.company_id AND u.is_active = TRUE
WHERE cr.user_id = %s AND u.id <> %s;

-- Sincron tree descent from the caller's responsable nodes
WITH RECURSIVE resp_nodes AS (
    SELECT som.node_id AS id
    FROM sincron_org_members som
    JOIN sincron_employees se
      ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
    WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
),
descendants AS (
    SELECT id FROM resp_nodes
    UNION ALL
    SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
)
SELECT DISTINCT se.mapped_jarvis_user_id
FROM descendants d
JOIN sincron_org_members m ON m.node_id = d.id AND m.role = 'member'
JOIN sincron_employees se
  ON se.sincron_employee_id = m.sincron_employee_id AND se.company_name = m.company_name
WHERE se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE
  AND se.mapped_jarvis_user_id <> %s;
```

Return `list(set(l0_ids + tree_ids))`. (The old L0 branch also unioned a `structure_users` sub-CTE; it is dropped because `company_users` — all active users of the L0 companies — is a superset.)

### `get_visible_tree(user_id) -> {companies, nodes}` (unchanged contract)

`companies` from L0 (unchanged); `nodes` from the caller's Sincron responsable-node + descendants. Node `id` is now a `sincron_org_nodes.id`:

```sql
-- companies (UNCHANGED)
SELECT c.id, c.company AS name, 0 AS level
FROM company_responsables cr JOIN companies c ON c.id = cr.company_id
WHERE cr.user_id = %s;
-- → [{'id': 'company-{id}', 'name', 'level': 0, 'parent_id': None, 'company_id': id}]

-- nodes (Sincron)
WITH RECURSIVE resp_nodes AS (
    SELECT som.node_id AS id
    FROM sincron_org_members som
    JOIN sincron_employees se
      ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
    WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
),
descendants AS (
    SELECT id FROM resp_nodes
    UNION ALL
    SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
)
SELECT DISTINCT n.id, n.name, n.level, n.parent_id, n.company_id
FROM descendants d JOIN sincron_org_nodes n ON n.id = d.id
ORDER BY n.level, n.name;
-- → [{'id', 'name', 'level', 'parent_id', 'company_id'}]
```

### Node-id namespace consistency

`get_visible_tree` emits Sincron node-ids and `get_managed_employee_ids(node_id=…)` consumes Sincron node-ids — same source, coherent. `node_id` is a **transient request param** (frontend loads the tree, user picks a node, sends it back), never persisted. The plan will `grep` to confirm no saved filter/preset persists a `structure_nodes.id` as an org node id.

## Known impact (from prod analysis 2026-07-29, accepted as intended)

- **Mapping coverage:** 323/324 Sincron org members resolve to an active mapped JARVIS user (~100%). 1 unmapped member simply won't appear.
- **Manager count:** 44 today → 37 under Sincron (L0 = 5, unchanged).
- **16 lose manager access** (responsable in the JARVIS tree only); 8 have real teams today — e.g. Capota Teodora (15), Ilies Emanuela (11), Radu Anda (11). These are division/sales heads the Sincron org doesn't yet model at the top.
- **9 gain** (responsable in Sincron only) — e.g. Tulbure Ovidiu (18), Vlaic Teodor (14) — foremen who own real crews in Sincron.
- **Team-size shifts** for those who stay — e.g. Parocescu 57→1, Duca 29→3 — because the Sincron org is a flatter operational map (workshops) vs the JARVIS management rollup (division heads see all below).

These changes are **expected** given the current Sincron organigram and are accepted (user chose to proceed).

## Edge cases

- **User not a `responsable` and not L0** → empty team, `is_manager=False` (correct).
- **User not mapped to any Sincron employee** → no tree team (only L0 if applicable).
- **Unmapped Sincron member** (`mapped_jarvis_user_id IS NULL`) → excluded (can't reference a JARVIS user).
- **Node with no responsable** (1 of 74) → nobody manages it via the tree (its members only appear under an ancestor responsable).
- **Multiple responsables on one node** → each sees that node + descendants (union across consumers as before).
- **`node_id` outside the caller's scope** → the descendant query still returns that node's members; callers already pass node-ids from `get_visible_tree` (their own scope), matching prior behavior (no server-side re-check today; unchanged).

## Testing

pytest on **localhost/defaultdb** only, with a seeded fixture (a company + `company_responsables` L0 user, a small `sincron_org_nodes` tree with responsable + member `sincron_org_members`, `sincron_employees` mapping members to `users`, plus an unmapped member and a user outside the tree). Assert:
- `is_manager`: Sincron responsable → True; L0 → True; plain member / outsider → False.
- `get_managed_employee_ids`: responsable sees node + descendant members (mapped); `node_id` filter; L0 sees whole company; excludes self; unmapped member excluded.
- `get_visible_tree`: `nodes` from Sincron (correct ids/parent_id/level), `companies` from L0.
Reuse the CI-safe DB-test harness from Department Pulse (`tests/dept_pulse/conftest.py` pattern: real-psycopg2 bypass + skip when no DB, so CI stays green). New tests under `tests/org/`.

## Deploy

Isolated `feature/team-sincron-org` branch (off `dev`). After merge/verify, ship via **surgical cherry-pick** to `staging` then `main` (the repo's dev↔main content divergence makes a wholesale merge unsafe — see the branch-drift reference). `manager_utils.py` currently matches `main`, so the cherry-pick is clean. Backend-only change; no migration, no frontend build.

## Out of scope

- Accounting / invoice visibility (separate `org_scope.py`, untouched).
- Completing the Sincron organigram's upper management layer (division-head nodes).
- Any org-editing UI.
- Feature flag / gradual rollout.
- The consumers themselves (their code is unchanged).
