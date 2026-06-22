"""Voucher module schema."""
import logging

logger = logging.getLogger(__name__)


def create_schema_vouchers(conn, cursor):
    """Create vouchers table and indexes."""

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vouchers (
            id SERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES companies(id),
            voucher_code VARCHAR(20) NOT NULL UNIQUE,
            client_name VARCHAR(255) NOT NULL,
            contract_number VARCHAR(100) NOT NULL,
            car_vin VARCHAR(17) NOT NULL,
            validity_months INT NOT NULL,
            expires_at DATE,
            issued_at DATE,
            issued_by_user_id INT NOT NULL REFERENCES users(id),
            voucher_type VARCHAR(30) NOT NULL,
            value_lei NUMERIC(12,2),
            discount_code VARCHAR(100),
            discount_percentage NUMERIC(5,2),
            service_items JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending_approval',
            approval_request_id INT,
            approver_user_id INT REFERENCES users(id),
            redeemed_at TIMESTAMP,
            redeemed_by_user_id INT REFERENCES users(id),
            redemption_notes TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_voucher_status'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_status
                CHECK (status IN ('draft', 'pending_approval', 'approved', 'active', 'rejected', 'redeemed', 'expired'));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_voucher_type'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_type
                CHECK (voucher_type IN ('value', 'accessory_discount_code', 'accessory_percentage', 'service_items'));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_validity_months'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_validity_months
                CHECK (validity_months IN (1, 3, 6, 12, 24));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_car_vin_length'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_car_vin_length
                CHECK (char_length(car_vin) = 17);
            END IF;
        END $$;
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_company_id ON vouchers(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_issued_by ON vouchers(issued_by_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_expires_at ON vouchers(expires_at)')

    conn.commit()
    logger.info('Vouchers schema created/updated')
