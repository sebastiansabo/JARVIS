-- Migration: Convert company_brands from TEXT to FK-based
-- Date: 2026-01-26
-- Description: Change company_brands.brand (TEXT) to company_brands.brand_id (FK to brands.id)

-- Step 1: Add brand_id column
ALTER TABLE company_brands ADD COLUMN IF NOT EXISTS brand_id INTEGER;

-- Step 2: Ensure all brand names exist in brands master table
INSERT INTO brands (name, is_active)
SELECT DISTINCT cb.brand, TRUE
FROM company_brands cb
WHERE cb.brand IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM brands b WHERE b.name = cb.brand)
ON CONFLICT DO NOTHING;

-- Step 3: Populate brand_id by matching brand names
UPDATE company_brands cb
SET brand_id = b.id
FROM brands b
WHERE cb.brand = b.name AND cb.brand_id IS NULL;

-- Step 4: Verify migration (should return 0 orphaned)
SELECT COUNT(*) as total,
       COUNT(brand_id) as with_brand_id,
       COUNT(*) FILTER (WHERE brand_id IS NULL AND brand IS NOT NULL) as orphaned
FROM company_brands;

-- Step 5: Add FK constraint
ALTER TABLE company_brands
DROP CONSTRAINT IF EXISTS fk_company_brands_brand;

ALTER TABLE company_brands
ADD CONSTRAINT fk_company_brands_brand FOREIGN KEY (brand_id) REFERENCES brands(id);

-- Step 6: Drop old brand TEXT column
ALTER TABLE company_brands DROP COLUMN IF EXISTS brand;

-- Step 7: Verify new schema
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'company_brands'
ORDER BY ordinal_position;

-- Done! Verify with JOIN query
SELECT cb.id, c.company, b.name as brand, cb.brand_id
FROM company_brands cb
JOIN companies c ON cb.company_id = c.id
JOIN brands b ON cb.brand_id = b.id
ORDER BY c.company, b.name
LIMIT 20;
