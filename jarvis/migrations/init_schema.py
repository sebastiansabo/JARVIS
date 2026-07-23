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
from .domains.schema_sincron import create_schema_sincron
from .domains.schema_connecteam import create_schema_connecteam
from .domains.schema_holidays import create_schema_holidays
from .domains.schema_incremental import create_schema_incremental
from .domains.schema_telemetry import create_schema_telemetry
from .domains.schema_courses import create_schema_courses
from .domains.schema_facturare import create_schema_facturare
from .domains.schema_time_bank import create_schema_time_bank
from .domains.schema_ticketing import create_schema_ticketing
from .domains.schema_controlling_bab import create_schema_controlling_bab
from .domains.schema_vouchers import create_schema_vouchers
from .domains.schema_evaluation360 import create_schema_evaluation360
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
    create_schema_sincron(conn, cursor)
    create_schema_connecteam(conn, cursor)
    create_schema_holidays(conn, cursor)
    create_schema_telemetry(conn, cursor)
    create_schema_courses(conn, cursor)
    create_schema_facturare(conn, cursor)
    create_schema_time_bank(conn, cursor)
    create_schema_ticketing(conn, cursor)
    create_schema_controlling_bab(conn, cursor)
    create_schema_vouchers(conn, cursor)
    create_schema_evaluation360(conn, cursor)
    create_schema_incremental(conn, cursor)
    run_pending_migrations(conn, cursor)
    conn.commit()

    # Seed voucher issuance form (idempotent, needs forms table to exist)
    try:
        from accounting.vouchers.form_seed import ensure_voucher_form
        ensure_voucher_form()
    except Exception:
        pass  # May fail during initial import chain; app.py will retry

    # Retire the Forms-engine 'test-drive' form. Test drives are now recorded
    # exclusively via the in-module custom form (POST /api/foi-parcurs/test-drive).
    # This unpublishes any previously-seeded row (idempotent).
    try:
        from foi_parcurs.form_seed import retire_test_drive_form
        retire_test_drive_form()
    except Exception:
        pass  # May fail during initial import chain; app.py will retry
