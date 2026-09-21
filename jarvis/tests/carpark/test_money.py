"""Pure unit tests for carpark.money.net_buy (no DB)."""
from carpark.money import net_buy


def test_prefers_stored_net():
    assert net_buy({'purchase_price_net': 48500}) == 48500.0


def test_derives_net_from_gross_and_vat_when_net_missing():
    # 57715 gross / 1.19 = 48500 net
    v = {'purchase_price_net': None, 'acquisition_price': 57715, 'purchase_vat_rate': 19}
    assert round(net_buy(v), 2) == 48500.0


def test_no_vat_gross_equals_net():
    v = {'purchase_price_net': None, 'acquisition_price': 25900, 'purchase_vat_rate': 0}
    assert net_buy(v) == 25900.0


def test_missing_vat_treated_as_zero():
    v = {'purchase_price_net': None, 'acquisition_price': 10000}
    assert net_buy(v) == 10000.0


def test_no_prices_returns_zero():
    assert net_buy({'purchase_price_net': None, 'acquisition_price': None}) == 0.0
    assert net_buy({}) == 0.0
    assert net_buy(None) == 0.0
