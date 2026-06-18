"""Controlling BAB module — database schema."""


def create_schema_controlling_bab(conn, cursor):
    """Create BAB tables, indexes, and seed permissions."""

    # ── bab_uploads ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_uploads (
            id              SERIAL PRIMARY KEY,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            period_year     SMALLINT NOT NULL,
            period_month    SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
            filename        TEXT NOT NULL,
            uploaded_by     INTEGER NOT NULL REFERENCES users(id),
            uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            row_count       INTEGER,
            status          TEXT NOT NULL DEFAULT 'processing'
                              CHECK (status IN ('processing', 'ready', 'error')),
            error_msg       TEXT,
            locked_at       TIMESTAMPTZ,
            locked_by       INTEGER REFERENCES users(id),
            unlocked_at     TIMESTAMPTZ,
            unlocked_by     INTEGER REFERENCES users(id),
            import_count    SMALLINT NOT NULL DEFAULT 1,
            UNIQUE (company_id, period_year, period_month)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_uploads_company ON bab_uploads(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_uploads_period ON bab_uploads(period_year, period_month)')

    # ── bab_entries ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_entries (
            id              SERIAL PRIMARY KEY,
            upload_id       INTEGER NOT NULL REFERENCES bab_uploads(id) ON DELETE CASCADE,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            konto           INTEGER NOT NULL,
            konto_bez       TEXT,
            saldo1          NUMERIC(18,2) NOT NULL,
            kostenstelle    INTEGER NOT NULL,
            kst_bez1        TEXT
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_upload ON bab_entries(upload_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_konto ON bab_entries(upload_id, konto)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_kst ON bab_entries(upload_id, kostenstelle)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_entries_company ON bab_entries(company_id)')

    # ── bab_eur_rates ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_eur_rates (
            id              SERIAL PRIMARY KEY,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            period_year     SMALLINT NOT NULL,
            period_month    SMALLINT NOT NULL,
            eur_rate        NUMERIC(10,4) NOT NULL,
            set_by          INTEGER REFERENCES users(id),
            set_at          TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, period_year, period_month)
        )
    ''')

    # ── Permissions V2 ──
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'controlling'")
    if cursor.fetchone()['cnt'] == 0:
        controlling_perms = [
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'view', 'View', 'View BAB uploads and margin reports', False, 1),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'add', 'Add', 'Import and re-import BAB files', False, 2),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'edit', 'Edit', 'Set EUR exchange rate', False, 3),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'delete', 'Delete', 'Delete BAB uploads', False, 4),
            ('controlling', 'Controlling', 'bi-bar-chart', 'bab', 'BAB', 'lock', 'Lock', 'Lock and unlock periods', False, 5),
        ]
        for p in controlling_perms:
            cursor.execute('''
                INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
            ''', p)

        # Admin gets all
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Admin' AND p.module_key = 'controlling'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        # Manager gets view + add + edit
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Manager' AND p.module_key = 'controlling'
            AND p.action_key IN ('view', 'add', 'edit')
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        # User + Viewer get view only
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name IN ('User', 'Viewer') AND p.module_key = 'controlling'
            AND p.action_key = 'view'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

    conn.commit()
