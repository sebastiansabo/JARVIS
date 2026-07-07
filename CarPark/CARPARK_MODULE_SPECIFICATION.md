# JARVIS CarPark Module — Complete Technical Specification v2.0

**Version:** 2.0
**Date:** April 2, 2026
**Author:** Strategic Architecture Review
**Status:** Ready for Implementation
**Reference System:** CarStock (Autoworld HOLDING production DMS — 29 screenshots analyzed pixel-by-pixel)

---

## 1. CONTEXT

You already run CarStock — a production DMS managing your Autoworld HOLDING fleet across multiple brands (Volvo, MG, Audi, Toyota, Suzuki, Mazda, DS Automobiles, VW). This spec doesn't invent from zero. It reverse-engineers every CarStock feature, fills the gaps CarStock has, and rebuilds it natively inside JARVIS where it can leverage your existing Accounting, CRM, DMS, e-Factura, AI Agent, Approvals, Marketing, and Notifications modules.

The result: a single system instead of two disconnected platforms.

---

## 2. INDUSTRY STANDARD ANALYSIS

### 2.1 What Top DMS Platforms Deliver (CDK Global, Tekion, DealerTrack, Spyne)

Core inventory lifecycle: Acquisition → Reconditioning → Merchandising → Listing → Negotiation → Sale → Post-sale. Every vehicle tracked from VIN entry to delivery with full cost waterfall.

**KPIs the industry tracks:**

| KPI | Formula | Gold Standard |
|-----|---------|---------------|
| Inventory Turn Rate | Annual Sales ÷ Average Inventory | 12x/year (30-day turns) |
| Average Days on Lot | Sum(days per vehicle) ÷ Count | < 45 days |
| Gross Return on Investment (GROI) | (Gross % × Turn Rate) | > 100% |
| Aged Stock % | Vehicles > 60 days ÷ Total | < 10-15% |
| Front-end Gross per Unit | Sale Price - (Purchase + Recon + Carry) | Market-dependent |
| Cost to Carry per Day | (Floorplan interest + Insurance + Depreciation) ÷ 30 | Track per vehicle |
| Stocking Efficiency | Vehicles sold < 30 days ÷ Total sold | > 60% |

**Dynamic pricing:** 70%+ of modern DMS platforms use AI-driven repricing. Rules-based at minimum: auto-reduce price after 30/45/60 days, competitor-aware pricing, demand-signal integration.

### 2.2 Autovit.ro API Integration

Autovit.ro provides a dealer API for CRUD operations on listings. Access requires dealer account + API key (request via api@autovit.ro). One API key serves all branches even across different accounts. Supports: creating, updating, deactivating, deleting listings, and reading listing status/stats.

### 2.3 Multi-Platform Publishing (From CarStock Screenshots)

CarStock publishes to 10+ platforms simultaneously per vehicle. This is not Autovit-only. The screenshot shows:
- Autovit per brand: VOLVO, MG MOTOR, Car Craiit, Suzuki/Mazda, AAP, Audi, Toyota
- Websites: mg-cluj.ro, automotivegroup.ro
- Rulote MD: rulote.mgbroker.ro
- Bulk action bar: "Activează, modifică sau sterge anunțurile cu un singur click"

JARVIS CarPark must support a platform-agnostic publishing system, not just Autovit.

---

## 3. VEHICLE CLASSIFICATION SYSTEM

### 3.1 Vehicle Categories

| Category | Code | Description | Typical Margin | Max Acceptable Days |
|----------|------|-------------|---------------|-------------------|
| New Car | `NEW` | Factory-ordered, unregistered | Fixed by OEM | 90 |
| Ordered Car | `ORD` | Customer-ordered, in transit from factory | Pre-sold, fixed | N/A (pre-sold) |
| Second Hand | `SH` | Used vehicles acquired for resale | 8-15% | 60 |
| Test Drive | `TD` | Demo/test drive fleet vehicles | Eventual resale at discount | 180 (then convert to SH) |
| Custody | `CUS` | Vehicles held on behalf of third party | Service fee only | Per agreement |
| Showroom | `SHR` | Display vehicles in showroom | Eventual sale | 120 |
| Display Show | `DSP` | Event/exhibition display vehicles | Marketing cost center | Per event |
| Consignment | `CON` | Vehicles sold on behalf of owner (toggle: "Masina in consemnație") | Commission-based | 90 |
| Trade-In | `TI` | Vehicles taken in trade during sale | 10-20% | 45 |

### 3.2 Vehicle Status Workflow

```
ACQUIRED → INSPECTION → RECONDITIONING → READY_FOR_SALE → LISTED → RESERVED → SOLD → DELIVERED
                                              ↓
                                         PRICE_REDUCED (automated)
                                              ↓
                                         AUCTION_CANDIDATE (> threshold days)
```

Additional statuses: `IN_TRANSIT`, `AT_BODYSHOP`, `INSURANCE_CLAIM`, `RETURNED`, `SCRAPPED`, `TRANSFERRED`

### 3.3 Vehicle States from CarStock (Catalog Tabs)

The CarStock catalog uses these filter tabs at the top level:
- **TOATE** (All)
- **ACTIVE** (Active/in stock)
- **REZERVATE** (Reserved)
- **IN DESFACERE** (Being sold / sale in progress)
- **VANDUTE** (Sold)
- **LIVRATE** (Delivered)

---

## 4. COMPLETE VEHICLE DETAIL PAGE STRUCTURE

**Derived directly from CarStock screenshots.** The vehicle detail page has a left sidebar with thumbnail + status badge + navigation, and a main content area. Navigation sections:

| # | Section | Romanian Label | Description |
|---|---------|---------------|-------------|
| 1 | General Info | Informații generale | All vehicle specs, identification, acquisition info, pricing, equipment, description |
| 2 | Photo Gallery & 360° | Galerie foto & 360° | Photos (drag-drop reorder), Interior 360°, Exterior 360° tabs |
| 3 | Offers | Ofertare | Generate client-facing offers/quotes per vehicle ("Lista oferte generate", "OFERTEAZĂ" button) |
| 4 | Interested Contacts | Contacte interesate | Per-vehicle CRM: add/manage prospects interested in this specific car |
| 5 | Reservations | Rezervări | Create reservation (client, period, deposit), view reservation history ("Rezervări anterioare") |
| 6 | Invoicing & Collection | Facturare & Încasare | Vehicle-level invoice linking and payment collection tracking |
| 7 | Costs & Revenue | Costuri & Venituri | Separate COSTURI and VENITURI sections with add forms |
| 8 | Documents | Documente | Document vault with upload, view, download per document type |
| 9 | Scheduling | Programări | Test drives and appointments with date, responsible, client, route, notifications |
| 10 | Trip Log | Foaie de parcurs | Vehicle usage/mileage tracking log |
| 11 | Listing Publishing | Publicare anunțuri | Multi-platform listing management (Autovit per brand, websites, others) |
| 12 | Activity | Activitate | Audit trail with sub-tabs: Activitate, Istoric modificări, Evoluție Kilometraj, Evoluție Preț de vânzare |

---

## 5. DATABASE SCHEMA

### 5.1 Core Tables

