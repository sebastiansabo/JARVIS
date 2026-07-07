# BAB Indicator References — Junction Table Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile comma-separated string references in `subtotal_of` with a proper junction table (`bab_subtotal_refs`) using foreign keys, so subtotals reference indicators by ID.

**Architecture:** Keep `bab_report_config` as the single config table for both sum and subtotal rows. Add `bab_subtotal_refs(subtotal_row_id FK, indicator_row_id FK)` junction table. Migrate existing `subtotal_of` strings to junction rows. Update backend to read/write junction table. Update frontend to send/receive indicator IDs. Calculator resolves by ID lookup instead of string matching.

**Tech Stack:** PostgreSQL, Python/Flask, React/TypeScript, psycopg2 (raw SQL via BaseRepository)

## Global Constraints

- All DB changes via idempotent migration in `database.py` schema init
- Repository pattern: all SQL in `repository.py`, never in routes
- JARVIS uses raw psycopg2 + `BaseRepository`, NOT SQLAlchemy
- Frontend uses `@tanstack/react-query` for data fetching
- `subtotal_of` column kept temporarily for backward compat during migration, dropped in final task
- Production data: 3 companies, 51 sum rows, 6 subtotal rows — small migration

## File Structure

| File | Role | Change |
|------|------|--------|
| `jarvis/database.py` | Schema migrations | Add `bab_subtotal_refs` table DDL |
| `jarvis/accounting/controlling_bab/repository.py` | Data access | Add junction CRUD, update config queries to JOIN refs |
| `jarvis/accounting/controlling_bab/routes.py` | API endpoints | Return `indicator_ids[]` on config rows, accept `indicator_ids[]` on save |
| `jarvis/accounting/controlling_bab/calculator.py` | Report engine | Resolve subtotals by ID instead of string match |
| `jarvis/frontend/src/types/controlling.ts` | TS types | Add `indicator_ids?: number[]` to `BabConfigRow` |
| `jarvis/frontend/src/pages/Accounting/Controlling/index.tsx` | UI | SubtotalPicker toggles by row ID instead of qualified string |

---

### Task 1: Create junction table + migrate existing data

**Files:**
- Modify: `jarvis/database.py` (schema init section)
- Modify: `jarvis/accounting/controlling_bab/repository.py`

**Produces:**
- `bab_subtotal_refs` table with FK constraints
- All existing `subtotal_of` strings migrated to junction rows
- `repo.get_subtotal_refs(subtotal_row_id) -> list[int]`
- `repo.set_subtotal_refs(subtotal_row_id, indicator_ids: list[int])`

- [ ] **Step 1: Add DDL to database.py**

Find the BAB schema section in `database.py` and add:

```sql
CREATE TABLE IF NOT EXISTS bab_subtotal_refs (
    subtotal_row_id INTEGER NOT NULL REFERENCES bab_report_config(id) ON DELETE CASCADE,
    indicator_row_id INTEGER NOT NULL REFERENCES bab_report_config(id) ON DELETE CASCADE,
    PRIMARY KEY (subtotal_row_id, indicator_row_id)
);
```

- [ ] **Step 2: Add migration function to populate junction from existing subtotal_of**

In `database.py` migration section, add an idempotent migration that:
1. Selects all `bab_report_config` rows where `row_type='subtotal'` and `subtotal_of IS NOT NULL`
2. For each, parses `subtotal_of` by comma, matches each `"Group → Label"` to a sum row's ID in the same company
3. Inserts into `bab_subtotal_refs` (ON CONFLICT DO NOTHING)

```python
def _migrate_subtotal_refs(cursor):
    """Migrate subtotal_of strings to bab_subtotal_refs junction table."""
    cursor.execute("""
        SELECT id, company_id, subtotal_of FROM bab_report_config
        WHERE row_type = 'subtotal' AND subtotal_of IS NOT NULL AND subtotal_of != ''
    """)
    subtotals = cursor.fetchall()
    for sub in subtotals:
        sub_id, company_id, refs_str = sub[0], sub[1], sub[2]
        refs = [r.strip() for r in refs_str.split(',') if r.strip()]
        for ref in refs:
            if '→' in ref:
                parts = ref.split('→', 1)
                group = parts[0].strip()
                label = parts[1].strip()
                cursor.execute("""
                    INSERT INTO bab_subtotal_refs (subtotal_row_id, indicator_row_id)
                    SELECT %s, id FROM bab_report_config
                    WHERE company_id = %s AND group_name = %s AND item_label = %s AND row_type = 'sum'
                    LIMIT 1
                    ON CONFLICT DO NOTHING
                """, (sub_id, company_id, group, label))
            else:
                # Legacy: match by label only
                cursor.execute("""
                    INSERT INTO bab_subtotal_refs (subtotal_row_id, indicator_row_id)
                    SELECT %s, id FROM bab_report_config
                    WHERE company_id = %s AND item_label = %s AND row_type = 'sum'
                    LIMIT 1
                    ON CONFLICT DO NOTHING
                """, (sub_id, company_id, ref))
```

