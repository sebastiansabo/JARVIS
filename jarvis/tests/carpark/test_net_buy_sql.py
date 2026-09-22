"""DB-backed tests for carpark.money.NET_BUY_SQL — the SQL twin of net_buy().

Runs the fragment against an inline VALUES row (no vehicle seeding) so it stays
a focused unit test of the expression. Skips when localhost Postgres is absent.
"""
import pytest

from carpark.money import NET_BUY_SQL

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.skipif(
    not REAL_DB_AVAILABLE, reason='Real Postgres not available — skipping NET_BUY_SQL test')


def _net_buy_sql(currency, acq_price, ppn, kurs, vat):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            f"SELECT {NET_BUY_SQL} AS nb FROM (VALUES "
            "(%s::text, %s::numeric, %s::numeric, %s::numeric, %s::numeric)) "
            "AS v(acquisition_currency, acquisition_price, purchase_price_net, "
            "acquisition_exchange_rate, purchase_vat_rate)",
            (currency, acq_price, ppn, kurs, vat),
        )
        return float(cur.fetchone()['nb'])
    finally:
        release_db(conn)


def test_sql_canonical_prefers_stored_net():
    assert round(_net_buy_sql('EUR', 57715, 48500, None, 19), 2) == 48500.0


def test_sql_canonical_derives_net_from_gross_when_net_missing():
    # 57715 gross / 1.19 = 48500 net
    assert round(_net_buy_sql('EUR', 57715, None, None, 19), 2) == 48500.0


def test_sql_legacy_ron_net_from_net_lei_over_kurs():
    # RON: acquisition_price = NET LEI; net EUR = 500000 / 5.2439 = 95348.88
    # (purchase_price_net here is GROSS EUR and must be ignored on the RON path).
    assert round(_net_buy_sql('RON', 500000, 115372.15, 5.2439, 21), 2) == 95348.88


def test_sql_legacy_ron_without_kurs_falls_back_to_gross_eur_ppn():
    # No usable kurs → purchase_price_net holds GROSS EUR; 11900 / 1.19 = 10000
    assert round(_net_buy_sql('RON', 500000, 11900, 0, 19), 2) == 10000.0
