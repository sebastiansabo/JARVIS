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

    # ---- Canonical category registry backfill (per-user notification prefs) ----
    # Idempotent + additive. (1) Rename legacy slugs that don't match what the
    # code emits — preserves each row's id and admin-tuned settings so their
    # settings (and per-user preferences) finally bind. (2) Upsert the full
    # canonical set as builtin, adding only genuinely-missing categories.
    # Lazy import (migration pattern) — categories.py is pure data, no DB import.
    from core.notifications.categories import CATEGORY_REGISTRY, LEGACY_SLUG_RENAMES

    for old_slug, new_slug in LEGACY_SLUG_RENAMES.items():
        # Only rename when the canonical slug doesn't already exist, so a re-run
        # (or a row seeded under the new slug) never hits the UNIQUE(slug) wall.
        cursor.execute(
            '''UPDATE push_notification_categories
               SET slug = %s, updated_at = NOW()
               WHERE slug = %s
                 AND NOT EXISTS (
                     SELECT 1 FROM push_notification_categories WHERE slug = %s
                 )''',
            (new_slug, old_slug, new_slug),
        )

    for slug, meta in CATEGORY_REGISTRY.items():
        # DO NOTHING preserves any existing row's admin-tuned is_active /
        # max_per_hour / priority; this only inserts missing categories.
        cursor.execute(
            '''INSERT INTO push_notification_categories
                   (slug, name, priority, android_channel_id, is_builtin)
               VALUES (%s, %s, %s, %s, TRUE)
               ON CONFLICT (slug) DO NOTHING''',
            (slug, meta['name'], meta.get('priority', 'normal'),
             meta.get('android_channel_id', 'default_notifications')),
        )

    conn.commit()
