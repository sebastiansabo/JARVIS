"""360° Evaluation module schema.

Competency library, versioned form templates, review cycles, participants,
reviewer assignments, responses, reports, development plans — plus the
append-only event log that drives the indicator catalog
(docs/360/jarvis2-360-indicators.json) and an admin/anonymity audit log.

All tables are prefixed `eval_`. Idempotent (CREATE TABLE IF NOT EXISTS), so
this is safe to run on every boot like the other schema domains.
"""


def create_schema_evaluation360(conn, cursor):
    """Create all 360°-evaluation module tables and indexes."""

    # ============== Competency library ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_competencies (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            definition TEXT,
            cluster TEXT,
            level_descriptors JSONB DEFAULT '[]'::jsonb,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
    ''')

    # ============== Form templates (versioned; fork-on-edit) ==============
    # Editing a template used by an active cycle forks a NEW row (version+1,
    # forked_from_id set) rather than mutating in place — enforced in the service
    # layer; the schema keeps every version immutable once `published`.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_form_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            forked_from_id INTEGER REFERENCES eval_form_templates(id),
            rating_scale JSONB NOT NULL
                DEFAULT '{"type":"1-5","min":1,"max":5,"not_observed":true}'::jsonb,
            competency_ids INTEGER[] DEFAULT '{}',
            audience_variants JSONB DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            CONSTRAINT eval_form_templates_status_check
                CHECK (status IN ('draft', 'published', 'archived'))
        )
    ''')

    # ============== Question blocks ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_question_blocks (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES eval_form_templates(id) ON DELETE CASCADE,
            competency_id INTEGER REFERENCES eval_competencies(id),
            type TEXT NOT NULL,
            text_by_audience JSONB DEFAULT '{}'::jsonb,
            required BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            CONSTRAINT eval_question_blocks_type_check
                CHECK (type IN ('rating', 'behavioral_frequency', 'open_text', 'forced_choice'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_question_blocks_template ON eval_question_blocks(template_id)')

    # ============== Review cycles ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_cycles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            template_id INTEGER REFERENCES eval_form_templates(id),
            population_filter JSONB DEFAULT '{}'::jsonb,
            nomination_start DATE,
            review_start DATE,
            review_end DATE,
            calibration_end DATE,
            release_at DATE,
            anonymity_policy JSONB DEFAULT '{"min_n": 3}'::jsonb,
            reminder_policy JSONB DEFAULT '{}'::jsonb,
            release_policy TEXT NOT NULL DEFAULT 'manager_gated',
            status TEXT NOT NULL DEFAULT 'draft',
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT eval_cycles_status_check CHECK (status IN (
                'draft', 'nomination', 'active', 'calibration', 'released', 'closed', 'archived'
            )),
            CONSTRAINT eval_cycles_release_policy_check
                CHECK (release_policy IN ('all_at_once', 'manager_gated', 'rolling'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_cycles_status ON eval_cycles(status)')

    # ============== Participants ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_participants (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL REFERENCES eval_cycles(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES users(id),
            self_status TEXT DEFAULT 'pending',
            nomination_status TEXT DEFAULT 'pending',
            report_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT eval_participants_unique UNIQUE (cycle_id, employee_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_participants_cycle ON eval_participants(cycle_id)')

    # ============== Reviewer assignments ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_assignments (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL REFERENCES eval_cycles(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES users(id),
            reviewer_id INTEGER REFERENCES users(id),
            external_email TEXT,
            relationship TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'hr_assigned',
            status TEXT NOT NULL DEFAULT 'pending_approval',
            due_at TIMESTAMP,
            decline_reason TEXT,
            replaced_by_id INTEGER REFERENCES eval_assignments(id),
            started_at TIMESTAMP,
            submitted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT eval_assignments_relationship_check CHECK (relationship IN (
                'self', 'manager', 'peer', 'direct_report', 'external'
            )),
            CONSTRAINT eval_assignments_source_check CHECK (source IN (
                'self_nominated', 'manager_assigned', 'hr_assigned', 'auto_suggested'
            )),
            CONSTRAINT eval_assignments_status_check CHECK (status IN (
                'pending_approval', 'invited', 'in_progress', 'submitted', 'declined', 'replaced'
            )),
            CONSTRAINT eval_assignments_reviewer_or_email
                CHECK (reviewer_id IS NOT NULL OR external_email IS NOT NULL)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_assignments_subject ON eval_assignments(cycle_id, subject_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_assignments_reviewer ON eval_assignments(reviewer_id, status)')

    # ============== Responses ==============
    # `answers` holds the submitted ratings/comments; field-level encryption at
    # rest (key separated from identity) is a P6 hardening step. A single row per
    # assignment; `draft_payload` is the autosaved in-progress state (idempotent
    # per question), `answers`+`is_submitted` become write-once on submit.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_responses (
            id SERIAL PRIMARY KEY,
            assignment_id INTEGER NOT NULL REFERENCES eval_assignments(id) ON DELETE CASCADE,
            answers JSONB DEFAULT '[]'::jsonb,
            draft_payload JSONB DEFAULT '{}'::jsonb,
            device TEXT,
            is_submitted BOOLEAN DEFAULT FALSE,
            submitted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT eval_responses_device_check CHECK (device IS NULL OR device IN ('mobile', 'web')),
            CONSTRAINT eval_responses_assignment_unique UNIQUE (assignment_id)
        )
    ''')

    # ============== Reports ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_reports (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL REFERENCES eval_cycles(id) ON DELETE CASCADE,
            participant_id INTEGER NOT NULL REFERENCES eval_participants(id) ON DELETE CASCADE,
            aggregates_by_relationship JSONB DEFAULT '{}'::jsonb,
            gap_analysis JSONB DEFAULT '{}'::jsonb,
            hidden_categories TEXT[] DEFAULT '{}',
            manager_summary TEXT,
            debrief_scheduled_at TIMESTAMP,
            released_at TIMESTAMP,
            acknowledged_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT eval_reports_participant_unique UNIQUE (participant_id)
        )
    ''')
    # Existing DBs already have eval_reports; add the debrief column idempotently.
    cursor.execute(
        'ALTER TABLE eval_reports ADD COLUMN IF NOT EXISTS debrief_scheduled_at TIMESTAMP')

    # ============== Development plans ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_development_plans (
            id SERIAL PRIMARY KEY,
            participant_id INTEGER NOT NULL REFERENCES eval_participants(id) ON DELETE CASCADE,
            goals JSONB DEFAULT '[]'::jsonb,
            linked_competencies INTEGER[] DEFAULT '{}',
            check_in_dates DATE[] DEFAULT '{}',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ============== Development-plan check-ins ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_devplan_checkins (
            id SERIAL PRIMARY KEY,
            plan_id INTEGER NOT NULL REFERENCES eval_development_plans(id) ON DELETE CASCADE,
            scheduled_date DATE,
            completed_at TIMESTAMP,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_devplan_checkins_plan ON eval_devplan_checkins(plan_id)')

    # ============== Event log (append-only; drives indicators) ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_events (
            id SERIAL PRIMARY KEY,
            event_name TEXT NOT NULL,
            cycle_id INTEGER REFERENCES eval_cycles(id) ON DELETE CASCADE,
            subject_id INTEGER REFERENCES users(id),
            assignment_id INTEGER,
            actor_id INTEGER REFERENCES users(id),
            payload JSONB DEFAULT '{}'::jsonb,
            device TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_events_name_ts ON eval_events(event_name, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_events_cycle ON eval_events(cycle_id)')

    # ============== Nudge log (DB-backed 1/day/user rate limit) ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_nudges (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER REFERENCES eval_cycles(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            source TEXT NOT NULL DEFAULT 'hr_manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_nudges_user_ts ON eval_nudges(user_id, created_at)')

    # ============== Admin / anonymity audit log (append-only) ==============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eval_audit_log (
            id SERIAL PRIMARY KEY,
            actor_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_audit_actor ON eval_audit_log(actor_id, created_at)')

    conn.commit()
