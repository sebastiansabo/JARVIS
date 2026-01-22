-- Migration: Add company_id to department_structure and create company_brands table
-- Run this on PRODUCTION database

-- Step 1: Add company_id column to department_structure
ALTER TABLE department_structure ADD COLUMN IF NOT EXISTS company_id INTEGER;

-- Step 2: Populate company_id from company name
UPDATE department_structure ds
SET company_id = c.id
FROM companies c
WHERE ds.company = c.company AND ds.company_id IS NULL;

-- Step 3: Create company_brands table (normalized brands)
CREATE TABLE IF NOT EXISTS company_brands (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    brand TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, brand)
);

-- Step 4: Populate company_brands from existing brands column in companies
-- (This extracts comma-separated brands into separate rows)
INSERT INTO company_brands (company_id, brand)
SELECT c.id, TRIM(unnest(string_to_array(c.brands, ',')))
FROM companies c
WHERE c.brands IS NOT NULL AND c.brands != ''
ON CONFLICT (company_id, brand) DO NOTHING;

-- Step 5: Verify the migration
SELECT 'department_structure company_id populated:' as check,
       COUNT(*) as count FROM department_structure WHERE company_id IS NOT NULL;
       
SELECT 'company_brands created:' as check,
       COUNT(*) as count FROM company_brands;
