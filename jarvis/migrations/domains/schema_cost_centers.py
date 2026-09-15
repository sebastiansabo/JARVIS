"""Cost Centers schema — Finance budgeting dimension (a.k.a. kostenstelle).

Depends on schema_core (companies, structure_nodes). Registered in
init_schema AFTER create_schema_core and create_schema_divisions.
Fully idempotent; auto-applied on boot via database.init_db().
"""
import logging

from .cost_centers_seed import SEED_ROWS, SHEET_TO_COMPANY

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

    cursor.execute('SELECT COUNT(*) FROM cost_centers')
    if cursor.fetchone()['count'] == 0:
        _seed_cost_centers(cursor)

    conn.commit()
    logger.info('Cost Centers schema created/verified')


def _seed_cost_centers(cursor):
    inserted, skipped = 0, 0
    for sheet_key, code, name in SEED_ROWS:
        company_name = SHEET_TO_COMPANY.get(sheet_key)
        cursor.execute('SELECT id FROM companies WHERE company = %s', (company_name,))
        row = cursor.fetchone()
        if not row:
            logger.warning('cost_centers seed: no company for sheet %r (%r) — skipping %s %s',
                           sheet_key, company_name, code, name)
            skipped += 1
            continue
        cursor.execute(
            "INSERT INTO cost_centers (company_id, code, name) VALUES (%s, %s, %s) "
            "ON CONFLICT (company_id, code) DO NOTHING",
            (row['id'], code, name),
        )
        inserted += 1
    logger.info('cost_centers seeded: %s inserted, %s skipped', inserted, skipped)
