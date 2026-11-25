"""ClientRepository.merge() must repoint KAM field-sales visits by updating
`kam_visit_plans.client_id` (that table owns the client_id FK). The old code
ran `UPDATE kam_visit_notes SET client_id = ...`, but kam_visit_notes has NO
client_id column (it links to a client only via visit_id -> kam_visit_plans),
so every merge raised `column "client_id" does not exist` and rolled back —
breaking the CRM Sanitize "Unifică" button for all merges.

These tests capture the SQL merge() issues (psycopg2 is mocked by conftest) and
assert the repoint targets kam_visit_plans and never references kam_visit_notes.
"""
import sys, os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


@pytest.fixture(scope='module')
def app():
    # Bootstrap the full import graph in the right order first — importing the
    # repository directly otherwise hits a partially-initialized circular import.
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    return application


def _merge_sql(keep=100, remove=200):
    """Run merge() with a mocked cursor; return the list of SQL strings issued."""
    from crm.repositories.client_repository import ClientRepository
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    with patch('core.base_repository.get_db', return_value=MagicMock()), \
         patch('core.base_repository.get_cursor', return_value=cursor), \
         patch('core.base_repository.release_db'):
        ClientRepository().merge(keep, remove)
    return [str(c.args[0]) for c in cursor.execute.call_args_list if c.args]


def test_merge_repoints_kam_visit_plans(app):
    joined = ' | '.join(_merge_sql())
    assert 'UPDATE kam_visit_plans SET client_id' in joined


def test_merge_never_references_kam_visit_notes(app):
    joined = ' | '.join(_merge_sql())
    assert 'kam_visit_notes' not in joined


def test_merge_still_repoints_core_tables(app):
    joined = ' | '.join(_merge_sql())
    for tbl in ('crm_deals', 'client_fleet', 'client_phones'):
        assert tbl in joined
    assert 'merged_into_id' in joined
