"""Lightweight schema version tracking.

Wraps the existing IF NOT EXISTS init_schema pattern with a version table
so we can track which schema version each environment is running.

Usage (called automatically by database.init_db via init_schema.create_schema):
    from migrations.version_manager import run_pending_migrations
    run_pending_migrations(conn, cursor)
"""
import logging

logger = logging.getLogger(__name__)

# Increment this when a non-idempotent migration is added to init_schema
CURRENT_VERSION = 1


def ensure_version_table(cursor):
    """Create schema_version table if it doesn't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 0,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT schema_version_singleton CHECK (id = 1)
        )
    """)


def get_schema_version(cursor) -> int:
    """Return current schema version, or 0 if not set."""
    cursor.execute("SELECT version FROM schema_version WHERE id = 1")
    row = cursor.fetchone()
    return row[0] if row else 0


def set_schema_version(cursor, version: int):
    """Upsert the schema version record."""
    cursor.execute("""
        INSERT INTO schema_version (id, version, applied_at)
        VALUES (1, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, applied_at = NOW()
    """, (version,))


def run_pending_migrations(conn, cursor):
    """Ensure version table exists and record current schema version.

    Called after create_schema() completes. Since init_schema uses IF NOT EXISTS
    throughout, this is safe to call on any environment regardless of prior state.
    """
    ensure_version_table(cursor)
    current = get_schema_version(cursor)
    if current < CURRENT_VERSION:
        set_schema_version(cursor, CURRENT_VERSION)
        logger.info(f'Schema version updated: {current} → {CURRENT_VERSION}')
    else:
        logger.debug(f'Schema version current: {current}')
