"""T6: the three real AAP contract templates are seeded (templatized) by
create_schema_buyback, idempotently.

DB-backed (see tests/buyback/conftest.py). Resolves company/brand BY NAME the
same way the seed does; skips if the real DB lacks those catalog rows (bare
environments), so the assertions only run where the seed could resolve them.
"""
import pytest

from database import get_db, get_cursor, release_db
from migrations.domains.schema_buyback import create_schema_buyback
from buyback.seed_contract_templates import seed_contract_templates
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


@pytest.mark.parametrize('autocommit', [True, False])
def test_seed_isolates_failing_spec(require_real_db, autocommit):
    """A spec whose INSERT fails (e.g. a UNIQUE race on concurrent boot) does
    not stop the others. Tested in both modes: autocommit=True (the real boot
    path — each statement independent) and autocommit=False (a transaction,
    where the per-spec SAVEPOINT prevents InFailedSqlTransaction cascading)."""
    conn = get_db()
    original_ac = conn.autocommit
    try:
        conn.autocommit = autocommit
        cur = get_cursor(conn)

        def _commit():
            if not autocommit:
                conn.commit()

        create_schema_buyback(conn, cur)
        _commit()
        intl, volvo = _resolve(cur, '%INTERNATIONAL%', 'Volvo')
        if not intl or not volvo:
            pytest.skip('International/Volvo absent on this DB')

        # scratch keys (not among the real _SPECS): clean so insertion is observable
        cur.execute("DELETE FROM buyback_contract_templates WHERE company_id=%s AND brand_id=%s "
                    "AND document_type IN ('purchase','consignment')", (intl, volvo))
        _commit()

        bad = ('%INTERNATIONAL%', 'Volvo', 'purchase',
               'X' * 300, 'corp {price_eur}', '')          # title > VARCHAR(255) -> real DB error
        good = ('%INTERNATIONAL%', 'Volvo', 'consignment',
                'ok', 'corp {owner_price} {commission}', '')
        seed_contract_templates(conn, cur, specs=[bad, good])
        _commit()

        # the good spec inserted despite the bad one failing -> no poisoning
        assert ContractTemplateRepository().get_active(intl, volvo, 'consignment') is not None
        # the connection is still usable
        cur.execute('SELECT 1')
        assert _scalar(cur.fetchone()) == 1

        cur.execute("DELETE FROM buyback_contract_templates WHERE company_id=%s AND brand_id=%s "
                    "AND document_type IN ('purchase','consignment')", (intl, volvo))
        _commit()
    finally:
        try:
            if not conn.autocommit:
                conn.rollback()
        except Exception:
            pass
        conn.autocommit = original_ac  # restore before returning to the pool
        release_db(conn)
