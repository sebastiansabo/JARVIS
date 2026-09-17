# CarPark Permissions — Wire the Matrix, Scope Companies, Close Finance Leak

- **Date:** 2026-09-17
- **Branch:** `feature/carpark-permissions-matrix` (off `origin/staging`)
- **Status:** Design — awaiting review before implementation plan
- **Related tickets:** JAR-1171/1175/1176 (tenant switcher), JAR-1521 (autovit), CarPark permission review (this session)

---

## 1. Problem

CarPark runs on **two disconnected permission systems**:

1. **v2 matrix** — `permissions_v2` + `role_permissions_v2` with scopes (`deny/own/department/all`). This is what admins edit in the permissions UI. For CarPark it contains **one** row: `carpark.module.access`.
2. **v1 booleans** — `roles.can_access_carpark / can_edit_carpark / can_delete_carpark / can_view_carpark_finance`. **Every** CarPark API decorator (`carpark_required`, `carpark_edit_required`, `carpark_delete_required` in `jarvis/carpark/routes/vehicles.py`) and **every** frontend Guard/Sidebar entry read these booleans.

The two are **never synced for CarPark**. The booleans are only ever set `TRUE` for the `Admin` role, hardcoded in a migration (`jarvis/migrations/domains/schema_carpark.py:913-925`). No admin UI, no role editor, and no v2→boolean sync writes them for any other role:

- `MODULE_ACCESS_COLUMNS` (`jarvis/core/roles/routes.py:191`) lists `hr, accounting, statements, efactura, settings, sales` — **carpark absent**.
- `_sync_v2_permissions_to_booleans` (`jarvis/core/roles/repositories/permission_repository.py:329`) — **carpark absent**.
- `RoleRepository.create_role/update_role` — handles only invoices/accounting/settings/connectors/templates/hr — **carpark absent**.

### Observed symptom
A **Manager** granted CarPark = "all" in the matrix (the v2 seed grants Manager `carpark.module.access = all`) still cannot select **his own company** in the tenant switcher. Chain:

1. Matrix shows "CarPark: All" for Manager → false expectation of access.
2. `roles.can_access_carpark` for Manager stays `FALSE` (nothing synced it).
3. `GET /api/carpark/companies` is gated by `@carpark_required` → **403**.
4. Frontend: `companies = companiesData?.companies ?? []` → empty; the `<Select>` still renders (its value is `user.company_id` from the non-gated `/api/auth/current-user`) but has **zero options** → he cannot pick any company, including his own (`jarvis/frontend/src/pages/CarPark/index.tsx`, tenant switcher block).

`list_companies()` (`jarvis/carpark/repositories/vehicle_repository.py`, `SELECT id, company AS name FROM companies`) is **unscoped** and `_acting_company_id()` (`jarvis/carpark/routes/vehicles.py:70`) **trusts client-supplied `company_id` with no authorization** — so the same design is simultaneously over-permissive (any acting company) and under-functional (no access without the hidden boolean). Role scope (`own/department/all`) never touches company selection.

---

## 2. Goals / Non-goals

### Goals
- Make the permissions matrix **actually drive** CarPark access/edit/delete/finance (sync-bridge; keep the boolean columns).
- Scope the company switcher to **own + org-responsable** companies; Admin sees all. Stop trusting client `company_id`.
- Close the **finance-data leak**: acquisition price / costs / margins / profitability must require `can_view_carpark_finance`.
- Backfill so the fix takes effect for existing roles on deploy (fixes the live Manager).

### Non-goals (deferred to separate tickets)
- Full migration of CarPark to `@v2_permission_required` (drop the booleans). Not now — higher risk, ~15 route files + FE.
- Photo IDOR (`PUT/DELETE /photos/<id>`).
- Connector auth holes (Autofox / Autovit gated on any-login).
- `can_access_carpark_mobile` wiring (no v2 key, unused in FE) — leave as-is.

### Resolved decisions
- **Manager delete default = `all`** (consistent with how Manager is treated for every other module; adjustable per-role in the matrix post-deploy).
- **Base branch = `staging`** (repo CLAUDE.md default).

---

## 3. Design

### 3.1 New v2 permission catalog

Add three entity permissions to `permissions_v2` so the matrix can express the full CarPark surface, each mapping 1:1 to an existing boolean column:

| v2 key (`module.entity.action`) | boolean it drives | is_scope_based |
|---|---|---|
| `carpark.module.access` (exists) | `can_access_carpark` | False |
| `carpark.vehicles.edit` (new) | `can_edit_carpark` | False |
| `carpark.vehicles.delete` (new) | `can_delete_carpark` | False |
| `carpark.finance.view` (new) | `can_view_carpark_finance` | False |