```sql
-- ============================================================
-- VEHICLES: Central entity
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_vehicles (
    id SERIAL PRIMARY KEY,

    -- Identity
    vin VARCHAR(17) UNIQUE NOT NULL,
    identification_number VARCHAR(50),      -- Nr. comandă / Identificator
    registration_number VARCHAR(20),        -- Număr de înmatriculare (e.g., CJ-53-ATW)
    chassis_code VARCHAR(50),              -- Cod entitate
    emission_code VARCHAR(50),             -- Cod de emisiune

    -- Classification
    category VARCHAR(5) NOT NULL DEFAULT 'SH',
    status VARCHAR(20) NOT NULL DEFAULT 'ACQUIRED',
    vehicle_type VARCHAR(30) DEFAULT 'Autoturism',  -- Tip vehicul: Autoturism, Utilitara, etc.
    state VARCHAR(20) DEFAULT 'Nou',                -- Stare: Nou, Rulat

    -- Specs
    brand VARCHAR(100) NOT NULL,
    model VARCHAR(200) NOT NULL,
    variant VARCHAR(200),                  -- Versiune (e.g., "Recharge Single Motor Extended Range RWD Plus")
    generation VARCHAR(100),               -- Generație (selectable dropdown)
    equipment_level VARCHAR(100),          -- Nivel de echipare (e.g., ULTIMATE)
    body_type VARCHAR(50),                 -- Caroserie: sedan, SUV, hatchback, wagon, coupe, van, pickup
    year_of_manufacture INTEGER,           -- An de fabricație
    first_registration_date DATE,          -- Data primei înmatriculări
    color_exterior VARCHAR(50),            -- Culoare
    color_code VARCHAR(30),                -- Cod culoare
    color_interior VARCHAR(50),            -- Denumire tapițerie
    interior_code VARCHAR(30),             -- Cod tapițerie
    fuel_type VARCHAR(30),                 -- Combustibil: Benzina, Diesel, Hibrid, Electric, GPL
    transmission VARCHAR(20),              -- Cutie de viteze: Manuala, Automata
    drive_type VARCHAR(10),                -- Tracțiune: FWD, RWD, AWD, 4WD, Spate
    engine_displacement_cc INTEGER,        -- Cilindree motor
    engine_power_hp INTEGER,               -- Putere (CP)
    engine_power_kw INTEGER,               -- Putere (kW)
    engine_power_electric_hp INTEGER,      -- Putere motor electric (CP)
    engine_torque_nm INTEGER,              -- Putere motor termic (optional)
    co2_emissions INTEGER,                 -- Emisii CO2
    euro_standard VARCHAR(10),             -- Norma de poluare: Euro 6d
    mileage_km INTEGER DEFAULT 0,          -- Kilometraj
    max_weight_kg INTEGER,                 -- Masă maximă autorizată
    doors INTEGER,                         -- Nr. uși
    seats INTEGER,                         -- Nr. vaci (seats)
    tire_type VARCHAR(50),                 -- Tip anvelope: Mixte/All Season
    fuel_consumption VARCHAR(50),          -- Norma de poluare km/kw

    -- Equipment & Features (Structured — from CarStock checkbox matrix)
    equipment JSONB DEFAULT '{}',          -- Structured by category, see Section 5.2
    optional_packages JSONB DEFAULT '[]',

    -- General Info flags (from CarStock)
    has_manufacturer_warranty BOOLEAN DEFAULT FALSE,  -- Garanție producator
    manufacturer_warranty_date DATE,                   -- Garanție producator date (0000-00-00 format)
    has_dealer_warranty BOOLEAN DEFAULT FALSE,          -- Garanție dealer
    dealer_warranty_months INTEGER,
    is_registered BOOLEAN DEFAULT FALSE,               -- Înmatriculat: Da/Nu
    is_first_owner BOOLEAN DEFAULT FALSE,              -- Primul proprietar: Da/Nu
    has_accident_history BOOLEAN DEFAULT FALSE,         -- Fără accident: Da/Nu
    has_service_book BOOLEAN DEFAULT FALSE,             -- Carte service: Da/Nu
    is_electric_vehicle BOOLEAN DEFAULT FALSE,          -- Vehicul electric: Da/Nu (field visible)
    has_tuning BOOLEAN DEFAULT FALSE,                   -- Tuning: Da/Nu

    -- YouTube Video
    youtube_url TEXT,                       -- Link video YouTube

    -- Title & Description (for listings)
    listing_title TEXT,                     -- TITLU MASINA
    listing_description TEXT,               -- DESCRIERE (auto-populated, editable)

    -- Location
    location_id INTEGER REFERENCES carpark_locations(id),
    parking_spot VARCHAR(50),
    location_text VARCHAR(100),            -- Free-text location (e.g., "CLUJ")

    -- Ownership / Source
    source VARCHAR(50),                    -- Sursă: (optional) de ex.: link, buy back, etc.
    supplier_name VARCHAR(200),
    supplier_cif VARCHAR(30),
    purchase_contract_number VARCHAR(100),
    purchase_contract_date DATE,
    owner_name VARCHAR(200),               -- Proprietar (e.g., AUTOWORLD PRESTIGE)

    -- Acquisition Info (from CarStock "INFORMATII DESPRE ACHIZITIE")
    acquisition_manager_id INTEGER,        -- Manager achiziție
    acquisition_document_number VARCHAR(50), -- Nr. doc intern
    acquisition_date DATE NOT NULL DEFAULT CURRENT_DATE,  -- Data achiziție
    arrival_date DATE,                     -- Data intrare în stoc
    acquisition_value DECIMAL(12,2),       -- Valoare achiziție (RON)
    acquisition_vat DECIMAL(12,2),         -- Valoare TVA
    acquisition_price DECIMAL(12,2),       -- Preț achiziție
    acquisition_currency VARCHAR(3) DEFAULT 'EUR',  -- Curs (optional ex.: 5.1234)
    acquisition_exchange_rate DECIMAL(10,4),

    -- Financial / Cost Tracking
    purchase_price_net DECIMAL(12,2),
    purchase_price_currency VARCHAR(3) DEFAULT 'EUR',
    purchase_vat_rate DECIMAL(5,2) DEFAULT 19.00,
    reconditioning_cost DECIMAL(12,2) DEFAULT 0,
    transport_cost DECIMAL(12,2) DEFAULT 0,
    registration_cost DECIMAL(12,2) DEFAULT 0,
    other_costs DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) GENERATED ALWAYS AS (
        COALESCE(purchase_price_net, 0) + COALESCE(reconditioning_cost, 0) +
        COALESCE(transport_cost, 0) + COALESCE(registration_cost, 0) +
        COALESCE(other_costs, 0)
    ) STORED,

    -- Pricing (from CarStock "OPTIUNI PRET" + "PRET MOUNT" sections)
    list_price DECIMAL(12,2),              -- Preț
    promotional_price DECIMAL(12,2),       -- Preț promoțional
    minimum_price DECIMAL(12,2),
    current_price DECIMAL(12,2),
    price_currency VARCHAR(3) DEFAULT 'EUR',  -- Monedă: EUR/RON
    price_includes_vat BOOLEAN DEFAULT TRUE,  -- Include TVA: Da (NETT) / Nu
    vat_deductible BOOLEAN DEFAULT FALSE,     -- TVA deductibil (with explanatory note logic)
    is_negotiable BOOLEAN DEFAULT TRUE,       -- Negociabil: Da/Nu
    margin_scheme BOOLEAN DEFAULT FALSE,      -- Regim marjă

    -- Financing options (from CarStock)
    eligible_for_financing BOOLEAN DEFAULT FALSE,  -- Eligibil pentru finanțare: Da/Nu
    available_for_leasing BOOLEAN DEFAULT FALSE,   -- Predare leasing: X Nu
    can_issue_invoice BOOLEAN DEFAULT TRUE,        -- Se emite factură: Da/Nu

    -- Consignment (from CarStock toggle)
    is_consignment BOOLEAN DEFAULT FALSE,   -- Mașina în consemnație: Nu/Da

    -- Promotions link
    promotion_id INTEGER,                   -- FK to carpark_promotions

    -- Test Drive / Demo flag
    is_test_drive BOOLEAN DEFAULT FALSE,    -- Test Drive / Demo: Nu/Da
    service_exchange_vehicle BOOLEAN DEFAULT FALSE,  -- Mașină de schimb service: Da/Nu

    -- Sale
    sale_price DECIMAL(12,2),
    sale_date DATE,
    buyer_client_id INTEGER,
    salesperson_user_id INTEGER,

    -- Marketplace Integration (generic, not just Autovit)
    nr_stoc VARCHAR(50),                    -- NR STOC: 1486 (stock number visible in CarStock)

    -- Dates
    ready_for_sale_date DATE,
    listing_date DATE,
    reservation_date DATE,
    sale_date_actual DATE,
    delivery_date DATE,

    -- Computed
    stationary_days INTEGER GENERATED ALWAYS AS (
        CURRENT_DATE - COALESCE(arrival_date, acquisition_date)
    ) STORED,
    days_listed INTEGER,

    -- Metadata
    notes TEXT,
    internal_notes TEXT,
    created_by INTEGER,
    updated_by INTEGER,
    company_id INTEGER,
    brand_id INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_cv_vin ON carpark_vehicles(vin);
CREATE INDEX IF NOT EXISTS idx_cv_status ON carpark_vehicles(status);
CREATE INDEX IF NOT EXISTS idx_cv_category ON carpark_vehicles(category);
CREATE INDEX IF NOT EXISTS idx_cv_brand_model ON carpark_vehicles(brand, model);
CREATE INDEX IF NOT EXISTS idx_cv_company ON carpark_vehicles(company_id);
CREATE INDEX IF NOT EXISTS idx_cv_acquisition ON carpark_vehicles(acquisition_date);
CREATE INDEX IF NOT EXISTS idx_cv_stationary ON carpark_vehicles(stationary_days);
CREATE INDEX IF NOT EXISTS idx_cv_deleted ON carpark_vehicles(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_cv_equipment ON carpark_vehicles USING GIN (equipment);
CREATE INDEX IF NOT EXISTS idx_cv_nr_stoc ON carpark_vehicles(nr_stoc);


-- ============================================================
-- EQUIPMENT CATEGORIES: Structured checkbox matrix
-- (From CarStock: "DOTARI STANDARD SI OPTIONALE")
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_equipment_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- Category name
    name_ro VARCHAR(100),                 -- Romanian name
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed data based on CarStock screenshot categories:
-- Audio & conectivitate, Electronice și sisteme solar, Mașini electrice,
-- Performanță & tuning, Siguranță

CREATE TABLE IF NOT EXISTS carpark_equipment_items (
    id SERIAL PRIMARY KEY,
    category_id INTEGER REFERENCES carpark_equipment_categories(id),
    name VARCHAR(200) NOT NULL,
    name_ro VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed items from CarStock screenshots:
-- Apple Carplay, Android Auto, Bluetooth, Port USB, Smart hands-free,
-- Wireless charging, Sistem audio, Sistem navigatie, Monitor cu touch screen,
-- Control vocal, Conexiune Internet, Camera 360°, Digiteck exterioare/ideburide electric,
-- Avertizare unghi mort, Senzori acustice/luminosi banda, Lane assist,
-- Controlul distanței, Asistenta de urgenta si finare, Inchidere automatizata,
-- Incuiere centralizata keyless, Airbag uri frontal, lateral, spate,
-- Senzor lumini, Senzor ploaie, Faruri LED, Sistem de monitorizare presiune pnevuri,
-- Senzori de garaj/asistenta la parcare (fata si spate), Camera marsarier,
-- Asistenta la mentinerea benzii de rulare, Pilot automat, Control trafic,
-- Lante alia 19" cu anvelope 235/050 R19, Plafon panoramic, etc.

CREATE TABLE IF NOT EXISTS carpark_vehicle_equipment (
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    equipment_item_id INTEGER NOT NULL REFERENCES carpark_equipment_items(id),
    PRIMARY KEY (vehicle_id, equipment_item_id)
);


-- ============================================================
-- LOCATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    address TEXT,
    city VARCHAR(100),
    type VARCHAR(30),
    capacity INTEGER DEFAULT 0,
    company_id INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- COSTS: Per-vehicle cost tracking
-- (From CarStock: "COSTURI" section with dropdown types)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_vehicle_costs (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    cost_type VARCHAR(50) NOT NULL,
    -- Types from CarStock dropdown:
    -- Accesorii/redecorare, Alimentare, Alt cost, Caroserie, CASCO,
    -- Cost intern, Dotare, Leasing, IBA, ITP – pregătire tehnică,
    -- RCA, Reparații, Revizie, Transport
    description TEXT,
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RON',
    vat_rate DECIMAL(5,2) DEFAULT 19,
    vat_amount DECIMAL(12,2) DEFAULT 0,
    exchange_rate_eur DECIMAL(10,4),       -- Curs EUR (from CarStock form)
    invoice_number VARCHAR(100),           -- Nr. factură
    invoice_date DATE,                     -- Dată factură
    invoice_value DECIMAL(12,2),           -- Valoare factură (fără TVA)
    invoice_id INTEGER,                    -- FK to JARVIS invoices
    supplier_name VARCHAR(200),            -- Furnizor (from Simconsult dropdown)
    radio_cost_type VARCHAR(20),           -- Radio: cost / Estimat
    document_file TEXT,                    -- Sursă document: Choose File
    observation TEXT,                       -- Observații (optional)
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vcc_vehicle ON carpark_vehicle_costs(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vcc_type ON carpark_vehicle_costs(cost_type);
CREATE INDEX IF NOT EXISTS idx_vcc_invoice ON carpark_vehicle_costs(invoice_id);


-- ============================================================
-- REVENUE: Per-vehicle revenue tracking
-- (From CarStock: "VENITURI" section, separate from costs)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_vehicle_revenues (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    revenue_type VARCHAR(50) NOT NULL,     -- sale, trade_in_bonus, accessory_sale, financing_commission, etc.
    description TEXT,
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RON',
    vat_amount DECIMAL(12,2) DEFAULT 0,
    invoice_number VARCHAR(100),
    invoice_id INTEGER,
    client_name VARCHAR(200),
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vcr_vehicle ON carpark_vehicle_revenues(vehicle_id);


-- ============================================================
-- DOCUMENTS: Per-vehicle document vault
-- (From CarStock: exact document types observed)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_vehicle_documents (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    document_type VARCHAR(50) NOT NULL,
    -- Types from CarStock screenshot:
    -- CASCO, CIV, CMR transport, COC, Factură activitate finală,
    -- Factură Petrici, Factură primire impozit, Impozare primară,
    -- Proforme tip B, PV Livrare, PV Recepție, RCA, Talon mașină
    title VARCHAR(300),
    file_url TEXT,
    dms_document_id INTEGER,
    file_size INTEGER,
    mime_type VARCHAR(100),
    notes TEXT,
    uploaded_by INTEGER,
    upload_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vcd_vehicle ON carpark_vehicle_documents(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vcd_type ON carpark_vehicle_documents(document_type);

-- Document generation templates (from CarStock: "Generare documente" section)
-- "Creează forme cu datele autocompletate" with template thumbnails
CREATE TABLE IF NOT EXISTS carpark_document_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    template_file_url TEXT,
    auto_fill_fields JSONB DEFAULT '{}',   -- Maps template fields to vehicle fields
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- PHOTOS: Vehicle image gallery with 360° support
-- (From CarStock: "Galerie foto", "Interior 360°", "Exterior 360°" tabs)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_vehicle_photos (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    url TEXT NOT NULL,
    thumbnail_url TEXT,
    sort_order INTEGER DEFAULT 0,
    is_primary BOOLEAN DEFAULT FALSE,
    photo_type VARCHAR(30) NOT NULL DEFAULT 'gallery',
    -- Types: gallery, interior_360, exterior_360
    caption TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vcp_vehicle ON carpark_vehicle_photos(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vcp_type ON carpark_vehicle_photos(photo_type);


-- ============================================================
-- OFFERS: Client-facing offer/quote generation
-- (From CarStock: "Ofertare" / "Lista oferte generate" / "OFERTEAZĂ")
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_offers (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    client_id INTEGER,                     -- FK to crm_clients
    client_name VARCHAR(200),
    client_email VARCHAR(200),
    client_phone VARCHAR(50),

    -- Offer details
    offered_price DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'EUR',
    includes_vat BOOLEAN DEFAULT TRUE,
    discount_amount DECIMAL(12,2) DEFAULT 0,
    discount_reason TEXT,
    financing_details TEXT,
    trade_in_vehicle TEXT,
    trade_in_value DECIMAL(12,2),

    -- Generated document
    offer_pdf_url TEXT,                    -- Generated PDF offer document
    offer_number VARCHAR(50),

    -- Status
    status VARCHAR(20) DEFAULT 'draft',    -- draft, sent, viewed, accepted, rejected, expired
    valid_until DATE,
    sent_at TIMESTAMP,

    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vo_vehicle ON carpark_offers(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vo_client ON carpark_offers(client_id);
CREATE INDEX IF NOT EXISTS idx_vo_status ON carpark_offers(status);


-- ============================================================
-- INTERESTED CONTACTS: Per-vehicle CRM
-- (From CarStock: "Contacte interesate" with "Adaugă contact interesat" button)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_interested_contacts (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    client_id INTEGER,                     -- FK to crm_clients (if existing)
    client_name VARCHAR(200) NOT NULL,
    client_phone VARCHAR(50),
    client_email VARCHAR(200),
    company_name VARCHAR(200),

    source VARCHAR(50),                    -- walk_in, phone, autovit, website, referral
    interest_level VARCHAR(20),            -- hot, warm, cold
    notes TEXT,
    follow_up_date DATE,

    salesperson_id INTEGER,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vic_vehicle ON carpark_interested_contacts(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vic_client ON carpark_interested_contacts(client_id);


-- ============================================================
-- RESERVATIONS
-- (From CarStock: "Lista rezervări" with client, user, period, previous reservations)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_reservations (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    client_id INTEGER,
    client_name VARCHAR(200),
    client_company VARCHAR(200),           -- e.g., "SMART ELEVTORS"
    client_phone VARCHAR(50),
    client_email VARCHAR(200),

    -- Reservation details
    user_id INTEGER,                       -- Utilizator (salesperson who created it)
    reservation_start TIMESTAMP NOT NULL,  -- De la
    reservation_end TIMESTAMP,             -- Până la
    deposit_amount DECIMAL(12,2) DEFAULT 0,
    deposit_paid BOOLEAN DEFAULT FALSE,

    status VARCHAR(20) DEFAULT 'active',   -- active, expired, converted_to_sale, cancelled
    notes TEXT,

    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vr_vehicle ON carpark_reservations(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vr_status ON carpark_reservations(status);


-- ============================================================
-- INVOICING & COLLECTION: Per-vehicle billing
-- (From CarStock: "Facturare & Încasare" section)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_vehicle_invoices (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    invoice_type VARCHAR(20) NOT NULL,     -- purchase, sale, proforma, advance, credit_note
    invoice_id INTEGER,                    -- FK to JARVIS invoices
    invoice_number VARCHAR(100),
    invoice_date DATE,
    amount DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'RON',
    vat_amount DECIMAL(12,2),
    payment_status VARCHAR(20) DEFAULT 'unpaid',  -- unpaid, partial, paid
    payment_date DATE,
    payment_amount DECIMAL(12,2),
    client_name VARCHAR(200),
    notes TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vvi_vehicle ON carpark_vehicle_invoices(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vvi_invoice ON carpark_vehicle_invoices(invoice_id);


-- ============================================================
-- SCHEDULING: Test drives and appointments
-- (From CarStock: "Programări" with full scheduling grid)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_appointments (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    appointment_type VARCHAR(30) DEFAULT 'test_drive',  -- test_drive, viewing, delivery, service

    -- Scheduling
    scheduled_date DATE NOT NULL,          -- Data început
    scheduled_time TIME,
    actual_date DATE,                      -- Data finalizare

    -- People
    responsible_id INTEGER,                -- Responsabil (user)
    responsible_name VARCHAR(200),
    client_id INTEGER,
    client_name VARCHAR(200) NOT NULL,     -- Client / Utilizator
    client_company VARCHAR(200),

    -- Test drive specific
    route TEXT,                            -- Traseu
    driver_license_number VARCHAR(50),
    mileage_before INTEGER,
    mileage_after INTEGER,

    -- Feedback
    observation TEXT,                       -- Observații
    feedback TEXT,
    rating INTEGER,
    led_to_sale BOOLEAN DEFAULT FALSE,

    -- Notification
    send_notification BOOLEAN DEFAULT TRUE,  -- Notificare toggle (from screenshot)
    notification_sent BOOLEAN DEFAULT FALSE,

    -- Status
    status VARCHAR(20) DEFAULT 'scheduled',  -- scheduled, confirmed, in_progress, completed, cancelled, no_show

    -- Signature (from "Solicită semnătură" button in CarStock)
    signature_requested BOOLEAN DEFAULT FALSE,
    signature_url TEXT,

    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_va_vehicle ON carpark_appointments(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_va_date ON carpark_appointments(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_va_status ON carpark_appointments(status);


-- ============================================================
-- TRIP LOG: Vehicle usage tracking
-- (From CarStock: "Foaie de parcurs")
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_trip_log (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    trip_date DATE NOT NULL,
    driver_name VARCHAR(200),
    driver_id INTEGER,
    departure_location VARCHAR(200),
    arrival_location VARCHAR(200),
    purpose TEXT,
    mileage_start INTEGER,
    mileage_end INTEGER,
    distance_km INTEGER GENERATED ALWAYS AS (mileage_end - mileage_start) STORED,
    fuel_consumed DECIMAL(8,2),
    notes TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vtl_vehicle ON carpark_trip_log(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vtl_date ON carpark_trip_log(trip_date);


-- ============================================================
-- MULTI-PLATFORM PUBLISHING
-- (From CarStock: "Publicare Anunțuri Vânzare" with 10+ platforms)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_publishing_platforms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,            -- e.g., "Autovit", "Website", "Rulote MD"
    platform_type VARCHAR(30),             -- autovit, website, marketplace, custom
    brand_scope VARCHAR(100),              -- Which brand this account covers (VOLVO, MG MOTOR, etc.)
    api_base_url TEXT,
    api_key_encrypted TEXT,
    dealer_account_id VARCHAR(100),
    website_url TEXT,                       -- e.g., mg-cluj.ro, automotivegroup.ro
    icon_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    company_id INTEGER,
    config JSONB DEFAULT '{}',             -- Platform-specific configuration
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS carpark_vehicle_listings (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    platform_id INTEGER NOT NULL REFERENCES carpark_publishing_platforms(id),
    external_listing_id VARCHAR(100),      -- ID on the external platform
    status VARCHAR(20) DEFAULT 'draft',    -- draft, active, inactive, expired, error
    published_at TIMESTAMP,
    expires_at TIMESTAMP,                  -- Vizibilitate: "până la" date
    external_url TEXT,
    views INTEGER DEFAULT 0,
    inquiries INTEGER DEFAULT 0,
    last_sync TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vl_vehicle ON carpark_vehicle_listings(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vl_platform ON carpark_vehicle_listings(platform_id);
CREATE INDEX IF NOT EXISTS idx_vl_status ON carpark_vehicle_listings(status);


-- ============================================================
-- PRICING HISTORY
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_pricing_history (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    old_price DECIMAL(12,2),
    new_price DECIMAL(12,2),
    change_reason VARCHAR(100),
    rule_id INTEGER,
    changed_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vph_vehicle ON carpark_pricing_history(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vph_date ON carpark_pricing_history(created_at);


-- ============================================================
-- MILEAGE HISTORY: Tracks km evolution over time
-- (From CarStock: "Evoluție Kilometraj" tab showing date → km entries)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_mileage_history (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    recorded_date DATE NOT NULL,
    mileage_km INTEGER NOT NULL,
    source VARCHAR(30),                    -- manual, trip_log, test_drive, service, import
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vmh_vehicle ON carpark_mileage_history(vehicle_id);

-- CarStock data example from screenshot:
-- 2026-01-13: 8,700 km
-- 2026-01-16: 8,345 km (correction?)
-- 2025-10-28: 7,000 km
-- 2025-10-08: 5,500 km
-- 2025-07-31: 5,000 km
-- 2025-06-14: 3,000 km
-- 2024-07-09: 1,000 km


-- ============================================================
-- PRICING RULES: Dynamic pricing engine
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_pricing_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,

    condition_category VARCHAR(5)[],
    condition_brand VARCHAR(100)[],
    condition_min_days INTEGER,
    condition_max_days INTEGER,
    condition_min_price DECIMAL(12,2),
    condition_max_price DECIMAL(12,2),

    action_type VARCHAR(20) NOT NULL,      -- reduce_percent, reduce_amount, set_price, alert_only
    action_value DECIMAL(12,2),
    action_floor_type VARCHAR(20),
    action_floor_value DECIMAL(12,2),

    frequency VARCHAR(20) DEFAULT 'daily',
    last_executed TIMESTAMP,

    company_id INTEGER,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- PROMOTIONS
-- (From CarStock: "PROMOTII" section with dropdown selector)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_promotions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    description TEXT,

    target_type VARCHAR(20) NOT NULL,
    target_categories VARCHAR(5)[],
    target_brands VARCHAR(100)[],
    target_vehicle_ids INTEGER[],

    promo_type VARCHAR(30) NOT NULL,
    discount_type VARCHAR(20),
    discount_value DECIMAL(12,2),
    special_financing_rate DECIMAL(5,2),
    gift_description TEXT,

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,

    budget DECIMAL(12,2),
    spent DECIMAL(12,2) DEFAULT 0,
    vehicles_sold INTEGER DEFAULT 0,

    push_to_platforms BOOLEAN DEFAULT FALSE,
    platform_badge TEXT,

    company_id INTEGER,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- STATUS HISTORY: Full audit trail
-- (From CarStock: "Activitate" + "Istoric modificări" tabs)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_status_history (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    old_status VARCHAR(20),
    new_status VARCHAR(20) NOT NULL,
    old_location_id INTEGER,
    new_location_id INTEGER,
    notes TEXT,
    changed_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sh_vehicle ON carpark_status_history(vehicle_id);


-- ============================================================
-- MODIFICATION HISTORY: Field-level change audit
-- (From CarStock: "Istoric modificări" tab)
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_modification_history (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by INTEGER,
    changed_by_name VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mh_vehicle ON carpark_modification_history(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_mh_date ON carpark_modification_history(created_at);


-- ============================================================
-- PUBLISHING SYNC LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS carpark_publishing_sync_log (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id),
    platform_id INTEGER NOT NULL REFERENCES carpark_publishing_platforms(id),
    action VARCHAR(20) NOT NULL,
    request_payload JSONB,
    response_payload JSONB,
    http_status INTEGER,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_psl_vehicle ON carpark_publishing_sync_log(vehicle_id);


-- ============================================================
-- ANALYTICS VIEW
-- ============================================================
CREATE OR REPLACE VIEW carpark_vehicle_analytics AS
SELECT
    v.id, v.vin, v.nr_stoc, v.brand, v.model, v.variant, v.category, v.status,
    v.acquisition_date, v.stationary_days,
    v.purchase_price_net, v.total_cost, v.current_price, v.list_price,
    v.promotional_price, v.sale_price,
    v.is_consignment, v.is_test_drive,

    CASE WHEN v.sale_price IS NOT NULL
        THEN v.sale_price - v.total_cost
        ELSE v.current_price - v.total_cost
    END AS gross_margin,

    CASE WHEN v.total_cost > 0 AND v.current_price > 0
        THEN ROUND(((v.current_price - v.total_cost) / v.total_cost * 100)::numeric, 2)
        ELSE 0
    END AS margin_percent,

    CASE WHEN v.stationary_days > 0 AND v.total_cost > 0
        THEN ROUND((v.total_cost / v.stationary_days)::numeric, 2)
        ELSE 0
    END AS cost_per_day,

    CASE
        WHEN v.stationary_days <= 30 THEN '0-30'
        WHEN v.stationary_days <= 60 THEN '31-60'
        WHEN v.stationary_days <= 90 THEN '61-90'
        ELSE '90+'
    END AS aging_bucket,

    COALESCE((SELECT SUM(amount) FROM carpark_vehicle_costs WHERE vehicle_id = v.id), 0) AS additional_costs_total,
    COALESCE((SELECT SUM(amount) FROM carpark_vehicle_revenues WHERE vehicle_id = v.id), 0) AS total_revenue,
    (SELECT COUNT(*) FROM carpark_vehicle_photos WHERE vehicle_id = v.id) AS photo_count,
    (SELECT COUNT(*) FROM carpark_vehicle_documents WHERE vehicle_id = v.id) AS document_count,
    (SELECT COUNT(*) FROM carpark_interested_contacts WHERE vehicle_id = v.id) AS interested_contacts_count,
    (SELECT COUNT(*) FROM carpark_vehicle_listings WHERE vehicle_id = v.id AND status = 'active') AS active_listings_count,

    l.name AS location_name,
    l.code AS location_code

FROM carpark_vehicles v
LEFT JOIN carpark_locations l ON v.location_id = l.id
WHERE v.deleted_at IS NULL;
```

