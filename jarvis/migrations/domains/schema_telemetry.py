"""Telemetry schema: telemetry_events, telemetry_sessions tables."""


def create_schema_telemetry(conn, cursor):
    """Create telemetry tracking tables."""

    # ── Events table ─────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry_events (
            id              BIGSERIAL PRIMARY KEY,
            event_name      TEXT NOT NULL,
            event_category  TEXT NOT NULL DEFAULT 'interaction',
            session_id      TEXT NOT NULL,
            user_id         INTEGER REFERENCES users(id),
            company_id      INTEGER,
            role_name       TEXT,

            properties      JSONB NOT NULL DEFAULT '{}',

            page_path       TEXT,
            page_title      TEXT,
            referrer        TEXT,
            screen_width    SMALLINT,
            screen_height   SMALLINT,
            user_agent      TEXT,
            locale          TEXT,
            timezone        TEXT,

            client_ts       TIMESTAMPTZ NOT NULL,
            server_ts       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_events_user_ts
        ON telemetry_events (user_id, server_ts DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_events_name_ts
        ON telemetry_events (event_name, server_ts DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_events_session
        ON telemetry_events (session_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_events_page
        ON telemetry_events (page_path, server_ts DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_events_ts
        ON telemetry_events (server_ts DESC)
    ''')

    # ── Sessions table ───────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry_sessions (
            id              BIGSERIAL PRIMARY KEY,
            session_id      TEXT UNIQUE NOT NULL,
            user_id         INTEGER REFERENCES users(id),
            company_id      INTEGER,
            role_name       TEXT,

            started_at      TIMESTAMPTZ NOT NULL,
            last_seen_at    TIMESTAMPTZ NOT NULL,
            ended_at        TIMESTAMPTZ,
            duration_seconds INTEGER,

            page_views      INTEGER DEFAULT 0,
            event_count     INTEGER DEFAULT 0,
            entry_page      TEXT,
            exit_page       TEXT,

            screen_width    SMALLINT,
            screen_height   SMALLINT,
            user_agent      TEXT,
            locale          TEXT,
            timezone        TEXT,
            is_mobile       BOOLEAN DEFAULT FALSE,

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_sessions_user
        ON telemetry_sessions (user_id, started_at DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_telemetry_sessions_started
        ON telemetry_sessions (started_at DESC)
    ''')

    conn.commit()
