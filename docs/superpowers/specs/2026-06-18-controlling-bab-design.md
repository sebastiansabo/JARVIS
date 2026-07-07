# BAB Module (Controlling) — Design Spec

**Date**: 2026-06-18
**Module**: `accounting/controlling_bab/`
**Nav**: Accounting → Controlling
**Route**: `/app/accounting/controlling`

---

## 1. Mission

Monthly BAB (Betriebsabrechnungsbogen) import from `.xlsx` ERP exports, with a structured Marja (margin) report computed from the imported data. Two views: 12-month period dashboard grid + detailed MarjaReport.

---

## 2. Backend Structure

```
jarvis/accounting/controlling_bab/
├── __init__.py          # Blueprint: controlling_bab_bp
├── routes.py            # All API routes under /controlling/bab/api/
├── repository.py        # BabRepository(BaseRepository) — raw SQL
├── parser.py            # parse_bab_xlsx() — openpyxl → list[dict]
├── calculator.py        # compute_marja_report() — pure function
└── exporter.py          # export_marja_xlsx() — openpyxl styled output
```

- Flask blueprint, registered in `app.py` with no URL prefix
- Raw SQL via `BaseRepository` (query_one, query_all, execute, execute_many)
- Permission check via `_check_bab_perm(action)` using V2 system
- No Redis caching — compute on-the-fly (<50ms for ~500 rows)
- No Pydantic schemas — plain dicts + `request.get_json()`

---

## 3. Database Schema

### 3.1 `bab_uploads`

One row per company per period. Tracks upload state and lock status.

```sql
CREATE TABLE IF NOT EXISTS bab_uploads (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    period_year     SMALLINT NOT NULL,
    period_month    SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    filename        TEXT NOT NULL,
    uploaded_by     INTEGER NOT NULL REFERENCES users(id),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_count       INTEGER,
    status          TEXT NOT NULL DEFAULT 'processing'
                      CHECK (status IN ('processing', 'ready', 'error')),
    error_msg       TEXT,
    locked_at       TIMESTAMPTZ,
    locked_by       INTEGER REFERENCES users(id),
    unlocked_at     TIMESTAMPTZ,
    unlocked_by     INTEGER REFERENCES users(id),
    import_count    SMALLINT NOT NULL DEFAULT 1,
    UNIQUE (company_id, period_year, period_month)
);
```

### 3.2 `bab_entries`

Parsed account lines from the BAB xlsx. Raw data, no aggregation.

```sql
CREATE TABLE IF NOT EXISTS bab_entries (
    id              SERIAL PRIMARY KEY,
    upload_id       INTEGER NOT NULL REFERENCES bab_uploads(id) ON DELETE CASCADE,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    konto           INTEGER NOT NULL,
    konto_bez       TEXT,
    saldo1          NUMERIC(18,2) NOT NULL,
    kostenstelle    INTEGER NOT NULL,
    kst_bez1        TEXT
);

CREATE INDEX IF NOT EXISTS idx_bab_entries_upload ON bab_entries(upload_id);
CREATE INDEX IF NOT EXISTS idx_bab_entries_konto ON bab_entries(upload_id, konto);
CREATE INDEX IF NOT EXISTS idx_bab_entries_kst ON bab_entries(upload_id, kostenstelle);
CREATE INDEX IF NOT EXISTS idx_bab_entries_company ON bab_entries(company_id);
```

### 3.3 `bab_eur_rates`

EUR exchange rate per company per period.

```sql
CREATE TABLE IF NOT EXISTS bab_eur_rates (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    period_year     SMALLINT NOT NULL,
    period_month    SMALLINT NOT NULL,
    eur_rate        NUMERIC(10,4) NOT NULL,
    set_by          INTEGER REFERENCES users(id),
    set_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (company_id, period_year, period_month)
);
```

---

## 4. Period Lifecycle

```
MISSING → IMPORTED → LOCKED
             ↑            ↓
         (re-import)   (unlock — reversible)
```

- **MISSING**: no upload for this company+period
- **IMPORTED** (status='ready'): BAB parsed, report available, re-import allowed
- **LOCKED** (locked_at NOT NULL): no imports/deletes allowed (423), unlock requires `controlling.bab.lock` permission

### Re-import flow (before lock)
1. Delete all `bab_entries` for that upload_id
2. Insert new parsed entries
3. Update `bab_uploads`: filename, uploaded_by, uploaded_at, row_count, increment import_count

### Lock/Unlock
- Lock: sets `locked_at`, `locked_by`
- Unlock: clears `locked_at`/`locked_by`, sets `unlocked_at`/`unlocked_by`
- Both require `controlling.bab.lock` permission

---

## 5. API Routes

