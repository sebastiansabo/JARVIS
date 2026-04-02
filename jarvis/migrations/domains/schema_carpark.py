"""CarPark schema: vehicles, locations, photos, costs, revenues, documents,
offers, contacts, reservations, appointments, trip log, publishing, pricing,
promotions, and all audit/history tables.

Slice 1: vehicles, locations, photos, status_history, modification_history, mileage_history
Subsequent slices add remaining tables via IF NOT EXISTS (safe to re-run).
"""


def create_schema_carpark(conn, cursor):
    """Create all CarPark module tables, indexes, and views."""

    # ── Locations (must exist before vehicles FK) ──
    cursor.execute('''
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
        )
    ''')

    # ── Vehicles: Central entity ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicles (
            id SERIAL PRIMARY KEY,

            -- Identity
            vin VARCHAR(17) UNIQUE NOT NULL,
            identification_number VARCHAR(50),
            registration_number VARCHAR(20),
            chassis_code VARCHAR(50),
            emission_code VARCHAR(50),

            -- Classification
            category VARCHAR(5) NOT NULL DEFAULT 'SH',
            status VARCHAR(20) NOT NULL DEFAULT 'ACQUIRED',
            vehicle_type VARCHAR(30) DEFAULT 'Autoturism',
            state VARCHAR(20) DEFAULT 'Nou',

            -- Specs
            brand VARCHAR(100) NOT NULL,
            model VARCHAR(200) NOT NULL,
            variant VARCHAR(200),
            generation VARCHAR(100),
            equipment_level VARCHAR(100),
            body_type VARCHAR(50),
            year_of_manufacture INTEGER,
            first_registration_date DATE,
            color_exterior VARCHAR(50),
            color_code VARCHAR(30),
            color_interior VARCHAR(50),
            interior_code VARCHAR(30),
            fuel_type VARCHAR(30),
            transmission VARCHAR(20),
            drive_type VARCHAR(10),
            engine_displacement_cc INTEGER,
            engine_power_hp INTEGER,
            engine_power_kw INTEGER,
            engine_power_electric_hp INTEGER,
            engine_torque_nm INTEGER,
            co2_emissions INTEGER,
            euro_standard VARCHAR(10),
            mileage_km INTEGER DEFAULT 0,
            max_weight_kg INTEGER,
            doors INTEGER,
            seats INTEGER,
            tire_type VARCHAR(50),
            fuel_consumption VARCHAR(50),

            -- Equipment (structured JSONB for quick filter/display)
            equipment JSONB DEFAULT '{}',
            optional_packages JSONB DEFAULT '[]',

            -- Warranty & flags
            has_manufacturer_warranty BOOLEAN DEFAULT FALSE,
            manufacturer_warranty_date DATE,
            has_dealer_warranty BOOLEAN DEFAULT FALSE,
            dealer_warranty_months INTEGER,
            is_registered BOOLEAN DEFAULT FALSE,
            is_first_owner BOOLEAN DEFAULT FALSE,
            has_accident_history BOOLEAN DEFAULT FALSE,
            has_service_book BOOLEAN DEFAULT FALSE,
            is_electric_vehicle BOOLEAN DEFAULT FALSE,
            has_tuning BOOLEAN DEFAULT FALSE,

            -- Media
            youtube_url TEXT,

            -- Listing title/description
            listing_title TEXT,
            listing_description TEXT,

            -- Location
            location_id INTEGER REFERENCES carpark_locations(id),
            parking_spot VARCHAR(50),
            location_text VARCHAR(100),

            -- Ownership / Source
            source VARCHAR(50),
            supplier_name VARCHAR(200),
            supplier_cif VARCHAR(30),
            purchase_contract_number VARCHAR(100),
            purchase_contract_date DATE,
            owner_name VARCHAR(200),

            -- Acquisition info
            acquisition_manager_id INTEGER,
            acquisition_document_number VARCHAR(50),
            acquisition_date DATE NOT NULL DEFAULT CURRENT_DATE,
            arrival_date DATE,
            acquisition_value DECIMAL(12,2),
            acquisition_vat DECIMAL(12,2),
            acquisition_price DECIMAL(12,2),
            acquisition_currency VARCHAR(3) DEFAULT 'EUR',
            acquisition_exchange_rate DECIMAL(10,4),

            -- Financial / Cost tracking
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

            -- Pricing
            list_price DECIMAL(12,2),
            promotional_price DECIMAL(12,2),
            minimum_price DECIMAL(12,2),
            current_price DECIMAL(12,2),
            price_currency VARCHAR(3) DEFAULT 'EUR',
            price_includes_vat BOOLEAN DEFAULT TRUE,
            vat_deductible BOOLEAN DEFAULT FALSE,
            is_negotiable BOOLEAN DEFAULT TRUE,
            margin_scheme BOOLEAN DEFAULT FALSE,

            -- Financing options
            eligible_for_financing BOOLEAN DEFAULT FALSE,
            available_for_leasing BOOLEAN DEFAULT FALSE,
            can_issue_invoice BOOLEAN DEFAULT TRUE,

            -- Consignment
            is_consignment BOOLEAN DEFAULT FALSE,

            -- Promotion
            promotion_id INTEGER,

            -- Test Drive / Demo
            is_test_drive BOOLEAN DEFAULT FALSE,
            service_exchange_vehicle BOOLEAN DEFAULT FALSE,

            -- Sale
            sale_price DECIMAL(12,2),
            sale_date DATE,
            buyer_client_id INTEGER,
            salesperson_user_id INTEGER,

            -- Stock number
            nr_stoc VARCHAR(50),

            -- Lifecycle dates
            ready_for_sale_date DATE,
            listing_date DATE,
            reservation_date DATE,
            delivery_date DATE,

            -- Computed (days_listed updated by scheduled job, not generated column)
            days_listed INTEGER DEFAULT 0,

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
        )
    ''')

    # Performance indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_vin ON carpark_vehicles(vin)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_status ON carpark_vehicles(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_category ON carpark_vehicles(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_brand_model ON carpark_vehicles(brand, model)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_company ON carpark_vehicles(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_acquisition ON carpark_vehicles(acquisition_date)')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cv_deleted ON carpark_vehicles(deleted_at) WHERE deleted_at IS NULL")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_equipment ON carpark_vehicles USING GIN (equipment)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cv_nr_stoc ON carpark_vehicles(nr_stoc)')

    # ── Equipment categories & items (structured checkbox matrix) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_equipment_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            name_ro VARCHAR(100),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_equipment_items (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES carpark_equipment_categories(id),
            name VARCHAR(200) NOT NULL,
            name_ro VARCHAR(200),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_equipment (
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            equipment_item_id INTEGER NOT NULL REFERENCES carpark_equipment_items(id),
            PRIMARY KEY (vehicle_id, equipment_item_id)
        )
    ''')

    # ── Photos & 360 ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_photos (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            thumbnail_url TEXT,
            sort_order INTEGER DEFAULT 0,
            is_primary BOOLEAN DEFAULT FALSE,
            photo_type VARCHAR(30) NOT NULL DEFAULT 'gallery',
            caption TEXT,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcp_vehicle ON carpark_vehicle_photos(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcp_type ON carpark_vehicle_photos(photo_type)')

    # ── Costs ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_costs (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            cost_type VARCHAR(50) NOT NULL,
            description TEXT,
            amount DECIMAL(12,2) NOT NULL,
            currency VARCHAR(3) DEFAULT 'RON',
            vat_rate DECIMAL(5,2) DEFAULT 19,
            vat_amount DECIMAL(12,2) DEFAULT 0,
            exchange_rate_eur DECIMAL(10,4),
            invoice_number VARCHAR(100),
            invoice_date DATE,
            invoice_value DECIMAL(12,2),
            invoice_id INTEGER,
            supplier_name VARCHAR(200),
            radio_cost_type VARCHAR(20),
            document_file TEXT,
            observation TEXT,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcc_vehicle ON carpark_vehicle_costs(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcc_type ON carpark_vehicle_costs(cost_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcc_invoice ON carpark_vehicle_costs(invoice_id)')

    # ── Revenues ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_revenues (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            revenue_type VARCHAR(50) NOT NULL,
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
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcr_vehicle ON carpark_vehicle_revenues(vehicle_id)')

    # ── Documents ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_documents (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            document_type VARCHAR(50) NOT NULL,
            title VARCHAR(300),
            file_url TEXT,
            dms_document_id INTEGER,
            file_size INTEGER,
            mime_type VARCHAR(100),
            notes TEXT,
            uploaded_by INTEGER,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcd_vehicle ON carpark_vehicle_documents(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vcd_type ON carpark_vehicle_documents(document_type)')

    # ── Document templates ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_document_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            template_file_url TEXT,
            auto_fill_fields JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Offers ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_offers (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            client_id INTEGER,
            client_name VARCHAR(200),
            client_email VARCHAR(200),
            client_phone VARCHAR(50),
            offered_price DECIMAL(12,2),
            currency VARCHAR(3) DEFAULT 'EUR',
            includes_vat BOOLEAN DEFAULT TRUE,
            discount_amount DECIMAL(12,2) DEFAULT 0,
            discount_reason TEXT,
            financing_details TEXT,
            trade_in_vehicle TEXT,
            trade_in_value DECIMAL(12,2),
            offer_pdf_url TEXT,
            offer_number VARCHAR(50),
            status VARCHAR(20) DEFAULT 'draft',
            valid_until DATE,
            sent_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vo_vehicle ON carpark_offers(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vo_client ON carpark_offers(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vo_status ON carpark_offers(status)')

    # ── Interested Contacts ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_interested_contacts (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            client_id INTEGER,
            client_name VARCHAR(200) NOT NULL,
            client_phone VARCHAR(50),
            client_email VARCHAR(200),
            company_name VARCHAR(200),
            source VARCHAR(50),
            interest_level VARCHAR(20),
            notes TEXT,
            follow_up_date DATE,
            salesperson_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vic_vehicle ON carpark_interested_contacts(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vic_client ON carpark_interested_contacts(client_id)')

    # ── Reservations ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_reservations (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            client_id INTEGER,
            client_name VARCHAR(200),
            client_company VARCHAR(200),
            client_phone VARCHAR(50),
            client_email VARCHAR(200),
            user_id INTEGER,
            reservation_start TIMESTAMP NOT NULL,
            reservation_end TIMESTAMP,
            deposit_amount DECIMAL(12,2) DEFAULT 0,
            deposit_paid BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) DEFAULT 'active',
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vr_vehicle ON carpark_reservations(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vr_status ON carpark_reservations(status)')

    # ── Vehicle Invoices (per-vehicle billing link) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_invoices (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            invoice_type VARCHAR(20) NOT NULL,
            invoice_id INTEGER,
            invoice_number VARCHAR(100),
            invoice_date DATE,
            amount DECIMAL(12,2),
            currency VARCHAR(3) DEFAULT 'RON',
            vat_amount DECIMAL(12,2),
            payment_status VARCHAR(20) DEFAULT 'unpaid',
            payment_date DATE,
            payment_amount DECIMAL(12,2),
            client_name VARCHAR(200),
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vvi_vehicle ON carpark_vehicle_invoices(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vvi_invoice ON carpark_vehicle_invoices(invoice_id)')

    # ── Appointments / Scheduling ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_appointments (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            appointment_type VARCHAR(30) DEFAULT 'test_drive',
            scheduled_date DATE NOT NULL,
            scheduled_time TIME,
            actual_date DATE,
            responsible_id INTEGER,
            responsible_name VARCHAR(200),
            client_id INTEGER,
            client_name VARCHAR(200) NOT NULL,
            client_company VARCHAR(200),
            route TEXT,
            driver_license_number VARCHAR(50),
            mileage_before INTEGER,
            mileage_after INTEGER,
            observation TEXT,
            feedback TEXT,
            rating INTEGER,
            led_to_sale BOOLEAN DEFAULT FALSE,
            send_notification BOOLEAN DEFAULT TRUE,
            notification_sent BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) DEFAULT 'scheduled',
            signature_requested BOOLEAN DEFAULT FALSE,
            signature_url TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_va_vehicle ON carpark_appointments(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_va_date ON carpark_appointments(scheduled_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_va_status ON carpark_appointments(status)')

    # ── Trip Log ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_trip_log (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
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
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vtl_vehicle ON carpark_trip_log(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vtl_date ON carpark_trip_log(trip_date)')

    # ── Publishing Platforms ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_publishing_platforms (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            platform_type VARCHAR(30),
            brand_scope VARCHAR(100),
            api_base_url TEXT,
            api_key_encrypted TEXT,
            dealer_account_id VARCHAR(100),
            website_url TEXT,
            icon_url TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            company_id INTEGER,
            config JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Vehicle Listings ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_listings (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            platform_id INTEGER NOT NULL REFERENCES carpark_publishing_platforms(id),
            external_listing_id VARCHAR(100),
            status VARCHAR(20) DEFAULT 'draft',
            published_at TIMESTAMP,
            expires_at TIMESTAMP,
            external_url TEXT,
            views INTEGER DEFAULT 0,
            inquiries INTEGER DEFAULT 0,
            last_sync TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vl_vehicle ON carpark_vehicle_listings(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vl_platform ON carpark_vehicle_listings(platform_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vl_status ON carpark_vehicle_listings(status)')

    # ── Pricing History ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_pricing_history (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            old_price DECIMAL(12,2),
            new_price DECIMAL(12,2),
            change_reason VARCHAR(100),
            rule_id INTEGER,
            changed_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vph_vehicle ON carpark_pricing_history(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vph_date ON carpark_pricing_history(created_at)')

    # ── Mileage History ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_mileage_history (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            recorded_date DATE NOT NULL,
            mileage_km INTEGER NOT NULL,
            source VARCHAR(30),
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vmh_vehicle ON carpark_mileage_history(vehicle_id)')

    # ── Pricing Rules ──
    cursor.execute('''
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
            action_type VARCHAR(20) NOT NULL,
            action_value DECIMAL(12,2),
            action_floor_type VARCHAR(20),
            action_floor_value DECIMAL(12,2),
            frequency VARCHAR(20) DEFAULT 'daily',
            last_executed TIMESTAMP,
            company_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Promotions ──
    cursor.execute('''
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
        )
    ''')

    # ── Status History ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_status_history (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            old_status VARCHAR(20),
            new_status VARCHAR(20) NOT NULL,
            old_location_id INTEGER,
            new_location_id INTEGER,
            notes TEXT,
            changed_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sh_vehicle ON carpark_status_history(vehicle_id)')

    # ── Modification History (field-level audit) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_modification_history (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            field_name VARCHAR(100) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by INTEGER,
            changed_by_name VARCHAR(200),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mh_vehicle ON carpark_modification_history(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mh_date ON carpark_modification_history(created_at)')

    # ── Publishing Sync Log ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_publishing_sync_log (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            platform_id INTEGER NOT NULL REFERENCES carpark_publishing_platforms(id),
            action VARCHAR(20) NOT NULL,
            request_payload JSONB,
            response_payload JSONB,
            http_status INTEGER,
            success BOOLEAN,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_psl_vehicle ON carpark_publishing_sync_log(vehicle_id)')

    # ── Permission column on roles table ──
    for col_name in ['can_access_carpark', 'can_edit_carpark', 'can_delete_carpark',
                      'can_access_carpark_mobile']:
        cursor.execute(f'''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'roles' AND column_name = '{col_name}') THEN
                    ALTER TABLE roles ADD COLUMN {col_name} BOOLEAN DEFAULT FALSE;
                    UPDATE roles SET {col_name} = TRUE WHERE name = 'Admin';
                END IF;
            END $$;
        ''')

    # ── Seed equipment categories ──
    cursor.execute('''
        INSERT INTO carpark_equipment_categories (name, name_ro, sort_order)
        SELECT * FROM (VALUES
            ('Audio & Connectivity', 'Audio & conectivitate', 1),
            ('Electronics', 'Electronice și sisteme', 2),
            ('Electric Vehicle', 'Mașini electrice', 3),
            ('Performance & Tuning', 'Performanță & tuning', 4),
            ('Safety', 'Siguranță', 5),
            ('Comfort', 'Confort', 6),
            ('Exterior', 'Exterior', 7),
            ('Interior', 'Interior', 8)
        ) AS v(name, name_ro, sort_order)
        WHERE NOT EXISTS (SELECT 1 FROM carpark_equipment_categories LIMIT 1)
    ''')

    conn.commit()
