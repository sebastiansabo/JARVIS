-- Clear old combined brands and insert proper individual brands
TRUNCATE company_brands RESTART IDENTITY;

-- Insert proper brands (mapped by company name)
INSERT INTO company_brands (company_id, brand, is_active) VALUES
((SELECT id FROM companies WHERE company = 'AUTOWORLD S.R.L.'), 'Autoworld.ro', true),
((SELECT id FROM companies WHERE company = 'AUTOWORLD S.R.L.'), 'CarFun.ro', true),
((SELECT id FROM companies WHERE company = 'AUTOWORLD S.R.L.'), 'Carcloud', true),
((SELECT id FROM companies WHERE company = 'Autoworld INTERNATIONAL S.R.L.'), 'Volkswagen (PKW)', true),
((SELECT id FROM companies WHERE company = 'Autoworld INTERNATIONAL S.R.L.'), 'Volkswagen Comerciale (LNF)', true),
((SELECT id FROM companies WHERE company = 'Autoworld NEXT S.R.L.'), 'Autoworld.ro', true),
((SELECT id FROM companies WHERE company = 'Autoworld NEXT S.R.L.'), 'Carcloud', true),
((SELECT id FROM companies WHERE company = 'Autoworld NEXT S.R.L.'), 'DasWeltAuto', true),
((SELECT id FROM companies WHERE company = 'Autoworld NEXT S.R.L.'), 'Motion', true),
((SELECT id FROM companies WHERE company = 'Autoworld ONE S.R.L.'), 'Toyota', true),
((SELECT id FROM companies WHERE company = 'Autoworld PLUS S.R.L.'), 'MG Motor', true),
((SELECT id FROM companies WHERE company = 'Autoworld PLUS S.R.L.'), 'Mazda', true),
((SELECT id FROM companies WHERE company = 'Autoworld PREMIUM S.R.L.'), 'Audi', true),
((SELECT id FROM companies WHERE company = 'Autoworld PREMIUM S.R.L.'), 'Audi Approved Plus', true),
((SELECT id FROM companies WHERE company = 'Autoworld PRESTIGE S.R.L.'), 'Volvo', true);

-- Verify
SELECT c.company, cb.brand FROM company_brands cb 
JOIN companies c ON cb.company_id = c.id ORDER BY c.company, cb.brand;
