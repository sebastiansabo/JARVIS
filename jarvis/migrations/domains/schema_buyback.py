"""Buyback schema: vehicle buyback/trade-in records, client offers, photos,
and audit events.

buyback_records is the central entity (evaluation -> offer -> purchase
lifecycle). buyback_offers tracks each offer made to a seller and their
decision. buyback_photos stores vehicle photo gallery entries. buyback_events
is an append-only audit log of actions taken on a record.

All DDL is IF NOT EXISTS / idempotent, safe to re-run (mirrors
schema_carpark.py style).
"""


def create_schema_buyback(conn, cursor):
    """Create all buyback module tables and indexes."""

    # ── Records: central entity ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_records (
            id BIGSERIAL PRIMARY KEY,
            record_code VARCHAR(64) UNIQUE NOT NULL,
            company_id BIGINT NOT NULL,
            brand_id BIGINT,
            status VARCHAR(24) NOT NULL DEFAULT 'PENDING_EVALUATION',
            acquisition_type VARCHAR(20), is_trade_in BOOLEAN DEFAULT FALSE,
            advisor_id INTEGER, advisor_name VARCHAR(255),
            client_type VARCHAR(20), vat_status VARCHAR(20), client_id BIGINT,
            seller_name VARCHAR(255), seller_email VARCHAR(255),
            seller_phone VARCHAR(50), seller_cui VARCHAR(30),
            brand VARCHAR(100), model VARCHAR(200), variant VARCHAR(200), equipment VARCHAR(200),
            vin VARCHAR(17), mileage_km INTEGER, engine_capacity_cm3 INTEGER,
            fuel_type VARCHAR(50), transmission VARCHAR(50), gearbox VARCHAR(50),
            manufacture_date DATE, first_registration_date DATE,
            service_history_uptodate BOOLEAN, extra_wheels BOOLEAN, keys_count SMALLINT,
            has_damage BOOLEAN, damage_details TEXT, general_condition SMALLINT,
            client_asking_price_eur NUMERIC(12,2), client_source VARCHAR(100),
            other_details TEXT, drive_folder_link TEXT,
            target_vehicle_text TEXT, target_carpark_vehicle_id BIGINT, crm_deal_id BIGINT,
            inspection_report_key TEXT, inspection_rating SMALLINT,
            reconditioning_cost_eur NUMERIC(12,2), inspection_notes TEXT,
            inspected_by INTEGER, inspected_at TIMESTAMPTZ,
            purchase_price_eur NUMERIC(12,2), carpark_vehicle_id BIGINT,
            bought_at TIMESTAMPTZ, finalized_by INTEGER, lost_reason TEXT,
            created_by INTEGER, updated_by INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
            closed_at TIMESTAMPTZ
        )
    ''')
    for idx, col in [('idx_bb_company', 'company_id'), ('idx_bb_status', 'status'),
                      ('idx_bb_vin', 'vin'), ('idx_bb_created', 'created_at')]:
        cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx} ON buyback_records ({col})')

    # ── Offers: offers made to the seller for a record ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_offers (
            id BIGSERIAL PRIMARY KEY,
            record_id BIGINT NOT NULL REFERENCES buyback_records(id) ON DELETE CASCADE,
            offer_type VARCHAR(10) NOT NULL, amount_eur NUMERIC(12,2) NOT NULL,
            vat_status VARCHAR(20), valid_until DATE, notes TEXT,
            created_by INTEGER, created_at TIMESTAMPTZ DEFAULT NOW(),
            client_decision VARCHAR(10) NOT NULL DEFAULT 'pending',
            decided_by INTEGER, decided_at TIMESTAMPTZ, decline_reason TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bb_offers_record ON buyback_offers (record_id)')

    # ── Photos: vehicle photo gallery for a record ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_photos (
            id BIGSERIAL PRIMARY KEY,
            record_id BIGINT NOT NULL REFERENCES buyback_records(id) ON DELETE CASCADE,
            url TEXT NOT NULL, thumbnail_url TEXT, sort_order INTEGER DEFAULT 0,
            is_primary BOOLEAN DEFAULT FALSE, photo_type VARCHAR(30) NOT NULL DEFAULT 'gallery',
            caption TEXT, file_size INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(), deleted_at TIMESTAMPTZ
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bb_photos_record ON buyback_photos (record_id)')

    # ── Events: append-only audit log for a record ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_events (
            id BIGSERIAL PRIMARY KEY,
            record_id BIGINT NOT NULL REFERENCES buyback_records(id) ON DELETE CASCADE,
            action VARCHAR(64) NOT NULL, actor INTEGER, details JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_bb_events_record ON buyback_events (record_id, created_at DESC)'
    )