### 5.2 Equipment JSONB Structure

For quick filtering and display, the `equipment` JSONB field on vehicles stores the structured checkbox matrix:

```json
{
  "audio_connectivity": ["apple_carplay", "android_auto", "bluetooth", "port_usb", "wireless_charging", "sistem_audio", "sistem_navigatie", "monitor_touch_screen", "control_vocal", "conexiune_internet"],
  "electronics": ["camera_360", "senzori_parcare_fata", "senzori_parcare_spate", "camera_marsarier"],
  "electric_vehicle": ["masini_electrice"],
  "performance_tuning": ["performanta_tuning"],
  "safety": ["airbag_frontal", "airbag_lateral", "lane_assist", "control_distanta", "asistenta_urgenta_franare", "pilot_automat", "senzor_lumini", "senzor_ploaie", "faruri_led"]
}
```

---

## 6. BACKEND ARCHITECTURE

### 6.1 Module Structure

```
jarvis/carpark/
├── __init__.py                    # Blueprint: carpark_bp
├── routes.py                      # All API endpoints
├── repositories/
│   ├── __init__.py
│   ├── vehicle_repository.py      # VehicleRepository(BaseRepository)
│   ├── location_repository.py     # LocationRepository(BaseRepository)
│   ├── cost_repository.py         # CostRepository(BaseRepository)
│   ├── revenue_repository.py      # RevenueRepository(BaseRepository)
│   ├── document_repository.py     # DocumentRepository(BaseRepository)
│   ├── photo_repository.py        # PhotoRepository(BaseRepository)
│   ├── offer_repository.py        # OfferRepository(BaseRepository)
│   ├── contact_repository.py      # InterestedContactRepository(BaseRepository)
│   ├── pricing_repository.py      # PricingRepository(BaseRepository)
│   ├── promotion_repository.py    # PromotionRepository(BaseRepository)
│   ├── reservation_repository.py  # ReservationRepository(BaseRepository)
│   ├── appointment_repository.py  # AppointmentRepository(BaseRepository)
│   ├── trip_log_repository.py     # TripLogRepository(BaseRepository)
│   ├── listing_repository.py      # ListingRepository(BaseRepository)
│   ├── invoice_repository.py      # VehicleInvoiceRepository(BaseRepository)
│   └── history_repository.py      # StatusHistory + ModificationHistory + MileageHistory + PricingHistory
├── services/
│   ├── __init__.py
│   ├── vehicle_service.py         # Core CRUD + business logic
│   ├── pricing_service.py         # Dynamic pricing engine
│   ├── offer_service.py           # Offer generation + PDF creation
│   ├── publishing_service.py      # Multi-platform listing management
│   ├── analytics_service.py       # KPIs, reports, dashboards
│   ├── import_service.py          # Bulk import from Excel/CSV
│   ├── promotion_service.py       # Promotional campaign logic
│   └── document_service.py        # Document generation from templates
└── connectors/
    ├── __init__.py
    ├── autovit/
    │   ├── client.py              # Autovit.ro API client
    │   ├── mapper.py              # JARVIS ↔ Autovit data mapping
    │   └── config.py
    └── base_connector.py          # Abstract connector for any marketplace
```

