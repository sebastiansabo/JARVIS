"""Marketing schema: mkt_* tables."""
import psycopg2
import psycopg2.errors


def create_schema_marketing(conn, cursor):
    """Create marketing module tables."""
    # ============== Marketing Projects Module ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_projects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            company_ids INTEGER[] DEFAULT '{}',
            brand_id INTEGER REFERENCES brands(id),
            brand_ids INTEGER[] DEFAULT '{}',
            department_structure_id INTEGER REFERENCES department_structure(id),
            department_ids INTEGER[] DEFAULT '{}',
            project_type TEXT NOT NULL DEFAULT 'campaign',
            channel_mix TEXT[] DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'draft',
            start_date DATE,
            end_date DATE,
            total_budget NUMERIC(15,2) NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'RON',
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            objective TEXT,
            target_audience TEXT,
            brief JSONB DEFAULT '{}'::jsonb,
            external_ref TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            CONSTRAINT mkt_projects_status_check CHECK (status IN (
                'draft','pending_approval','approved','active','paused','completed','archived','cancelled'
            )),
            CONSTRAINT mkt_projects_type_check CHECK (project_type IN (
                'campaign','always_on','event','launch','branding','research'
            ))
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_mkt_projects_slug ON mkt_projects(slug)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_projects_company ON mkt_projects(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_projects_brand ON mkt_projects(brand_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_projects_status ON mkt_projects(status) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_projects_owner ON mkt_projects(owner_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_projects_dates ON mkt_projects(start_date, end_date) WHERE deleted_at IS NULL')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_members (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            role TEXT NOT NULL DEFAULT 'member',
            department_structure_id INTEGER REFERENCES department_structure(id),
            added_by INTEGER NOT NULL REFERENCES users(id),
            responsibility TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_members_unique UNIQUE (project_id, user_id)
        )
    ''')
    cursor.execute("ALTER TABLE mkt_project_members ADD COLUMN IF NOT EXISTS responsibility TEXT")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_members_user ON mkt_project_members(user_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_budget_lines (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            description TEXT,
            department_structure_id INTEGER REFERENCES department_structure(id),
            agency_name TEXT,
            planned_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            approved_amount NUMERIC(15,2) DEFAULT 0,
            spent_amount NUMERIC(15,2) DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'RON',
            period_type TEXT DEFAULT 'campaign',
            period_start DATE,
            period_end DATE,
            status TEXT NOT NULL DEFAULT 'draft',
            notes TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_budget_status_check CHECK (status IN (
                'draft','pending_approval','approved','active','exhausted','cancelled'
            ))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_budget_lines_project ON mkt_budget_lines(project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_budget_lines_channel ON mkt_budget_lines(channel)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_budget_transactions (
            id SERIAL PRIMARY KEY,
            budget_line_id INTEGER NOT NULL REFERENCES mkt_budget_lines(id) ON DELETE CASCADE,
            amount NUMERIC(15,2) NOT NULL,
            direction TEXT NOT NULL DEFAULT 'debit',
            source TEXT NOT NULL DEFAULT 'manual',
            reference_id TEXT,
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
            file_id INTEGER REFERENCES mkt_project_files(id) ON DELETE SET NULL,
            transaction_date DATE NOT NULL,
            description TEXT,
            recorded_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_budget_tx_dir_check CHECK (direction IN ('debit','credit'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_budget_tx_line ON mkt_budget_transactions(budget_line_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_budget_tx_date ON mkt_budget_transactions(transaction_date)')
    # Migration: add file_id column if missing
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE mkt_budget_transactions ADD COLUMN file_id INTEGER REFERENCES mkt_project_files(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_definitions (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL DEFAULT 'number',
            direction TEXT NOT NULL DEFAULT 'higher',
            category TEXT NOT NULL DEFAULT 'performance',
            formula TEXT,
            description TEXT,
            benchmarks JSONB,
            is_active BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_kpis (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            kpi_definition_id INTEGER NOT NULL REFERENCES mkt_kpi_definitions(id),
            channel TEXT,
            target_value NUMERIC(15,4),
            current_value NUMERIC(15,4) DEFAULT 0,
            weight INTEGER DEFAULT 50,
            threshold_warning NUMERIC(15,4),
            threshold_critical NUMERIC(15,4),
            currency TEXT DEFAULT 'RON',
            status TEXT DEFAULT 'no_data',
            last_synced_at TIMESTAMP,
            notes TEXT,
            show_on_overview BOOLEAN DEFAULT FALSE,
            aggregation TEXT DEFAULT 'latest',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_kpi_status_check CHECK (status IN ('no_data','on_track','at_risk','behind','exceeded')),
            CONSTRAINT mkt_kpi_unique UNIQUE (project_id, kpi_definition_id, channel)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_kpis_project ON mkt_project_kpis(project_id)')
    cursor.execute("ALTER TABLE mkt_project_kpis ADD COLUMN IF NOT EXISTS aggregation TEXT DEFAULT 'latest'")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_snapshots (
            id SERIAL PRIMARY KEY,
            project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            value NUMERIC(15,4) NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recorded_by INTEGER REFERENCES users(id),
            notes TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_snapshots_kpi ON mkt_kpi_snapshots(project_kpi_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_snapshots_date ON mkt_kpi_snapshots(recorded_at)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_activity (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            actor_id INTEGER REFERENCES users(id),
            actor_type TEXT DEFAULT 'user',
            details JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_activity_project ON mkt_project_activity(project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_activity_date ON mkt_project_activity(created_at)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_comments (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES mkt_project_comments(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            is_internal BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_comments_project ON mkt_project_comments(project_id)')

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

    # Project ↔ DMS Document linking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_dms_links (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
            linked_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_project_dms_links_unique UNIQUE (project_id, document_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_dms_links_project ON mkt_project_dms_links(project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_dms_links_doc ON mkt_project_dms_links(document_id)')

    # KPI ↔ Budget Line linking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_budget_lines (
            id SERIAL PRIMARY KEY,
            project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            budget_line_id INTEGER NOT NULL REFERENCES mkt_budget_lines(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'input',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_kpi_budget_lines_unique UNIQUE (project_kpi_id, budget_line_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_bl_kpi ON mkt_kpi_budget_lines(project_kpi_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_bl_line ON mkt_kpi_budget_lines(budget_line_id)')

    # KPI ↔ KPI dependencies
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

    # Project ↔ CRM Client linking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_project_clients (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
            client_id INTEGER NOT NULL REFERENCES crm_clients(id) ON DELETE CASCADE,
            linked_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_project_clients_unique UNIQUE (project_id, client_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_clients_project ON mkt_project_clients(project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_clients_client ON mkt_project_clients(client_id)')

    # KPI ↔ Deal Sources (aggregated CRM deal metrics)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_deal_sources (
            id SERIAL PRIMARY KEY,
            project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'input',
            metric TEXT NOT NULL DEFAULT 'count',
            brand_filter TEXT,
            source_filter VARCHAR(5),
            status_filter TEXT,
            date_from DATE,
            date_to DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_kpi_deal_sources_unique UNIQUE (project_kpi_id, role, metric)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deal_src_kpi ON mkt_kpi_deal_sources(project_kpi_id)')

    # Individual deal links to KPIs (each deal = 1 unit toward the KPI)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mkt_kpi_deals (
            id SERIAL PRIMARY KEY,
            project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
            deal_id INTEGER NOT NULL REFERENCES crm_deals(id) ON DELETE CASCADE,
            linked_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT mkt_kpi_deals_unique UNIQUE (project_kpi_id, deal_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deals_kpi ON mkt_kpi_deals(project_kpi_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deals_deal ON mkt_kpi_deals(deal_id)')

    conn.commit()

    # Seed approval permissions_v2 if not already present
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'approvals'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            ('approvals', 'Approvals', 'bi-check2-square', 'queue', 'Approval Queue', 'access', 'Access', 'Access approval queue', FALSE, 1),
            ('approvals', 'Approvals', 'bi-check2-square', 'queue', 'Approval Queue', 'decide', 'Decide', 'Approve or reject requests', FALSE, 2),
            ('approvals', 'Approvals', 'bi-check2-square', 'requests', 'Requests', 'submit', 'Submit', 'Submit entities for approval', FALSE, 3),
            ('approvals', 'Approvals', 'bi-check2-square', 'requests', 'Requests', 'view_all', 'View All', 'View all approval requests', FALSE, 4),
            ('approvals', 'Approvals', 'bi-check2-square', 'flows', 'Flows', 'view', 'View', 'View approval flows', FALSE, 5),
            ('approvals', 'Approvals', 'bi-check2-square', 'flows', 'Flows', 'manage', 'Manage', 'Create and edit flows', FALSE, 6),
            ('approvals', 'Approvals', 'bi-check2-square', 'delegations', 'Delegations', 'manage', 'Manage', 'Manage approval delegations', FALSE, 7),
            ('approvals', 'Approvals', 'bi-check2-square', 'audit', 'Audit Log', 'view', 'View', 'View approval audit log', FALSE, 8)
        ''')

        # Grant to existing roles
        cursor.execute('SELECT id, name FROM roles')
        for role in cursor.fetchall():
            role_name = role['name']
            cursor.execute("SELECT id FROM permissions_v2 WHERE module_key = 'approvals'")
            perm_rows = cursor.fetchall()
            for p in perm_rows:
                if role_name == 'Admin':
                    cursor.execute('''
                        INSERT INTO role_permissions_v2 (role_id, permission_id, granted)
                        VALUES (%s, %s, TRUE)
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role['id'], p['id']))
                elif role_name == 'Manager':
                    cursor.execute("SELECT action_key FROM permissions_v2 WHERE id = %s", (p['id'],))
                    action = cursor.fetchone()['action_key']
                    if action in ('access', 'decide', 'submit', 'view_all', 'manage'):
                        cursor.execute('''
                            INSERT INTO role_permissions_v2 (role_id, permission_id, granted)
                            VALUES (%s, %s, TRUE)
                            ON CONFLICT (role_id, permission_id) DO NOTHING
                        ''', (role['id'], p['id']))
                else:
                    cursor.execute("SELECT action_key FROM permissions_v2 WHERE id = %s", (p['id'],))
                    action = cursor.fetchone()['action_key']
                    if action in ('access', 'decide', 'submit'):
                        cursor.execute('''
                            INSERT INTO role_permissions_v2 (role_id, permission_id, granted)
                            VALUES (%s, %s, TRUE)
                            ON CONFLICT (role_id, permission_id) DO NOTHING
                        ''', (role['id'], p['id']))

        conn.commit()

    # Seed marketing permissions_v2 if not already present
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
        # Grant marketing perms to roles
        cursor.execute('SELECT id, name FROM roles')
        for role in cursor.fetchall():
            role_name = role['name']
            cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'marketing'")
            for p in cursor.fetchall():
                if role_name == 'Admin':
                    scope = 'all'
                elif role_name == 'Manager':
                    scope = 'department' if p['action_key'] not in ('delete',) else 'deny'
                else:
                    scope = 'own' if p['action_key'] in ('view', 'create') else 'deny'
                if scope != 'deny':
                    cursor.execute('''
                        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role['id'], p['id'], scope))
        conn.commit()

    # ── Migration: Add missing permissions_v2 for uncovered modules ──
    from .schema_roles import _seed_missing_permissions_v2
    _seed_missing_permissions_v2(cursor, conn)

    # Seed marketing dropdown_options if not present
    cursor.execute("SELECT COUNT(*) as cnt FROM dropdown_options WHERE dropdown_type = 'mkt_project_type'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order, is_active) VALUES
            ('mkt_project_type', 'campaign', 'Campaign', '#0d6efd', 1, TRUE),
            ('mkt_project_type', 'always_on', 'Always-On', '#198754', 2, TRUE),
            ('mkt_project_type', 'event', 'Event', '#fd7e14', 3, TRUE),
            ('mkt_project_type', 'launch', 'Product Launch', '#6f42c1', 4, TRUE),
            ('mkt_project_type', 'branding', 'Branding', '#d63384', 5, TRUE),
            ('mkt_project_type', 'research', 'Research', '#6c757d', 6, TRUE),
            ('mkt_channel', 'meta_ads', 'Meta Ads', '#1877F2', 1, TRUE),
            ('mkt_channel', 'google_ads', 'Google Ads', '#4285F4', 2, TRUE),
            ('mkt_channel', 'radio', 'Radio', '#FF6B35', 3, TRUE),
            ('mkt_channel', 'print', 'Print', '#2D3436', 4, TRUE),
            ('mkt_channel', 'ooh', 'OOH / Outdoor', '#00B894', 5, TRUE),
            ('mkt_channel', 'influencer', 'Influencer', '#E84393', 6, TRUE),
            ('mkt_channel', 'email', 'Email Marketing', '#FDCB6E', 7, TRUE),
            ('mkt_channel', 'sms', 'SMS', '#636E72', 8, TRUE),
            ('mkt_channel', 'events', 'Events', '#6C5CE7', 9, TRUE),
            ('mkt_channel', 'other', 'Other', '#95A5A6', 10, TRUE),
            ('mkt_project_status', 'draft', 'Draft', '#6c757d', 1, TRUE),
            ('mkt_project_status', 'pending_approval', 'Pending Approval', '#ffc107', 2, TRUE),
            ('mkt_project_status', 'approved', 'Approved', '#198754', 3, TRUE),
            ('mkt_project_status', 'active', 'Active', '#0d6efd', 4, TRUE),
            ('mkt_project_status', 'paused', 'Paused', '#fd7e14', 5, TRUE),
            ('mkt_project_status', 'completed', 'Completed', '#20c997', 6, TRUE),
            ('mkt_project_status', 'cancelled', 'Cancelled', '#dc3545', 7, TRUE),
            ('mkt_project_status', 'archived', 'Archived', '#adb5bd', 8, TRUE),
            ('mkt_kpi_status', 'no_data', 'No Data', '#6c757d', 1, TRUE),
            ('mkt_kpi_status', 'exceeded', 'Exceeded', '#198754', 2, TRUE),
            ('mkt_kpi_status', 'on_track', 'On Track', '#0d6efd', 3, TRUE),
            ('mkt_kpi_status', 'at_risk', 'At Risk', '#ffc107', 4, TRUE),
            ('mkt_kpi_status', 'behind', 'Behind', '#dc3545', 5, TRUE)
        ''')
        conn.commit()

    # Seed KPI definitions if not present
    cursor.execute("SELECT COUNT(*) as cnt FROM mkt_kpi_definitions")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO mkt_kpi_definitions (name, slug, unit, direction, category, formula, sort_order) VALUES
            ('Cost Per Acquisition', 'cpa', 'currency', 'lower', 'performance', 'spent / conversions', 1),
            ('Return On Ad Spend', 'roas', 'ratio', 'higher', 'financial', 'revenue / spent', 2),
            ('Cost Per Lead', 'cpl', 'currency', 'lower', 'performance', 'spent / leads', 3),
            ('Click-Through Rate', 'ctr', 'percentage', 'higher', 'engagement', 'clicks / impressions * 100', 4),
            ('Conversion Rate', 'cvr', 'percentage', 'higher', 'conversion', 'conversions / clicks * 100', 5),
            ('Cost Per Click', 'cpc', 'currency', 'lower', 'performance', 'spent / clicks', 6),
            ('Cost Per Mille', 'cpm', 'currency', 'lower', 'performance', 'spent / impressions * 1000', 7),
            ('Impressions', 'impressions', 'number', 'higher', 'brand', NULL, 8),
            ('Reach', 'reach', 'number', 'higher', 'brand', NULL, 9),
            ('Leads Generated', 'leads', 'number', 'higher', 'conversion', NULL, 10),
            ('Sales / Conversions', 'conversions', 'number', 'higher', 'conversion', NULL, 11),
            ('Revenue Generated', 'revenue', 'currency', 'higher', 'financial', NULL, 12),
            ('Total Spend', 'total_spend', 'currency', 'lower', 'financial', NULL, 13),
            ('Video Views', 'video_views', 'number', 'higher', 'engagement', NULL, 14),
            ('Engagement Rate', 'engagement_rate', 'percentage', 'higher', 'engagement', '(likes + comments + shares) / impressions * 100', 15)
        ''')
        conn.commit()

    # ── Campaign Simulator benchmarks table ──
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

    # OKR tables
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
    conn.commit()

    # Seed simulator benchmarks from exercitiu.xlsx Foaie2
    cursor.execute("SELECT COUNT(*) as cnt FROM mkt_sim_benchmarks")
    if cursor.fetchone()['cnt'] == 0:
        _seed_sim_benchmarks(cursor)
        conn.commit()

    # Migration: Add context_window column to ai_agent.model_configs
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ai_agent')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema = 'ai_agent'
                               AND table_name = 'model_configs'
                               AND column_name = 'context_window') THEN
                ALTER TABLE ai_agent.model_configs ADD COLUMN context_window INTEGER DEFAULT 200000;
                -- Set known context windows per model
                UPDATE ai_agent.model_configs SET context_window = 200000 WHERE model_name LIKE 'claude-%';
                UPDATE ai_agent.model_configs SET context_window = 128000 WHERE model_name = 'gpt-4-turbo';
                UPDATE ai_agent.model_configs SET context_window = 16385 WHERE model_name = 'gpt-3.5-turbo';
                UPDATE ai_agent.model_configs SET context_window = 32768 WHERE model_name IN ('mixtral-8x7b-32768', 'gemini-pro');
                UPDATE ai_agent.model_configs SET context_window = 128000 WHERE model_name = 'llama-3.3-70b-versatile';
            END IF;
        END $$;
    ''')
    conn.commit()

    # Seed Grok (xAI) models if not present
    cursor.execute('''
        INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, context_window, is_default)
        SELECT 'grok', 'grok-3', 'Grok 3', 0.005, 0.015, 4096, 131072, FALSE
        WHERE EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ai_agent')
        AND NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'grok' AND model_name = 'grok-3')
    ''')
    cursor.execute('''
        INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, context_window, is_default)
        SELECT 'grok', 'grok-2-1212', 'Grok 2', 0.002, 0.010, 4096, 131072, FALSE
        WHERE EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ai_agent')
        AND NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'grok' AND model_name = 'grok-2-1212')
    ''')
    conn.commit()

    # Seed default approval flow for marketing projects (context_approver)
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


def _seed_sim_benchmarks(cursor):
    """Seed campaign simulator benchmarks from exercitiu.xlsx Foaie2."""
    cursor.execute('''
        INSERT INTO mkt_sim_benchmarks (channel_key, channel_label, funnel_stage, month_index, cpc, cvr_lead, cvr_car) VALUES
        -- Awareness (8 channels x 3 months)
        ('youtube_skippable_aw', 'YouTube Skippable In-Stream', 'awareness', 1, 1.0000, 0.007500, 0.001500),
        ('youtube_skippable_aw', 'YouTube Skippable In-Stream', 'awareness', 2, 1.0000, 0.005500, 0.001500),
        ('youtube_skippable_aw', 'YouTube Skippable In-Stream', 'awareness', 3, 1.0000, 0.003500, 0.001500),
        ('meta_reach', 'Meta Reach', 'awareness', 1, 0.3000, 0.004000, 0.001500),
        ('meta_reach', 'Meta Reach', 'awareness', 2, 0.3000, 0.002000, 0.001500),
        ('meta_reach', 'Meta Reach', 'awareness', 3, 0.3000, 0.002000, 0.001500),
        ('meta_traffic_aw', 'Meta Traffic', 'awareness', 1, 0.0600, 0.002000, 0.000500),
        ('meta_traffic_aw', 'Meta Traffic', 'awareness', 2, 0.0600, 0.001000, 0.000500),
        ('meta_traffic_aw', 'Meta Traffic', 'awareness', 3, 0.0600, 0.001000, 0.000500),
        ('meta_video_views', 'Meta Video Views', 'awareness', 1, 1.0000, 0.007500, 0.001000),
        ('meta_video_views', 'Meta Video Views', 'awareness', 2, 1.0000, 0.005500, 0.001000),
        ('meta_video_views', 'Meta Video Views', 'awareness', 3, 1.0000, 0.003500, 0.001000),
        ('google_display', 'Google Display', 'awareness', 1, 0.6000, 0.003000, 0.000500),
        ('google_display', 'Google Display', 'awareness', 2, 0.6000, 0.001500, 0.000500),
        ('google_display', 'Google Display', 'awareness', 3, 0.6000, 0.001500, 0.000500),
        ('google_search_aw', 'Google Search', 'awareness', 1, 0.0800, 0.003000, 0.000500),
        ('google_search_aw', 'Google Search', 'awareness', 2, 0.0800, 0.001500, 0.000500),
        ('google_search_aw', 'Google Search', 'awareness', 3, 0.0800, 0.001500, 0.000500),
        ('programmatic_display', 'Programmatic Display', 'awareness', 1, 0.4000, 0.005000, 0.001000),
        ('programmatic_display', 'Programmatic Display', 'awareness', 2, 0.4000, 0.002500, 0.001000),
        ('programmatic_display', 'Programmatic Display', 'awareness', 3, 0.4000, 0.002500, 0.001000),
        ('google_pmax_clicks', 'Google Pmax (clicks)', 'awareness', 1, 0.1000, 0.004000, 0.000500),
        ('google_pmax_clicks', 'Google Pmax (clicks)', 'awareness', 2, 0.1000, 0.002000, 0.000500),
        ('google_pmax_clicks', 'Google Pmax (clicks)', 'awareness', 3, 0.1000, 0.002000, 0.000500),
        -- Consideration (6 channels x 3 months)
        ('youtube_skippable_co', 'YouTube Skippable In-Stream', 'consideration', 1, 1.0000, 0.008000, 0.001500),
        ('youtube_skippable_co', 'YouTube Skippable In-Stream', 'consideration', 2, 1.0000, 0.007000, 0.001500),
        ('youtube_skippable_co', 'YouTube Skippable In-Stream', 'consideration', 3, 1.0000, 0.007000, 0.001500),
        ('youtube_bumper', 'YouTube Bumper', 'consideration', 1, 1.0000, 0.005500, 0.000500),
        ('youtube_bumper', 'YouTube Bumper', 'consideration', 2, 1.0000, 0.006500, 0.000500),
        ('youtube_bumper', 'YouTube Bumper', 'consideration', 3, 1.0000, 0.006500, 0.000500),
        ('google_demand_gen', 'Google Demand Gen', 'consideration', 1, 0.2500, 0.003500, 0.000500),
        ('google_demand_gen', 'Google Demand Gen', 'consideration', 2, 0.2500, 0.004500, 0.000500),
        ('google_demand_gen', 'Google Demand Gen', 'consideration', 3, 0.2500, 0.004500, 0.000500),
        ('meta_engagement', 'Meta Engagement', 'consideration', 1, 0.5000, 0.008000, 0.001500),
        ('meta_engagement', 'Meta Engagement', 'consideration', 2, 0.5000, 0.010000, 0.001500),
        ('meta_engagement', 'Meta Engagement', 'consideration', 3, 0.5000, 0.010000, 0.004000),
        ('meta_traffic_co', 'Meta Traffic', 'consideration', 1, 0.0600, 0.005000, 0.000500),
        ('meta_traffic_co', 'Meta Traffic', 'consideration', 2, 0.0600, 0.006500, 0.000500),
        ('meta_traffic_co', 'Meta Traffic', 'consideration', 3, 0.0600, 0.006500, 0.000500),
        ('special_activation', 'Special Activation', 'consideration', 1, 0.3000, 0.008000, 0.004000),
        ('special_activation', 'Special Activation', 'consideration', 2, 0.3000, 0.012000, 0.004000),
        ('special_activation', 'Special Activation', 'consideration', 3, 0.3000, 0.012000, 0.000000),
        -- Conversion (3 channels x 3 months)
        ('google_search_hi', 'Google Search High Intent', 'conversion', 1, 1.5000, 0.010000, 0.002500),
        ('google_search_hi', 'Google Search High Intent', 'conversion', 2, 1.2000, 0.018000, 0.002500),
        ('google_search_hi', 'Google Search High Intent', 'conversion', 3, 1.0000, 0.035000, 0.002500),
        ('google_pmax_conv', 'Google Pmax (conversion)', 'conversion', 1, 0.4500, 0.018000, 0.001500),
        ('google_pmax_conv', 'Google Pmax (conversion)', 'conversion', 2, 0.4500, 0.022000, 0.001500),
        ('google_pmax_conv', 'Google Pmax (conversion)', 'conversion', 3, 0.4500, 0.026000, 0.001500),
        ('meta_conversion', 'Meta Conversion', 'conversion', 1, 0.8000, 0.022000, 0.001500),
        ('meta_conversion', 'Meta Conversion', 'conversion', 2, 0.8000, 0.025000, 0.001500),
        ('meta_conversion', 'Meta Conversion', 'conversion', 3, 0.8000, 0.028000, 0.001500)
    ''')
