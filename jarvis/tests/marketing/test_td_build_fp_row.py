"""Unit tests for TdBookingService._build_fp_row — the pure mapping from a
confirmed booking to the PLANNED foi_de_parcurs row. No DB / app context needed:
the method only reads its dict arguments, so we call it on a bare instance.

Regression cover for the public-TD data-propagation bug: a public booking must
carry the customer's identity onto the fișă so the staff Activate form prefills
it (client_id links the CRM client the confirm flow already created; client_email
is the customer's email). Before the fix, client_id was hardcoded None and email
was never mapped, so the Activate form's Client section came up empty.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone  # noqa: E402

from marketing.services.td_booking_service import TdBookingService  # noqa: E402


def _build(*, crm_client_id, extra_answers=None):
    svc = object.__new__(TdBookingService)  # no __init__ / DB
    booking = {
        'id': 42,
        'customer_name': 'Roxana Biris',
        'customer_phone_e164': '+40738764546',
        'customer_email': 'roxana@example.com',
        'extra_answers': extra_answers or {},
    }
    page = {'company_id': 10, 'event_id': None, 'project_id': None}
    car = {'vin': 'TESTVIN0001', 'default_advisor_user_id': None}
    slot = {
        'starts_at': datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc),
        'ends_at': datetime(2026, 9, 30, 8, 30, tzinfo=timezone.utc),
    }
    return svc._build_fp_row(booking, page, car, slot, 'Margineanu Irina',
                             crm_client_id=crm_client_id)


def test_build_fp_row_links_the_crm_client():
    row = _build(crm_client_id=77)
    assert row['client_id'] == 77


def test_build_fp_row_carries_customer_email():
    row = _build(crm_client_id=77)
    assert row['client_email'] == 'roxana@example.com'


def test_build_fp_row_client_id_none_when_crm_create_failed():
    # _find_or_create_crm_client is best-effort and may return None; the fișă
    # must still be insertable (text identity carries name/phone).
    row = _build(crm_client_id=None)
    assert row['client_id'] is None
    assert row['client_name'] == 'Roxana Biris'
    assert row['client_email'] == 'roxana@example.com'
