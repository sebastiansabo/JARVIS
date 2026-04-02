"""Database schema initialization — orchestrator.

Delegates to domain-specific modules under jarvis/migrations/domains/.
Called by database.init_db() on module import.
"""
from .domains.schema_core import create_schema_core
from .domains.schema_statements import create_schema_statements
from .domains.schema_roles import create_schema_roles
from .domains.schema_misc import create_schema_misc
from .domains.schema_hr import create_schema_hr
from .domains.schema_efactura import create_schema_efactura
from .domains.schema_approvals import create_schema_approvals
from .domains.schema_marketing import create_schema_marketing
from .domains.schema_signatures import create_schema_signatures
from .domains.schema_bilant import create_schema_bilant
from .domains.schema_crm import create_schema_crm
from .domains.schema_field_sales import create_schema_field_sales
from .domains.schema_forms import create_schema_forms
from .domains.schema_digest import create_schema_digest
from .domains.schema_carpark import create_schema_carpark
from .version_manager import run_pending_migrations


def create_schema(conn, cursor):
    """Create all database tables, indexes, and seed data.

    Args:
        conn: Database connection (for commit/rollback)
        cursor: Database cursor from get_cursor(conn)
    """
    create_schema_core(conn, cursor)
    create_schema_statements(conn, cursor)
    create_schema_roles(conn, cursor)
    create_schema_misc(conn, cursor)
    create_schema_hr(conn, cursor)
    create_schema_efactura(conn, cursor)
    create_schema_approvals(conn, cursor)
    create_schema_marketing(conn, cursor)
    create_schema_signatures(conn, cursor)
    create_schema_bilant(conn, cursor)
    create_schema_crm(conn, cursor)
    create_schema_field_sales(conn, cursor)
    create_schema_forms(conn, cursor)
    create_schema_digest(conn, cursor)
    create_schema_carpark(conn, cursor)
    run_pending_migrations(conn, cursor)
    conn.commit()
