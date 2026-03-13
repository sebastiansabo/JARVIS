"""Signatures schema: document_signatures, mobile_devices, checkin_nfc_tags."""
import psycopg2
import psycopg2.errors


def create_schema_signatures(conn, cursor):
    """Create document signatures and mobile app tables."""
    # ============== Document Signatures ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_signatures (
            id SERIAL PRIMARY KEY,
            document_type VARCHAR(50) NOT NULL,
            document_id INTEGER NOT NULL,
            signed_by INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            signed_at TIMESTAMP,
            ip_address VARCHAR(45),
            signature_image TEXT,
            document_hash VARCHAR(64),
            original_pdf_path TEXT,
            signed_pdf_path TEXT,
            callback_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_sig_status CHECK (status IN ('pending','signed','rejected','expired'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc_sig_doc ON document_signatures(document_type, document_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc_sig_signer ON document_signatures(signed_by, status)')

    conn.commit()

    # ============== Mobile App Tables ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mobile_devices (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            push_token TEXT NOT NULL UNIQUE,
            platform VARCHAR(20) NOT NULL DEFAULT 'unknown',
            device_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mobile_devices_user ON mobile_devices(user_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin_nfc_tags (
            id SERIAL PRIMARY KEY,
            tag_id TEXT NOT NULL UNIQUE,
            location_id INTEGER NOT NULL REFERENCES checkin_locations(id) ON DELETE CASCADE,
            label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nfc_tags_location ON checkin_nfc_tags(location_id)')

    conn.commit()