### 6.2 Complete API Endpoints

```
# ═══════════════════════════════════════════════
# VEHICLES
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles                     # List with filters, pagination (catalog view)
GET    /api/carpark/vehicles/<id>                # Full detail (all sections data)
POST   /api/carpark/vehicles                     # Create vehicle
PUT    /api/carpark/vehicles/<id>                # Update vehicle (logs field changes to modification_history)
DELETE /api/carpark/vehicles/<id>                # Soft delete
POST   /api/carpark/vehicles/search              # Advanced search (POST for complex filters)
POST   /api/carpark/vehicles/import              # Bulk import from Excel
GET    /api/carpark/vehicles/<id>/timeline       # Combined status + price + mileage history
PUT    /api/carpark/vehicles/<id>/status         # Change status (triggers workflow)
POST   /api/carpark/vehicles/<id>/duplicate      # Clone vehicle record

# ═══════════════════════════════════════════════
# EQUIPMENT
# ═══════════════════════════════════════════════
GET    /api/carpark/equipment/categories         # List all categories with items
PUT    /api/carpark/vehicles/<id>/equipment      # Set equipment items (checkbox matrix)

# ═══════════════════════════════════════════════
# PHOTOS & 360°
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/photos         # List by type (gallery, interior_360, exterior_360)
POST   /api/carpark/vehicles/<id>/photos         # Upload (supports batch + type)
PUT    /api/carpark/photos/<id>                  # Update sort order / primary / type
PUT    /api/carpark/vehicles/<id>/photos/reorder # Batch reorder (drag-drop)
DELETE /api/carpark/photos/<id>                  # Delete photo
DELETE /api/carpark/vehicles/<id>/photos         # Delete all photos ("Șterge toate imaginile")

# ═══════════════════════════════════════════════
# OFFERS (Ofertare)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/offers         # List offers for vehicle
POST   /api/carpark/vehicles/<id>/offers         # Generate new offer (creates PDF)
PUT    /api/carpark/offers/<id>                  # Update offer
POST   /api/carpark/offers/<id>/send             # Send offer to client (email)
GET    /api/carpark/offers/<id>/pdf              # Download offer PDF

# ═══════════════════════════════════════════════
# INTERESTED CONTACTS (Contacte interesate)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/contacts       # List interested contacts
POST   /api/carpark/vehicles/<id>/contacts       # Add interested contact
PUT    /api/carpark/contacts/<id>                # Update contact
DELETE /api/carpark/contacts/<id>                # Remove contact
GET    /api/carpark/vehicles/<id>/contacts/export # "Descarcă" button export

# ═══════════════════════════════════════════════
# RESERVATIONS (Rezervări)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/reservations   # List (active + "Rezervări anterioare")
POST   /api/carpark/vehicles/<id>/reservations   # Create reservation ("CREAZĂ REZERVARE")
PUT    /api/carpark/reservations/<id>            # Update reservation
POST   /api/carpark/reservations/<id>/convert    # Convert to sale
POST   /api/carpark/reservations/<id>/cancel     # Cancel
POST   /api/carpark/reservations/<id>/extend     # Extend ("Reactivare Rezervare")

# ═══════════════════════════════════════════════
# INVOICING & COLLECTION (Facturare & Încasare)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/invoices       # List vehicle invoices
POST   /api/carpark/vehicles/<id>/invoices       # Link/create invoice
PUT    /api/carpark/vehicle-invoices/<id>        # Update payment status
POST   /api/carpark/vehicle-invoices/<id>/pay    # Record payment

# ═══════════════════════════════════════════════
# COSTS & REVENUE (Costuri & Venituri)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/costs          # List costs
POST   /api/carpark/vehicles/<id>/costs          # Add cost (with all CarStock form fields)
PUT    /api/carpark/costs/<id>                   # Update cost
DELETE /api/carpark/costs/<id>                   # Delete cost
GET    /api/carpark/vehicles/<id>/revenues       # List revenues
POST   /api/carpark/vehicles/<id>/revenues       # Add revenue
PUT    /api/carpark/revenues/<id>                # Update revenue
DELETE /api/carpark/revenues/<id>                # Delete revenue
GET    /api/carpark/cost-types                   # List cost type dropdown options

# ═══════════════════════════════════════════════
# DOCUMENTS
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/documents      # List documents
POST   /api/carpark/vehicles/<id>/documents      # Upload document
DELETE /api/carpark/documents/<id>               # Delete
GET    /api/carpark/documents/<id>/download       # Download ("Descarcă")
GET    /api/carpark/documents/<id>/view           # View inline ("Vezi")
POST   /api/carpark/vehicles/<id>/documents/generate  # Generate from template ("Generare documente")
GET    /api/carpark/document-templates            # List available templates

# ═══════════════════════════════════════════════
# SCHEDULING (Programări)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/appointments   # List appointments for vehicle
POST   /api/carpark/vehicles/<id>/appointments   # Schedule appointment ("Programare nouă")
PUT    /api/carpark/appointments/<id>            # Update
DELETE /api/carpark/appointments/<id>            # Cancel
POST   /api/carpark/appointments/<id>/signature  # Request signature ("Solicită semnătură")
GET    /api/carpark/appointments                 # List all appointments (global view)

# ═══════════════════════════════════════════════
# TRIP LOG (Foaie de parcurs)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/trips          # List trips
POST   /api/carpark/vehicles/<id>/trips          # Add trip entry
PUT    /api/carpark/trips/<id>                   # Update
DELETE /api/carpark/trips/<id>                   # Delete

# ═══════════════════════════════════════════════
# PUBLISHING (Publicare anunțuri)
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/listings       # List all platform listings for vehicle
POST   /api/carpark/vehicles/<id>/publish        # Publish to selected platforms
PUT    /api/carpark/listings/<id>                # Update listing
POST   /api/carpark/listings/<id>/activate       # Activate ("Activ")
POST   /api/carpark/listings/<id>/deactivate     # Deactivate ("Republică" → deactivate)
POST   /api/carpark/vehicles/<id>/publish-all    # Bulk publish ("Publică" button at bottom)
GET    /api/carpark/platforms                    # List configured platforms
POST   /api/carpark/platforms                    # Add platform
PUT    /api/carpark/platforms/<id>               # Configure platform
POST   /api/carpark/publishing/sync              # Full sync all platforms

# ═══════════════════════════════════════════════
# PRICING ENGINE
# ═══════════════════════════════════════════════
GET    /api/carpark/pricing/rules                # List pricing rules
POST   /api/carpark/pricing/rules                # Create rule
PUT    /api/carpark/pricing/rules/<id>           # Update rule
POST   /api/carpark/pricing/simulate             # Dry-run
POST   /api/carpark/pricing/execute              # Run now

# ═══════════════════════════════════════════════
# PROMOTIONS
# ═══════════════════════════════════════════════
GET    /api/carpark/promotions                   # List
POST   /api/carpark/promotions                   # Create
PUT    /api/carpark/promotions/<id>              # Update
GET    /api/carpark/promotions/<id>/vehicles     # Vehicles in promotion

# ═══════════════════════════════════════════════
# ACTIVITY / HISTORY
# ═══════════════════════════════════════════════
GET    /api/carpark/vehicles/<id>/activity       # Activity log
GET    /api/carpark/vehicles/<id>/modifications  # Istoric modificări
GET    /api/carpark/vehicles/<id>/mileage-history  # Evoluție Kilometraj
GET    /api/carpark/vehicles/<id>/price-history    # Evoluție Preț de vânzare

# ═══════════════════════════════════════════════
# DASHBOARD & ANALYTICS
# ═══════════════════════════════════════════════
GET    /api/carpark/dashboard                    # KPI summary
GET    /api/carpark/analytics/aging              # Aging report
GET    /api/carpark/analytics/margins            # Margin analysis
GET    /api/carpark/analytics/turnover           # Turn rate
GET    /api/carpark/analytics/costs              # Cost breakdown
GET    /api/carpark/analytics/salesperson         # Per-salesperson performance
POST   /api/carpark/analytics/export             # Export to Excel

# ═══════════════════════════════════════════════
# LOCATIONS
# ═══════════════════════════════════════════════
GET    /api/carpark/locations                    # List
POST   /api/carpark/locations                    # Create
PUT    /api/carpark/locations/<id>               # Update
```