- [ ] **Step 3: Add repository methods**

In `repository.py`, add:

```python
def get_subtotal_refs(self, subtotal_row_id):
    """Get indicator IDs for a subtotal row."""
    return [r['indicator_row_id'] for r in self.query_all(
        'SELECT indicator_row_id FROM bab_subtotal_refs WHERE subtotal_row_id = %s',
        (subtotal_row_id,))]

def set_subtotal_refs(self, subtotal_row_id, indicator_ids):
    """Replace all refs for a subtotal row."""
    def _work(cursor):
        cursor.execute('DELETE FROM bab_subtotal_refs WHERE subtotal_row_id = %s', (subtotal_row_id,))
        for ind_id in indicator_ids:
            cursor.execute(
                'INSERT INTO bab_subtotal_refs (subtotal_row_id, indicator_row_id) VALUES (%s, %s) ON CONFLICT DO NOTHING',
                (subtotal_row_id, ind_id))
        return len(indicator_ids)
    return self.execute_many(_work)
```

- [ ] **Step 4: Verify migration**

Run the app locally to trigger schema init. Then verify:

```sql
SELECT sr.subtotal_row_id, s.item_label as subtotal, sr.indicator_row_id, i.group_name, i.item_label as indicator
FROM bab_subtotal_refs sr
JOIN bab_report_config s ON s.id = sr.subtotal_row_id
JOIN bab_report_config i ON i.id = sr.indicator_row_id
ORDER BY sr.subtotal_row_id, i.sort_order;
```

- [ ] **Step 5: Commit**

```bash
git add jarvis/database.py jarvis/accounting/controlling_bab/repository.py
git commit -m "feat(controlling): add bab_subtotal_refs junction table + migrate existing data"
```

---

### Task 2: Update API to use indicator IDs

**Files:**
- Modify: `jarvis/accounting/controlling_bab/routes.py`
- Modify: `jarvis/accounting/controlling_bab/repository.py`

**Consumes:** `repo.get_subtotal_refs()`, `repo.set_subtotal_refs()` from Task 1

**Produces:**
- GET `/config` returns `indicator_ids: number[]` on each subtotal row
- POST/PUT `/config` accepts `indicator_ids: number[]` and writes to junction table
- `subtotal_of` still written for backward compat (calculator still reads it until Task 3)

- [ ] **Step 1: Update get_config to include indicator_ids**

In `repository.py`, modify `get_config()` to LEFT JOIN and aggregate indicator IDs:

```python
def get_config(self, company_id):
    rows = self.query_all(
        'SELECT * FROM bab_report_config WHERE company_id = %s ORDER BY sort_order',
        (company_id,))
    # Attach indicator_ids for subtotal rows
    for row in rows:
        if row.get('row_type') == 'subtotal':
            row['indicator_ids'] = self.get_subtotal_refs(row['id'])
        else:
            row['indicator_ids'] = []
    return rows
```

- [ ] **Step 2: Update add/update routes to handle indicator_ids**

In `routes.py`, after saving a config row, if `indicator_ids` is provided and `row_type == 'subtotal'`, call `repo.set_subtotal_refs()`:

```python
# In api_add_config_row, after row = _repo.save_config_row(...)
if data.get('row_type') == 'subtotal' and 'indicator_ids' in data:
    _repo.set_subtotal_refs(row['id'], data['indicator_ids'])
    row['indicator_ids'] = data['indicator_ids']

# In api_update_config_row, after row = _repo.update_config_row(...)
if data.get('row_type') == 'subtotal' and 'indicator_ids' in data:
    _repo.set_subtotal_refs(row['id'], data['indicator_ids'])
    row['indicator_ids'] = data['indicator_ids']
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/accounting/controlling_bab/routes.py jarvis/accounting/controlling_bab/repository.py
git commit -m "feat(controlling): API returns/accepts indicator_ids for subtotal rows"
```

