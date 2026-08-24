"""Pure-logic units for the Service courtesy-car rental pricing service."""
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from datetime import datetime, timedelta

from foi_parcurs.services.rental_pricing import (
    rental_days,
    resolve_policy,
    compute_service_pricing,
)


class TestRentalDays:
    def test_less_than_one_hour_rounds_up_to_one(self):
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = datetime(2026, 1, 1, 8, 30)
        assert rental_days(departure, return_dt) == 1

    def test_exactly_24_hours_is_one_day(self):
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(hours=24)
        assert rental_days(departure, return_dt) == 1

    def test_25_hours_rounds_up_to_two_days(self):
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(hours=25)
        assert rental_days(departure, return_dt) == 2

    def test_30_days_is_30(self):
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=30)
        assert rental_days(departure, return_dt) == 30

    def test_sub_day_remainder_rounds_up(self):
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=5, hours=1)
        assert rental_days(departure, return_dt) == 6

    def test_accepts_iso_strings(self):
        assert rental_days('2026-01-01T08:00:00', '2026-01-02T08:00:00') == 1

    def test_accepts_iso_strings_with_trailing_z(self):
        assert rental_days('2026-01-01T08:00:00Z', '2026-01-02T09:00:00Z') == 2

    def test_negative_or_zero_span_is_still_min_one_day(self):
        departure = datetime(2026, 1, 1, 8, 0)
        assert rental_days(departure, departure) == 1
        assert rental_days(departure, departure - timedelta(hours=2)) == 1

    def test_mixed_aware_string_and_naive_datetime_does_not_crash(self):
        # tz-aware ISO string departure + naive datetime return: normalized to
        # naive wall-clock so the subtraction never raises. 2 days apart -> 2.
        assert rental_days('2026-01-01T10:00:00Z', datetime(2026, 1, 3, 10, 0, 0)) == 2


class TestResolvePolicy:
    def test_vehicle_value_wins(self):
        vehicle = {'svc_km_included_day': 200, 'svc_extra_km_eur': 0.5,
                    'svc_deposit_eur': 500, 'svc_franchise_eur': 300}
        company_policy = {'svc_km_included_day': 100, 'svc_extra_km_eur': 0.3,
                           'svc_deposit_eur': 400, 'svc_franchise_eur': 250}
        resolved = resolve_policy(vehicle, company_policy)
        assert resolved == {
            'km_included_day': 200,
            'extra_km_eur': 0.5,
            'deposit_eur': 500,
            'franchise_eur': 300,
        }

    def test_none_on_vehicle_falls_back_to_company_default(self):
        vehicle = {'svc_km_included_day': None, 'svc_extra_km_eur': None,
                    'svc_deposit_eur': None, 'svc_franchise_eur': None}
        company_policy = {'svc_km_included_day': 100, 'svc_extra_km_eur': 0.3,
                           'svc_deposit_eur': 400, 'svc_franchise_eur': 250}
        resolved = resolve_policy(vehicle, company_policy)
        assert resolved == {
            'km_included_day': 100,
            'extra_km_eur': 0.3,
            'deposit_eur': 400,
            'franchise_eur': 250,
        }

    def test_none_on_both_is_none(self):
        vehicle = {}
        company_policy = {}
        resolved = resolve_policy(vehicle, company_policy)
        assert resolved == {
            'km_included_day': None,
            'extra_km_eur': None,
            'deposit_eur': None,
            'franchise_eur': None,
        }

    def test_missing_keys_treated_as_none(self):
        vehicle = {'svc_km_included_day': 150}
        company_policy = {'svc_extra_km_eur': 0.4}
        resolved = resolve_policy(vehicle, company_policy)
        assert resolved == {
            'km_included_day': 150,
            'extra_km_eur': 0.4,
            'deposit_eur': None,
            'franchise_eur': None,
        }


