# CRM / Car Sales RAG Database — Implementation Plan

## Goal
Import 4 data sources (NW new cars, GW used cars, Leads, CRM Clients) into JARVIS, make them searchable by the AI via RAG, and provide an admin-only UI to manage uploads.

---

## Data Sources Summary

| Source | Rows | Key Fields |
|---|---|---|
| NW (New Cars) | 31,220 | Dossier, model, brand, client, pricing (7 fields), vehicle specs, order status |
| GW (Used Cars) | 10,155 | Dossier, model, brand, client, gross price, VIN |
| Leads (Workleto) | 6,756 | Contact, phone, email, lead status, score, UTM, sales advisor, model |
| CRM Clients | 15,207 | Name, type, address, phone, email, responsible, date |

---

## Architecture

### Phase 1: Database Tables

**3 new tables** in public schema:

#### `crm_clients` (~15K rows)
- id, name, client_type (fizica/juridica), address, phone, email, responsible, source (workleto/nw/gw), source_id
- imported_at, created_at, updated_at, deleted_at

#### `crm_car_dossiers` (~41K rows — NW + GW merged)
- id, dossier_type (new/used), dealer, dealer_code, branch, dossier_number, order_number
- model_name, body_code, brand, model_year, vehicle_type, door_count, model_code, engine_code
- fuel_type, color, color_code, vin, engine_serial, emission_class, co2_emissions
- gearbox, upholstery_code, upholstery_name, equipment_code
- contract_date, order_date, order_year, delivery_date, invoice_date, registration_date
- dossier_status, order_status, contract_status
- list_price, discount_value, discount_base, other_costs, net_purchase_price, net_sale_price, gross_profit, gross_sale_price
- client_name, client_address, owner_name, owner_address, customer_group
- salesperson, registration_number, civ_date, civ_number, entry_date
- damage_accident, damage_repaired, product_group, vehicle_id
- imported_at, created_at, updated_at, deleted_at

#### `crm_leads` (~7K rows)
- id, group_name, person_type, contact_name, phone, email
- lead_text, added_by, added_date, responsible, assigned_date, first_contact_date
- lead_score, lead_status, status_reason, status_reason_notes, status_date
- next_contact_date, last_activity_date
- utm_source, utm_medium, utm_campaign, utm_term, utm_content
- sales_advisor, model, model_of_interest, form_type, request_type, brand, financing
- imported_at, created_at, updated_at, deleted_at

### Phase 2: Backend — Import Service + Repository

#### New module: `jarvis/crm/`
```
jarvis/crm/
  __init__.py
  routes.py              # Admin API endpoints
  repositories/
    __init__.py
    client_repository.py
    dossier_repository.py
    lead_repository.py
  services/
    __init__.py
    import_service.py    # Excel parsing + DB insert
```

**Import Service:**
- Parse .xlsx with openpyxl (streaming read_only mode for large files)
- Column mapping dicts (Romanian headers → DB columns)
- Batch INSERT with ON CONFLICT DO UPDATE (upsert by dossier_number or phone+name)
- Return import stats (inserted, updated, skipped, errors)

**Routes (admin-only):**
- `POST /api/crm/import` — Upload Excel file (multipart/form-data), params: type (nw/gw/leads/clients)
- `GET /api/crm/stats` — Row counts per table, last import date
- `GET /api/crm/dossiers` — Paginated list with search/filters
- `GET /api/crm/clients` — Paginated list with search/filters
- `GET /api/crm/leads` — Paginated list with search/filters
- `DELETE /api/crm/purge/<type>` — Delete all records of a type (with confirmation)

### Phase 3: RAG Integration

**3 new source types** added to `RAGSourceType` enum:
- `CRM_CLIENT = "crm_client"`
- `CAR_DOSSIER = "car_dossier"`
- `CRM_LEAD = "crm_lead"`

**New indexing methods in `rag_service.py`:**
- `index_crm_client(client_id)` + `index_crm_clients_batch(limit=500)`
- `index_car_dossier(dossier_id)` + `index_car_dossiers_batch(limit=500)`
- `index_crm_lead(lead_id)` + `index_crm_leads_batch(limit=500)`

**Content composition examples:**

```
# Car Dossier content:
"Dosar masina noua Nr. 28379\nModel: Caravelle Life LR 2.0 TDI\nMarca: VW Vehicule Comerciale\n
Status: Comandat/Confirmat\nClient: SWING AUTOVERMIETUNG\nPret lista: 269,758.72 RON\n
Profit brut: -3,395.07 RON\nCombustibil: Diesel\nCuloare: Gri\nVIN: WV2ZZZST3SH042807\n
Data livrare: 2025-03-15\nVanzator: Graur Constantin"

# Lead content:
"Lead vanzari - Grup: Vanzari MG\nContact: Ion Popescu\nTelefon: 0741234567\n
Email: ion@test.com\nStatus: In lucru\nScor: 85\nSursa: Facebook\n
Model interes: MG4\nConsilier: Graur Constantin\nData: 2025-10-15"

# CRM Client content:
"Client CRM: Ion Popescu\nTip: Persoana fizica\nTelefon: 0741234567\n
Email: ion@test.com\nAdresa: Cluj, Str. Eroilor 15\nResponsabil: Graur Constantin"
```

**Metadata:**
- car_dossier: `{dossier_number, model, brand, client, status, price, fuel, dossier_type}`
- crm_lead: `{contact_name, status, score, source, model, advisor}`
- crm_client: `{name, type, phone, email, responsible}`

**METADATA_DISPLAY_KEYS additions** for formatted context display.

### Phase 4: AI Tools

**3 new tools** registered in `jarvis/ai_agent/tools/definitions/crm.py`:

1. **`search_car_dossiers`** — Search by model, brand, client, status, date range, fuel, dossier_type (new/used), price range
2. **`search_crm_leads`** — Search by status, score range, source, advisor, model, date range
3. **`search_crm_clients`** — Search by name, type, phone, email, responsible

Permission: `can_access_crm` (new permission added to roles table).

### Phase 5: Frontend — Admin CRM Page

**New page:** `jarvis/frontend/src/pages/CRM/` (admin-only)

Tabs:
1. **Dashboard** — Stats cards (total dossiers NW/GW, leads, clients), last import dates
2. **Car Dossiers** — DataTable with search, filters (type, brand, status), pagination
3. **Leads** — DataTable with search, filters (status, source, advisor), pagination
4. **Clients** — DataTable with search, filters (type, responsible), pagination
5. **Import** — Upload zone per data type (NW, GW, Leads, Clients), import history/stats

**Sidebar entry:** "CRM Data" under a new section, gated by `can_access_crm` permission.

**Route:** `/app/crm/*` with lazy-loaded sub-routes.

---

## Implementation Order

1. DB tables (init_schema.py + database.py newest-table check)
2. Backend: repositories + import service + routes
3. RAG: new source types + indexing methods + metadata display keys
4. AI tools: 3 new CRM search tools
5. Frontend: CRM page with tabs (dashboard, tables, import)
6. Test: upload files, verify RAG search, test AI queries

---

## Additional DB Changes
- Add `can_access_crm BOOLEAN DEFAULT FALSE` to `roles` table
- Add `can_access_crm` to User type in frontend
- Seed: grant `can_access_crm = TRUE` to admin role

## Questions Resolved
- Tables are in **public schema** (not ai_agent) since they're real business data
- RAG source types added to existing enum (same pattern as 10 existing types)
- New `can_access_crm` permission — grants CRM access to specific roles (not just admins)
- Import is manual upload (no auto-sync) — user re-uploads when they have new data
