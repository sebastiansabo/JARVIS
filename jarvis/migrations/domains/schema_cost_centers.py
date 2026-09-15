"""Cost Centers schema — Finance budgeting dimension (a.k.a. kostenstelle).

Depends on schema_core (companies, structure_nodes). Registered in
init_schema AFTER create_schema_core and create_schema_divisions.
Fully idempotent; auto-applied on boot via database.init_db().
"""
import logging

logger = logging.getLogger(__name__)


def create_schema_cost_centers(conn, cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_centers (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            code VARCHAR(8) NOT NULL,
            name VARCHAR(255) NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, code)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_centers_company ON cost_centers(company_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_center_structure_map (
            id SERIAL PRIMARY KEY,
            cost_center_id INTEGER NOT NULL REFERENCES cost_centers(id) ON DELETE CASCADE,
            structure_node_id INTEGER REFERENCES structure_nodes(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (cost_center_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cc_map_node ON cost_center_structure_map(structure_node_id)")

    conn.commit()
    logger.info('Cost Centers schema created/verified')