---

### Task 3: Update calculator to resolve by ID

**Files:**
- Modify: `jarvis/accounting/controlling_bab/calculator.py`
- Modify: `jarvis/accounting/controlling_bab/routes.py` (pass config with IDs to calculator)

**Consumes:** Config rows now have `indicator_ids: list[int]`

**Produces:** Calculator resolves subtotals by row ID instead of string matching

- [ ] **Step 1: Update calculator to use indicator_ids**

In `calculator.py`, change the subtotal resolution from string matching to ID lookup:

```python
# Build id → row_key map
id_to_key = {}
for row in sorted(config, key=lambda r: r.get('sort_order', 0)):
    if row.get('id'):
        id_to_key[row['id']] = f"{row['group_name']}|{row['item_label']}"

# In the subtotal branch:
if row.get('row_type') == 'subtotal':
    indicator_ids = row.get('indicator_ids', [])
    if indicator_ids:
        # New: resolve by ID
        total = Decimal('0')
        for ind_id in indicator_ids:
            ref_key = id_to_key.get(ind_id)
            if ref_key and ref_key in computed:
                total += computed[ref_key]
        computed[row_key] = total
    elif row.get('subtotal_of'):
        # Legacy fallback: string matching (keep for backward compat)
        # ... existing string matching code ...
```

- [ ] **Step 2: Commit**

```bash
git add jarvis/accounting/controlling_bab/calculator.py jarvis/accounting/controlling_bab/routes.py
git commit -m "feat(controlling): calculator resolves subtotals by indicator ID"
```

---

### Task 4: Update frontend to use indicator IDs

**Files:**
- Modify: `jarvis/frontend/src/types/controlling.ts`
- Modify: `jarvis/frontend/src/pages/Accounting/Controlling/index.tsx`

**Consumes:** API now returns `indicator_ids: number[]` on config rows

**Produces:** SubtotalPicker toggles by row ID. Save sends `indicator_ids` array.

- [ ] **Step 1: Update TypeScript type**

In `controlling.ts`, add `indicator_ids` to `BabConfigRow`:

```typescript
export interface BabConfigRow {
  id?: number
  company_id: number
  sort_order: number
  kst: number
  group_name: string
  item_label: string
  konto_list: string
  row_type: 'sum' | 'subtotal'
  subtotal_of?: string | null  // kept for backward compat
  indicator_ids?: number[]     // NEW: array of indicator row IDs
  is_main_total?: boolean
}
```

- [ ] **Step 2: Update SubtotalPicker to use IDs**

Change `availableIndicators` to include `id`:

```typescript
const availableIndicators = useMemo(() => {
  return sumRows.map(r => ({
    id: r.id!,
    label: r.item_label,
    group: r.group_name,
  }))
}, [sumRows])
```

Change `SubtotalPicker` props from `selected: string` + `onToggle(qualified)` to `selectedIds: number[]` + `onToggle(id: number)`.

Chip selection uses `selectedIds.includes(item.id)` instead of `selectedSet.has(item.qualified)`.

- [ ] **Step 3: Update ConfigTable state and mutations**

`newTotalRow` and `editRow` use `indicator_ids: number[]` instead of `subtotal_of: string`.

The `addMutation` and `updateMutation` send `indicator_ids` in the request body.

- [ ] **Step 4: Build and verify**

```bash
cd jarvis/frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/types/controlling.ts jarvis/frontend/src/pages/Accounting/Controlling/index.tsx
git commit -m "feat(controlling): frontend uses indicator IDs instead of string refs"
```

---

### Task 5: Drop subtotal_of column (cleanup)

**Files:**
- Modify: `jarvis/database.py`
- Modify: `jarvis/accounting/controlling_bab/repository.py`
- Modify: `jarvis/accounting/controlling_bab/calculator.py`

**Note:** Only do this AFTER verifying everything works end-to-end on staging.

- [ ] **Step 1: Remove subtotal_of from all SQL queries**

Remove `subtotal_of` from INSERT, UPDATE, and SELECT in repository.py.

- [ ] **Step 2: Remove legacy string matching from calculator**

Remove the `elif row.get('subtotal_of')` fallback branch.

- [ ] **Step 3: Add column drop migration**

```sql
ALTER TABLE bab_report_config DROP COLUMN IF EXISTS subtotal_of;
```

- [ ] **Step 4: Remove subtotal_of from TypeScript type**

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(controlling): drop subtotal_of column — fully migrated to junction table"
```