### 6.3 Scheduled Tasks

```python
# Daily pricing engine (06:00)
scheduler.add_job(pricing_service.execute_pricing_rules, 'cron', hour=6, minute=0)

# Multi-platform stats sync (every 4 hours)
scheduler.add_job(publishing_service.sync_all_platform_stats, 'interval', hours=4)

# Reservation expiry check (every hour)
scheduler.add_job(reservation_service.expire_stale_reservations, 'interval', hours=1)

# Aging alerts (daily 08:00)
scheduler.add_job(analytics_service.send_aging_alerts, 'cron', hour=8, minute=0)

# Days listed counter update (daily 00:05)
scheduler.add_job(vehicle_service.update_days_listed, 'cron', hour=0, minute=5)

# Mileage consistency check (weekly Sunday 06:00)
scheduler.add_job(vehicle_service.check_mileage_consistency, 'cron', day_of_week='sun', hour=6)
```

---

## 7. FRONTEND ARCHITECTURE

### 7.1 Page Structure

```
frontend/src/pages/CarPark/
├── index.tsx                      # Main page: catalog view + tabs (mirrors CarStock top bar)
├── VehicleDetail.tsx              # Full vehicle detail with left sidebar navigation
├── VehicleForm.tsx                # Create/Edit vehicle (mirrors CarStock edit mode)
├── components/
│   ├── Catalog/
│   │   ├── CatalogToolbar.tsx     # Search, filters, "+ Adaugă în catalog" button
│   │   ├── CatalogTabs.tsx        # TOATE | ACTIVE | REZERVATE | IN DESFACERE | VANDUTE | LIVRATE
│   │   ├── CatalogFilters.tsx     # Left sidebar: Lista, brand, model, fuel, body, color, price, year, location
│   │   ├── VehicleListItem.tsx    # Row in catalog list (thumbnail, specs, price, status badge, days)
│   │   └── BulkActions.tsx
│   ├── Detail/
│   │   ├── DetailSidebar.tsx      # Left nav with vehicle thumbnail + status + section links
│   │   ├── GeneralInfo.tsx        # Section 1: Full specs form (Informații generale)
│   │   ├── PhotoGallery.tsx       # Section 2: Photos + Interior 360° + Exterior 360° tabs
│   │   ├── Offers.tsx             # Section 3: Offer list + "OFERTEAZĂ" button
│   │   ├── InterestedContacts.tsx # Section 4: Contact list + "+ Adaugă contact interesat"
│   │   ├── Reservations.tsx       # Section 5: Active + historical reservations
│   │   ├── Invoicing.tsx          # Section 6: Facturare & Încasare
│   │   ├── CostsRevenue.tsx       # Section 7: Dual section (Costuri | Venituri)
│   │   ├── CostForm.tsx           # Cost add form (matches CarStock exactly)
│   │   ├── Documents.tsx          # Section 8: Document vault + "Generare documente"
│   │   ├── Appointments.tsx       # Section 9: Scheduling grid (Programări)
│   │   ├── TripLog.tsx            # Section 10: Foaie de parcurs
│   │   ├── Publishing.tsx         # Section 11: Multi-platform listing management
│   │   └── Activity.tsx           # Section 12: Tabs (Activitate | Istoric modificări | Evoluție Km | Evoluție Preț)
│   ├── Dashboard/
│   │   ├── KpiCards.tsx
│   │   ├── AgingChart.tsx
│   │   ├── StockByCategory.tsx
│   │   ├── MarginAnalysis.tsx
│   │   └── RecentActivity.tsx
│   ├── Pricing/
│   │   ├── PricingRules.tsx
│   │   └── PricingSimulator.tsx
│   ├── Promotions/
│   │   ├── PromotionList.tsx
│   │   └── PromotionForm.tsx
│   └── Charts/
│       ├── MileageEvolution.tsx   # Line chart: date → km (from Evoluție Kilometraj)
│       └── PriceEvolution.tsx     # Line chart: date → price EUR (from Evoluție Preț de vânzare)
```

