"""Connecteam connector schema — leave permission form submissions via Excel import."""

import logging

logger = logging.getLogger(__name__)


def create_schema_connecteam(conn, cursor):
    """Create Connecteam connector tables."""

    # ── Connecteam users (mapping table) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connecteam_users (
            id SERIAL PRIMARY KEY,
            connecteam_user_id BIGINT NOT NULL UNIQUE,
            connecteam_user_name VARCHAR(255),
            connecteam_email VARCHAR(255),
            connecteam_phone VARCHAR(50),
            mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            mapping_method VARCHAR(50),
            mapping_confidence INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_users_mapped
        ON connecteam_users(mapped_jarvis_user_id)
        WHERE mapped_jarvis_user_id IS NOT NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_users_email
        ON connecteam_users(connecteam_email)
        WHERE connecteam_email IS NOT NULL
    """)

    # ── Connecteam form submissions (parsed leave permission data) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connecteam_form_submissions (
            id SERIAL PRIMARY KEY,
            submission_id VARCHAR(100) NOT NULL UNIQUE,
            form_id BIGINT NOT NULL,
            form_name VARCHAR(255),
            connecteam_user_id BIGINT NOT NULL,
            mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            submission_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            submission_timezone VARCHAR(50) DEFAULT 'Europe/Bucharest',
            entry_num INTEGER DEFAULT 1,
            is_anonymous BOOLEAN DEFAULT FALSE,
            leave_date DATE,
            leave_start_time TIME,
            leave_end_time TIME,
            leave_hours NUMERIC(4,2),
            leave_reason TEXT,
            leave_destination TEXT,
            approved_by VARCHAR(255),
            status VARCHAR(20) DEFAULT 'submitted',
            raw_answers JSONB NOT NULL DEFAULT '[]',
            raw_payload JSONB,
            event_type VARCHAR(50) NOT NULL DEFAULT 'form_submission',
            received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_submissions_user
        ON connecteam_form_submissions(mapped_jarvis_user_id)
        WHERE mapped_jarvis_user_id IS NOT NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_submissions_date
        ON connecteam_form_submissions(leave_date)
        WHERE leave_date IS NOT NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_submissions_form
        ON connecteam_form_submissions(form_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_submissions_ct_user
        ON connecteam_form_submissions(connecteam_user_id)
    """)

    # ── Webhook event log (debugging / replay) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connecteam_webhook_log (
            id SERIAL PRIMARY KEY,
            request_id VARCHAR(100),
            event_type VARCHAR(50),
            form_id BIGINT,
            status VARCHAR(20) NOT NULL DEFAULT 'received',
            error_message TEXT,
            raw_payload JSONB NOT NULL,
            received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_webhook_log_status
        ON connecteam_webhook_log(status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_connecteam_webhook_log_date
        ON connecteam_webhook_log(received_at)
    """)

    # ── CHECK constraints ──
    for stmt in [
        """ALTER TABLE connecteam_users ADD CONSTRAINT chk_ct_user_confidence
           CHECK (mapping_confidence BETWEEN 0 AND 100)""",
        """ALTER TABLE connecteam_form_submissions ADD CONSTRAINT chk_ct_sub_hours
           CHECK (leave_hours IS NULL OR leave_hours >= 0)""",
        """ALTER TABLE connecteam_webhook_log ADD CONSTRAINT chk_ct_wh_status
           CHECK (status IN ('received', 'processed', 'failed', 'ignored'))""",
    ]:
        try:
            cursor.execute(stmt)
        except Exception:
            conn.rollback()  # constraint already exists — safe to skip

    conn.commit()
    logger.info('Connecteam schema created/verified')
