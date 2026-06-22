"""Controlling BAB module — database schema."""


def _migrate_subtotal_refs(cursor):
    """Migrate subtotal_of strings to bab_subtotal_refs junction table (idempotent)."""
    cursor.execute("""
        SELECT id, company_id, subtotal_of FROM bab_report_config
        WHERE row_type = 'subtotal' AND subtotal_of IS NOT NULL AND subtotal_of != ''
    """)
    subtotals = cursor.fetchall()
    for sub in subtotals:
        sub_id, company_id, refs_str = sub['id'], sub['company_id'], sub['subtotal_of']
        refs = [r.strip() for r in refs_str.split(',') if r.strip()]
        for ref in refs:
            if '\u2192' in ref:
                parts = ref.split('\u2192', 1)
                group = parts[0].strip()
                label = parts[1].strip()
                cursor.execute("""
                    INSERT INTO bab_subtotal_refs (subtotal_row_id, indicator_row_id)
                    SELECT %s, id FROM bab_report_config
                    WHERE company_id = %s AND group_name = %s AND item_label = %s AND row_type = 'sum'
                    LIMIT 1
                    ON CONFLICT DO NOTHING
                """, (sub_id, company_id, group, label))
            else:
                # Legacy: match by label only
                cursor.execute("""
                    INSERT INTO bab_subtotal_refs (subtotal_row_id, indicator_row_id)
                    SELECT %s, id FROM bab_report_config
                    WHERE company_id = %s AND item_label = %s AND row_type = 'sum'
                    LIMIT 1
                    ON CONFLICT DO NOTHING
                """, (sub_id, company_id, ref))


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

    # ── bab_report_config — configurable report row definitions ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_report_config (
            id              SERIAL PRIMARY KEY,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            sort_order      INTEGER NOT NULL DEFAULT 0,
            kst             INTEGER NOT NULL,
            group_name      TEXT NOT NULL,
            item_label      TEXT NOT NULL,
            konto_list      TEXT NOT NULL,
            row_type        TEXT NOT NULL DEFAULT 'sum'
                              CHECK (row_type IN ('sum', 'subtotal')),
            subtotal_of     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_config_company ON bab_report_config(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_config_sort ON bab_report_config(company_id, sort_order)')

    # Add is_main_total column (idempotent)
    cursor.execute("ALTER TABLE bab_report_config ADD COLUMN IF NOT EXISTS is_main_total BOOLEAN NOT NULL DEFAULT FALSE")

    # ── bab_subtotal_refs — junction table for subtotal → indicator FK refs ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bab_subtotal_refs (
            subtotal_row_id  INTEGER NOT NULL REFERENCES bab_report_config(id) ON DELETE CASCADE,
            indicator_row_id INTEGER NOT NULL REFERENCES bab_report_config(id) ON DELETE CASCADE,
            PRIMARY KEY (subtotal_row_id, indicator_row_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_subtotal_refs_subtotal ON bab_subtotal_refs(subtotal_row_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bab_subtotal_refs_indicator ON bab_subtotal_refs(indicator_row_id)')

    _migrate_subtotal_refs(cursor)

    # Seed default config if empty
    cursor.execute('SELECT COUNT(*) as cnt FROM bab_report_config')
    if cursor.fetchone()['cnt'] == 0:
        default_rows = [
            # sort, kst, group, label, kontos, type, subtotal_of
            (10,  211, 'VW PKW INTERN (retail)',  'Venit Sales realizat',           '707111,707116',           'sum',      None),
            (20,  211, 'VW PKW INTERN (retail)',  'Marjă Brută realizată',          '707111,707116,607111',    'sum',      None),
            (30,  211, 'VW PKW INTERN (retail)',  'Bonus trimestrial (importator)', '609010',                  'sum',      None),
            (40,  211, 'VW PKW INTERN (retail)',  'Venit Test Drive',               '707112',                  'sum',      None),
            (50,  211, 'VW PKW INTERN (retail)',  'Marjă Test Drive',               '707112,607112',           'sum',      None),
            (60,  211, 'VW PKW INTERN (flote)',   'Venit Sales realizat',           '707110,707115',           'sum',      None),
            (70,  211, 'VW PKW INTERN (flote)',   'Marjă Brută realizată',          '707110,707115,607110',    'sum',      None),
            (80,  211, 'VW PKW INTERN (flote)',   'Bonus trimestrial (importator)', '609011',                  'sum',      None),
            (90,  211, 'Bonus & Discount',        'Bonus PFG',                      '708001',                  'sum',      None),
            (100, 211, 'Bonus & Discount',        'Discount accesorii',             '704315,902700',           'sum',      None),
            (110, 211, 'MARJA FINALĂ PKW',        'MARJA FINALĂ',                   '',                        'subtotal', 'Marjă Brută realizată,Bonus trimestrial (importator),Marjă Test Drive,Marjă Brută realizată,Bonus trimestrial (importator),Bonus PFG,Discount accesorii'),
            (120, 215, 'VW PKW EXTERN',           'Venit Sales realizat',           '707127',                  'sum',      None),
            (130, 215, 'VW PKW EXTERN',           'Marjă Brută realizată',          '707127,607127',           'sum',      None),
            (140, 215, 'VW PKW EXTERN',           'Bonus trimestrial (importator)', '609012',                  'sum',      None),
            (150, 215, 'VW PKW EXTERN',           'Marjă Totală Extern',            '',                        'subtotal', 'Marjă Brută realizată,Bonus trimestrial (importator)'),
        ]
        # Insert for all companies
        cursor.execute('SELECT id FROM companies')
        company_ids = [r['id'] for r in cursor.fetchall()]
        for cid in company_ids:
            for (sort, kst, group, label, kontos, rtype, sub_of) in default_rows:
                cursor.execute('''
                    INSERT INTO bab_report_config (company_id, sort_order, kst, group_name, item_label, konto_list, row_type, subtotal_of)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (cid, sort, kst, group, label, kontos, rtype, sub_of))

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
