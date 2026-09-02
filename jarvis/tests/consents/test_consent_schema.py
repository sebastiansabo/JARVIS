"""Task 1 — consent_documents / user_consent_signatures schema + seed.

Runs against localhost/defaultdb when a real Postgres is reachable; skips
cleanly under CI's mocked/unreachable DB. The psycopg2 mock-drop/rebind +
real-DB probe lives centrally in this package's conftest.py
(REAL_DB_AVAILABLE), which also restores the pre-probe mock state on failure
so a no-DB run doesn't leak real-driver bindings into other test packages
collected in the same pytest session. This module just consults that flag and
skips (matching the idiom in jarvis/tests/dept_pulse/test_dept_pulse_schema.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from core.base_repository import BaseRepository
from database import get_db, get_cursor, release_db

from .conftest import REAL_DB_AVAILABLE


def _repo():
    return BaseRepository()


def _run_migration():
    """Apply the incremental migration (idempotent) so the tables exist."""
    from migrations.domains.schema_incremental import create_schema_incremental
    conn = get_db()
    try:
        conn.autocommit = False
        cur = get_cursor(conn)
        create_schema_incremental(conn, cur)
        conn.commit()
    finally:
        release_db(conn)


@pytest.fixture(scope='module', autouse=True)
def ensure_migrated():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping consents schema tests'
        )
    _run_migration()


def test_consent_tables_exist():
    r = _repo()
    cols = r.query_all("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_name IN ('consent_documents','user_consent_signatures')
    """)
    names = {(c['table_name'], c['column_name']) for c in cols}
    assert ('consent_documents', 'doc_key') in names
    assert ('user_consent_signatures', 'signature_image') in names
    assert ('user_consent_signatures', 'document_hash') in names


def test_unique_signature_per_user_doc():
    r = _repo()
    con = r.query_one("""
        SELECT COUNT(*) AS n FROM information_schema.table_constraints
        WHERE table_name = 'user_consent_signatures' AND constraint_type = 'UNIQUE'
    """)
    assert con['n'] >= 1


def test_three_docs_seeded_inactive():
    r = _repo()
    rows = r.query_all("SELECT doc_key, is_active FROM consent_documents ORDER BY sort_order")
    keys = [x['doc_key'] for x in rows]
    assert keys == ['data_usage', 'gdpr', 'nda']
    assert all(x['is_active'] is False for x in rows)
