"""Signatures schema: document_signatures, mobile_devices, checkin_nfc_tags,
push_notification_categories, push_rate_limit_log."""
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

    # ============== Push Notification Categories & Rate Limiting ==============
    # These two tables already exist in production (created ad-hoc) but had no
    # migration, so a schema rebuilt from scratch (fresh dev / staging restore)
    # was missing them and the push-manager admin endpoints would 500. Columns
    # mirror the SQL in core/notifications/repositories/notification_repository.py.

    # Column order / nullability / defaults mirror the production table exactly
    # (verified against the live DB) so a fresh rebuild is byte-for-byte compatible.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS push_notification_categories (
            id SERIAL PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            priority TEXT NOT NULL DEFAULT 'normal',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            max_per_hour INTEGER,
            ttl_seconds INTEGER,
            android_channel_id TEXT DEFAULT 'default_notifications',
            is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS push_rate_limit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category_slug TEXT NOT NULL,
            sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Serves the rate-limit hot query (WHERE user_id = %s AND category_slug = %s
    # AND sent_at > ...); name + definition match the existing production index.
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_push_rate_user_cat '
                   'ON push_rate_limit_log(user_id, category_slug, sent_at DESC)')

    conn.commit()
