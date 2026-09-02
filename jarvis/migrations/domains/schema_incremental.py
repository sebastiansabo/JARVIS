"""
Incremental schema migrations — columns, indexes, and tables added
after initial schema creation.

Contains idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS, CREATE TABLE IF NOT EXISTS,
CREATE INDEX IF NOT EXISTS, and seed INSERT ... ON CONFLICT DO NOTHING statements.

Called by:
  - init_schema.create_schema()  (fresh installs, ensures parity)
  - database.init_db()           (existing schemas on every startup)
"""
import importlib.util
import logging
import os

logger = logging.getLogger(__name__)


# ── Consent documents — mandatory first-login legal gate seed bodies ──
# Placeholder copy only — never binding legal text. Seeded is_active=FALSE so
# these never block real users until an admin finalizes wording and flips
# active. See the "Consent documents" incremental block below.
_SEED_DATA_USAGE = (
    "Pentru o comunicare directă a informațiilor dinspre companie către "
    "dumneavoastră și dinspre dumneavoastră către companie, Autoworld vă invită "
    "să utilizați aplicația JARVIS, autentificându-vă cu:\n"
    "• numele și prenumele\n"
    "• numărul de telefon\n"
    "• și/sau adresa de e-mail personală sau de firmă\n\n"
    "Aplicația NU urmărește și NU prelucrează date privind:\n"
    "• locația telefonului\n"
    "• conținutul din telefon\n"
    "• alte date personale în afara celor menționate mai sus\n\n"
    "Prin semnarea prezentului acord confirm că sunt de acord ca datele "
    "menționate să fie utilizate în cadrul aplicației JARVIS a Autoworld."
)
_SEED_GDPR = (
    "‹DE COMPLETAT DPO›\n\n"
    "Notă de informare privind prelucrarea datelor cu caracter personal\n"
    "Temei legal: Regulamentul (UE) 2016/679 (GDPR) și Legea nr. 190/2018.\n\n"
    "1. Operator de date: ‹denumire, CUI, sediu›\n"
    "2. Categoriile de date prelucrate: ‹…›\n"
    "3. Scopul prelucrării: ‹…›\n"
    "4. Durata de stocare: ‹…›\n"
    "5. Drepturile persoanei vizate: acces, rectificare, ștergere, "
    "restricționare, portabilitate, opoziție, retragerea consimțământului, "
    "plângere la ANSPDCP.\n"
    "6. Date de contact DPO: ‹…›"
)
_SEED_NDA = (
    "‹DE COMPLETAT — juridic›\n\n"
    "Acord de confidențialitate (NDA)\n\n"
    "1. Părțile\n"
    "2. Definiția informațiilor confidențiale\n"
    "3. Obligațiile de confidențialitate\n"
    "4. Durata obligațiilor\n"
    "5. Consecințele încălcării\n"
    "6. Legea aplicabilă și jurisdicția"
)


def _recompute_bilant_formula_values(cursor):
    """Recompute all formula_rd values in bilant_results.

    After OMF→B numbering migration, row numbers shifted but stored values
    were stale. This recomputes formula_rd sums in dependency order and
    updates verification strings with detailed row amounts.
    """
    cursor.execute("SELECT DISTINCT generation_id FROM bilant_results WHERE formula_rd IS NOT NULL")
    gen_ids = [r['generation_id'] for r in cursor.fetchall()]
    if not gen_ids:
        return

    updated = 0
    for gen_id in gen_ids:
        cursor.execute("""
            SELECT id, nr_rd, value, formula_rd
            FROM bilant_results WHERE generation_id = %s
            ORDER BY CASE
                WHEN nr_rd = '35a' THEN 35.5
                WHEN nr_rd ~ '^[0-9]+$' THEN CAST(nr_rd AS FLOAT)
                ELSE 999 END
        """, (gen_id,))
        all_rows = cursor.fetchall()
        values = {r['nr_rd']: float(r['value'] or 0) for r in all_rows if r['nr_rd']}

        for row in all_rows:
            if not row['formula_rd']:
                continue
            expr = row['formula_rd']
            total = 0.0
            sign = 1
            token = ''
            parts = []
            for ch in expr + '+':
                if ch.isdigit() or ch.isalpha():
                    token += ch
                elif ch in '+-':
                    if token:
                        row_num = token.lstrip('0') or '0'
                        val = values.get(row_num, 0)
                        total += sign * val
                        pfx = '+' if sign == 1 else '-'
                        parts.append(f"{pfx} rd.{row_num} ({val:,.2f})")
                        token = ''
                    sign = 1 if ch == '+' else -1
            if row['nr_rd']:
                values[row['nr_rd']] = total
            if parts and parts[0].startswith('+ '):
                parts[0] = parts[0][2:]
            verification = ' '.join(parts) + f" = {total:,.2f}"
            old_val = float(row['value'] or 0)
            if abs(total - old_val) > 0.001:
                cursor.execute(
                    "UPDATE bilant_results SET value = %s, verification = %s WHERE id = %s",
                    (total, verification, row['id'])
                )
                updated += 1
            else:
                cursor.execute(
                    "UPDATE bilant_results SET verification = %s WHERE id = %s",
                    (verification, row['id'])
                )
    if updated:
        logger.info('Recomputed %d stale formula_rd values across %d generation(s)', updated, len(gen_ids))


def _seed_service_contract_configs(conn, cursor):
    """Seed the Service courtesy-car contract config for every active (company, brand).

    Idempotent via ON CONFLICT DO NOTHING — existing rows (including any an
    admin has already hand-edited) are left untouched; only missing
    (company_id, brand_id, 'service') combos get inserted.

    Templates are loaded by file path via importlib rather than
    `import foi_parcurs...` because importing the foi_parcurs package triggers
    foi_parcurs/__init__.py -> routes -> repositories -> database, which is a
    circular import when called from database.init_db(). Any failure here
    (missing file, bad SQL, etc.) must never break schema init, so the whole
    thing is wrapped in try/except.

    IMPORTANT: when create_schema() runs inside ONE shared transaction
    (conn.autocommit is False, committed only at the very end), a bare
    conn.rollback() here would discard ALL prior uncommitted schema-init work
    in this run. So the INSERT is scoped inside a SAVEPOINT and only that
    SAVEPOINT is rolled back on failure — the outer schema-creation
    transaction is left intact, and NO mid-schema conn.commit() is introduced.

    The SAVEPOINT is used only when there is an open transaction to scope it
    to: database.init_db() gets its connection from get_db(), which sets
    conn.autocommit = True, and SAVEPOINT is invalid outside a transaction
    block (psycopg2 raises NoActiveSqlTransaction). In autocommit mode there
    is no shared transaction to protect — each statement commits on its own
    and a failed INSERT only rolls back itself — so the SAVEPOINT is skipped.
    """
    try:
        tpl_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'foi_parcurs',
            'services', 'service_contract_templates.py'
        )
        spec = importlib.util.spec_from_file_location('_svc_contract_tpl', tpl_path)
        tpl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tpl)
        face, terms = tpl.SERVICE_CONTRACT_FACE, tpl.SERVICE_CONTRACT_TERMS

        use_savepoint = not getattr(conn, 'autocommit', False)
        if use_savepoint:
            cursor.execute('SAVEPOINT svc_contract_seed')
        try:
            cursor.execute('''
                INSERT INTO fp_contract_configs
                    (company_id, brand_id, document_type, title, body_template, general_conditions, is_active, updated_at)
                SELECT cb.company_id, cb.brand_id, 'service', %s, %s, %s, TRUE, NOW()
                FROM company_brands cb
                JOIN brands b ON b.id = cb.brand_id
                WHERE cb.is_active = TRUE AND b.is_active = TRUE
                ON CONFLICT (company_id, brand_id, document_type) DO NOTHING
            ''', ('Contract închiriere autovehicul – Mașini de curtoazie', face, terms))
            if use_savepoint:
                cursor.execute('RELEASE SAVEPOINT svc_contract_seed')
        except Exception:
            if use_savepoint:
                cursor.execute('ROLLBACK TO SAVEPOINT svc_contract_seed')
            raise
    except Exception:
        logger.exception('Failed to seed fp_contract_configs (service) — continuing schema init')


def _seed_document_types(conn, cursor):
    """Seed the user-defined document-type registry (fp_document_types).

    Two idempotent inserts, both ON CONFLICT (company_id, key) DO NOTHING so
    re-runs and admin edits are preserved:
      1. A fixed 'sales' default row per company (label 'Vânzări', not rental,
         no template — Sales uses the legacy legal PDF).
      2. One 'service' row per company, collapsing the per-(company, brand)
         fp_contract_configs 'service' rows (templates are identical/tag-based —
         take the lowest-id active one) into a single rental type.

    Same SAVEPOINT discipline as _seed_service_contract_configs: only the seed is
    rolled back on failure, never the outer schema-init transaction.
    """
    try:
        use_savepoint = not getattr(conn, 'autocommit', False)
        if use_savepoint:
            cursor.execute('SAVEPOINT doctype_seed')
        try:
            # 1. Fixed sales default per company.
            cursor.execute('''
                INSERT INTO fp_document_types
                    (company_id, key, label, is_rental, is_active, is_default, sort_order, updated_at)
                SELECT c.id, 'sales', 'Vânzări', FALSE, TRUE, TRUE, 0, NOW()
                FROM companies c
                ON CONFLICT (company_id, key) DO NOTHING
            ''')
            # 2. Collapse existing per-brand service templates into one rental type.
            cursor.execute('''
                INSERT INTO fp_document_types
                    (company_id, key, label, title, body_template, general_conditions,
                     is_rental, is_active, is_default, sort_order, updated_at)
                SELECT DISTINCT ON (cc.company_id)
                       cc.company_id, 'service', 'Mașini de curtoazie',
                       cc.title, cc.body_template, cc.general_conditions,
                       TRUE, TRUE, FALSE, 1, NOW()
                FROM fp_contract_configs cc
                WHERE cc.document_type = 'service' AND cc.is_active = TRUE
                ORDER BY cc.company_id, cc.id
                ON CONFLICT (company_id, key) DO NOTHING
            ''')
            if use_savepoint:
                cursor.execute('RELEASE SAVEPOINT doctype_seed')
        except Exception:
            if use_savepoint:
                cursor.execute('ROLLBACK TO SAVEPOINT doctype_seed')
            raise
    except Exception:
        logger.exception('Failed to seed fp_document_types — continuing schema init')


def _seed_rental_tariffs(conn, cursor):
    """Seed the SHARETOO rental tariff scheme for Autoworld PREMIUM (company 11).

    Idempotent (ON CONFLICT DO NOTHING everywhere) and company-scoped, so
    re-runs and every other company are untouched; admins edit afterwards. Seed
    data is loaded by file path (importlib) to avoid the foi_parcurs package
    circular import when called from database.init_db(). Same SAVEPOINT
    discipline as _seed_document_types — only the seed rolls back on failure."""
    try:
        seed_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'foi_parcurs',
            'services', 'rental_tariff_seed.py'
        )
        spec = importlib.util.spec_from_file_location('_rental_tariff_seed', seed_path)
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        co = seed.SHARETOO_COMPANY_ID

        use_savepoint = not getattr(conn, 'autocommit', False)
        if use_savepoint:
            cursor.execute('SAVEPOINT rental_tariff_seed')
        try:
            for label, mn, mx, so in seed.SHARETOO_INTERVALS:
                cursor.execute(
                    '''INSERT INTO fp_rental_intervals
                           (company_id, label, min_days, max_days, sort_order)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (company_id, min_days) DO NOTHING''',
                    (co, label, mn, mx, so))
            cursor.execute(
                'SELECT id, min_days FROM fp_rental_intervals WHERE company_id=%s', (co,))
            iv_by_min = {r['min_days']: r['id'] for r in cursor.fetchall()}
            mins_in_order = [mn for (_, mn, _, _) in seed.SHARETOO_INTERVALS]

            for idx, (name, note, fr, ekm, prices) in enumerate(seed.SHARETOO_CATEGORIES):
                cursor.execute(
                    '''INSERT INTO fp_rental_categories
                           (company_id, name, models_note, franchise_eur,
                            extra_km_eur, sort_order, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                       ON CONFLICT (company_id, name) DO NOTHING''',
                    (co, name, note, fr, ekm, idx))
                cursor.execute(
                    'SELECT id FROM fp_rental_categories WHERE company_id=%s AND name=%s',
                    (co, name))
                cat_id = cursor.fetchone()['id']
                for mn, price in zip(mins_in_order, prices):
                    cursor.execute(
                        '''INSERT INTO fp_rental_category_prices
                               (company_id, category_id, interval_id, eur_per_day)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (company_id, category_id, interval_id) DO NOTHING''',
                        (co, cat_id, iv_by_min[mn], price))
            if use_savepoint:
                cursor.execute('RELEASE SAVEPOINT rental_tariff_seed')
        except Exception:
            if use_savepoint:
                cursor.execute('ROLLBACK TO SAVEPOINT rental_tariff_seed')
            raise
    except Exception:
        logger.exception('Failed to seed rental tariffs — continuing schema init')


