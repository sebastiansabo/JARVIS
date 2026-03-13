"""Approvals schema: data migrations, approval_*, notifications, smart_notification_state."""
import psycopg2
import psycopg2.errors


def create_schema_approvals(conn, cursor):
    """Create approval engine tables."""
    # ============== Migration: REAL → NUMERIC for financial columns ==============
    # Idempotent: ALTER TYPE on already-NUMERIC columns is a no-op that raises
    # "column is already of type" which we catch and ignore.
    _real_to_numeric_migrations = [
        ('invoices', 'invoice_value', 'NUMERIC(15,2)'),
        ('invoices', 'value_ron', 'NUMERIC(15,2)'),
        ('invoices', 'value_eur', 'NUMERIC(15,2)'),
        ('invoices', 'exchange_rate', 'NUMERIC(10,6)'),
        ('invoices', 'vat_rate', 'NUMERIC(5,2)'),
        ('invoices', 'net_value', 'NUMERIC(15,2)'),
        ('allocations', 'allocation_percent', 'NUMERIC(7,4)'),
        ('allocations', 'allocation_value', 'NUMERIC(15,2)'),
        ('bank_statement_transactions', 'amount', 'NUMERIC(15,2)'),
        ('bank_statement_transactions', 'original_amount', 'NUMERIC(15,2)'),
        ('bank_statement_transactions', 'exchange_rate', 'NUMERIC(10,6)'),
        ('bank_statement_transactions', 'match_confidence', 'NUMERIC(5,4)'),
        ('vat_rates', 'rate', 'NUMERIC(5,2)'),
        ('dropdown_options', 'opacity', 'NUMERIC(3,2)'),
        ('reinvoice_destinations', 'percentage', 'NUMERIC(7,4)'),
        ('reinvoice_destinations', 'value', 'NUMERIC(15,2)'),
    ]
    for table, column, new_type in _real_to_numeric_migrations:
        try:
            cursor.execute(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type} USING {column}::{new_type}')
            conn.commit()
        except Exception:
            conn.rollback()

    # ============== Missing indexes ==============
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bst_invoice_id ON bank_statement_transactions(invoice_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_payment_status ON invoices(payment_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notification_log_status ON notification_log(status)')
    conn.commit()

    # ============== Missing foreign keys ==============
    try:
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_sync_errors_run_id'
                ) THEN
                    ALTER TABLE efactura_sync_errors
                    ADD CONSTRAINT fk_sync_errors_run_id
                    FOREIGN KEY (run_id) REFERENCES efactura_sync_runs(run_id);
                END IF;
            END $$;
        ''')
        conn.commit()
    except Exception:
        conn.rollback()

    # ============== Approval Engine Tables ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_flows (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT,
            entity_type TEXT NOT NULL,
            trigger_conditions JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT TRUE,
            priority INTEGER DEFAULT 0,
            allow_parallel_steps BOOLEAN DEFAULT FALSE,
            auto_approve_below NUMERIC(15,2),
            auto_reject_after_hours INTEGER,
            requires_signature BOOLEAN DEFAULT FALSE,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_flows_entity_type ON approval_flows(entity_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_flows_active ON approval_flows(is_active)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_steps (
            id SERIAL PRIMARY KEY,
            flow_id INTEGER NOT NULL REFERENCES approval_flows(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            approver_type TEXT NOT NULL,
            approver_user_id INTEGER REFERENCES users(id),
            approver_role_name TEXT,
            requires_all BOOLEAN DEFAULT FALSE,
            min_approvals INTEGER DEFAULT 1,
            skip_conditions JSONB DEFAULT '{}',
            timeout_hours INTEGER,
            escalation_step_id INTEGER REFERENCES approval_steps(id),
            escalation_user_id INTEGER REFERENCES users(id),
            notify_on_pending BOOLEAN DEFAULT TRUE,
            notify_on_decision BOOLEAN DEFAULT TRUE,
            reminder_after_hours INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_steps_flow ON approval_steps(flow_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_requests (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            flow_id INTEGER NOT NULL REFERENCES approval_flows(id),
            current_step_id INTEGER REFERENCES approval_steps(id),
            status TEXT NOT NULL DEFAULT 'pending',
            context_snapshot JSONB DEFAULT '{}',
            requested_by INTEGER NOT NULL REFERENCES users(id),
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolution_note TEXT,
            priority TEXT DEFAULT 'normal',
            due_by TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_approval_status CHECK (
                status IN ('pending','in_progress','approved','rejected','cancelled','expired','escalated','on_hold')
            ),
            CONSTRAINT chk_approval_priority CHECK (
                priority IN ('low','normal','high','urgent')
            )
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_requests_entity ON approval_requests(entity_type, entity_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_requests_step_status ON approval_requests(current_step_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_requests_requested_by ON approval_requests(requested_by)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_decisions (
            id SERIAL PRIMARY KEY,
            request_id INTEGER NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
            step_id INTEGER NOT NULL REFERENCES approval_steps(id),
            decided_by INTEGER NOT NULL REFERENCES users(id),
            decision TEXT NOT NULL,
            comment TEXT,
            delegated_to INTEGER REFERENCES users(id),
            delegation_reason TEXT,
            conditions JSONB,
            decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_decision_type CHECK (
                decision IN ('approved','rejected','returned','delegated','abstained')
            )
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_decisions_request ON approval_decisions(request_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_decisions_step ON approval_decisions(step_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_audit_log (
            id SERIAL PRIMARY KEY,
            request_id INTEGER NOT NULL REFERENCES approval_requests(id),
            action TEXT NOT NULL,
            actor_id INTEGER REFERENCES users(id),
            actor_type TEXT DEFAULT 'user',
            details JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_audit_request ON approval_audit_log(request_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_audit_timestamp ON approval_audit_log(created_at)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_delegations (
            id SERIAL PRIMARY KEY,
            delegator_id INTEGER NOT NULL REFERENCES users(id),
            delegate_id INTEGER NOT NULL REFERENCES users(id),
            entity_type TEXT,
            flow_id INTEGER REFERENCES approval_flows(id),
            starts_at TIMESTAMP NOT NULL,
            ends_at TIMESTAMP NOT NULL,
            reason TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_delegations_delegate ON approval_delegations(delegate_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_delegations_active ON approval_delegations(is_active, starts_at, ends_at)')

    # In-app notifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT,
            link TEXT,
            entity_type TEXT,
            entity_id INTEGER,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read) WHERE is_read = FALSE')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC)')

    # ============== Smart Notification State ==============

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

    # Seed smart alert defaults
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
