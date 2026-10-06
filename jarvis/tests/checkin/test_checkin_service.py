"""Strict location-only GPS check-in gate.

A punch is accepted ONLY when the user is inside a configured location's
radius (or matches its WiFi IP / QR token). There is NO per-user or
permission-based radius bypass — not for admins, not for any role.
"""
import inspect
from unittest.mock import MagicMock

from core.checkin.service import CheckinService

# Autoworld Audi coords (from check-in locations), 50 m radius.
_AUDI = {
    'id': 2, 'name': 'Autoworld Audi',
    'latitude': 46.7431658, 'longitude': 23.5925554,
    'allowed_radius_meters': 50, 'allowed_ips': [],
}


def _service(locations, today_punches=None):
    """CheckinService with a fully mocked repo (no DB)."""
    svc = CheckinService()
    svc.repo = MagicMock()
    svc.repo.get_biostar_user_id.return_value = {'biostar_user_id': 'b1'}
    svc.repo.get_active_locations.return_value = locations
    svc.repo.get_today_punches.return_value = today_punches or []
    svc.repo.insert_gps_punch.return_value = {'id': 1, 'biostar_event_id': 'e1'}
    return svc


def test_far_gps_punch_is_rejected():
    # ~2.5 km north of Audi — well outside the 50 m radius.
    svc = _service([_AUDI])
    res = svc.punch(jarvis_user_id=10, lat=46.7656, lng=23.5925, direction='IN')
    assert res['success'] is False
    assert 'Too far' in res['error']
    svc.repo.insert_gps_punch.assert_not_called()


def test_in_radius_gps_punch_is_accepted():
    # A few meters from Audi — inside the 50 m radius.
    svc = _service([_AUDI])
    res = svc.punch(jarvis_user_id=10, lat=46.74318, lng=23.59257, direction='IN')
    assert res['success'] is True
    assert res['direction'] == 'IN'
    svc.repo.insert_gps_punch.assert_called_once()


def test_qr_token_punch_still_works_without_gps():
    # The NFC endpoint (core/mobile/routes/checkin.py) punches via a
    # "checkin:<id>" QR token and no GPS. Removing the radius bypass must
    # not affect this location-bound path.
    svc = _service([_AUDI])
    res = svc.punch(jarvis_user_id=10, qr_token='checkin:2', direction='IN')
    assert res['success'] is True
    assert res['location'] == 'Autoworld Audi'
    svc.repo.insert_gps_punch.assert_called_once()


def test_punch_has_no_bypass_radius_parameter():
    # The radius bypass has been removed entirely — the signature must not
    # expose any way to skip the geofence.
    params = inspect.signature(CheckinService.punch).parameters
    assert 'bypass_radius' not in params
