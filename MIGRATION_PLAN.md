# Database Consolidation Plan

## Goal
Consolidate 3 people tables (`users`, `responsables`, `hr.employees`) into a single `users` table.

## Current State

| Table | Rows | Purpose |
|-------|------|---------|
| `users` | 17 | App users (login) |
| `responsables` | 139 | Invoice responsibles |
| `hr.employees` | 113 | HR employees |

**Problem**: Same person can exist in multiple tables with different data.

## Target Structure

```
┌─────────────────────────────────────────────────────────────┐
│                          users                               │
│  id | name | email | phone | role_id | is_active            │
│  (SINGLE source for ALL people)                              │
└───────────────────────────┬─────────────────────────────────┘
                            │ user_id (FK)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   company_structure                          │
│  id | user_id | company_id | brand | department | subdept   │
│  (Links users to organizational units)                       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   companies            brands            departments
```

## Migration Steps

### Phase 1: Prepare `users` table
1. Add columns to `users`: `phone`, `is_active`, `notify_on_allocation`
2. These columns already exist from previous migration

### Phase 2: Merge `responsables` → `users`
1. For each responsable with email:
   - If user with same email exists → update user with responsable data
   - If no user exists → create new user (without login, role=NULL)
2. For responsables without email:
   - Create user with name only (email=NULL, can't login)

### Phase 3: Merge `hr.employees` → `users`
1. For each employee:
   - Match by email first, then by name
   - If user exists → link employee to user
   - If no user → create new user

### Phase 4: Update foreign key references
1. `allocations.responsible` (text) → `allocations.responsible_user_id` (FK)
2. `department_structure.manager` (text) → `department_structure.manager_user_id` (FK)
3. `hr.event_bonuses.employee_id` → points to `users.id`

### Phase 5: Update application code
1. Update all queries to use `user_id` instead of name matching
2. Update forms to use user dropdowns
3. Update profile page to use user data directly

### Phase 6: Cleanup (after verification)
1. Drop `responsables` table
2. Drop `hr.employees` table
3. Remove legacy columns

## Data Mapping

### responsables → users
| responsables | users |
|--------------|-------|
| name | name |
| email | email |
| phone | phone |
| notify_on_allocation | notify_on_allocation |
| company | (via company_structure) |
| brand | (via company_structure) |
| departments | (via company_structure) |

### hr.employees → users
| hr.employees | users |
|--------------|-------|
| name | name |
| company | (via company_structure) |
| brand | (via company_structure) |
| department | (via company_structure) |
| is_active | is_active |

## Rollback Plan
- Keep original tables until migration verified
- Add `_migrated_at` timestamp to track migrated records
- Create backup before migration