All `is_scope_based = False` (on/off, matching every other module's fine-grained perms). Company scoping is derived from the org hierarchy (§3.3), **not** from the permission scope field, so we do not need scope-based rows.

### 3.2 Seed + sync-bridge + backfill

**Dedicated seed** `_seed_carpark_permissions_v2(cursor, conn)` in `jarvis/migrations/domains/schema_roles.py`, invoked from the same place the other v2 seeds run (`schema_marketing.py`, after `_seed_sidebar_permissions_v2`). It:

1. `INSERT ... ON CONFLICT (module_key, entity_key, action_key) DO NOTHING` the three new `permissions_v2` rows.
2. Seeds `role_permissions_v2` with **explicit per-role defaults** (NOT the generic role-defaults loop inside `_seed_sidebar_permissions_v2`, whose "any `view`/`access` action → User gets `own`" rule would silently grant regular Users `carpark.finance.view`):

| perm | Admin | Manager | User | Viewer |
|---|---|---|---|---|
| `module.access` | all | all | own | deny |
| `vehicles.edit` | all | all | deny | deny |
| `vehicles.delete` | all | all | deny | deny |
| `finance.view` | all | all | deny | deny |

Insert with `ON CONFLICT (role_id, permission_id) DO NOTHING` so existing grants (e.g. an admin who already tuned a role) are never clobbered. `module.access` rows already exist on live DBs — the DO NOTHING keeps them.

**Sync-bridge** — add the four keys to `_sync_v2_permissions_to_booleans` `bool_updates` (`permission_repository.py:329`):

```python
'can_access_carpark':       perms.get('carpark.module.access', False),
'can_edit_carpark':         perms.get('carpark.vehicles.edit', False),
'can_delete_carpark':       perms.get('carpark.vehicles.delete', False),
'can_view_carpark_finance': perms.get('carpark.finance.view', False),
```

Both `set_role_permission_v2` (`:282`) and `set_role_permissions_v2_bulk` (`:311`) already call this, so any matrix save (single toggle or bulk) now writes the carpark booleans. Also add `'carpark': 'can_access_carpark'` to `MODULE_ACCESS_COLUMNS` (`routes.py:191`) for the module.access single-set path (belt-and-suspenders; `_sync` already covers it).

**One-time backfill** — seeding does not call `_sync` (that only fires on writes). End the seed function with an idempotent UPDATE that derives the carpark booleans from `role_permissions_v2` for **all** roles:

```sql
UPDATE roles r SET
  can_access_carpark       = COALESCE(x.access, FALSE),
  can_edit_carpark         = COALESCE(x.edit, FALSE),
  can_delete_carpark       = COALESCE(x.del, FALSE),
  can_view_carpark_finance = COALESCE(x.fin, FALSE)
FROM (
  SELECT rp.role_id,
    bool_or(p.entity_key='module'   AND p.action_key='access' AND rp.scope <> 'deny') AS access,
    bool_or(p.entity_key='vehicles' AND p.action_key='edit'   AND rp.scope <> 'deny') AS edit,
    bool_or(p.entity_key='vehicles' AND p.action_key='delete' AND rp.scope <> 'deny') AS del,
    bool_or(p.entity_key='finance'  AND p.action_key='view'   AND rp.scope <> 'deny') AS fin
  FROM role_permissions_v2 rp
  JOIN permissions_v2 p ON p.id = rp.permission_id
  WHERE p.module_key = 'carpark'
  GROUP BY rp.role_id
) x
WHERE x.role_id = r.id;
```

After deploy, Manager's existing `carpark.module.access = all` flips `can_access_carpark → TRUE`, and the new edit/delete/finance grants land — fixing the live symptom without manual DB edits.

> **Note on Admin:** the migration `schema_carpark.py:913-925` still sets all booleans TRUE for Admin; the backfill re-derives the same TRUE from the seeded Admin=all rows. Consistent.

### 3.3 Company scoping (own + org-responsable)

**New helper** in `jarvis/core/organization/manager_utils.py`:

```python
def get_actable_company_ids(user_id: int) -> set[int]:
    """Company ids a user may act on in CarPark:
    own company + L0 company_responsables + Sincron responsable subtree companies.
    (Admin bypass is handled by the caller — Admin sees all.)"""
```

Implementation unions three sources (all already used elsewhere in this file):
- own: `SELECT company_id FROM users WHERE id=%s AND company_id IS NOT NULL`
- L0: `SELECT company_id FROM company_responsables WHERE user_id=%s`
- subtree: reuse `get_visible_tree(user_id)` → `{c['company_id'] for c in tree['companies']} | {n['company_id'] for n in tree['nodes']}`

**`list_companies` route** (`vehicles.py:541`): Admin (`can_access_settings`) → all companies; otherwise pass `get_actable_company_ids(current_user.id)` to the repo. Add a `company_ids: set|None` filter to `VehicleRepository.list_companies` / `VehicleService.get_companies` (None = all). Empty set → return `[]` (defensive; user with no company and no responsibilities).

**`_acting_company_id()`** (`vehicles.py:70`): stop trusting the client.
- Compute `allowed = None if getattr(current_user, 'can_access_settings', False) else get_actable_company_ids(current_user.id)` (there is no `is_admin` on the User model — `can_access_settings` is the de-facto admin flag).
- If a `company_id` is supplied and `allowed is not None and cid not in allowed` → **403** (`{'success': False, 'error': 'Company not permitted'}`). Raising here requires callers to handle it; simplest is to keep `_acting_company_id` returning the int and add a companion `_require_acting_company_id()` that aborts 403, used by the read/catalog/analytics/pricing/publishing routes that currently call `_acting_company_id`.
- Absent `company_id` → own company (unchanged).

This closes the cross-tenant switcher hole while keeping the write paths (which already use `_user_company_id()` / `DispoService` company checks) intact.

### 3.4 Finance-leak closure

**New decorator** `carpark_finance_required` in `vehicles.py` (403 without `can_view_carpark_finance`, stacked after `carpark_required`). Apply to **purely-financial** read endpoints:
- `costs.py`: `/vehicles/<id>/costs`, `/costs/totals`, `/cost-lines*`, `/revenues*`, `/profitability`
- `pricing.py`: `/vehicles/<id>/floor-price`, `/pricing-history`
- `analytics.py`: `/analytics/costs`

**Field-stripping** for **mixed** endpoints non-finance users still need — lift the dispo `_strip_finance` pattern (`dispo.py`) into a shared `jarvis/carpark/finance_guard.py` exposing `FINANCE_FIELDS` + `strip_finance(payload)`; apply guarded by `can_view_carpark_finance` in:
- `vehicles.py` `GET /vehicles/<id>` (drop `acquisition_price`, cost/margin fields)
- `analytics.py` `/analytics/dashboard`, `/analytics/kpis`
- keep the existing dispo `/dispo/summary`, `/dispo/kpis` stripping (refactor to use the shared helper).

### 3.5 Frontend

- **Matrix**: no change — data-driven from `permissions_v2`; the three new toggles (Edit / Delete / Financial Data) appear automatically under CarPark.
- **Detail tabs** (`jarvis/frontend/src/pages/CarPark/Detail.tsx`): gate the **Costuri** and **Venituri** tabs and the profitability panel behind `can_view_carpark_finance` so non-finance users don't call now-403 endpoints. (ProfitabilityPanel is already gated; extend to the tabs.)
- **Switcher** (`pages/CarPark/index.tsx`): default the selected company to the user's own; hide the `<Select>` when only one company is available.

---

## 4. Data model changes

- `permissions_v2`: +3 rows (`carpark.vehicles.edit`, `carpark.vehicles.delete`, `carpark.finance.view`). No column changes.
- `role_permissions_v2`: +up-to-`(3 new perms × roles)` rows via explicit-default seed.
- `roles`: no new columns (the four boolean columns already exist). Values re-derived by backfill.
- No table/column drops. `company_responsables` and `sincron_org_*` are **read-only** here.

---

## 5. Testing

Backend (`jarvis/tests/carpark/`, `jarvis/tests/auth/`; DB tests need `DATABASE_URL=postgresql://localhost/defaultdb` forced — see repo gotcha):
- **sync**: toggling `carpark.vehicles.edit` via `set_role_permission_v2` flips `can_edit_carpark`; bulk save flips all four; `module.access` deny flips `can_access_carpark` FALSE.
- **seed defaults**: after seed, per-role booleans match the §3.2 matrix (esp. User/Viewer `finance = FALSE`).
- **backfill**: a role with only `carpark.module.access = all` and `can_access_carpark = FALSE` ends up TRUE after the backfill UPDATE.
- **company scoping**: `get_actable_company_ids` returns own + L0 + subtree; Admin path returns all; `list_companies` filtered; `_acting_company_id` foreign company → 403; own/absent → own.
- **finance**: `carpark_finance_required` → 403 without flag; `strip_finance` removes fields on mixed endpoints; extend `tests/auth/test_carpark_finance_flag.py`.

Frontend: `cd jarvis/frontend && npm run build` (zero TS errors); manual smoke — Manager with matrix access sees switcher + own company; non-finance user has no Costuri/Venituri tabs.

Pre-push checklist (repo CLAUDE.md): FE build, `pytest tests/ -x -q`, `py_compile app.py`, clean `git status`.

---

## 6. Rollout & safety

- All DDL/seed idempotent (`ON CONFLICT DO NOTHING`, guarded `UPDATE`). Migration is **additive** — no drops.
- Touches two protected files (`permission_repository.py`, `jarvis/migrations/domains/*`) — hence the spec-approval gate.
- Deploy order per repo workflow: **staging first**, validate `/health` + a Manager login, then main after explicit double confirmation.
- Backfill is safe to re-run (derives from current v2 grants each time).
- **Plan/spec doc stays on this feature branch and is removed before FF-promotion to `staging`** (per "no plan docs on staging/prod" preference).

---

## 7. Open questions

None blocking. Post-deploy, an admin may want to dial back specific roles (e.g. Manager delete) in the matrix — now possible for the first time.
