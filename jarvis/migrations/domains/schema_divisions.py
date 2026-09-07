"""HR Divisions schema — a JARVIS-owned overlay on the Sincron organigram.

A Division groups Sincron departments (`sincron_org_nodes`) across companies and
assigns one or more responsables (division managers). The division responsable
acts as a fallback manager for anyone in those departments who has no manager
above them in Sincron. See
docs/superpowers/specs/2026-09-07-hr-divisions-design.md.

`node_id` FKs to `sincron_org_nodes` are safe: that table is maintained by an
incremental CRUD repository (stable ids), and `sincron_org_members` /
`hr_event_bonus_days` already reference it the same way.

Runs after schema_sincron (needs `sincron_org_nodes`) and schema_core (needs
`users`).
"""
import logging

logger = logging.getLogger(__name__)


def create_schema_divisions(conn, cursor):
    # A division: name only; grouping + responsables live in the child tables.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_divisions (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # Sincron departments assigned to a division. A department belongs to at
    # most one division (UNIQUE node_id).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_division_departments (
            id SERIAL PRIMARY KEY,
            division_id INTEGER NOT NULL REFERENCES hr_divisions(id) ON DELETE CASCADE,
            node_id INTEGER NOT NULL REFERENCES sincron_org_nodes(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (node_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hr_division_departments_div ON hr_division_departments(division_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hr_division_departments_node ON hr_division_departments(node_id)")

    # Division responsable(s) — one or more JARVIS users; any can approve.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_division_responsables (
            id SERIAL PRIMARY KEY,
            division_id INTEGER NOT NULL REFERENCES hr_divisions(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (division_id, user_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hr_division_responsables_div ON hr_division_responsables(division_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hr_division_responsables_user ON hr_division_responsables(user_id)")

    conn.commit()
    logger.info('HR Divisions schema created/verified')
