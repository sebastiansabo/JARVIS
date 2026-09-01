"""Task 2 — ConsentRepository data-access tests.

Real-DB integration tests (Ruling R6): placed under jarvis/tests/consents/ so
they reuse this package's conftest.py probe/skip (REAL_DB_AVAILABLE), which
un-mocks psycopg2 for a real local Postgres and skips cleanly when the DB is
unreachable (e.g. in CI, matching test_consent_schema.py's idiom). Task 1
already created + seeded consent_documents/user_consent_signatures (all 3
seed docs is_active=FALSE), so these tests assume that state rather than
re-running the migration themselves.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from core.consents.repositories.consent_repository import ConsentRepository

from .conftest import REAL_DB_AVAILABLE


@pytest.fixture(autouse=True)
def _skip_without_real_db():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping consent repository tests'
        )


@pytest.fixture
def repo():
    return ConsentRepository()


def test_get_by_key_returns_seeded_doc(repo):
    doc = repo.get_by_key('data_usage')
    # seeded inactive -> get_by_key filters is_active=TRUE, so None until activated
    assert doc is None


def test_list_all_includes_inactive(repo):
    docs = repo.list_all()
    keys = {d['doc_key'] for d in docs}
    assert {'data_usage', 'gdpr', 'nda'}.issubset(keys)


def test_count_active_mandatory_zero_when_all_inactive(repo):
    # all seeds inactive at start
    assert repo.count_active_mandatory() == 0
