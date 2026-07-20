import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from unittest.mock import MagicMock
from core.organization.repositories.company_repository import CompanyRepository


def test_update_includes_gdpr_text_in_sql():
    repo = CompanyRepository()
    captured = {}
    def fake_execute_many(work):
        cur = MagicMock(); cur.rowcount = 1
        work(cur)
        captured['sql'], captured['params'] = cur.execute.call_args[0]
        return True
    repo.execute_many = fake_execute_many
    repo.update(1, gdpr_text='## T\n\nbody')
    assert 'gdpr_text = %s' in captured['sql']
    assert '## T\n\nbody' in captured['params']


def test_update_skips_gdpr_text_when_unset():
    repo = CompanyRepository()
    captured = {}
    def fake_execute_many(work):
        cur = MagicMock(); cur.rowcount = 1
        work(cur)
        captured['sql'] = cur.execute.call_args[0][0]
        return True
    repo.execute_many = fake_execute_many
    repo.update(1, company='X')  # gdpr_text defaults to 'UNSET'
    assert 'gdpr_text' not in captured['sql']