class TestComputeServicePricing:
    def _policy_free_vehicle(self, **overrides):
        vehicle = {
            'svc_tariff_eur_day': 40,
            'svc_tariff_eur_month': 700,
            'svc_km_included_day': None,
            'svc_extra_km_eur': None,
            'svc_deposit_eur': None,
            'svc_franchise_eur': None,
        }
        vehicle.update(overrides)
        return vehicle

    def test_day_basis_5_days(self):
        vehicle = self._policy_free_vehicle()
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=5)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'day'
        assert result['svc_units'] == 5
        assert result['svc_tariff_eur'] == 40
        assert result['svc_total_eur'] == 200

    def test_29_days_stays_day_basis(self):
        vehicle = self._policy_free_vehicle()
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=29)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'day'
        assert result['svc_units'] == 29
        assert result['svc_total_eur'] == 40 * 29

    def test_reversed_span_bills_one_day_non_negative_total(self):
        vehicle = self._policy_free_vehicle()
        company_policy = {}
        departure = datetime(2026, 1, 5, 8, 0)
        return_dt = datetime(2026, 1, 1, 8, 0)  # return before departure
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'day'
        assert result['svc_units'] == 1
        assert result['svc_total_eur'] == 40
        assert result['svc_total_eur'] >= 0

    def test_month_basis_exactly_30_days(self):
        vehicle = self._policy_free_vehicle()
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=30)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'month'
        assert result['svc_units'] == 1
        assert result['svc_tariff_eur'] == 700
        assert result['svc_total_eur'] == 700

    def test_month_basis_45_days_ceils_to_two_units(self):
        vehicle = self._policy_free_vehicle()
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=45)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'month'
        assert result['svc_units'] == 2
        assert result['svc_total_eur'] == 1400

    def test_total_day_rate_40_times_5(self):
        vehicle = self._policy_free_vehicle(svc_tariff_eur_day=40)
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=5)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_total_eur'] == 200

    def test_total_month_rate_700_times_2(self):
        vehicle = self._policy_free_vehicle(svc_tariff_eur_month=700)
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=45)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_total_eur'] == 1400

    def test_none_daily_rate_gives_total_zero_no_crash(self):
        vehicle = self._policy_free_vehicle(svc_tariff_eur_day=None)
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=5)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'day'
        assert result['svc_tariff_eur'] == 0
        assert result['svc_total_eur'] == 0

    def test_none_monthly_rate_gives_total_zero_no_crash(self):
        vehicle = self._policy_free_vehicle(svc_tariff_eur_month=None)
        company_policy = {}
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=30)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_rate_basis'] == 'month'
        assert result['svc_total_eur'] == 0

    def test_merges_resolved_policy_fields(self):
        vehicle = self._policy_free_vehicle(
            svc_km_included_day=None, svc_extra_km_eur=None,
            svc_deposit_eur=None, svc_franchise_eur=None,
        )
        company_policy = {
            'svc_km_included_day': 150, 'svc_extra_km_eur': 0.4,
            'svc_deposit_eur': 500, 'svc_franchise_eur': 300,
        }
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=5)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_km_included_day'] == 150
        assert result['svc_extra_km_eur'] == 0.4
        assert result['svc_garantie_eur'] == 500
        assert result['svc_fransiza_eur'] == 300

    def test_vehicle_policy_overrides_company_default(self):
        vehicle = self._policy_free_vehicle(
            svc_km_included_day=200, svc_deposit_eur=700,
        )
        company_policy = {
            'svc_km_included_day': 150, 'svc_deposit_eur': 500,
        }
        departure = datetime(2026, 1, 1, 8, 0)
        return_dt = departure + timedelta(days=5)
        result = compute_service_pricing(vehicle, company_policy, departure, return_dt)
        assert result['svc_km_included_day'] == 200
        assert result['svc_garantie_eur'] == 700

    def test_accepts_iso_string_datetimes(self):
        vehicle = self._policy_free_vehicle()
        company_policy = {}
        result = compute_service_pricing(
            vehicle, company_policy, '2026-01-01T08:00:00Z', '2026-01-06T08:00:00Z'
        )
        assert result['svc_rate_basis'] == 'day'
        assert result['svc_units'] == 5
        assert result['svc_total_eur'] == 200