def create_schema_incremental(conn, cursor):
    """Run all incremental column/index/table migrations.

    All statements are idempotent — safe to run on any existing schema.
    """
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'auto_tag_rules' AND column_name = 'match_mode') THEN
                ALTER TABLE auto_tag_rules ADD COLUMN match_mode VARCHAR(10) NOT NULL DEFAULT 'all';
            END IF;
        END $$;
    ''')
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_projects' AND column_name = 'company_ids') THEN
                ALTER TABLE mkt_projects ADD COLUMN company_ids INTEGER[] DEFAULT '{}';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_projects' AND column_name = 'brand_ids') THEN
                ALTER TABLE mkt_projects ADD COLUMN brand_ids INTEGER[] DEFAULT '{}';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_projects' AND column_name = 'department_ids') THEN
                ALTER TABLE mkt_projects ADD COLUMN department_ids INTEGER[] DEFAULT '{}';
            END IF;
        END $$;
    ''')
    # Add can_access_crm permission to roles (if not exists)
    cursor.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'roles' AND column_name = 'can_access_crm') THEN
                ALTER TABLE roles ADD COLUMN can_access_crm BOOLEAN DEFAULT FALSE;
                UPDATE roles SET can_access_crm = TRUE WHERE name = 'Admin';
            END IF;
        END $$;
    """)
    # CRM CRUD + export permissions
    cursor.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'roles' AND column_name = 'can_edit_crm') THEN
                ALTER TABLE roles ADD COLUMN can_edit_crm BOOLEAN DEFAULT FALSE;
                ALTER TABLE roles ADD COLUMN can_delete_crm BOOLEAN DEFAULT FALSE;
                ALTER TABLE roles ADD COLUMN can_export_crm BOOLEAN DEFAULT FALSE;
                UPDATE roles SET can_edit_crm = TRUE, can_delete_crm = TRUE, can_export_crm = TRUE WHERE name = 'Admin';
            END IF;
        END $$;
    """)
    # Ensure 'approved' invoice status exists
    cursor.execute('''
        INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order, is_active, min_role)
        SELECT 'invoice_status', 'approved', 'Approved', '#22c55e', 5, TRUE, 'Viewer'
        WHERE NOT EXISTS (
            SELECT 1 FROM dropdown_options WHERE dropdown_type = 'invoice_status' AND value = 'approved'
        )
    ''')
    # Create mkt_project_files if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_files (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            file_name TEXT NOT NULL,
            file_type TEXT,
            mime_type TEXT,
            file_size INTEGER,
            storage_uri TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL REFERENCES users(id),
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_files_project ON mkt_project_files(project_id)')
    # Create mkt_project_events if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_events (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES hr.events(id) ON DELETE CASCADE,
            notes TEXT,
            linked_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_project_events_unique UNIQUE (project_id, event_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_events_project ON mkt_project_events(project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_events_event ON mkt_project_events(event_id)')
    # KPI linking tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_budget_lines (
            id SERIAL PRIMARY KEY,
            project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            budget_line_id INTEGER NOT NULL REFERENCES mkt_budget_lines(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_kpi_budget_lines_unique UNIQUE (project_kpi_id, budget_line_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_bl_kpi ON mkt_kpi_budget_lines(project_kpi_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_bl_line ON mkt_kpi_budget_lines(budget_line_id)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_dependencies (
            id SERIAL PRIMARY KEY,
            project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            depends_on_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'input',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_kpi_deps_unique UNIQUE (project_kpi_id, depends_on_kpi_id),
            CONSTRAINT mkt_kpi_deps_no_self CHECK (project_kpi_id != depends_on_kpi_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deps_kpi ON mkt_kpi_dependencies(project_kpi_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deps_dep ON mkt_kpi_dependencies(depends_on_kpi_id)')
    # Seed default mkt_project approval flow if missing
    cursor.execute('''
        INSERT INTO approval_flows (name, slug, entity_type, is_active, created_by)
        SELECT 'Marketing Project Approval', 'mkt-project-approval', 'mkt_project', TRUE, 1
        WHERE NOT EXISTS (
            SELECT 1 FROM approval_flows WHERE slug = 'mkt-project-approval'
        )
    ''')
    cursor.execute('''
        INSERT INTO approval_steps (flow_id, name, step_order, approver_type, notify_on_pending, notify_on_decision)
        SELECT f.id, 'Selected Approver', 1, 'context_approver', TRUE, TRUE
        FROM approval_flows f
        WHERE f.slug = 'mkt-project-approval'
        AND NOT EXISTS (
            SELECT 1 FROM approval_steps s WHERE s.flow_id = f.id
        )
    ''')
    # Smart notification state table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS smart_notification_state (
            id SERIAL PRIMARY KEY,
            alert_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            last_alerted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_value NUMERIC(15,4),
            CONSTRAINT smart_notif_state_unique UNIQUE (alert_type, entity_type, entity_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_smart_notif_state_type ON smart_notification_state(alert_type)')
    # AI6: line_items + invoice_type columns on invoices
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'invoices' AND column_name = 'line_items') THEN
                ALTER TABLE invoices ADD COLUMN line_items JSONB;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'invoices' AND column_name = 'invoice_type') THEN
                ALTER TABLE invoices ADD COLUMN invoice_type TEXT DEFAULT 'standard';
            END IF;
        END $$;
    ''')
    cursor.execute('''
        INSERT INTO notification_settings (setting_key, setting_value) VALUES
            ('smart_alerts_enabled', 'true'),
            ('smart_kpi_alerts_enabled', 'true'),
            ('smart_budget_alerts_enabled', 'true'),
            ('smart_invoice_anomaly_enabled', 'true'),
            ('smart_efactura_backlog_enabled', 'true'),
            ('smart_efactura_backlog_threshold', '50'),
            ('smart_alert_cooldown_hours', '24'),
            ('smart_invoice_anomaly_sigma', '2')
        ON CONFLICT (setting_key) DO NOTHING
    ''')
    # M-KPI: role column on mkt_kpi_budget_lines
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_kpi_budget_lines' AND column_name = 'role') THEN
                ALTER TABLE mkt_kpi_budget_lines ADD COLUMN role TEXT NOT NULL DEFAULT 'input';
            END IF;
        END $$;
    ''')
    # M-KPI: currency column on mkt_project_kpis
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_project_kpis' AND column_name = 'currency') THEN
                ALTER TABLE mkt_project_kpis ADD COLUMN currency TEXT DEFAULT 'RON';
            END IF;
        END $$;
    ''')
    # Drop hardcoded member role CHECK — roles now from global roles table
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
                       WHERE table_name = 'mkt_project_members' AND constraint_name = 'mkt_members_role_check') THEN
                ALTER TABLE mkt_project_members DROP CONSTRAINT mkt_members_role_check;
            END IF;
        END $$;
    ''')
    # Seed marketing permissions_v2 if not present
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'marketing'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'view', 'View', 'View marketing projects', TRUE, 1),
            ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'create', 'Create', 'Create marketing projects', TRUE, 2),
            ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'edit', 'Edit', 'Edit marketing projects', TRUE, 3),
            ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'delete', 'Delete', 'Delete marketing projects', TRUE, 4),
            ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'approve', 'Submit for Approval', 'Submit projects for approval', TRUE, 5),
            ('marketing', 'Marketing', 'bi-megaphone', 'budget', 'Budgets', 'view', 'View', 'View budget allocations', TRUE, 6),
            ('marketing', 'Marketing', 'bi-megaphone', 'budget', 'Budgets', 'edit', 'Edit', 'Edit budgets and record spend', TRUE, 7),
            ('marketing', 'Marketing', 'bi-megaphone', 'kpi', 'KPIs', 'view', 'View', 'View KPI targets and actuals', TRUE, 8),
            ('marketing', 'Marketing', 'bi-megaphone', 'kpi', 'KPIs', 'edit', 'Edit', 'Set KPI targets and record values', TRUE, 9),
            ('marketing', 'Marketing', 'bi-megaphone', 'report', 'Reports', 'view', 'View', 'View marketing reports', TRUE, 10)
        ''')
        cursor.execute('SELECT id, name FROM roles')
        for role in cursor.fetchall():
            rn = role['name']
            cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'marketing'")
            for p in cursor.fetchall():
                scope = 'deny'
                if rn == 'Admin':
                    scope = 'all'
                elif rn == 'Manager':
                    scope = 'department' if p['action_key'] != 'delete' else 'deny'
                elif p['action_key'] in ('view', 'create'):
                    scope = 'own'
                if scope != 'deny':
                    cursor.execute('''
                        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role['id'], p['id'], scope))
    # M-KPI: benchmarks column on definitions
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_kpi_definitions' AND column_name = 'benchmarks') THEN
                ALTER TABLE mkt_kpi_definitions ADD COLUMN benchmarks JSONB;
            END IF;
        END $$;
    ''')
    # M-KPI: migrate abstract roles to formula variable names
    cursor.execute('''
        UPDATE mkt_kpi_budget_lines kb
        SET role = COALESCE(
            (SELECT split_part(kd.formula, ' ', 1)
             FROM mkt_project_kpis pk
             JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
             WHERE pk.id = kb.project_kpi_id AND kd.formula IS NOT NULL),
            'input')
        WHERE kb.role IN ('numerator', 'denominator', 'input')
        AND EXISTS (
            SELECT 1 FROM mkt_project_kpis pk
            JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
            WHERE pk.id = kb.project_kpi_id AND kd.formula IS NOT NULL)
    ''')
    cursor.execute('''
        UPDATE mkt_kpi_dependencies kd_link
        SET role = COALESCE(
            (SELECT dep_def.slug
             FROM mkt_project_kpis dep_pk
             JOIN mkt_kpi_definitions dep_def ON dep_def.id = dep_pk.kpi_definition_id
             WHERE dep_pk.id = kd_link.depends_on_kpi_id),
            'input')
        WHERE kd_link.role IN ('numerator', 'denominator', 'input')
        AND EXISTS (
            SELECT 1 FROM mkt_project_kpis pk
            JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
            WHERE pk.id = kd_link.project_kpi_id AND kd.formula IS NOT NULL)
    ''')
    # KPI show_on_overview flag
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_project_kpis' AND column_name = 'show_on_overview') THEN
                ALTER TABLE mkt_project_kpis ADD COLUMN show_on_overview BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    ''')
    # Campaign Simulator benchmarks table + seed
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_sim_benchmarks (
            id SERIAL PRIMARY KEY,
            channel_key TEXT NOT NULL,
            channel_label TEXT NOT NULL,
            funnel_stage TEXT NOT NULL,
            month_index INTEGER NOT NULL,
            cpc NUMERIC(10,4) NOT NULL,
            cvr_lead NUMERIC(8,6) NOT NULL,
            cvr_car NUMERIC(8,6) NOT NULL DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_sim_bench_stage CHECK (funnel_stage IN ('awareness','consideration','conversion')),
            CONSTRAINT mkt_sim_bench_month CHECK (month_index BETWEEN 1 AND 3),
            CONSTRAINT mkt_sim_bench_unique UNIQUE (channel_key, funnel_stage, month_index)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_sim_bench_stage ON mkt_sim_benchmarks(funnel_stage)')
    cursor.execute("SELECT COUNT(*) as cnt FROM mkt_sim_benchmarks")
    if cursor.fetchone()['cnt'] == 0:
        from .schema_marketing import _seed_sim_benchmarks
        _seed_sim_benchmarks(cursor)
    # OKR tables for marketing projects
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_objectives (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_objectives_project ON mkt_objectives(project_id)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_key_results (
            id SERIAL PRIMARY KEY,
            objective_id INTEGER NOT NULL REFERENCES mkt_objectives(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            target_value NUMERIC(15,4) NOT NULL DEFAULT 100,
            current_value NUMERIC(15,4) NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'number',
            linked_kpi_id INTEGER REFERENCES mkt_project_kpis(id) ON DELETE SET NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_key_results_objective ON mkt_key_results(objective_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_key_results_kpi ON mkt_key_results(linked_kpi_id)')
    # OKR permissions
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'marketing' AND entity_key = 'okr'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            ('marketing', 'Marketing', 'bi-megaphone', 'okr', 'OKR', 'view', 'View', 'View objectives & key results', TRUE, 11),
            ('marketing', 'Marketing', 'bi-megaphone', 'okr', 'OKR', 'edit', 'Edit', 'Edit objectives & key results', TRUE, 12)
        ''')
        cursor.execute('SELECT id, name FROM roles')
        for role in cursor.fetchall():
            rn = role['name']
            cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'marketing' AND entity_key = 'okr'")
            for p in cursor.fetchall():
                scope = 'deny'
                if rn == 'Admin':
                    scope = 'all'
                elif rn == 'Manager':
                    scope = 'department'
                elif p['action_key'] == 'view':
                    scope = 'own'
                elif p['action_key'] == 'edit':
                    scope = 'own'
                if scope != 'deny':
                    cursor.execute('''
                        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role['id'], p['id'], scope))
    # Document signatures table
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
    # requires_signature flag on approval_flows
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'approval_flows' AND column_name = 'requires_signature') THEN
                ALTER TABLE approval_flows ADD COLUMN requires_signature BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    ''')
    # Stakeholder approval: approval_mode column on mkt_projects
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'mkt_projects' AND column_name = 'approval_mode') THEN
                ALTER TABLE mkt_projects ADD COLUMN approval_mode TEXT NOT NULL DEFAULT 'any';
            END IF;
        END $$;
    ''')
    # AI: context_window column on ai_agent.model_configs
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ai_agent')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema = 'ai_agent'
                               AND table_name = 'model_configs'
                               AND column_name = 'context_window') THEN
                ALTER TABLE ai_agent.model_configs ADD COLUMN context_window INTEGER DEFAULT 200000;
                UPDATE ai_agent.model_configs SET context_window = 200000 WHERE model_name LIKE 'claude-%';
                UPDATE ai_agent.model_configs SET context_window = 128000 WHERE model_name = 'gpt-4-turbo';
                UPDATE ai_agent.model_configs SET context_window = 16385 WHERE model_name = 'gpt-3.5-turbo';
                UPDATE ai_agent.model_configs SET context_window = 32768 WHERE model_name IN ('mixtral-8x7b-32768', 'gemini-pro');
                UPDATE ai_agent.model_configs SET context_window = 128000 WHERE model_name = 'llama-3.3-70b-versatile';
            END IF;
        END $$;
    ''')
    # ── Bilant (Balance Sheet) Generator tables ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            is_default BOOLEAN DEFAULT FALSE,
            version INTEGER DEFAULT 1,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_templates_company ON bilant_templates(company_id)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_template_rows (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES bilant_templates(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            nr_rd TEXT,
            formula_ct TEXT,
            formula_rd TEXT,
            row_type TEXT DEFAULT 'data',
            is_bold BOOLEAN DEFAULT FALSE,
            indent_level INTEGER DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_tpl_rows_template ON bilant_template_rows(template_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_tpl_rows_order ON bilant_template_rows(template_id, sort_order)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_metric_configs (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES bilant_templates(id) ON DELETE CASCADE,
            metric_key TEXT NOT NULL,
            metric_label TEXT NOT NULL,
            nr_rd TEXT NOT NULL,
            metric_group TEXT DEFAULT 'summary',
            sort_order INTEGER DEFAULT 0,
            CONSTRAINT bilant_metric_unique UNIQUE (template_id, metric_key)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_metric_cfg_template ON bilant_metric_configs(template_id)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_generations (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES bilant_templates(id),
            company_id INTEGER NOT NULL REFERENCES companies(id),
            period_label TEXT,
            period_date DATE,
            status TEXT DEFAULT 'completed',
            error_message TEXT,
            original_filename TEXT,
            generated_by INTEGER NOT NULL REFERENCES users(id),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_company ON bilant_generations(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_date ON bilant_generations(period_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_template ON bilant_generations(template_id)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_results (
            id SERIAL PRIMARY KEY,
            generation_id INTEGER NOT NULL REFERENCES bilant_generations(id) ON DELETE CASCADE,
            template_row_id INTEGER REFERENCES bilant_template_rows(id) ON DELETE SET NULL,
            nr_rd TEXT,
            description TEXT,
            formula_ct TEXT,
            formula_rd TEXT,
            value NUMERIC(15,2) DEFAULT 0,
            verification TEXT,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_results_gen ON bilant_results(generation_id)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_metrics (
            id SERIAL PRIMARY KEY,
            generation_id INTEGER NOT NULL REFERENCES bilant_generations(id) ON DELETE CASCADE,
            metric_key TEXT NOT NULL,
            metric_label TEXT NOT NULL,
            metric_group TEXT NOT NULL,
            value NUMERIC(15,4),
            interpretation TEXT,
            percent NUMERIC(7,2),
            CONSTRAINT bilant_metric_gen_unique UNIQUE (generation_id, metric_key)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_metrics_gen ON bilant_metrics(generation_id)')
    # ── Chart of Accounts (Plan de Conturi) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chart_of_accounts (
            id SERIAL PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            account_class SMALLINT NOT NULL,
            account_type TEXT NOT NULL DEFAULT 'synthetic',
            parent_code TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chart_of_accounts_unique UNIQUE (code, company_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_coa_class ON chart_of_accounts(account_class)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_coa_parent ON chart_of_accounts(parent_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_coa_company ON chart_of_accounts(company_id)')
    # Seed standard Romanian chart of accounts (global, no company)
    cursor.execute("SELECT COUNT(*) as cnt FROM chart_of_accounts WHERE company_id IS NULL")
    if cursor.fetchone()['cnt'] == 0:
        from .schema_bilant import _seed_chart_of_accounts
        _seed_chart_of_accounts(cursor)
    # Seed default Bilant template
    cursor.execute("SELECT COUNT(*) as cnt FROM bilant_templates")
    if cursor.fetchone()['cnt'] == 0:
        from .schema_bilant import _seed_bilant_default_template
        _seed_bilant_default_template(cursor)
    # Dynamic metrics: add new columns to bilant_metric_configs
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'bilant_metric_configs' AND column_name = 'formula_expr') THEN
                ALTER TABLE bilant_metric_configs ADD COLUMN formula_expr TEXT;
                ALTER TABLE bilant_metric_configs ADD COLUMN display_format TEXT DEFAULT 'currency';
                ALTER TABLE bilant_metric_configs ADD COLUMN interpretation TEXT;
                ALTER TABLE bilant_metric_configs ADD COLUMN threshold_good NUMERIC(12,4);
                ALTER TABLE bilant_metric_configs ADD COLUMN threshold_warning NUMERIC(12,4);
                ALTER TABLE bilant_metric_configs ADD COLUMN structure_side TEXT;
                ALTER TABLE bilant_metric_configs ALTER COLUMN nr_rd DROP NOT NULL;
            END IF;
        END $$;
    ''')
    # Seed ratio/derived/structure configs for default template if missing
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM bilant_metric_configs mc
        JOIN bilant_templates t ON t.id = mc.template_id
        WHERE t.is_default = TRUE AND mc.metric_group = 'ratio'
    """)
    if cursor.fetchone()['cnt'] == 0:
        from .schema_bilant import _seed_bilant_dynamic_metrics
        _seed_bilant_dynamic_metrics(cursor)
    # Fix corrupted seed data from original export
    cursor.execute("""
        UPDATE bilant_template_rows SET formula_rd = NULL
        WHERE formula_rd ~ '^[a-z]'
    """)
    cursor.execute("""
        UPDATE bilant_template_rows SET row_type = 'data', is_bold = FALSE, indent_level = 1
        WHERE nr_rd IN ('19', '21', '95') AND row_type = 'total'
    """)
    # ── Migrate default bilant template from OMF to column B numbering ──
    # Check if migration needed: dividende row still has OMF nr_rd='36'
    cursor.execute("""
        SELECT tr.id FROM bilant_template_rows tr
        JOIN bilant_templates t ON t.id = tr.template_id
        WHERE t.is_default = TRUE AND tr.nr_rd = '36'
          AND tr.description LIKE '%%dividende%%'
        LIMIT 1
    """)
    if cursor.fetchone():
        logger.info('Migrating default bilant template from OMF to column B numbering')
        cursor.execute("SELECT id FROM bilant_templates WHERE is_default = TRUE LIMIT 1")
        tpl = cursor.fetchone()
        if tpl:
            tid = tpl['id']
            # 1. Dividende row: OMF 36 → B '35a'
            cursor.execute("""
                UPDATE bilant_template_rows SET nr_rd = '35a'
                WHERE template_id = %s AND nr_rd = '36'
                  AND description LIKE '%%dividende%%'
            """, (tid,))
            # 2. All rows with integer nr_rd >= 37: decrement by 1
            cursor.execute(r"""
                UPDATE bilant_template_rows
                SET nr_rd = CAST(CAST(nr_rd AS INTEGER) - 1 AS TEXT)
                WHERE template_id = %s
                  AND nr_rd ~ '^\d+$' AND CAST(nr_rd AS INTEGER) >= 37
            """, (tid,))
            # 3. Update formula_rd values (explicit by sort_order for reliability)
            _formula_rd_b = {
                43: '31+32+33+34+35+35a', 47: '37+38', 49: '30+36+39+40',
                50: '43+44', 63: '45+46+47+48+49+50+51+52',
                64: '41+43-53-70-73-76', 65: '25+44+54',
                75: '56+57+58+59+60+61+62+63', 80: '65+66+67',
                82: '70+71', 85: '73+74', 88: '76+77',
                92: '69+72+75+78', 101: '80+81+82+83+84',
                108: '88+89+90',
                118: '85+86+87+91-92+93-94+95-96+97-98-99',
                121: '100+101+102',
            }
            for so, frd in _formula_rd_b.items():
                cursor.execute("""
                    UPDATE bilant_template_rows SET formula_rd = %s
                    WHERE template_id = %s AND sort_order = %s AND formula_rd IS NOT NULL
                """, (frd, tid, so))
            # 4. Update metric_configs nr_rd to correct B values
            _metric_b = {
                'active_imobilizate': '25', 'active_circulante': '41',
                'stocuri': '30', 'creante': '36', 'disponibilitati': '40',
                'datorii_termen_scurt': '53', 'datorii_termen_lung': '64',
                'capitaluri_proprii': '100', 'capital_social': '80',
                'struct_active_imobilizate': '25', 'struct_stocuri': '30',
                'struct_creante': '36', 'struct_disponibilitati': '40',
                'struct_capitaluri_proprii': '100', 'struct_datorii_scurt': '53',
                'struct_datorii_lung': '64',
            }
            for mkey, b_nr in _metric_b.items():
                cursor.execute("""
                    UPDATE bilant_metric_configs SET nr_rd = %s
                    WHERE template_id = %s AND metric_key = %s
                """, (b_nr, tid, mkey))
            # 5. Update existing bilant_results from OMF to B numbering
            #    Dividende results: nr_rd '36' with dividende description → '35a'
            cursor.execute("""
                UPDATE bilant_results SET nr_rd = '35a'
                WHERE nr_rd = '36' AND description LIKE '%%dividende%%'
            """)
            #    All results with integer nr_rd >= 37: decrement by 1
            cursor.execute(r"""
                UPDATE bilant_results
                SET nr_rd = CAST(CAST(nr_rd AS INTEGER) - 1 AS TEXT)
                WHERE nr_rd ~ '^\d+$' AND CAST(nr_rd AS INTEGER) >= 37
            """)
            #    Update formula_rd in results too
            cursor.execute("""
                UPDATE bilant_results br
                SET formula_rd = tr.formula_rd
                FROM bilant_template_rows tr
                WHERE br.template_row_id = tr.id AND tr.formula_rd IS NOT NULL
            """)
            # 6. Recompute formula_rd values (they're stale after nr_rd shift)
            _recompute_bilant_formula_values(cursor)
            logger.info('Bilant template migrated to column B numbering')

    # ── Repair stale formula_rd values (runs if OMF→B migration already applied) ──
    cursor.execute("""
        SELECT DISTINCT br.generation_id
        FROM bilant_results br
        WHERE br.nr_rd = '35a'
          AND EXISTS (
              SELECT 1 FROM bilant_results br2
              WHERE br2.generation_id = br.generation_id
                AND br2.formula_rd IS NOT NULL
          )
    """)
    repair_gens = [r['generation_id'] for r in cursor.fetchall()]
    if repair_gens:
        _recompute_bilant_formula_values(cursor)

    # ── AI Agent learning tables (message_feedback + learned_knowledge) ──
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'ai_agent' AND table_name = 'message_feedback'
        )
    """)
    if not cursor.fetchone()['exists']:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_agent.message_feedback (
                id SERIAL PRIMARY KEY,
                message_id INTEGER NOT NULL REFERENCES ai_agent.messages(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                feedback_type VARCHAR(10) NOT NULL CHECK (feedback_type IN ('positive', 'negative')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, user_id)
            )
        """)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_message ON ai_agent.message_feedback(message_id)')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_positive ON ai_agent.message_feedback(feedback_type) WHERE feedback_type = 'positive'")
        # learned_knowledge with optional vector column
        cursor.execute("""
            DO $$
            BEGIN
                CREATE TABLE IF NOT EXISTS ai_agent.learned_knowledge (
                    id SERIAL PRIMARY KEY,
                    pattern TEXT NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    source_count INTEGER DEFAULT 1,
                    confidence FLOAT DEFAULT 0.5,
                    embedding vector(1536),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            EXCEPTION WHEN undefined_object THEN
                CREATE TABLE IF NOT EXISTS ai_agent.learned_knowledge (
                    id SERIAL PRIMARY KEY,
                    pattern TEXT NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    source_count INTEGER DEFAULT 1,
                    confidence FLOAT DEFAULT 0.5,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            END $$;
        """)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_active ON ai_agent.learned_knowledge(is_active, confidence DESC)')
        logger.info('Created AI agent learning tables (message_feedback, learned_knowledge)')

    # ── CRM / Car Sales Database tables ──
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'crm_import_batches'
        )
    """)
    if not cursor.fetchone()['exists']:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crm_import_batches (
                id SERIAL PRIMARY KEY,
                source_type VARCHAR(20) NOT NULL,
                filename TEXT NOT NULL,
                uploaded_by INTEGER REFERENCES users(id),
                total_rows INTEGER DEFAULT 0,
                new_rows INTEGER DEFAULT 0,
                updated_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                new_clients INTEGER DEFAULT 0,
                matched_clients INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'processing',
                error_log JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_import_source ON crm_import_batches(source_type)')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crm_clients (
                id SERIAL PRIMARY KEY,
                display_name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                client_type VARCHAR(20) DEFAULT 'person',
                phone TEXT,
                phone_raw TEXT,
                email TEXT,
                street TEXT,
                city TEXT,
                region TEXT,
                country TEXT DEFAULT 'Romania',
                company_name TEXT,
                responsible TEXT,
                source_flags JSONB DEFAULT '{}',
                merged_into_id INTEGER REFERENCES crm_clients(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_phone ON crm_clients(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_email ON crm_clients(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_merged ON crm_clients(merged_into_id)')
        cursor.execute("""
            DO $$ BEGIN
                CREATE EXTENSION IF NOT EXISTS pg_trgm;
            EXCEPTION WHEN OTHERS THEN NULL;
            END $$;
        """)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_name ON crm_clients USING gin (name_normalized gin_trgm_ops)')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crm_deals (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES crm_clients(id) ON DELETE SET NULL,
                source VARCHAR(5) NOT NULL,
                dealer_code TEXT, dealer_name TEXT, branch TEXT,
                dossier_number TEXT, order_number TEXT,
                contract_date DATE, order_date DATE, delivery_date DATE,
                invoice_date DATE, registration_date DATE, entry_date DATE,
                brand TEXT, model_name TEXT, model_code TEXT, model_year INTEGER, order_year INTEGER,
                body_code TEXT, vin TEXT, engine_code TEXT, fuel_type TEXT,
                color TEXT, color_code TEXT, door_count INTEGER, vehicle_type TEXT,
                list_price NUMERIC(12,2), purchase_price_net NUMERIC(12,2),
                sale_price_net NUMERIC(12,2), gross_profit NUMERIC(12,2),
                discount_value NUMERIC(12,2), other_costs NUMERIC(12,2),
                gw_gross_value NUMERIC(12,2),
                dossier_status TEXT, order_status TEXT, contract_status TEXT,
                sales_person TEXT, buyer_name TEXT, buyer_address TEXT,
                owner_name TEXT, owner_address TEXT, customer_group TEXT,
                registration_number TEXT,
                vehicle_specs JSONB DEFAULT '{}',
                import_batch_id INTEGER REFERENCES crm_import_batches(id),
                source_row_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_client ON crm_deals(client_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_source ON crm_deals(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_vin ON crm_deals(vin)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_brand ON crm_deals(brand)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_dossier ON crm_deals(source, dossier_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_contract ON crm_deals(contract_date DESC)')
        # Add can_access_crm permission to roles
        cursor.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'roles' AND column_name = 'can_access_crm') THEN
                    ALTER TABLE roles ADD COLUMN can_access_crm BOOLEAN DEFAULT FALSE;
                    UPDATE roles SET can_access_crm = TRUE WHERE name = 'Admin';
                END IF;
            END $$;
        """)
        logger.info('Created CRM tables (crm_import_batches, crm_clients, crm_deals)')

    # CRM: nr_reg column on crm_clients
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'crm_clients' AND column_name = 'nr_reg') THEN
                ALTER TABLE crm_clients ADD COLUMN nr_reg TEXT;
            END IF;
        END $$;
    ''')
    # CRM: is_blacklisted column on crm_clients
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'crm_clients' AND column_name = 'is_blacklisted') THEN
                ALTER TABLE crm_clients ADD COLUMN is_blacklisted BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    ''')
    # CRM: cnp (personal numeric code) on crm_clients — captured when creating a
    # client from a driving-license scan on the mobile Test Drive form.
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'crm_clients' AND column_name = 'cnp') THEN
                ALTER TABLE crm_clients ADD COLUMN cnp TEXT;
            END IF;
        END $$;
    ''')
    # ── DMS (Document Management System) tables ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            icon TEXT DEFAULT 'bi-folder',
            color TEXT DEFAULT '#6c757d',
            description TEXT,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'dms_categories_slug_company'
            ) THEN
                ALTER TABLE dms_categories ADD CONSTRAINT dms_categories_slug_company
                    UNIQUE (slug, company_id);
            END IF;
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_categories_company ON dms_categories(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_categories_active ON dms_categories(is_active, sort_order)')

    # Category permissions (NULL = all roles can see)
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE dms_categories ADD COLUMN allowed_role_ids INTEGER[] DEFAULT NULL;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_documents (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            category_id INTEGER REFERENCES dms_categories(id) ON DELETE SET NULL,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'draft',
            parent_id INTEGER REFERENCES dms_documents(id) ON DELETE CASCADE,
            relationship_type TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            doc_number TEXT,
            doc_date DATE,
            expiry_date DATE,
            notify_user_id INTEGER REFERENCES users(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            CONSTRAINT dms_doc_status CHECK (status IN ('draft','active','archived')),
            CONSTRAINT dms_doc_parent_child CHECK (
                (parent_id IS NULL AND relationship_type IS NULL) OR
                (parent_id IS NOT NULL AND relationship_type IS NOT NULL)
            )
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_category ON dms_documents(category_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_company ON dms_documents(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_parent ON dms_documents(parent_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_status ON dms_documents(status) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_created ON dms_documents(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_expiry ON dms_documents(expiry_date) WHERE expiry_date IS NOT NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_doc_number ON dms_documents(doc_number) WHERE doc_number IS NOT NULL')

    # Add columns if upgrading from earlier schema
    for col, coldef in [
        ('doc_number', 'TEXT'),
        ('doc_date', 'DATE'),
        ('expiry_date', 'DATE'),
        ('notify_user_id', 'INTEGER REFERENCES users(id)'),
        ('visibility', "TEXT DEFAULT 'all'"),
        ('allowed_role_ids', 'INTEGER[] DEFAULT NULL'),
        ('allowed_user_ids', 'INTEGER[] DEFAULT NULL'),
    ]:
        cursor.execute(f'''
            DO $$ BEGIN
                ALTER TABLE dms_documents ADD COLUMN {col} {coldef};
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_files (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
            file_name TEXT NOT NULL,
            file_type TEXT,
            mime_type TEXT,
            file_size INTEGER,
            storage_type TEXT NOT NULL DEFAULT 'drive',
            storage_uri TEXT NOT NULL,
            drive_file_id TEXT,
            uploaded_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT dms_file_storage CHECK (storage_type IN ('drive','local'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_files_document ON dms_files(document_id)')

    # ── dms_relationship_types ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_relationship_types (
            id SERIAL PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            icon TEXT DEFAULT 'bi-file-earmark',
            color TEXT DEFAULT '#6c757d',
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Drop old hardcoded CHECK on relationship_type (now dynamic via table)
    cursor.execute('''
        ALTER TABLE dms_documents DROP CONSTRAINT IF EXISTS dms_doc_rel_type
    ''')

    # ── Signature columns on dms_documents (Phase A) ──
    for col, coldef in [
        ('signature_status', 'TEXT'),
        ('signature_request_id', 'TEXT'),
        ('signature_requested_at', 'TIMESTAMP'),
        ('signature_completed_at', 'TIMESTAMP'),
        ('signature_provider', 'TEXT'),
    ]:
        cursor.execute(f'''
            DO $$ BEGIN
                ALTER TABLE dms_documents ADD COLUMN {col} {coldef};
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_dms_documents_sig_status
        ON dms_documents(signature_status)
        WHERE signature_status IS NOT NULL
    ''')

    # ── document_parties (Phase B) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_parties (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
            party_role TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'company',
            entity_id INTEGER,
            entity_name TEXT NOT NULL,
            entity_details JSONB DEFAULT '{}'::jsonb,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_document_parties_doc ON document_parties(document_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_document_parties_entity ON document_parties(entity_type, entity_id)')

    # ── dms_party_roles (configurable party roles) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_party_roles (
            id SERIAL PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── suppliers (master table) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            supplier_type TEXT NOT NULL DEFAULT 'company',
            cui TEXT,
            j_number TEXT,
            address TEXT,
            city TEXT,
            county TEXT,
            nr_reg_com TEXT,
            bank_account TEXT,
            iban TEXT,
            bank_name TEXT,
            phone TEXT,
            email TEXT,
            company_id INTEGER REFERENCES companies(id),
            created_by INTEGER REFERENCES users(id),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_suppliers_company ON suppliers(company_id)')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers USING gin (name gin_trgm_ops)")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_suppliers_active ON suppliers(is_active)')
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'suppliers' AND column_name = 'county') THEN
                ALTER TABLE suppliers ADD COLUMN county TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'suppliers' AND column_name = 'nr_reg_com') THEN
                ALTER TABLE suppliers ADD COLUMN nr_reg_com TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'suppliers' AND column_name = 'contact_name') THEN
                ALTER TABLE suppliers ADD COLUMN contact_name TEXT;
                ALTER TABLE suppliers ADD COLUMN contact_function TEXT;
                ALTER TABLE suppliers ADD COLUMN contact_email TEXT;
                ALTER TABLE suppliers ADD COLUMN contact_phone TEXT;
                ALTER TABLE suppliers ADD COLUMN owner_name TEXT;
                ALTER TABLE suppliers ADD COLUMN owner_function TEXT;
                ALTER TABLE suppliers ADD COLUMN owner_email TEXT;
                ALTER TABLE suppliers ADD COLUMN owner_phone TEXT;
            END IF;
        END $$;
    ''')

    # ── document_wml + chunks (Phase D) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_wml (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
            file_id INTEGER NOT NULL REFERENCES dms_files(id) ON DELETE CASCADE,
            raw_text TEXT,
            structured_json JSONB,
            extraction_method TEXT DEFAULT 'mammoth',
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_wml_document ON document_wml(document_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_wml_file ON document_wml(file_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_wml_chunks (
            id SERIAL PRIMARY KEY,
            wml_id INTEGER NOT NULL REFERENCES document_wml(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            heading TEXT,
            content TEXT NOT NULL,
            token_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_wml_chunks_wml ON document_wml_chunks(wml_id)')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wml_chunks_fts ON document_wml_chunks USING GIN (to_tsvector('simple', content))")

    # ── DMS Drive Sync ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_drive_sync (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
            drive_folder_id TEXT NOT NULL,
            drive_folder_url TEXT,
            last_synced_at TIMESTAMP,
            sync_status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id)
        )
    ''')

    # ── DMS Folders (hierarchical organization) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_folders (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT 'bi-folder',
            color TEXT DEFAULT '#6c757d',
            parent_id INTEGER REFERENCES dms_folders(id) ON DELETE CASCADE,
            path TEXT NOT NULL DEFAULT '/',
            depth INTEGER NOT NULL DEFAULT 0,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by INTEGER NOT NULL REFERENCES users(id),
            inherit_permissions BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            UNIQUE(parent_id, name, company_id)
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_folders_path ON dms_folders(path text_pattern_ops)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_folders_parent ON dms_folders(parent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_folders_company ON dms_folders(company_id)")

    # ── DMS Folder ACL (per-user/role permissions) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_folder_acl (
            id SERIAL PRIMARY KEY,
            folder_id INTEGER NOT NULL REFERENCES dms_folders(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
            can_view BOOLEAN DEFAULT FALSE,
            can_add BOOLEAN DEFAULT FALSE,
            can_edit BOOLEAN DEFAULT FALSE,
            can_delete BOOLEAN DEFAULT FALSE,
            can_manage BOOLEAN DEFAULT FALSE,
            granted_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT acl_grantee_check CHECK (
                (user_id IS NOT NULL AND role_id IS NULL) OR
                (user_id IS NULL AND role_id IS NOT NULL)
            )
        )
    ''')
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dms_folder_acl_user
        ON dms_folder_acl(folder_id, user_id) WHERE user_id IS NOT NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dms_folder_acl_role
        ON dms_folder_acl(folder_id, role_id) WHERE role_id IS NOT NULL
    """)

    # ── DMS Audit Log (change tracking) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_audit_log (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            changes JSONB,
            user_id INTEGER NOT NULL REFERENCES users(id),
            company_id INTEGER NOT NULL REFERENCES companies(id),
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_audit_entity ON dms_audit_log(entity_type, entity_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_audit_user ON dms_audit_log(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_audit_created ON dms_audit_log(created_at DESC)")

    # ── DMS Module Links (universal cross-module linking) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dms_module_links (
            id SERIAL PRIMARY KEY,
            link_type TEXT NOT NULL,
            folder_id INTEGER REFERENCES dms_folders(id) ON DELETE CASCADE,
            document_id INTEGER REFERENCES dms_documents(id) ON DELETE CASCADE,
            module TEXT NOT NULL,
            module_entity_id INTEGER NOT NULL,
            linked_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT link_source_check CHECK (
                (link_type = 'folder' AND folder_id IS NOT NULL AND document_id IS NULL) OR
                (link_type = 'document' AND document_id IS NOT NULL AND folder_id IS NULL)
            )
        )
    ''')
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dms_module_links_folder
        ON dms_module_links(folder_id, module, module_entity_id)
        WHERE folder_id IS NOT NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dms_module_links_document
        ON dms_module_links(document_id, module, module_entity_id)
        WHERE document_id IS NOT NULL
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_module_links_module ON dms_module_links(module, module_entity_id)")

    # ── Add folder_id to dms_documents ──
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE dms_documents ADD COLUMN folder_id INTEGER REFERENCES dms_folders(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dms_documents_folder ON dms_documents(folder_id)")

    # ── Add Google Drive sync columns to dms_folders ──
    for col_def in [
        "drive_folder_id TEXT",
        "drive_folder_url TEXT",
        "drive_synced_at TIMESTAMP",
    ]:
        col_name = col_def.split()[0]
        cursor.execute(f"""
            DO $$ BEGIN
                ALTER TABLE dms_folders ADD COLUMN {col_def};
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        """)

    # Seed default relationship types
    cursor.execute('SELECT COUNT(*) as cnt FROM dms_relationship_types')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO dms_relationship_types (slug, label, icon, color, sort_order) VALUES
            ('annex', 'Anexe', 'bi-paperclip', '#0d6efd', 1),
            ('deviz', 'Devize', 'bi-calculator', '#fd7e14', 2),
            ('proof', 'Dovezi / Foto', 'bi-camera', '#198754', 3),
            ('other', 'Altele', 'bi-file-earmark', '#6c757d', 4)
        ''')

    # Seed default party roles
    cursor.execute('SELECT COUNT(*) as cnt FROM dms_party_roles')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO dms_party_roles (slug, label, sort_order) VALUES
            ('emitent', 'Emitent', 1),
            ('beneficiar', 'Beneficiar', 2),
            ('semnatar', 'Semnatar', 3),
            ('furnizor', 'Furnizor', 4),
            ('client', 'Client', 5),
            ('other', 'Altele', 6)
        ''')

    # Seed default DMS categories (global — company_id NULL)
    cursor.execute('SELECT COUNT(*) as cnt FROM dms_categories')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO dms_categories (name, slug, icon, color, description, company_id, sort_order, is_active) VALUES
            ('Contracte', 'contracte', 'bi-file-earmark-text', '#0d6efd', 'Contracte si acorduri', NULL, 1, TRUE),
            ('Facturi', 'facturi', 'bi-receipt', '#198754', 'Facturi furnizori si clienti', NULL, 2, TRUE),
            ('Autorizatii', 'autorizatii', 'bi-shield-check', '#6f42c1', 'Autorizatii si licente', NULL, 3, TRUE),
            ('Devize', 'devize', 'bi-calculator', '#fd7e14', 'Devize si estimari de cost', NULL, 4, TRUE),
            ('Documente HR', 'documente-hr', 'bi-person-badge', '#d63384', 'Documente resurse umane', NULL, 5, TRUE),
            ('Altele', 'altele', 'bi-folder2-open', '#6c757d', 'Alte documente', NULL, 6, TRUE)
        ''')

    # Seed DMS permissions
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'dms'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'view', 'View', 'View documents', TRUE, 1),
            ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'create', 'Create', 'Upload and create documents', TRUE, 2),
            ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'edit', 'Edit', 'Edit documents and metadata', TRUE, 3),
            ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'delete', 'Delete', 'Delete documents', TRUE, 4),
            ('dms', 'Documents', 'bi-folder', 'category', 'Categories', 'view', 'View', 'View document categories', FALSE, 5),
            ('dms', 'Documents', 'bi-folder', 'category', 'Categories', 'manage', 'Manage', 'Create and edit categories', FALSE, 6)
        ''')
        # Grant DMS permissions to existing roles
        cursor.execute('SELECT id, name FROM roles')
        roles_for_dms = cursor.fetchall()
        cursor.execute("SELECT id, is_scope_based, action_key FROM permissions_v2 WHERE module_key = 'dms'")
        dms_perms = cursor.fetchall()
        for role in roles_for_dms:
            for perm in dms_perms:
                if role['name'] == 'Admin':
                    scope, granted = 'all', True
                elif role['name'] == 'Manager':
                    scope, granted = ('all' if perm['is_scope_based'] else 'all'), True
                elif role['name'] == 'User':
                    if perm['action_key'] in ('view', 'create', 'edit'):
                        scope = 'own' if perm['is_scope_based'] else 'own'
                        granted = True
                    else:
                        scope, granted = 'deny', False
                else:
                    if perm['action_key'] == 'view':
                        scope, granted = ('own' if perm['is_scope_based'] else 'own'), True
                    else:
                        scope, granted = 'deny', False
                cursor.execute('''
                    INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                ''', (role['id'], perm['id'], scope, granted))

    # Seed supplier permissions (incremental — safe to re-run)
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'dms' AND entity_key = 'supplier'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            ('dms', 'Documents', 'bi-folder', 'supplier', 'Suppliers', 'view', 'View', 'View supplier list', FALSE, 7),
            ('dms', 'Documents', 'bi-folder', 'supplier', 'Suppliers', 'manage', 'Manage', 'Manage supplier list', FALSE, 8)
        ''')
        # Grant supplier permissions to Admin + Manager
        cursor.execute('SELECT id, name FROM roles')
        roles_for_sup = cursor.fetchall()
        cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'dms' AND entity_key = 'supplier'")
        sup_perms = cursor.fetchall()
        for role in roles_for_sup:
            for perm in sup_perms:
                if role['name'] in ('Admin', 'Manager'):
                    scope, granted = 'all', True
                else:
                    scope = 'all' if perm['action_key'] == 'view' else 'deny'
                    granted = perm['action_key'] == 'view'
                cursor.execute('''
                    INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                ''', (role['id'], perm['id'], scope, granted))

    # Seed folder permissions (incremental — safe to re-run)
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'dms' AND entity_key = 'folder'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            ('dms', 'Documents', 'bi-folder', 'folder', 'Folders', 'view', 'View', 'View folders', FALSE, 9),
            ('dms', 'Documents', 'bi-folder', 'folder', 'Folders', 'create', 'Create', 'Create folders', FALSE, 10),
            ('dms', 'Documents', 'bi-folder', 'folder', 'Folders', 'edit', 'Edit', 'Edit folders and settings', FALSE, 11),
            ('dms', 'Documents', 'bi-folder', 'folder', 'Folders', 'delete', 'Delete', 'Delete folders', FALSE, 12),
            ('dms', 'Documents', 'bi-folder', 'folder', 'Folders', 'manage_acl', 'Manage ACL', 'Manage folder permissions', FALSE, 13)
        ''')
        cursor.execute('SELECT id, name FROM roles')
        roles_for_folders = cursor.fetchall()
        cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'dms' AND entity_key = 'folder'")
        folder_perms = cursor.fetchall()
        for role in roles_for_folders:
            for perm in folder_perms:
                if role['name'] in ('Admin', 'Manager'):
                    scope, granted = 'all', True
                elif role['name'] == 'User':
                    if perm['action_key'] in ('view', 'create'):
                        scope, granted = 'all', True
                    else:
                        scope, granted = 'deny', False
                else:
                    scope = 'all' if perm['action_key'] == 'view' else 'deny'
                    granted = perm['action_key'] == 'view'
                cursor.execute('''
                    INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                ''', (role['id'], perm['id'], scope, granted))

    # ── Auto-seed company root folders ──
    # Each company gets a root folder named after the company
    cursor.execute('''
        INSERT INTO dms_folders (name, company_id, created_by, path, depth, sort_order)
        SELECT c.company, c.id, 1, '/', 0, c.id
        FROM companies c
        WHERE NOT EXISTS (
            SELECT 1 FROM dms_folders f
            WHERE f.company_id = c.id AND f.parent_id IS NULL AND f.depth = 0
        )
    ''')
    # Fix paths for newly inserted root folders (set path = /{id}/)
    cursor.execute('''
        UPDATE dms_folders
        SET path = '/' || id || '/'
        WHERE depth = 0 AND path = '/'
    ''')

    # ── Menu items: add 'archived' status + sync from registry ──
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE module_menu_items DROP CONSTRAINT IF EXISTS module_menu_items_status_check;
            ALTER TABLE module_menu_items ADD CONSTRAINT module_menu_items_status_check
                CHECK (status IN ('active', 'coming_soon', 'hidden', 'archived'));
        EXCEPTION WHEN others THEN NULL;
        END $$;
    """)
    # Sync menu items from registry (single source of truth)
    from core.settings.menus.registry import sync_menu_items
    sync_menu_items(cursor)

    # ── Leave-permit modify/cancel: allow cancellation_pending + cancelled statuses ──
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE form_submissions DROP CONSTRAINT IF EXISTS form_submissions_status_check;
            ALTER TABLE form_submissions ADD CONSTRAINT form_submissions_status_check
                CHECK (status IN ('new', 'read', 'flagged', 'approved', 'rejected',
                                  'pending_approval', 'cancellation_pending', 'cancelled'));
        EXCEPTION WHEN others THEN NULL;
        END $$;
    """)

    # ── BioStar tables (needed for GPS check-in + pontaje) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS biostar_employees (
            id SERIAL PRIMARY KEY,
            biostar_user_id VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            phone VARCHAR(50),
            user_group_id VARCHAR(50),
            user_group_name VARCHAR(255),
            department VARCHAR(255),
            title VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            photo_url TEXT,
            schedule_start VARCHAR(10),
            schedule_end VARCHAR(10),
            lunch_break_minutes INTEGER DEFAULT 60,
            working_hours INTEGER DEFAULT 8,
            is_blacklisted BOOLEAN NOT NULL DEFAULT FALSE,
            last_synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_employees_mapped ON biostar_employees(mapped_jarvis_user_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS biostar_punch_logs (
            id SERIAL PRIMARY KEY,
            biostar_event_id VARCHAR(100) NOT NULL,
            biostar_user_id VARCHAR(50) NOT NULL,
            event_datetime TIMESTAMP NOT NULL,
            event_type VARCHAR(50) DEFAULT 'DEVICE_PUNCH',
            direction VARCHAR(10),
            device_id VARCHAR(50),
            device_name VARCHAR(255),
            door_id VARCHAR(50),
            door_name VARCHAR(255),
            temperature NUMERIC(4,1),
            raw_data JSONB,
            synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_biostar_punch_dedup
        ON biostar_punch_logs(biostar_event_id, (event_datetime::date))''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_punch_user ON biostar_punch_logs(biostar_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_punch_datetime ON biostar_punch_logs(event_datetime)')

    # ── Checkin locations ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin_locations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            latitude NUMERIC(10,7) NOT NULL,
            longitude NUMERIC(10,7) NOT NULL,
            allowed_radius_meters INTEGER NOT NULL DEFAULT 50,
            allowed_ips JSONB NOT NULL DEFAULT '[]'::JSONB,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            auto_checkout_radius_meters INTEGER NOT NULL DEFAULT 200
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_checkin_locations_active ON checkin_locations(is_active)')

    # CarPark: two-level cost hierarchy (cost lines → cost entries)
    # Guard: only run if carpark_vehicles exists (requires schema_carpark to have run first)
    cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='carpark_vehicles')")
    if cursor.fetchone()['exists']:
        _create_carpark_incremental(conn, cursor)

    _create_schema_incremental_continued(conn, cursor)


def _create_carpark_incremental(conn, cursor):
    """Carpark incremental migrations — split out to guard on carpark_vehicles existence."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vehicle_cost_lines (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            cost_type VARCHAR(50) NOT NULL,
            description TEXT,
            planned_amount DECIMAL(12,2) DEFAULT 0,
            spent_amount DECIMAL(12,2) DEFAULT 0,
            currency VARCHAR(3) DEFAULT 'EUR',
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'carpark_vehicle_costs' AND column_name = 'cost_line_id') THEN
                ALTER TABLE carpark_vehicle_costs ADD COLUMN cost_line_id INTEGER REFERENCES carpark_vehicle_cost_lines(id) ON DELETE SET NULL;
                CREATE INDEX idx_carpark_costs_line ON carpark_vehicle_costs(cost_line_id);
            END IF;
        END $$;
    ''')

    # Pricing rules: project link + target mode
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'carpark_pricing_rules' AND column_name = 'project_id') THEN
                ALTER TABLE carpark_pricing_rules
                    ADD COLUMN project_id INTEGER REFERENCES mkt_projects(id) ON DELETE SET NULL;
                ALTER TABLE carpark_pricing_rules
                    ADD COLUMN target_mode VARCHAR(10) NOT NULL DEFAULT 'criteria';
                CREATE INDEX idx_cpr_project ON carpark_pricing_rules(project_id);
            END IF;
        END $$;
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_pricing_rule_vehicles (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER NOT NULL REFERENCES carpark_pricing_rules(id) ON DELETE CASCADE,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            added_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rule_id, vehicle_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_pending_price_changes (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER NOT NULL REFERENCES carpark_pricing_rules(id) ON DELETE CASCADE,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            old_price DECIMAL(12,2) NOT NULL,
            new_price DECIMAL(12,2) NOT NULL,
            reduction DECIMAL(12,2) NOT NULL,
            floor_hit BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            approval_request_id INTEGER,
            applied_at TIMESTAMP,
            applied_by INTEGER,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        INSERT INTO approval_flows (name, slug, entity_type, is_active, created_by)
        SELECT 'CarPark Price Approval', 'carpark-price-approval', 'carpark_price_change', TRUE, 1
        WHERE NOT EXISTS (SELECT 1 FROM approval_flows WHERE slug = 'carpark-price-approval')
    ''')
    cursor.execute('''
        INSERT INTO approval_steps (flow_id, name, step_order, approver_type, notify_on_pending, notify_on_decision)
        SELECT f.id, 'Selected Approver', 1, 'context_approver', TRUE, TRUE
        FROM approval_flows f WHERE f.slug = 'carpark-price-approval'
        AND NOT EXISTS (SELECT 1 FROM approval_steps s WHERE s.flow_id = f.id)
    ''')

    # ── CarPark Dispo: sales-lifecycle columns on carpark_vehicles ──
    for _col, _type in [
        ('intake_pv_date', 'DATE'), ('supplier_payment_date', 'DATE'),
        ('sale_type', 'VARCHAR(30)'), ('buyer_name', 'VARCHAR(200)'),
        ('gw_file_number', 'VARCHAR(50)'), ('is_impus', 'BOOLEAN DEFAULT FALSE'),
        ('missing_civ', 'BOOLEAN DEFAULT FALSE'), ('stock_removed', 'BOOLEAN DEFAULT FALSE'),
        ('stock_removed_date', 'DATE'),
        # Fabrication date at year+month precision (stored as the 1st of the
        # chosen month) — backs the "Date of fabrication" form field;
        # year_of_manufacture is kept in sync client-side for the existing
        # fleet year-range filters.
        ('manufacture_date', 'DATE'),
        # Inter-company transfer: marks a vehicle that landed here via a
        # transfer FROM another AutoWorld sibling company (see
        # carpark_transfers below — this column is the fast "is this a
        # transferred-in car" flag on the vehicle row itself, the transfers
        # table is the full log with price/date/document).
        ('transferred_from_company_id', 'INTEGER'),
    ]:
        cursor.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_name='carpark_vehicles' AND column_name='{_col}') THEN
                ALTER TABLE carpark_vehicles ADD COLUMN {_col} {_type};
              END IF;
            END $$;
        """)

    # ── CarPark specs: fuel-tank / battery capacity + consumption norms ──
    # Mirrors the Driving-Park (fp_vehicles) capacity/norm model so the
    # car-profile form can capture battery capacity for EV/hybrid/PHEV and the
    # fuel-consumption norm for combustion cars. Rendered conditionally by
    # fuel_type in the CarPark VehicleForm (usesFuelTank / usesBattery).
    for _col, _type in [
        ('fuel_tank_capacity_liters', 'NUMERIC'),
        ('battery_capacity_kwh', 'NUMERIC'),
        ('norma_combustibil', 'NUMERIC'),
        ('norma_energie', 'NUMERIC'),
    ]:
        cursor.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_name='carpark_vehicles' AND column_name='{_col}') THEN
                ALTER TABLE carpark_vehicles ADD COLUMN {_col} {_type};
              END IF;
            END $$;
        """)

    # ── CarPark specs: van / utilitară cargo details ──
    # Shown conditionally when body_type = 'van' in the CarPark VehicleForm.
    # (max_weight_kg / MMA already exists on the base carpark_vehicles table.)
    for _col, _type in [
        ('payload_kg', 'INTEGER'),
        ('cargo_volume_m3', 'NUMERIC'),
        ('cargo_length_mm', 'INTEGER'),
        ('cargo_width_mm', 'INTEGER'),
        ('cargo_height_mm', 'INTEGER'),
        ('euro_pallets', 'INTEGER'),
    ]:
        cursor.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_name='carpark_vehicles' AND column_name='{_col}') THEN
                ALTER TABLE carpark_vehicles ADD COLUMN {_col} {_type};
              END IF;
            END $$;
        """)

    # ── CarPark specs: interior upholstery material (Autovit «Tapițerie») ──
    cursor.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                         WHERE table_name='carpark_vehicles' AND column_name='interior_material') THEN
            ALTER TABLE carpark_vehicles ADD COLUMN interior_material VARCHAR(50);
          END IF;
        END $$;
    """)

    # ── CarPark: freeform acquisition cost lines — JSON text [{label, amount}] ──
    cursor.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                         WHERE table_name='carpark_vehicles' AND column_name='cost_lines') THEN
            ALTER TABLE carpark_vehicles ADD COLUMN cost_lines TEXT;
          END IF;
        END $$;
    """)

    # ── CarPark condition flags (Autovit «Detalii») ──
    for _col in ['is_right_hand_drive', 'has_particle_filter', 'is_vintage',
                 'is_damaged', 'certified_mileage']:
        cursor.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_name='carpark_vehicles' AND column_name='{_col}') THEN
                ALTER TABLE carpark_vehicles ADD COLUMN {_col} BOOLEAN DEFAULT FALSE;
              END IF;
            END $$;
        """)

    # ── CarPark specs: colour finish, consumption, EV range, owners, origin ──
    for _col, _type in [
        ('color_finish', 'VARCHAR(30)'),
        ('consum_urban', 'NUMERIC'), ('consum_extraurban', 'NUMERIC'),
        ('consum_mixt', 'NUMERIC'), ('electric_range_km', 'INTEGER'),
        ('previous_owners', 'INTEGER'), ('country_of_origin', 'VARCHAR(100)'),
    ]:
        cursor.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_name='carpark_vehicles' AND column_name='{_col}') THEN
                ALTER TABLE carpark_vehicles ADD COLUMN {_col} {_type};
              END IF;
            END $$;
        """)

    # ── CarPark equipment / Dotări (Autovit) — selected option keys ──
    cursor.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                         WHERE table_name='carpark_vehicles' AND column_name='equipment_options') THEN
            ALTER TABLE carpark_vehicles ADD COLUMN equipment_options TEXT[];
          END IF;
        END $$;
    """)

    # ── CarPark Dispo: inter-company vehicle transfer log ──
    # A transfer MOVES the vehicle row to the destination company
    # (carpark_vehicles.company_id changes — see DispoService.transfer /
    # VehicleRepository.VEHICLE_UPDATABLE_FIELDS) and this table is the
    # append-only audit record of that move: who moved what, from which
    # company, to which company, for how much, backed by which document.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_transfers (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
            from_company_id INTEGER NOT NULL REFERENCES companies(id),
            to_company_id INTEGER NOT NULL REFERENCES companies(id),
            transfer_price DECIMAL(12,2),
            transfer_currency VARCHAR(3) DEFAULT 'EUR',
            transfer_date DATE NOT NULL DEFAULT CURRENT_DATE,
            document_id INTEGER REFERENCES carpark_vehicle_documents(id) ON DELETE SET NULL,
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_carpark_transfers_from ON carpark_transfers(from_company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_carpark_transfers_vehicle ON carpark_transfers(vehicle_id)')


def _create_schema_incremental_continued(conn, cursor):
    """Continuation of create_schema_incremental — non-carpark migrations."""
    # Add company_id FK to users — used by AI agent for company-scoped DMS isolation
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'users' AND column_name = 'company_id') THEN
                ALTER TABLE users ADD COLUMN company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL;
                UPDATE users u
                SET company_id = c.id
                FROM companies c
                WHERE c.company = u.company;
                -- Backfill "AW *" aliases that don't match the full company name
                UPDATE users SET company_id = 10 WHERE company = 'AW International' AND company_id IS NULL;
                UPDATE users SET company_id = 12 WHERE company = 'AW Prestige'      AND company_id IS NULL;
                UPDATE users SET company_id = 11 WHERE company = 'AW Premium'       AND company_id IS NULL;
                UPDATE users SET company_id = 9  WHERE company = 'AW Plus'          AND company_id IS NULL;
                UPDATE users SET company_id = 15 WHERE company = 'AW One'           AND company_id IS NULL;
                UPDATE users SET company_id = 16 WHERE company = 'AW Holding'       AND company_id IS NULL;
                UPDATE users SET company_id = 13 WHERE company = 'AW Next'          AND company_id IS NULL;
                UPDATE users SET company_id = 14 WHERE company = 'AW Insurance'     AND company_id IS NULL;
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_company_id ON users (company_id) WHERE is_active = TRUE')

    # ── contract_status on users (active / suspended / closed) ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'users' AND column_name = 'contract_status') THEN
                ALTER TABLE users ADD COLUMN contract_status VARCHAR(20) DEFAULT 'active';
                UPDATE users SET contract_status = CASE WHEN is_active = TRUE THEN 'active' ELSE 'closed' END;
            END IF;
        END $$;
    ''')
    try:
        cursor.execute('''
            ALTER TABLE users ADD CONSTRAINT chk_users_contract_status
            CHECK (contract_status IN ('active', 'suspended', 'closed'))
        ''')
    except Exception:
        conn.rollback()
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_contract_status ON users(contract_status)')
    cursor.execute('''
        CREATE OR REPLACE FUNCTION sync_is_active_from_contract_status()
        RETURNS TRIGGER AS $tr$
        BEGIN
            NEW.is_active = (NEW.contract_status = 'active');
            RETURN NEW;
        END;
        $tr$ LANGUAGE plpgsql;
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sync_is_active') THEN
                CREATE TRIGGER trg_sync_is_active
                    BEFORE INSERT OR UPDATE OF contract_status ON users
                    FOR EACH ROW
                    EXECUTE FUNCTION sync_is_active_from_contract_status();
            END IF;
        END $$;
    ''')

    # ── contract_status prep on sincron_employees ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'sincron_employees' AND column_name = 'contract_status') THEN
                ALTER TABLE sincron_employees ADD COLUMN contract_status VARCHAR(20);
            END IF;
        END $$;
    ''')

    # ── notify_missing_punch toggle on users ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'users' AND column_name = 'notify_missing_punch') THEN
                ALTER TABLE users ADD COLUMN notify_missing_punch BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
    ''')

    # ── is_ghost (leadership privacy) toggle on users ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'users' AND column_name = 'is_ghost') THEN
                ALTER TABLE users ADD COLUMN is_ghost BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    ''')

    # ── seed the ghost super-admin list (empty by default; edit via Settings) ──
    cursor.execute('''
        INSERT INTO notification_settings (setting_key, setting_value)
        VALUES ('ghost_visible_admin_ids', '')
        ON CONFLICT (setting_key) DO NOTHING;
    ''')

    # ── company_id on biostar_employees — maps BioStar group → JARVIS company ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'biostar_employees' AND column_name = 'company_id') THEN
                ALTER TABLE biostar_employees
                    ADD COLUMN company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL;
                UPDATE biostar_employees SET company_id = CASE user_group_name
                    WHEN 'AW HOLDING'       THEN 16
                    WHEN 'ADMINISTRATIV'    THEN 16
                    WHEN 'AW ONE'           THEN 15
                    WHEN 'AW NEXT'          THEN 13
                    WHEN 'AW INTERNATIONAL' THEN 10
                    WHEN 'AW PREMIUM'       THEN 11
                    WHEN 'AW PLUS'          THEN 9
                    WHEN 'AW PRESTIGE'      THEN 12
                    WHEN 'AW INSURANCE'     THEN 14
                    ELSE NULL
                END;
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_employees_company ON biostar_employees(company_id)')

    # ── Leave permit CO conversion approval flow ──
    cursor.execute('''
        INSERT INTO approval_flows (name, slug, description, entity_type, is_active, priority, created_by)
        SELECT 'Leave Permit CO Conversion', 'leave-permit-co-conversion',
               'Convert accumulated leave permit hours into CO days',
               'leave_permit_conversion', TRUE, 100, 1
        WHERE NOT EXISTS (SELECT 1 FROM approval_flows WHERE slug = 'leave-permit-co-conversion')
    ''')
    cursor.execute('''
        INSERT INTO approval_steps (flow_id, name, step_order, approver_type, notify_on_pending, notify_on_decision)
        SELECT f.id, 'Selected Approver', 1, 'context_approver', TRUE, TRUE
        FROM approval_flows f WHERE f.slug = 'leave-permit-co-conversion'
        AND NOT EXISTS (SELECT 1 FROM approval_steps s WHERE s.flow_id = f.id)
    ''')

    # ── Verification tables — cross-source data consistency checks ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_runs (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL UNIQUE,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            triggered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            finished_at TIMESTAMP WITH TIME ZONE,
            summary JSONB DEFAULT '{}'
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verification_runs_ym ON verification_runs(year, month)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_discrepancies (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL,
            jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            company_name VARCHAR(255),
            employee_name VARCHAR(255),
            discrepancy_type VARCHAR(50) NOT NULL,
            day DATE,
            sincron_value JSONB,
            biostar_value JSONB,
            jarvis_value JSONB,
            severity VARCHAR(10) NOT NULL DEFAULT 'warning',
            is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resolved_at TIMESTAMP WITH TIME ZONE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verif_disc_run ON verification_discrepancies(run_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verif_disc_user ON verification_discrepancies(jarvis_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_verif_disc_resolved ON verification_discrepancies(is_resolved)')

    # ── Foi de Parcurs — route sheet contracts and person clients ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_clients (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(50) NOT NULL,
            email VARCHAR(255),
            date_of_birth DATE,
            id_document_type VARCHAR(20) NOT NULL DEFAULT 'ID_CARD',
            id_document_no VARCHAR(100) NOT NULL,
            driver_license_combined VARCHAR(100),
            address TEXT,
            previous_test_drives INTEGER NOT NULL DEFAULT 0,
            previous_comadats INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_clients_phone ON fp_clients(phone)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_clients_doc_no ON fp_clients(id_document_no)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_clients_license ON fp_clients(driver_license_combined)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS foi_de_parcurs (
            id BIGSERIAL PRIMARY KEY,
            contract_id VARCHAR(255) NOT NULL UNIQUE,
            vin VARCHAR(50) NOT NULL,
            batch_id VARCHAR(100),
            client_id BIGINT,
            company_id BIGINT NOT NULL,
            year INTEGER,
            month INTEGER,
            route_type VARCHAR(10) NOT NULL,
            slot_number INTEGER NOT NULL DEFAULT 0,
            km_start INTEGER NOT NULL,
            km_end INTEGER NOT NULL,
            distance_km INTEGER NOT NULL,
            fuel_tank_capacity_liters INTEGER NOT NULL,
            fuel_gauge_start_level VARCHAR(10) NOT NULL,
            fuel_gauge_end_level VARCHAR(10) NOT NULL,
            fuel_start_liters NUMERIC(10,2) NOT NULL,
            fuel_end_liters NUMERIC(10,2) NOT NULL,
            fuel_consumed_liters NUMERIC(10,2) NOT NULL,
            itinerary TEXT,
            advisor_name VARCHAR(255),
            signature_ai_generated TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_vin ON foi_de_parcurs(vin)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_contract ON foi_de_parcurs(contract_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_client ON foi_de_parcurs(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_status ON foi_de_parcurs(status)')
    cursor.execute('ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS general_observation TEXT')
    # Manual-edit audit marker: set when an admin corrects a session (date/km) or
    # an advisor extends its return. Drives the "Modificat" badge + who/when tooltip.
    cursor.execute('ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS corrected_at TIMESTAMP WITH TIME ZONE')
    cursor.execute('ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS corrected_by VARCHAR(255)')
    # Migrate: drop FK on client_id if exists, make nullable, add new columns
    cursor.execute('''
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints
                       WHERE constraint_name = 'foi_de_parcurs_client_id_fkey') THEN
                ALTER TABLE foi_de_parcurs DROP CONSTRAINT foi_de_parcurs_client_id_fkey;
            END IF;
            ALTER TABLE foi_de_parcurs ALTER COLUMN client_id DROP NOT NULL;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='batch_id') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN batch_id VARCHAR(100);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='year') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN year INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='month') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN month INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='slot_number') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN slot_number INTEGER NOT NULL DEFAULT 0;
            END IF;
            -- Internal driving session (QuickSession): a slim FILLED TD with no
            -- customer/signature, created from the mobile quick form.
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='is_internal') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN is_internal BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_batch ON foi_de_parcurs(batch_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS foi_de_parcurs_audit (
            id BIGSERIAL PRIMARY KEY,
            contract_id VARCHAR(255) NOT NULL,
            vin VARCHAR(50) NOT NULL,
            client_id BIGINT NOT NULL,
            company_id BIGINT NOT NULL,
            assigned_route_type VARCHAR(10) NOT NULL,
            assignment_rule VARCHAR(100),
            fuel_allocation_method VARCHAR(100),
            fuel_start_liters NUMERIC(10,2),
            fuel_end_liters NUMERIC(10,2),
            fuel_consumed_liters NUMERIC(10,2),
            total_consumption_period_liters NUMERIC(10,2),
            reasoning TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'FILLED',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_audit_contract ON foi_de_parcurs_audit(contract_id)')

    # ── Foi de Parcurs — vehicle stock ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_vehicles (
            id BIGSERIAL PRIMARY KEY,
            vin VARCHAR(50) NOT NULL UNIQUE,
            mark VARCHAR(100) NOT NULL,
            model VARCHAR(100) NOT NULL,
            fuel_type VARCHAR(20) NOT NULL DEFAULT 'Diesel',
            fuel_tank_capacity_liters INTEGER NOT NULL DEFAULT 50,
            company_id BIGINT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_vin ON fp_vehicles(vin)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_active ON fp_vehicles(is_active)')
    # Add fuel_type column if table already existed without it
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'fp_vehicles' AND column_name = 'fuel_type') THEN
                ALTER TABLE fp_vehicles ADD COLUMN fuel_type VARCHAR(20) NOT NULL DEFAULT 'Diesel';
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — vehicle lockout (block a car from the driving park) ──
    cursor.execute('''
        ALTER TABLE fp_vehicles
            ADD COLUMN IF NOT EXISTS locked_out BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS lockout_category VARCHAR(20),
            ADD COLUMN IF NOT EXISTS lockout_note TEXT,
            ADD COLUMN IF NOT EXISTS lockout_until DATE,
            ADD COLUMN IF NOT EXISTS locked_by BIGINT,
            ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP WITH TIME ZONE
    ''')

    # ── Foi de Parcurs — configurable lockout reasons (editable in Settings) ──
    # fp_vehicles.lockout_category stores the reason's stable `slug`; the label
    # is editable here without orphaning existing locks. Seeded with the four
    # historical categories so already-locked cars keep their label.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_lockout_reasons (
            id BIGSERIAL PRIMARY KEY,
            slug VARCHAR(40) NOT NULL UNIQUE,
            label VARCHAR(80) NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        INSERT INTO fp_lockout_reasons (slug, label, sort_order) VALUES
            ('service',   'În service',            1),
            ('damage',    'Avariat',               2),
            ('paperwork', 'Acte lipsă/expirate',   3),
            ('other',     'Altele',                4)
        ON CONFLICT (slug) DO NOTHING
    ''')
    # Widen lockout_category so custom reason slugs (up to 40 chars) fit.
    cursor.execute("ALTER TABLE fp_vehicles ALTER COLUMN lockout_category TYPE VARCHAR(40)")

    # ── Foi de Parcurs — vehicle lock/unlock audit trail ──────────────────────
    # One row per manual block OR unblock of a car, so the lock modal can show a
    # full history ("cine a blocat/deblocat, când, de ce"). This survives an
    # unlock — fp_vehicles.locked_by/locked_at hold only the CURRENT lock and are
    # NULLed on unblock. actor_name is snapshotted so the log stays correct even
    # if the acting user is later renamed or removed.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_vehicle_lock_events (
            id BIGSERIAL PRIMARY KEY,
            vehicle_id BIGINT NOT NULL,
            action VARCHAR(10) NOT NULL,          -- 'lock' | 'unlock'
            category VARCHAR(40),                 -- reason slug at the time
            note TEXT,
            until DATE,                           -- lockout_until for a lock event
            actor_id BIGINT,                      -- users.id who performed it
            actor_name TEXT,                      -- snapshot of the actor's name
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicle_lock_events_vehicle '
                   'ON fp_vehicle_lock_events(vehicle_id, created_at DESC, id DESC)')
    # One-time backfill: seed a 'lock' event for every car currently locked, so
    # the history isn't empty for cars blocked before this shipped. Idempotent —
    # only seeds cars that have no events yet.
    cursor.execute('''
        INSERT INTO fp_vehicle_lock_events
            (vehicle_id, action, category, note, until, actor_id, actor_name, created_at)
        SELECT v.id, 'lock', v.lockout_category, v.lockout_note, v.lockout_until,
               v.locked_by, u.name, COALESCE(v.locked_at, NOW())
        FROM fp_vehicles v
        LEFT JOIN users u ON u.id = v.locked_by
        WHERE v.locked_out = TRUE
          AND NOT EXISTS (SELECT 1 FROM fp_vehicle_lock_events e WHERE e.vehicle_id = v.id)
    ''')

    # ── Foi de Parcurs — scheduled vehicle blocks (to-do #3) ──
    # One row per scheduled block window for a car. Enforcement is dynamic: a car
    # is "blocked now" if CURRENT_DATE falls inside an active window (see
    # FPVehicleRepository.get_lock_by_vin / _LIST_SELECT). No cron flips a flag.
    # `category` stores a reason slug from the shared fp_lockout_reasons list.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_vehicle_blocks (
            id BIGSERIAL PRIMARY KEY,
            vehicle_id BIGINT NOT NULL,
            category VARCHAR(40),
            note TEXT,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by BIGINT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT fp_vehicle_blocks_dates_chk CHECK (end_date >= start_date)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicle_blocks_vehicle '
                   'ON fp_vehicle_blocks(vehicle_id, start_date, end_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicle_blocks_active '
                   'ON fp_vehicle_blocks(vehicle_id) WHERE is_active')

    # ── Foi de Parcurs — vehicle archival reason (why a car left the fleet) ──
    # Mirrors the lockout model: archive_category stores a stable slug from the
    # configurable fp_archive_reasons list; the label is editable without
    # orphaning already-archived cars. archived_at records when it happened.
    cursor.execute('''
        ALTER TABLE fp_vehicles
            ADD COLUMN IF NOT EXISTS archive_category VARCHAR(40),
            ADD COLUMN IF NOT EXISTS archive_note TEXT,
            ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_archive_reasons (
            id BIGSERIAL PRIMARY KEY,
            slug VARCHAR(40) NOT NULL UNIQUE,
            label VARCHAR(80) NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        INSERT INTO fp_archive_reasons (slug, label, sort_order) VALUES
            ('sold',        'Vândut',                   1),
            ('returned',    'Returnat (leasing/flotă)', 2),
            ('scrapped',    'Casat',                    3),
            ('transferred', 'Transferat',               4),
            ('other',       'Altele',                   5)
        ON CONFLICT (slug) DO NOTHING
    ''')

    # ── Foi de Parcurs — KM configs per company ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_km_configs (
            company_id BIGINT PRIMARY KEY,
            td_km_min INTEGER NOT NULL DEFAULT 5,
            td_km_max INTEGER NOT NULL DEFAULT 50,
            comodat_km_min INTEGER NOT NULL DEFAULT 10,
            comodat_km_max INTEGER NOT NULL DEFAULT 200,
            km_gap INTEGER NOT NULL DEFAULT 20,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'fp_km_configs' AND column_name = 'km_gap') THEN
                ALTER TABLE fp_km_configs ADD COLUMN km_gap INTEGER NOT NULL DEFAULT 20;
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — company config (base location, radius) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_company_config (
            company_id BIGINT PRIMARY KEY,
            base_location VARCHAR(255) NOT NULL DEFAULT '',
            td_radius_km INTEGER NOT NULL DEFAULT 50,
            comodat_avg_km INTEGER NOT NULL DEFAULT 150,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')

    # ── Foi de Parcurs — itinerary routes per company ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_routes (
            id BIGSERIAL PRIMARY KEY,
            company_id BIGINT NOT NULL,
            route_type VARCHAR(10) NOT NULL DEFAULT 'Comodat',
            itinerary TEXT NOT NULL,
            estimated_km INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_routes_company ON fp_routes(company_id)')

    # ── Foi de Parcurs — per company+brand dealer config (review link + contact) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_dealer_config (
            company_id BIGINT NOT NULL,
            brand_id BIGINT NOT NULL,
            review_url TEXT,
            address TEXT,
            phone TEXT,
            email TEXT,
            show_in_foi_parcurs BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (company_id, brand_id)
        )
    ''')
    cursor.execute("ALTER TABLE fp_dealer_config ADD COLUMN IF NOT EXISTS show_in_foi_parcurs BOOLEAN NOT NULL DEFAULT TRUE")
    cursor.execute("ALTER TABLE fp_dealer_config ADD COLUMN IF NOT EXISTS general_conditions TEXT")

    # ── Foi de Parcurs Phase 2 — TD form fields ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='registration_number') THEN
                ALTER TABLE fp_vehicles ADD COLUMN registration_number VARCHAR(20);
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — vehicle stock hotfix: car_id, brand, color, battery capacity, Hybrid ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='car_id') THEN
                ALTER TABLE fp_vehicles ADD COLUMN car_id VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='brand') THEN
                ALTER TABLE fp_vehicles ADD COLUMN brand VARCHAR(100);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='color') THEN
                ALTER TABLE fp_vehicles ADD COLUMN color VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='battery_capacity_kwh') THEN
                ALTER TABLE fp_vehicles ADD COLUMN battery_capacity_kwh INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='odometer_km') THEN
                ALTER TABLE fp_vehicles ADD COLUMN odometer_km INTEGER;
            END IF;
            -- Per-car fuel-consumption norm (l/100km); prefills the monthly Foaie
            -- de Parcurs Normă (a per-sheet value still overrides it).
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='norma_combustibil') THEN
                ALTER TABLE fp_vehicles ADD COLUMN norma_combustibil NUMERIC(5,2);
            END IF;
            -- Energy-consumption norm (kWh/100km) for electric/hybrid cars.
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='norma_energie') THEN
                ALTER TABLE fp_vehicles ADD COLUMN norma_energie NUMERIC(5,2);
            END IF;
            -- Vehicle category shown on the Foaie de Parcurs (e.g. "AUTOTURISM M1G").
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='category') THEN
                ALTER TABLE fp_vehicles ADD COLUMN category VARCHAR(60);
            END IF;
            -- Vehicle documents + validity dates (rovinietă/vignette, ITP, RCA
            -- insurance validity; talon/CIV/insurance/registration scans as base64).
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='vignette_valid_until') THEN
                ALTER TABLE fp_vehicles ADD COLUMN vignette_valid_until DATE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='itp_valid_until') THEN
                ALTER TABLE fp_vehicles ADD COLUMN itp_valid_until DATE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='insurance_valid_until') THEN
                ALTER TABLE fp_vehicles ADD COLUMN insurance_valid_until DATE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='insurance_doc') THEN
                ALTER TABLE fp_vehicles ADD COLUMN insurance_doc TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='talon_doc') THEN
                ALTER TABLE fp_vehicles ADD COLUMN talon_doc TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='civ_doc') THEN
                ALTER TABLE fp_vehicles ADD COLUMN civ_doc TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='registration_doc') THEN
                ALTER TABLE fp_vehicles ADD COLUMN registration_doc TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='fp_vehicles' AND column_name='offer_doc') THEN
                ALTER TABLE fp_vehicles ADD COLUMN offer_doc TEXT;
            END IF;
        END $$;
    ''')
    # Allow empty fuel tank capacity (pure-Electric vehicles use battery_capacity_kwh instead)
    cursor.execute("ALTER TABLE fp_vehicles ALTER COLUMN fuel_tank_capacity_liters DROP NOT NULL")
    # One-time: existing Electric rows stored their kWh in the liters column — move it to battery_capacity_kwh
    cursor.execute('''
        UPDATE fp_vehicles
        SET battery_capacity_kwh = fuel_tank_capacity_liters,
            fuel_tank_capacity_liters = NULL
        WHERE fuel_type = 'Electric'
          AND battery_capacity_kwh IS NULL
          AND fuel_tank_capacity_liters IS NOT NULL
    ''')
    # Allow decimal capacities (e.g. 1.8 kWh mild-hybrid) — widen INTEGER → NUMERIC.
    # Value-preserving; guarded so it only runs once.
    cursor.execute('''
        DO $$ BEGIN
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name='fp_vehicles' AND column_name='battery_capacity_kwh') = 'integer' THEN
                ALTER TABLE fp_vehicles ALTER COLUMN battery_capacity_kwh TYPE NUMERIC(7,2);
            END IF;
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name='fp_vehicles' AND column_name='fuel_tank_capacity_liters') = 'integer' THEN
                ALTER TABLE fp_vehicles ALTER COLUMN fuel_tank_capacity_liters TYPE NUMERIC(7,2);
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_brand ON fp_vehicles(brand)')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='registration_number') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN registration_number VARCHAR(20);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='departure_datetime') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN departure_datetime TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='return_datetime') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN return_datetime TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='client_signature') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN client_signature TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='gdpr_consent') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN gdpr_consent BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='inspection_acceptance') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN inspection_acceptance BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='inspection_id') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN inspection_id BIGINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='pdf_legal_path') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN pdf_legal_path TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='pdf_custom_path') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN pdf_custom_path TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='source') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN source VARCHAR(20) DEFAULT 'batch';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='general_conditions_accepted') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN general_conditions_accepted BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='general_conditions_accepted_at') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN general_conditions_accepted_at TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='general_conditions_text') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN general_conditions_text TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='missed_at') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN missed_at TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='late_notified_at') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN late_notified_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fp_planned_departure ON foi_de_parcurs(departure_datetime) WHERE status = 'PLANNED'")

    # ── Foi de Parcurs — Service context ("Mașini de curtoazie") ──
    # Generic document-type discriminator (sales|service), orthogonal to
    # route_type; a Service session is a courtesy-car handover.
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='document_type') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN document_type VARCHAR(16) NOT NULL DEFAULT 'sales';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='service_order_ref') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN service_order_ref VARCHAR(64);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='document_type') THEN
                ALTER TABLE fp_vehicles ADD COLUMN document_type VARCHAR(16) NOT NULL DEFAULT 'sales';
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_doctype ON foi_de_parcurs(company_id, document_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_doctype ON fp_vehicles(document_type)')
    # Per company+brand contract template (registry, Service-first). Existence of
    # an active document_type='service' row = Service enabled for that (company,brand).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_contract_configs (
            id            BIGSERIAL PRIMARY KEY,
            company_id    BIGINT NOT NULL,
            brand_id      BIGINT NOT NULL,
            document_type VARCHAR(16) NOT NULL DEFAULT 'service',
            title         VARCHAR(255),
            body_template TEXT,
            general_conditions TEXT,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, brand_id, document_type)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_contract_configs_lookup ON fp_contract_configs(company_id, brand_id, document_type, is_active)')
    # Idempotent seed — one 'service' row per active (company, brand); never
    # overwrites rows an admin already edited (ON CONFLICT DO NOTHING).
    _seed_service_contract_configs(conn, cursor)

    # ── Foi de Parcurs — user-defined document-type registry ──
    # Supersedes the per-(company, brand) fp_contract_configs read-path: a
    # document type IS its contract (per company). 'sales' is the fixed default
    # (no template, not rental); 'service' + custom types carry a template and an
    # is_rental flag (rental types expose the car pricing fields). The
    # document_type key is stored on fp_vehicles/foi_de_parcurs as before.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_document_types (
            id            BIGSERIAL PRIMARY KEY,
            company_id    BIGINT NOT NULL,
            key           VARCHAR(48) NOT NULL,
            label         VARCHAR(128) NOT NULL,
            title         VARCHAR(255),
            body_template TEXT,
            general_conditions TEXT,
            is_rental     BOOLEAN NOT NULL DEFAULT FALSE,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            is_default    BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order    INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, key)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_document_types_lookup ON fp_document_types(company_id, is_active)')
    _seed_document_types(conn, cursor)

    # ── Foi de Parcurs — Service courtesy-car rental pricing ──
    # Per-car price + optional policy override (fp_vehicles); company default
    # policy (fp_company_config); frozen session pricing snapshot (foi_de_parcurs).
    # All nullable / Service-only — Sales rows and flows are unaffected.
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='svc_tariff_eur_day') THEN
                ALTER TABLE fp_vehicles ADD COLUMN svc_tariff_eur_day NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='svc_tariff_eur_month') THEN
                ALTER TABLE fp_vehicles ADD COLUMN svc_tariff_eur_month NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='svc_km_included_day') THEN
                ALTER TABLE fp_vehicles ADD COLUMN svc_km_included_day INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='svc_extra_km_eur') THEN
                ALTER TABLE fp_vehicles ADD COLUMN svc_extra_km_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='svc_deposit_eur') THEN
                ALTER TABLE fp_vehicles ADD COLUMN svc_deposit_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='svc_franchise_eur') THEN
                ALTER TABLE fp_vehicles ADD COLUMN svc_franchise_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_company_config' AND column_name='svc_km_included_day') THEN
                ALTER TABLE fp_company_config ADD COLUMN svc_km_included_day INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_company_config' AND column_name='svc_extra_km_eur') THEN
                ALTER TABLE fp_company_config ADD COLUMN svc_extra_km_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_company_config' AND column_name='svc_deposit_eur') THEN
                ALTER TABLE fp_company_config ADD COLUMN svc_deposit_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_company_config' AND column_name='svc_franchise_eur') THEN
                ALTER TABLE fp_company_config ADD COLUMN svc_franchise_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_rate_basis') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_rate_basis VARCHAR(8);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_tariff_eur') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_tariff_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_units') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_units INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_total_eur') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_total_eur NUMERIC(12,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_km_included_day') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_km_included_day INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_extra_km_eur') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_extra_km_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_garantie_eur') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_garantie_eur NUMERIC(10,2);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='foi_de_parcurs' AND column_name='svc_fransiza_eur') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN svc_fransiza_eur NUMERIC(10,2);
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — category-based rental tariffs ──
    # Per-company duration intervals + categories + the category×interval €/day
    # grid. A car's rental_category_id + the rental day-count resolve to a €/day.
    # Additive/idempotent; legacy per-car svc_tariff_* stays as a fallback.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_rental_intervals (
            id          BIGSERIAL PRIMARY KEY,
            company_id  BIGINT NOT NULL,
            label       VARCHAR(64) NOT NULL,
            min_days    INTEGER NOT NULL,
            max_days    INTEGER,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, min_days)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_rental_categories (
            id            BIGSERIAL PRIMARY KEY,
            company_id    BIGINT NOT NULL,
            name          VARCHAR(128) NOT NULL,
            models_note   TEXT,
            franchise_eur NUMERIC(10,2),
            extra_km_eur  NUMERIC(10,2),
            sort_order    INTEGER NOT NULL DEFAULT 0,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, name)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_rental_category_prices (
            id          BIGSERIAL PRIMARY KEY,
            company_id  BIGINT NOT NULL,
            category_id BIGINT NOT NULL,
            interval_id BIGINT NOT NULL,
            eur_per_day NUMERIC(10,2),
            UNIQUE (company_id, category_id, interval_id)
        )
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='rental_category_id') THEN
                ALTER TABLE fp_vehicles ADD COLUMN rental_category_id BIGINT;
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_rental_prices_lookup ON fp_rental_category_prices(company_id, category_id, interval_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_rental_category ON fp_vehicles(rental_category_id)')
    _seed_rental_tariffs(conn, cursor)

    # ── Foi de Parcurs — Test Drive RETURN fields ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='returned_at') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN returned_at TIMESTAMPTZ;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='return_advisor_signature') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN return_advisor_signature TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='return_client_signature') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN return_client_signature TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='return_damage') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN return_damage JSONB DEFAULT '[]'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='return_notes') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN return_notes TEXT;
            END IF;
            -- Structured vehicle-condition report captured at handover (departure form).
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='departure_damage') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN departure_damage JSONB DEFAULT '[]'::jsonb;
            END IF;
            -- Driving-license photo (compressed JPEG base64) + number, captured on the departure form.
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_license_photo') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_license_photo TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_license_number') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_license_number TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_license_expiry') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_license_expiry VARCHAR(20);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_contact_id') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_contact_id BIGINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_name') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_name TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_email') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_email TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_phone') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_phone TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='driver_license_serie') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN driver_license_serie VARCHAR(10);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='event_id') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN event_id BIGINT;
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — CRM-sourced client name/phone (Test Drive) ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='client_name') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN client_name TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='client_phone') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN client_phone TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='client_email') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN client_email TEXT;
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — optional link to a marketing project/campaign ──
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='mkt_project_id') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN mkt_project_id BIGINT;
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_foi_parcurs_mkt_project ON foi_de_parcurs(mkt_project_id)')

    # ── CRM client contact-edit audit trail (mobile Test Drive PATCH) ──
    # The login-gated crm-clients PATCH lets any consilier correct a selected
    # client's phone/email/license. This table makes every such change
    # attributable and reversible (who changed what, old -> new).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crm_client_audit (
            id BIGSERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL,
            action TEXT NOT NULL DEFAULT 'contact_update',
            changes JSONB,
            user_id INTEGER,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_client_audit_client ON crm_client_audit(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_client_audit_user ON crm_client_audit(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_client_audit_created ON crm_client_audit(created_at DESC)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_vehicle_inspections (
            id BIGSERIAL PRIMARY KEY,
            vehicle_id BIGINT NOT NULL,
            vin VARCHAR(50) NOT NULL,
            inspection_date DATE NOT NULL,
            condition_notes TEXT,
            photos JSONB DEFAULT '[]',
            inspector_name VARCHAR(255),
            inspector_signature TEXT,
            created_by INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_inspections_vehicle ON fp_vehicle_inspections(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_inspections_date ON fp_vehicle_inspections(inspection_date DESC)')

    # ── Foi de Parcurs — stored monthly route sheets (one per car × month) ──
    # Durable record of a generated monthly Foaie de Parcurs: the PDF bytes, the
    # AI-composed content, user-entered fuel data, and provenance. Regeneration
    # overwrites the row (UNIQUE on vin/year/month).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_route_sheets (
            id BIGSERIAL PRIMARY KEY,
            vin VARCHAR(50) NOT NULL,
            company_id BIGINT,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            pdf_bytes BYTEA,
            ai_summary TEXT,
            ai_trips_json JSONB,
            norma_combustibil NUMERIC(6,2),
            alimentari JSONB DEFAULT '[]',
            evenimente JSONB DEFAULT '[]',
            session_count INTEGER NOT NULL DEFAULT 0,
            total_km INTEGER NOT NULL DEFAULT 0,
            generated_by INTEGER,
            generated_by_name VARCHAR(255),
            generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (vin, year, month)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_route_sheets_period ON fp_route_sheets(company_id, year, month)')
    # fuel fields added after the table's initial release (idempotent for existing DBs)
    cursor.execute("ALTER TABLE fp_route_sheets ADD COLUMN IF NOT EXISTS norma_combustibil NUMERIC(6,2)")
    cursor.execute("ALTER TABLE fp_route_sheets ADD COLUMN IF NOT EXISTS norma_energie NUMERIC(6,2)")
    cursor.execute("ALTER TABLE fp_route_sheets ADD COLUMN IF NOT EXISTS alimentari JSONB DEFAULT '[]'")
    cursor.execute("ALTER TABLE fp_route_sheets ADD COLUMN IF NOT EXISTS evenimente JSONB DEFAULT '[]'")

    # facturare per-document number registry (additive; never mutates facturare_invoices)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturare_document_numbers (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
            supplier_id INTEGER NOT NULL,
            series VARCHAR(16) NOT NULL,
            line_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            document_number INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    cursor.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # The number may repeat across the cars of ONE single_doc invoice, but must
    # not be reused by a DIFFERENT invoice. Enforced with an exclusion constraint
    # (a plain UNIQUE index would reject single_doc multi-car rows).
    cursor.execute("DROP INDEX IF EXISTS uq_facturare_docnum_series")
    cursor.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'excl_facturare_docnum_cross_invoice'
            ) THEN
                ALTER TABLE facturare_document_numbers
                    ADD CONSTRAINT excl_facturare_docnum_cross_invoice
                    EXCLUDE USING gist (
                        supplier_id     WITH =,
                        series          WITH =,
                        document_number WITH =,
                        invoice_id      WITH <>
                    ) WHERE (document_number IS NOT NULL);
            END IF;
        END $$;
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facturare_docnum_invoice
        ON facturare_document_numbers (invoice_id)
    """)
    # ── HR Department Pulse — backend-aggregated 360 qualitative votes ──
    # Rolling per-voter × department-node × perspective × competency vote scoped
    # to a Sincron org node. Re-voting UPDATEs the same row (the UNIQUE upsert
    # key) so a voter's latest vote always counts and there is no month history.
    # ON DELETE CASCADE from both FKs cleans up when a user or node is removed.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr_dept_pulse_votes (
            id SERIAL PRIMARY KEY,
            voter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department_node_id INTEGER NOT NULL REFERENCES sincron_org_nodes(id) ON DELETE CASCADE,
            perspective VARCHAR(20) NOT NULL,
            competency_key VARCHAR(40) NOT NULL,
            rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (voter_user_id, department_node_id, perspective, competency_key)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_hr_dept_pulse_votes_node_perspective
        ON hr_dept_pulse_votes(department_node_id, perspective)
    ''')

    # ── Facturare — widen invoice_number range 7 → 9 digits ──
    # The original ck_invoice_number_range capped invoice_number at 9,999,999
    # (7 digits). Suppliers now issue 8-digit numbers (e.g. 92005610), so relax
    # the CHECK to 999,999,999 — still well inside the INTEGER column's range.
    # Idempotent: no-op if the table is absent; loosening the bound never
    # violates existing rows (all ≤ 9,999,999).
    cursor.execute('''
        DO $$ BEGIN
            IF to_regclass('public.facturare_invoices') IS NOT NULL THEN
                ALTER TABLE facturare_invoices DROP CONSTRAINT IF EXISTS ck_invoice_number_range;
                ALTER TABLE facturare_invoices
                    ADD CONSTRAINT ck_invoice_number_range
                    CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 999999999));
            END IF;
        END $$;
    ''')

    # ── Sincron org nodes — allow 'unallocated' node_type ──
    # Seed-from-departments now flags a genuinely new department 'unallocated'
    # (shown as "Nealocat", needing a manager or placement) until it gets a
    # responsable or is moved under a parent. Widen the CHECK to accept it.
    # Idempotent: no-op if the table is absent; widening never violates rows.
    cursor.execute('''
        DO $$ BEGIN
            IF to_regclass('public.sincron_org_nodes') IS NOT NULL THEN
                ALTER TABLE sincron_org_nodes DROP CONSTRAINT IF EXISTS chk_sincron_org_node_type;
                ALTER TABLE sincron_org_nodes
                    ADD CONSTRAINT chk_sincron_org_node_type
                    CHECK (node_type IN ('department', 'role', 'team', 'unallocated'));
            END IF;
        END $$;
    ''')

    # ── Foi de Parcurs — per-session audit log ──
    # One row per session mutation (create/activate/return/correct/extend/…) with
    # the acting user + timestamp, surfaced as the "Istoric" modal in the Driving
    # Hub → Sesiuni Driving tab. FK cascades so deleting a session drops its log.
    # Idempotent: no-op if foi_de_parcurs is absent or the table already exists.
    cursor.execute('''
        DO $$ BEGIN
            IF to_regclass('public.foi_de_parcurs') IS NOT NULL THEN
                CREATE TABLE IF NOT EXISTS foi_parcurs_session_events (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER NOT NULL REFERENCES foi_de_parcurs(id) ON DELETE CASCADE,
                    action TEXT NOT NULL,
                    actor TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_fp_session_events_session
                    ON foi_parcurs_session_events(session_id, created_at DESC);
            END IF;
        END $$;
    ''')

    # ── HR Leave Permits — soft-delete (archive) support on both leave sources ──
    # The HR Leave-Permits tab (/app/hr/leave-permits) merges two backends:
    # form_submissions (JARVIS/Invoire leaves) and connecteam_form_submissions
    # (Excel-imported leaves). HR gets edit + archive controls; archive is a
    # recoverable soft-delete — archived_at IS NOT NULL hides the row from the
    # default list (HR "Show archived" toggle reveals it, restore clears it).
    # archived_by records the acting HR user for audit. Idempotent: ADD COLUMN
    # IF NOT EXISTS no-ops on re-run and never touches existing rows.
    cursor.execute('''
        DO $$ BEGIN
            IF to_regclass('public.form_submissions') IS NOT NULL THEN
                ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP DEFAULT NULL;
                ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS archived_by INTEGER DEFAULT NULL;
                CREATE INDEX IF NOT EXISTS idx_form_submissions_active
                    ON form_submissions(form_id) WHERE archived_at IS NULL;
            END IF;
            IF to_regclass('public.connecteam_form_submissions') IS NOT NULL THEN
                ALTER TABLE connecteam_form_submissions ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
                ALTER TABLE connecteam_form_submissions ADD COLUMN IF NOT EXISTS archived_by INTEGER DEFAULT NULL;
                CREATE INDEX IF NOT EXISTS idx_connecteam_submissions_active
                    ON connecteam_form_submissions(leave_date) WHERE archived_at IS NULL;
            END IF;
        END $$;
    ''')

    # ── HR Leave Permits — Trash (soft-delete) distinct from Archive ──
    # HR now has two separate recoverable states: Archive (filed, kept
    # indefinitely) and Trash (deleted_at set, auto-purged after 7 days by the
    # purge_old_trashed_leaves scheduler job). deleted_at takes precedence over
    # archived_at when both somehow set. archived_by/deleted_by record the actor.
    # Idempotent: ADD COLUMN IF NOT EXISTS no-ops on re-run.
    cursor.execute('''
        DO $$ BEGIN
            IF to_regclass('public.form_submissions') IS NOT NULL THEN
                ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP DEFAULT NULL;
                ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS deleted_by INTEGER DEFAULT NULL;
                CREATE INDEX IF NOT EXISTS idx_form_submissions_trashed
                    ON form_submissions(deleted_at) WHERE deleted_at IS NOT NULL;
            END IF;
            IF to_regclass('public.connecteam_form_submissions') IS NOT NULL THEN
                ALTER TABLE connecteam_form_submissions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
                ALTER TABLE connecteam_form_submissions ADD COLUMN IF NOT EXISTS deleted_by INTEGER DEFAULT NULL;
                CREATE INDEX IF NOT EXISTS idx_connecteam_submissions_trashed
                    ON connecteam_form_submissions(deleted_at) WHERE deleted_at IS NOT NULL;
            END IF;
        END $$;
    ''')

    # ── Driver license → single "Serie/Nr." field ──
    # The Romanian driving-license serie+number is one continuous code, so the
    # split driver_license_serie / driver_license_number is merged into
    # driver_license_number ("serie number") and serie is cleared. The WHERE
    # guard (serie non-empty) makes it re-run-safe: once merged serie is NULL so
    # a later deploy no-ops instead of double-merging.
    cursor.execute('''
        DO $$ BEGIN
            IF to_regclass('public.crm_client_contacts') IS NOT NULL THEN
                UPDATE crm_client_contacts
                   SET driver_license_number = NULLIF(TRIM(CONCAT_WS(' ', NULLIF(TRIM(driver_license_serie), ''), NULLIF(TRIM(driver_license_number), ''))), ''),
                       driver_license_serie = NULL
                 WHERE driver_license_serie IS NOT NULL AND TRIM(driver_license_serie) <> '';
            END IF;
            IF to_regclass('public.foi_de_parcurs') IS NOT NULL THEN
                UPDATE foi_de_parcurs
                   SET driver_license_number = NULLIF(TRIM(CONCAT_WS(' ', NULLIF(TRIM(driver_license_serie), ''), NULLIF(TRIM(driver_license_number), ''))), ''),
                       driver_license_serie = NULL
                 WHERE driver_license_serie IS NOT NULL AND TRIM(driver_license_serie) <> '';
            END IF;
        END $$;
    ''')

    # ── Consent documents — mandatory first-login legal gate ──
    # Two user-keyed tables (users table is intentionally NOT altered).
    # Seeded is_active=FALSE so placeholder copy never blocks staff; an admin
    # finalizes text in Settings then flips active. See consents module.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consent_documents (
            id                 SERIAL PRIMARY KEY,
            doc_key            TEXT NOT NULL UNIQUE,
            title              TEXT NOT NULL,
            body               TEXT NOT NULL DEFAULT '',
            sort_order         INTEGER NOT NULL DEFAULT 0,
            requires_signature BOOLEAN NOT NULL DEFAULT TRUE,
            is_mandatory       BOOLEAN NOT NULL DEFAULT TRUE,
            is_active          BOOLEAN NOT NULL DEFAULT TRUE,
            version            INTEGER NOT NULL DEFAULT 1,
            created_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_by         INTEGER REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_consent_signatures (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id      INTEGER NOT NULL REFERENCES consent_documents(id) ON DELETE CASCADE,
            document_version INTEGER NOT NULL DEFAULT 1,
            response         TEXT NOT NULL DEFAULT 'accepted'
                                CHECK (response IN ('accepted','declined')),
            signature_image  TEXT,
            document_hash    TEXT,
            ip_address       TEXT,
            user_agent       TEXT,
            signed_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_consent UNIQUE (user_id, document_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ucs_user ON user_consent_signatures(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ucs_document ON user_consent_signatures(document_id)')

    # Seed the 3 documents (inactive). Bodies are placeholders — the data_usage
    # body is adapted from the provided Connecteam example; gdpr/nda are marked
    # for DPO/legal completion. ON CONFLICT keeps admin edits on re-run.
    cursor.execute('''
        INSERT INTO consent_documents (doc_key, title, body, sort_order, is_active)
        VALUES
          ('data_usage',
           'Acord privind utilizarea datelor de contact',
           %s, 1, FALSE),
          ('gdpr',
           'Notă de informare și acord GDPR',
           %s, 2, FALSE),
          ('nda',
           'Acord de confidențialitate (NDA)',
           %s, 3, FALSE)
        ON CONFLICT (doc_key) DO NOTHING
    ''', (_SEED_DATA_USAGE, _SEED_GDPR, _SEED_NDA))

    conn.commit()