### 7.2 Sidebar Navigation

```typescript
{
  path: '/app/carpark',
  label: 'CarPark',
  icon: Car,
  moduleKey: 'carpark',
  permission: 'can_access_carpark',
  children: [
    { path: '/app/carpark', label: 'Catalog', icon: LayoutGrid, moduleKey: 'carpark_catalog' },
    { path: '/app/carpark?tab=dashboard', label: 'Dashboard', icon: LayoutDashboard, moduleKey: 'carpark_dashboard' },
    { path: '/app/carpark?tab=pricing', label: 'Pricing', icon: TrendingDown, moduleKey: 'carpark_pricing' },
    { path: '/app/carpark?tab=promotions', label: 'Promotions', icon: BadgePercent, moduleKey: 'carpark_promotions' },
    { path: '/app/carpark?tab=appointments', label: 'Programări', icon: Calendar, moduleKey: 'carpark_appointments' },
    { path: '/app/carpark?tab=publishing', label: 'Publishing', icon: Globe, moduleKey: 'carpark_publishing' },
    { path: '/app/carpark?tab=analytics', label: 'Analytics', icon: BarChart3, moduleKey: 'carpark_analytics' },
  ],
}
```

---

## 8. INTEGRATION MATRIX WITH EXISTING JARVIS MODULES