All under `/controlling/bab/api/`:

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/import` | add | Upload BAB xlsx (multipart: file, period_year, period_month, company_id) |
| GET | `/periods` | view | 12-month rolling grid with status + marja KPI |
| GET | `/uploads` | view | List uploads for company |
| DELETE | `/uploads/<id>` | delete | Delete upload (423 if locked) |
| POST | `/uploads/<id>/lock` | lock | Lock period |
| POST | `/uploads/<id>/unlock` | lock | Unlock period |
| GET | `/report/<upload_id>` | view | Compute + return MarjaReport |
| GET | `/report/<upload_id>/export` | view | Download marja xlsx |
| GET | `/eur-rate/<year>/<month>` | view | Get EUR rate for period |
| PUT | `/eur-rate/<year>/<month>` | edit | Set EUR rate |

### Import endpoint
- Multipart: `file` (xlsx), `period_year`, `period_month`, `company_id`
- Rejects non-xlsx → 415
- Locked period → 423
- Existing upload → re-import flow (delete old entries, insert new, increment import_count)
- New upload → create bab_uploads + parse + insert entries
- Returns: `{success, upload_id, period, status, import_count, row_count}`

### Report endpoint
- If EUR rate not set → 422
- Computes via calculator.py on-the-fly
- Returns structured MarjaReport dict

---

## 6. Calculator (Margin Engine)

Pure function. Input: list of bab_entries dicts + eur_rate. Output: MarjaReport dict.

### Sign conventions
- Revenue (7xxxxx): positive from source
- Expense (6xxxxx): negative from source
- Exceptions (stay positive): 609010, 609011, 609012
- Already negative (erode margin): 704315, 902700

### Account-to-row mapping

**KST 211 — PKW INTERN:**
```
retail_venit_sales    = Σ(konto ∈ [707111, 707116],         kst=211)
retail_marja_bruta    = Σ(konto ∈ [707111, 707116, 607111], kst=211)
retail_bonus_import   = Σ(konto ∈ [609010],                 kst=211)
retail_venit_td       = Σ(konto ∈ [707112],                 kst=211)
retail_marja_td       = Σ(konto ∈ [707112, 607112],         kst=211)

flote_venit_sales     = Σ(konto ∈ [707110, 707115],         kst=211)
flote_marja_bruta     = Σ(konto ∈ [707110, 707115, 607110], kst=211)
flote_bonus_import    = Σ(konto ∈ [609011],                 kst=211)

bonus_pfg             = Σ(konto ∈ [708001],                 kst=211)
discount_accesorii    = Σ(konto ∈ [704315, 902700],         kst=211)
```

**MARJA FINALĂ PKW (7 components):**
```
marja_finala = retail_marja_bruta + retail_bonus_import + retail_marja_td
             + flote_marja_bruta + flote_bonus_import + bonus_pfg
             + discount_accesorii
```

**KST 215 — PKW EXTERN:**
```
extern_venit_sales    = Σ(konto ∈ [707127],         kst=215)
extern_marja_bruta    = Σ(konto ∈ [707127, 607127], kst=215)
extern_bonus_import   = Σ(konto ∈ [609012],         kst=215)
extern_marja_total    = extern_marja_bruta + extern_bonus_import
```

### EUR conversion
```
to_eur(lei, rate) = lei / rate, rounded to 2 decimals
```

---

## 7. Frontend

### Structure
```
frontend/src/
├── pages/Accounting/Controlling/
│   ├── index.tsx              # Dashboard with 12-month period grid
│   └── MarjaReport.tsx        # Margin report detail view
├── api/controlling.ts         # API client
└── types/controlling.ts       # TypeScript interfaces
```

### Navigation
Sidebar.tsx: add under Accounting children:
```typescript
{ path: '/app/accounting/controlling', label: 'Controlling',
  icon: BarChart3, moduleKey: 'accounting_controlling',
  v2Permission: 'controlling.bab.view' }
```

Menu registry: add `accounting_controlling` child under `accounting`.

App.tsx routes:
```
/app/accounting/controlling              → Dashboard (period grid)
/app/accounting/controlling/:uploadId    → MarjaReport
```

### Dashboard (index.tsx)
- 12-month rolling grid (current month + 11 prior)
- Card states: MISSING (grey, import CTA), IMPORTED (green, marja EUR), LOCKED (blue padlock)
- Import modal: drag-drop xlsx, EUR rate field, re-import warning
- Lock/unlock actions on IMPORTED/LOCKED cards

### MarjaReport (MarjaReport.tsx)
- Structured table with sections (PKW Intern retail, flote, PKW Extern)
- LEI/EUR toggle
- Negative values in red
- MARJA FINALĂ row highlighted (dark bg, white text)
- Export xlsx button
- "Source accounts" tooltip per row

### Data fetching
- TanStack Query: `useQuery` for periods/report/eur-rate, `useMutation` for import/lock/unlock
- Query invalidation on import/lock/unlock mutations

---

## 8. Permissions (V2)

```
controlling.bab.view   — view uploads + reports
controlling.bab.add    — import and re-import BAB files
controlling.bab.edit   — set EUR rate
controlling.bab.delete — delete uploads
controlling.bab.lock   — lock and unlock periods
```

Default grants:
- Admin → all
- Manager → view + add + edit
- User → view
- Viewer → view

---

## 9. Export (xlsx)

Styled xlsx via openpyxl matching production template:
- Dark navy header row with period + EUR rate
- Section headers color-coded (retail=dark blue, flote=darker blue, extern=green)
- MARJA FINALĂ: navy bg, white bold text
- Negative values: red font
- Columns: Indicator | LEI | EUR | Conturi | KST
- Font: Arial 9pt, freeze panes at row 3

---

## 10. What's NOT included

- No Redis caching
- No per-car margins or unit economics
- No budget vs actual comparison
- No automated ERP sync
- No charts in v1
- No multi-currency beyond LEI/EUR
