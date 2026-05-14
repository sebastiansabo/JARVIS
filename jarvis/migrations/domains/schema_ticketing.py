"""Ticketing schema: IT helpdesk tickets and comments."""


def create_schema_ticketing(conn, cursor):
    """Create all Ticketing module tables and indexes."""

    # ── Tickets ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
            priority TEXT NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high', 'critical')),
            category TEXT NOT NULL DEFAULT 'other'
                CHECK (category IN ('hardware', 'software', 'network', 'access', 'other')),
            created_by INTEGER NOT NULL REFERENCES users(id),
            assigned_to INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            closed_at TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_assigned_to ON tickets(assigned_to)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON tickets(created_by)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at)')

    # ── Ticket Comments ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_comments (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticket_comments_ticket_id ON ticket_comments(ticket_id)')

    conn.commit()
