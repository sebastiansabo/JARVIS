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
            brand VARCHAR(100), model VARCHAR(200), variant VARCHAR(200), equipment TEXT,
            vin VARCHAR(17), mileage_km INTEGER, engine_capacity_cm3 INTEGER,
            fuel_type VARCHAR(50), transmission VARCHAR(50), gearbox VARCHAR(50),
            manufacture_date DATE, first_registration_date DATE,
            service_history_uptodate BOOLEAN, extra_wheels BOOLEAN, keys_count SMALLINT,
            has_damage BOOLEAN, damage_details TEXT, general_condition SMALLINT,
            client_asking_price_eur NUMERIC(12,2), market_price_eur NUMERIC(12,2),
            client_source VARCHAR(100),
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

    # ── Hold status: columns capturing the prior status, reason, note, and
    # who/when put a record on hold (info missing / blocked). Idempotent per
    # column via information_schema guard -- safe on already-seeded DBs.
    for _col, _type in [
        ('hold_prior_status', 'VARCHAR(24)'), ('hold_reason', 'VARCHAR(100)'),
        ('hold_note', 'TEXT'), ('held_at', 'TIMESTAMPTZ'), ('held_by', 'INTEGER'),
    ]:
        cursor.execute(f'''
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='buyback_records' AND column_name='{_col}') THEN
                    ALTER TABLE buyback_records ADD COLUMN {_col} {_type};
                END IF;
            END $$;
        ''')

    # ── Seller legal identity (for the purchase/consignație contract):
    # person CNP + CI, company reg/IBAN/legal-rep, universal address.
    # Idempotent per column — safe on already-seeded DBs.
    for _col, _type in [
        ('seller_address', 'TEXT'), ('seller_cnp', 'VARCHAR(13)'),
        ('seller_ci_serie', 'VARCHAR(10)'), ('seller_ci_number', 'VARCHAR(20)'),
        ('seller_reg_no', 'VARCHAR(30)'), ('seller_iban', 'VARCHAR(34)'),
        ('seller_legal_rep', 'VARCHAR(255)'),
    ]:
        cursor.execute(f'''
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='buyback_records' AND column_name='{_col}') THEN
                    ALTER TABLE buyback_records ADD COLUMN {_col} {_type};
                END IF;
            END $$;
        ''')

    # Seed buyback_hold_reason dropdown options (idempotent, one INSERT per
    # value guarded by WHERE NOT EXISTS, mirrors the invoice_status seed
    # pattern in schema_misc.py -- additive only, won't disturb existing rows).
    for _value, _sort in [
        ('Poze lipsă', 1), ('Talon/CIV lipsă', 2), ('VIN lipsă/greșit', 3),
        ('Preț incomplet', 4), ('Date contact lipsă', 5), ('Altele', 6),
    ]:
        cursor.execute('''
            INSERT INTO dropdown_options (dropdown_type, value, label, sort_order, is_active)
            SELECT 'buyback_hold_reason', %s, %s, %s, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM dropdown_options
                WHERE dropdown_type = 'buyback_hold_reason' AND value = %s
            )
        ''', (_value, _value, _sort, _value))

    # ── Preț Piață: the dealer's own market-value estimate for the car,
    # recorded at intake alongside the owner's asking price
    # (client_asking_price_eur) and distinct from the final purchase price.
    # Idempotent ADD COLUMN for EXISTING deployments (fresh DBs already have it
    # from the CREATE above); the information_schema guard makes it a no-op once
    # present.
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='buyback_records' AND column_name='market_price_eur') THEN
                ALTER TABLE buyback_records ADD COLUMN market_price_eur NUMERIC(12,2);
            END IF;
        END $$;
    ''')

    # equipment is declared TEXT above (fresh DBs). This widens EXISTING
    # deployments where it was still VARCHAR(200): the intake form stores every
    # selected Autovit feature as a comma-joined string, and a well-equipped car
    # (20+ features) overflows 200 chars -> StringDataRightTruncation on INSERT
    # -> uncaught 500 ("An internal error occurred"). Idempotent: the
    # information_schema guard makes it a no-op once the column is already TEXT.
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'buyback_records'
                  AND column_name = 'equipment'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE buyback_records ALTER COLUMN equipment TYPE TEXT;
            END IF;
        END $$;
    ''')

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

    # offer_type was VARCHAR(10) for the original 'initial'/'final' rounds; the
    # consignment proposal flow (Propune consignație) adds an 11-char
    # 'consignment' round that overflows it -> StringDataRightTruncation on
    # INSERT -> uncaught 500. Widen EXISTING deployments to VARCHAR(20).
    # Idempotent: the character_maximum_length guard makes it a no-op once the
    # column is already wide enough (fresh DBs created above still land at 10,
    # so this ALTER runs once for them too).
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'buyback_offers'
                  AND column_name = 'offer_type'
                  AND character_maximum_length < 20
            ) THEN
                ALTER TABLE buyback_offers ALTER COLUMN offer_type TYPE VARCHAR(20);
            END IF;
        END $$;
    ''')

    # consignment_terms holds a consignment proposal's terms (owner_price,
    # commission, floor, contract no., dates) as JSONB on the 'consignment'
    # offer, until the seller accepts and they're written to
    # carpark_vehicle_consignment at hand-off. Idempotent column add
    # (information_schema guard, mirrors the hold_* columns above).
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='buyback_offers' AND column_name='consignment_terms') THEN
                ALTER TABLE buyback_offers ADD COLUMN consignment_terms JSONB;
            END IF;
        END $$;
    ''')

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

    # ── Per-tenant notification config (one row per company) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_company_config (
            company_id BIGINT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            acquisition_emails TEXT,
            channel_email BOOLEAN NOT NULL DEFAULT TRUE,
            channel_in_app BOOLEAN NOT NULL DEFAULT TRUE,
            channel_push BOOLEAN NOT NULL DEFAULT TRUE,
            notify_new_request BOOLEAN NOT NULL DEFAULT TRUE,
            notify_milestones BOOLEAN NOT NULL DEFAULT TRUE,
            notify_inspection BOOLEAN NOT NULL DEFAULT TRUE,
            updated_by INTEGER,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Per-company×brand contract templates (purchase / consignment). The legal
    # body text carries {tokens} the renderer substitutes. One template per
    # (company, brand, document_type).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyback_contract_templates (
            id BIGSERIAL PRIMARY KEY,
            company_id BIGINT NOT NULL,
            brand_id BIGINT,
            document_type VARCHAR(20) NOT NULL DEFAULT 'purchase',
            title VARCHAR(255),
            body_template TEXT,
            general_conditions TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by INTEGER, updated_by INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, brand_id, document_type)
        )
    ''')
