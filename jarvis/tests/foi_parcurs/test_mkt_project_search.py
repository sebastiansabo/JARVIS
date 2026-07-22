import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


class FakeRepo:
    def __init__(self):
        self.last_sql = None
        self.last_params = None

    def query_all(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        return [{'id': 7, 'name': 'Audi Q6 Launch', 'status': 'active',
                 'company_id': 11, 'brand_id': 7}]


@pytest.fixture
def client(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(td_mod, '_fp_repo', fake)
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app._fake_repo = fake
    return app.test_client()


def test_search_returns_projects(client):
    r = client.get('/api/foi-parcurs/mkt-projects/search?q=Audi&company_id=11')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['projects'][0]['name'] == 'Audi Q6 Launch'


def test_search_scopes_by_company(client):
    client.get('/api/foi-parcurs/mkt-projects/search?company_id=11')
    fake = client.application._fake_repo
    assert 'company_id = %s OR %s = ANY(company_ids)' in fake.last_sql
    # company_id appears twice (direct + array), then the limit
    assert fake.last_params[0] == 11 and fake.last_params[1] == 11


def test_search_ignores_short_query(client):
    # q shorter than 2 chars must not add a name filter
    client.get('/api/foi-parcurs/mkt-projects/search?q=a&company_id=11')
    fake = client.application._fake_repo
    assert 'ILIKE' not in fake.last_sql
