"""Forms schema: forms + form_submissions tables."""


def create_schema_forms(conn, cursor):
    """Create forms module tables."""

    # ============== Forms ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS forms (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            status TEXT NOT NULL DEFAULT 'draft',
            schema JSONB NOT NULL DEFAULT '[]'::jsonb,
            published_schema JSONB,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            utm_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            branding JSONB NOT NULL DEFAULT '{}'::jsonb,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            version INTEGER NOT NULL DEFAULT 1,
            published_at TIMESTAMP,
            requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            CONSTRAINT forms_status_check CHECK (status IN (
                'draft', 'published', 'disabled', 'archived'
            ))
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_forms_slug ON forms(slug) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_forms_company ON forms(company_id) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_forms_status ON forms(status) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_forms_owner ON forms(owner_id) WHERE deleted_at IS NULL')

    # ============== Form Submissions ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS form_submissions (
            id SERIAL PRIMARY KEY,
            form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
            form_version INTEGER NOT NULL,
            answers JSONB NOT NULL DEFAULT '{}'::jsonb,
            form_schema_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            respondent_name TEXT,
            respondent_email TEXT,
            respondent_phone TEXT,
            respondent_ip INET,
            respondent_user_id INTEGER REFERENCES users(id),
            utm_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            source TEXT NOT NULL DEFAULT 'web_public',
            status TEXT NOT NULL DEFAULT 'new',
            approval_request_id INTEGER,
            company_id INTEGER REFERENCES companies(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT form_submissions_status_check CHECK (status IN (
                'new', 'read', 'flagged', 'approved', 'rejected'
            )),
            CONSTRAINT form_submissions_source_check CHECK (source IN (
                'web_public', 'web_internal', 'mobile'
            ))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_form_submissions_form ON form_submissions(form_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_form_submissions_status ON form_submissions(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_form_submissions_created ON form_submissions(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_form_submissions_utm ON form_submissions USING GIN (utm_data)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_form_submissions_answers ON form_submissions USING GIN (answers)')

    conn.commit()
