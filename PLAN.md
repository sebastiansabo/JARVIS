# Option B: Migrate company_brands to FK-based Junction Table

## Overview
Convert `company_brands` from TEXT-based brand storage to FK-based linking to `brands` master table.

**Before:** `company_brands(id, company_id, brand TEXT, is_active)`
**After:** `company_brands(id, company_id, brand_id FK→brands.id, is_active)`

---

## Phase 1: Database Schema Migration

### Step 1.1: Add brand_id column
```sql
ALTER TABLE company_brands ADD COLUMN brand_id INTEGER;
```

### Step 1.2: Ensure all brand names exist in brands table
```sql
INSERT INTO brands (name, is_active)
SELECT DISTINCT cb.brand, TRUE
FROM company_brands cb
WHERE cb.brand IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM brands b WHERE b.name = cb.brand);
```

### Step 1.3: Populate brand_id by matching brand names
```sql
UPDATE company_brands cb
SET brand_id = b.id
FROM brands b
WHERE cb.brand = b.name;
```

### Step 1.4: Verify migration completeness
```sql
SELECT COUNT(*) as orphaned FROM company_brands WHERE brand_id IS NULL AND brand IS NOT NULL;
-- Should return 0
```

### Step 1.5: Add FK constraint and drop old column
```sql
ALTER TABLE company_brands
ADD CONSTRAINT fk_company_brands_brand FOREIGN KEY (brand_id) REFERENCES brands(id);

ALTER TABLE company_brands DROP COLUMN brand;
```

---

## Phase 2: Backend Code Updates

### 2.1: jarvis/hr/events/routes.py

| Function | Change |
|----------|--------|
| `api_get_companies_full()` | JOIN brands table to get brand name |
| `api_get_company_brands()` | JOIN brands table to get brand name |
| `api_create_company_brand()` | Accept `brand_id` instead of `brand` TEXT |
| `api_update_company_brand()` | Update `brand_id` instead of `brand` |
| `api_get_brands_for_company()` | JOIN brands table to get brand name |

### 2.2: jarvis/services.py

| Function | Change |
|----------|--------|
| `get_companies_with_vat()` | JOIN brands table: `cb JOIN brands b ON cb.brand_id = b.id` |

### 2.3: jarvis/models.py

| Function | Change |
|----------|--------|
| `get_brands_for_company()` | JOIN brands table: `cb JOIN brands b ON cb.brand_id = b.id` |

---

## Phase 3: Frontend Updates

### 3.1: settings.html - Edit Company Modal
- Change brand input from TEXT input to `<select>` dropdown
- Populate dropdown from master brands table (`/hr/events/api/master/brands`)
- Save brand_id instead of brand text

### 3.2: settings.html - Add Brand to Company
- Use dropdown selection from master brands
- POST brand_id to API

---

## Phase 4: Testing Checklist

1. **Settings Page**
   - [ ] Companies tab loads correctly
   - [ ] Edit company modal shows brand dropdown
   - [ ] Can add brand to company from master list
   - [ ] Can remove brand from company
   - [ ] Brands tab (master table) still works

2. **Accounting Pages**
   - [ ] Invoice allocation dropdowns populate brands correctly
   - [ ] Bulk processor brand selection works
   - [ ] Dashboard filters by brand correctly

3. **HR Pages**
   - [ ] Employee brand dropdown populates correctly
   - [ ] Event creation with brand works

4. **API Endpoints**
   - [ ] GET /hr/events/api/structure/companies-full returns brands
   - [ ] GET /hr/events/api/structure/company-brands returns brand names
   - [ ] POST /hr/events/api/structure/company-brands creates with brand_id
   - [ ] GET /hr/events/api/structure/companies/{id}/brands returns brand names

---

## Rollback Plan (if needed)
```sql
-- Add back brand TEXT column
ALTER TABLE company_brands ADD COLUMN brand TEXT;

-- Populate from brands table
UPDATE company_brands cb
SET brand = b.name
FROM brands b
WHERE cb.brand_id = b.id;

-- Drop FK and brand_id
ALTER TABLE company_brands DROP CONSTRAINT fk_company_brands_brand;
ALTER TABLE company_brands DROP COLUMN brand_id;
```