| JARVIS Module | Integration Point | Direction | Description |
|--------------|-------------------|-----------|-------------|
| **Accounting/Invoices** | `invoice_id` in costs + vehicle_invoices | CarPark → Accounting | Link purchase/sale/cost invoices to vehicles |
| **e-Factura** | Sale invoice generation | CarPark → e-Factura | Auto-generate e-Factura on vehicle sale |
| **CRM** | `client_id` in contacts, reservations, offers | CarPark ↔ CRM | Bidirectional: vehicle interests feed CRM; CRM clients link to vehicles |
| **DMS** | `dms_document_id` in vehicle documents | CarPark → DMS | Store/retrieve documents via Google Drive |
| **AI Agent** | RAG indexing | CarPark → AI | Natural language queries on stock, margins, aging |
| **Approvals** | Price override, high-value sale | CarPark → Approvals | Manager approval for below-floor pricing |
| **Marketing** | Promotion campaigns | CarPark ↔ Marketing | Sync vehicle promotions with campaign tracking |
| **Notifications** | Aging alerts, reservation expiry, appointment reminders | CarPark → Notifications | Push notifications for critical events |
| **Bank Statements** | Payment reconciliation | Statements → CarPark | Auto-match payments to vehicle sales |
| **Field Sales** | Vehicle availability | CarPark → FieldSales | Check/reserve stock from field |

