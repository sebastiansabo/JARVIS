import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
import foi_parcurs.routes.test_drive as td


def test_category_pricing_wins_when_car_has_category(monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'query_one',
                        lambda *a, **k: {'svc_km_included_day': 300, 'svc_extra_km_eur': None,
                                         'svc_deposit_eur': 400, 'svc_franchise_eur': None})
    monkeypatch.setattr(td._rc_repo, 'price_for',
                        lambda cid, cat, days: {'eur_per_day': 33, 'interval_id': 1,
                                                'interval_label': '1-8 zile',
                                                'franchise_eur': 250, 'extra_km_eur': 0.25})
    veh = {'rental_category_id': 7, 'svc_tariff_eur_day': 999}   # legacy value ignored
    out = td._resolve_service_pricing(
        veh, 11, '2026-02-01T09:00:00', '2026-02-05T09:00:00', {})
    assert out['svc_tariff_eur'] == 33          # from category, not 999
    assert out['svc_units'] == 4
    assert out['svc_total_eur'] == 132.0
    assert out['svc_fransiza_eur'] == 250       # category franchise
    assert out['svc_garantie_eur'] == 400       # deposit from policy


def test_falls_back_to_legacy_when_no_category(monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'query_one',
                        lambda *a, **k: {'svc_km_included_day': 300})
    monkeypatch.setattr(td._rc_repo, 'price_for',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('should not call')))
    veh = {'svc_tariff_eur_day': 40}   # no rental_category_id
    out = td._resolve_service_pricing(
        veh, 11, '2026-02-01T09:00:00', '2026-02-03T09:00:00', {})
    assert out['svc_tariff_eur'] == 40          # legacy per-car path
    assert out['svc_rate_basis'] == 'day'
