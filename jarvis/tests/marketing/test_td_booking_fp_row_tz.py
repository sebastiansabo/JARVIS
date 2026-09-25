"""Confirm must write the fișă departure/return as NAIVE Bucharest wall-clock.

TD slots are stored tz-aware in UTC, but foi_de_parcurs stores TD datetimes as
naive Bucharest wall-clock -- the Hub / SessionDetailModal read them via naiveDate
and never shift the zone (see foi_parcurs/routes/test_drive.py: "TD datetimes are
stored and compared as Bucharest wall-clock"). If _build_fp_row copied the slot's
raw UTC value onto the fișă, a 09:00-local slot would land at 06:00 -- 3h early,
i.e. "outside project hours" and wrong in the staff detail modal.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone  # noqa: E402

from marketing.services.td_booking_service import TdBookingService  # noqa: E402


def _row(starts_at, ends_at):
    svc = TdBookingService()
    return svc._build_fp_row(
        booking={'id': 1, 'customer_name': 'Ion', 'customer_phone_e164': '+40712345678',
                 'customer_email': None, 'extra_answers': {'license': 'AB1'}},
        page={'company_id': 1, 'event_id': None, 'project_id': None},
        car={'vin': 'VIN1'},
        slot={'starts_at': starts_at, 'ends_at': ends_at},
        advisor_name='Adv')


def test_departure_return_are_naive_bucharest_wall_clock():
    # 06:00Z / 06:30Z == 09:00 / 09:30 Europe/Bucharest (UTC+3 on 1 Oct 2026).
    row = _row(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc),
               datetime(2026, 10, 1, 6, 30, tzinfo=timezone.utc))
    assert row['departure_datetime'] == datetime(2026, 10, 1, 9, 0)
    assert row['return_datetime'] == datetime(2026, 10, 1, 9, 30)
    assert row['departure_datetime'].tzinfo is None
    assert row['return_datetime'].tzinfo is None


def test_accepts_iso_string_slot_times():
    # BaseRepository serializes timestamptz to ISO strings; confirm may see either.
    row = _row('2026-10-01T06:00:00+00:00', '2026-10-01T06:30:00+00:00')
    assert row['departure_datetime'] == datetime(2026, 10, 1, 9, 0)
    assert row['return_datetime'] == datetime(2026, 10, 1, 9, 30)
    assert row['departure_datetime'].tzinfo is None