---

## 9. DYNAMIC PRICING ENGINE

### 9.1 Rule Types

Time-based decay: after 30 days reduce 3%, after 45 days reduce 5%, after 60 days reduce 8%, after 90 days flag for liquidation.

Competitor-aware (Phase 2): scrape Autovit for comparable vehicles, position at target percentile.

Demand-signal based (Phase 2): high views + low inquiries = price too high; high inquiries + no reservation = salesperson issue.

### 9.2 Floor Price Logic

```
floor_price = MAX(
    vehicle.minimum_price,
    vehicle.total_cost * (1 + minimum_margin_percent / 100),
    vehicle.purchase_price_net * minimum_recovery_percent / 100
)
```

---

## 10. IMPLEMENTATION PHASES

### Phase 1: Core Inventory + Vehicle Detail (Weeks 1-4)
- Database schema creation (all tables)
- Vehicle CRUD + equipment matrix
- Location management
- Photo gallery with 360° support
- Cost & revenue tracking (full CarStock form parity)
- Document vault + template generation
- Status workflow with history
- Mileage tracking
- Catalog view with filters + tabs
- Vehicle detail page (all 12 sections)
- Import from Excel

### Phase 2: CRM + Commercial (Weeks 5-6)
- Offer generation with PDF output
- Interested contacts per vehicle
- Reservation system with history
- Invoicing & collection per vehicle
- Appointment scheduling with notifications + signature

### Phase 3: Publishing + Pricing (Weeks 7-9)
- Multi-platform publishing system (abstract connector pattern)
- Autovit API connector (first implementation)
- Website connectors
- Bulk publish/deactivate actions
- Dynamic pricing rules engine
- Pricing simulator (dry-run)
- Promotion management

### Phase 4: Analytics + Intelligence (Weeks 10-12)
- Dashboard with KPI cards
- Aging report with drill-down
- Margin analysis (per vehicle, category, salesperson)
- Mileage evolution charts
- Price evolution charts
- Modification history viewer
- Activity timeline
- Export to Excel
- AI Agent integration (RAG indexing)
- Trip log (Foaie de parcurs)

### Phase 5: Advanced (Weeks 13-14)
- Dynamic pricing v2 (competitor-aware)
- Automated multi-platform repricing
- Push notification workflows
- Mobile-optimized views
- Bank statement reconciliation for vehicle payments

---

## 11. TECHNICAL NOTES

### 11.1 Permission Setup
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS can_access_carpark BOOLEAN DEFAULT FALSE;
```

### 11.2 Environment Variables
```
AUTOVIT_API_KEY=<key>
AUTOVIT_API_URL=https://api.autovit.ro/v1
AUTOVIT_DEALER_ID=<id>
CARPARK_MIN_MARGIN_PERCENT=2
CARPARK_PRICING_APPROVAL_THRESHOLD=500
CARPARK_AGING_ALERT_DAYS=60
```

### 11.3 Architecture Decision: Variant A (Monolithic Module)

Single `carpark` module inside JARVIS. Follows the exact pattern of CRM, Accounting, Marketing. Fastest to implement, full access to all JARVIS services, single deployment. Clean Repository/Service/Routes layering makes future extraction trivial if ever needed.

---

## 12. TABLE COUNT SUMMARY

| # | Table | Purpose |
|---|-------|---------|
| 1 | carpark_vehicles | Central vehicle entity |
| 2 | carpark_equipment_categories | Equipment checkbox categories |
| 3 | carpark_equipment_items | Equipment checkbox items |
| 4 | carpark_vehicle_equipment | Vehicle ↔ equipment junction |
| 5 | carpark_locations | Physical locations |
| 6 | carpark_vehicle_costs | Per-vehicle costs |
| 7 | carpark_vehicle_revenues | Per-vehicle revenues |
| 8 | carpark_vehicle_documents | Document vault |
| 9 | carpark_document_templates | Auto-fill document templates |
| 10 | carpark_vehicle_photos | Photos + 360° |
| 11 | carpark_offers | Client offers/quotes |
| 12 | carpark_interested_contacts | Per-vehicle prospects |
| 13 | carpark_reservations | Reservations |
| 14 | carpark_vehicle_invoices | Vehicle-level billing |
| 15 | carpark_appointments | Scheduling (test drives, viewings) |
| 16 | carpark_trip_log | Vehicle usage log |
| 17 | carpark_publishing_platforms | Marketplace platforms config |
| 18 | carpark_vehicle_listings | Per-vehicle per-platform listings |
| 19 | carpark_pricing_history | Price change audit |
| 20 | carpark_mileage_history | Km evolution tracking |
| 21 | carpark_pricing_rules | Dynamic pricing rules |
| 22 | carpark_promotions | Marketing promotions |
| 23 | carpark_status_history | Status change audit |
| 24 | carpark_modification_history | Field-level change audit |
| 25 | carpark_publishing_sync_log | Platform sync audit |
| + | carpark_vehicle_analytics | Analytics VIEW |

**Total: 25 tables + 1 view, 80+ API endpoints, 12 vehicle detail sections.**
