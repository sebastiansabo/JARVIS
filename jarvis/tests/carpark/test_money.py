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


def test_legacy_ron_row_net_from_net_lei_over_kurs():
    # Legacy editor convention: acquisition_price = NET LEI, purchase_price_net =
    # GROSS EUR, currency 'RON'. Net EUR = NET LEI / kurs (NOT purchase_price_net,
    # which is gross EUR). Mirrors vehicle 15: 500000 / 5.2439 = 95348.88.
    v = {
        'acquisition_currency': 'RON',
        'acquisition_price': 500000,
        'purchase_price_net': 115372.15,  # GROSS EUR — must be ignored on the RON path
        'acquisition_exchange_rate': 5.2439,
        'purchase_vat_rate': 21,
    }
    assert round(net_buy(v), 2) == 95348.88  # 500000 / 5.2439


def test_legacy_ron_row_without_kurs_falls_back_to_gross_eur_ppn():
    # No usable kurs → purchase_price_net holds the GROSS EUR paid; derive net.
    # 11900 gross / 1.19 = 10000 net.
    v = {
        'acquisition_currency': 'RON',
        'acquisition_price': 500000,  # NET LEI, but unusable without a kurs
        'purchase_price_net': 11900,  # GROSS EUR fallback
        'acquisition_exchange_rate': 0,
        'purchase_vat_rate': 19,
    }
    assert round(net_buy(v), 2) == 10000.0
