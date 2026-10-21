"""T6: the three real AAP contract templates are seeded (templatized) by
create_schema_buyback, idempotently.

DB-backed (see tests/buyback/conftest.py). Resolves company/brand BY NAME the
same way the seed does; skips if the real DB lacks those catalog rows (bare
environments), so the assertions only run where the seed could resolve them.
"""
import pytest

from database import get_db, get_cursor, release_db
from migrations.domains.schema_buyback import create_schema_buyback
from buyback.repositories.contract_template_repository import ContractTemplateRepository


def _scalar(row):
    if row is None:
        return None
    return row[0] if not isinstance(row, dict) else list(row.values())[0]


def _resolve(cur, company_like, brand_name):
    cur.execute('SELECT id FROM companies WHERE company ILIKE %s ORDER BY id LIMIT 1',
                (company_like,))
    company_id = _scalar(cur.fetchone())
    cur.execute('SELECT id FROM brands WHERE name ILIKE %s ORDER BY id LIMIT 1',
                (brand_name,))
    brand_id = _scalar(cur.fetchone())
    return company_id, brand_id


def test_three_contract_templates_seeded_and_idempotent(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        create_schema_buyback(conn, cur)
        create_schema_buyback(conn, cur)  # idempotent: re-run must not duplicate
        conn.commit()

        intl, vw = _resolve(cur, '%INTERNATIONAL%', 'Volkswagen (PKW)')
        _, dwa = _resolve(cur, '%INTERNATIONAL%', 'DasWeltAuto')
        prestige, volvo = _resolve(cur, '%PRESTIGE%', 'Volvo')
        if not all((intl, vw, dwa, prestige, volvo)):
            pytest.skip('seed catalog (International/Prestige + brands) absent on this DB')

        repo = ContractTemplateRepository()

        # consignment seed carries the depozit-only tokens
        dep = repo.get_active(intl, vw, 'consignment')
        assert dep is not None, 'consignment template not seeded'
        assert '{owner_price}' in dep['body_template']
        assert '{commission}' in dep['body_template']

        # purchase seeds carry the price + seller tokens
        pur = repo.get_active(intl, dwa, 'purchase')
        assert pur is not None, 'DWA purchase template not seeded'
        assert '{price_eur}' in pur['body_template']
        assert '{seller_name}' in pur['body_template']

        ante = repo.get_active(prestige, volvo, 'purchase')
        assert ante is not None, 'Volvo antecontract not seeded'
        assert '{price_eur}' in ante['body_template']

        # idempotency: exactly one row per seeded key after two schema runs
        for co, br, dt in ((intl, vw, 'consignment'), (intl, dwa, 'purchase'),
                           (prestige, volvo, 'purchase')):
            cur.execute(
                'SELECT COUNT(*) FROM buyback_contract_templates '
                'WHERE company_id = %s AND brand_id = %s AND document_type = %s',
                (co, br, dt))
            assert _scalar(cur.fetchone()) == 1
    finally:
        release_db(conn)
