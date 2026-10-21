"""Admin contract-template GET/PUT route tests."""
import pytest

pytestmark = pytest.mark.usefixtures('require_real_db')


def test_admin_can_upsert_and_list_template(client, as_role):
    as_role('Admin', 1)
    r = client.put('/api/buyback/contract-templates/7?company_id=1', json={
        'document_type': 'purchase', 'title': 'Achizitie',
        'body_template': 'Vanzator {seller_name} ... pret {price_eur}',
        'general_conditions': 'GC', 'is_active': True,
    })
    assert r.status_code == 200, r.get_json()
    lst = client.get('/api/buyback/contract-templates?company_id=1').get_json()['templates']
    assert any(t['brand_id'] == 7 and t['document_type'] == 'purchase'
               and t['title'] == 'Achizitie' for t in lst)


def test_bad_document_type_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.put('/api/buyback/contract-templates/7?company_id=1',
                   json={'document_type': 'nonsense'})
    assert r.status_code == 400


def test_non_admin_put_is_403(client, as_role):
    as_role('Acquisition', company_id=1)   # no can_access_settings
    r = client.put('/api/buyback/contract-templates/7?company_id=1',
                   json={'document_type': 'purchase'})
    assert r.status_code == 403
