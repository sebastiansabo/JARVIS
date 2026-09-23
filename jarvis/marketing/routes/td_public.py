"""Public (unauthenticated) test-drive booking API. Never returns 401.

Mirrors forms/routes/public.py's no-auth pattern: every handler here is
reachable by an anonymous customer following an emailed link or the public
`/td/<slug>` page, so a bad slug/token must resolve to 404/409/410 -- never
401. The SPA frontend hard-redirects any 401 response straight to /login,
which would strand an anonymous customer on a page they were never meant to
authenticate into.

Tenant/resource identity (company, car, advisor) is always resolved
server-side from the page `slug` (GET/POST /pages/<slug>...) or the signed
booking `token` (confirm/cancel) via TdBookingService/TdBookingRepository --
nothing identity-bearing is ever trusted from the request body, which only
supplies the customer's own contact details.
"""
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from marketing.services.td_booking_service import TdBookingService
from marketing.repositories.td_booking_repository import TdBookingRepository
from marketing.services.td_slot_service import TdSlotService

td_public_bp = Blueprint('td_public', __name__)

_svc = TdBookingService()
_repo = TdBookingRepository()
_slots = TdSlotService()


def _client_ip() -> str:
    """Best-effort client IP, honoring a single-hop X-Forwarded-For (as set
    by the app's own reverse proxy) -- mirrors forms/routes/public.py."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    return ip or '0.0.0.0'


def _result_response(result):
    """ServiceResult -> (body, status). Uses `is not None` (not truthiness)
    so a legitimately empty-but-present data dict isn't swallowed."""
    body = result.data if result.data is not None else {'error': result.error}
    return jsonify(body), result.status_code


@td_public_bp.route('/pages/<slug>', methods=['GET'])
def get_page(slug):
    """Public page config + live availability.

    404 (never 401) when the slug doesn't exist or the page isn't open, so an
    anonymous visitor can't distinguish "wrong slug" from "not published yet".
    """
    page = _repo.get_page_by_slug(slug)
    if not page or page['status'] != 'open':
        return jsonify({'error': 'not found'}), 404
    cars = _repo.list_cars_with_vehicle(page['id'])
    slots = _slots.available_slots(page['id'], datetime.now(timezone.utc))
    return jsonify({
        'page': {
            'title': page.get('title'),
            'intro': page.get('intro'),
            'thank_you': page.get('thank_you'),
            'logo_url': page.get('logo_url'),
            'company_name': _repo.get_company_name(page['company_id']),
            'gdpr_text': _repo.get_company_gdpr_text(page['company_id']),
        },
        'cars': [_car_public(c) for c in cars],
        'slots': slots,
    }), 200


def _car_public(car) -> dict:
    """Shape a joined car row for the public page: a friendly make/model label
    (VIN fallback when the fleet row has no make/model) and an optional plate."""
    label = f"{(car.get('mark') or '').strip()} {(car.get('model') or '').strip()}".strip()
    return {
        'id': car['id'],
        'vin': car['vin'],
        'label': label or car['vin'],
        'plate': car.get('registration_number'),
    }


@td_public_bp.route('/pages/<slug>/bookings', methods=['POST'])
def submit_booking(slug):
    """Submit a booking request. Body: {slot_id, name, phone, email, utm,
    license, license_expiry?, gdpr_consent, conditions_accepted}.

    The service re-validates the page/slot server-side from `slug`; the
    company/car/advisor are never taken from the body.

    Legal fields are required for a customer-facing booking: the driving-licence
    serie & number must be present and both consents (GDPR + test-drive
    conditions) must be explicitly given, else 422 with a Romanian message. They
    ride along in extra_answers and are mapped onto the fișă at confirm.
    """
    data = request.get_json(silent=True) or {}
    required = ('slot_id', 'name', 'phone', 'email')
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'missing fields'}), 400
    try:
        slot_id = int(data['slot_id'])
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid slot_id'}), 400
    license_str = (data.get('license') or '').strip()
    if not license_str:
        return jsonify({'error': 'Seria și numărul permisului de conducere sunt obligatorii.'}), 422
    if not data.get('gdpr_consent'):
        return jsonify({'error': 'Trebuie să fiți de acord cu prelucrarea datelor personale (GDPR).'}), 422
    if not data.get('conditions_accepted'):
        return jsonify({'error': 'Trebuie să acceptați condițiile de test drive.'}), 422
    extra_answers = {
        'license': license_str,
        'license_expiry': (data.get('license_expiry') or '').strip() or None,
        'gdpr_consent': True,
        'conditions_accepted': True,
    }
    result = _svc.submit_booking(
        slug, slot_id, data['name'], data['phone'], data['email'],
        data.get('utm') or {}, _client_ip(), request.headers.get('User-Agent', ''),
        request.host_url.rstrip('/'), extra_answers=extra_answers)
    return _result_response(result)


@td_public_bp.route('/bookings/confirm', methods=['POST'])
def confirm_booking():
    """Confirm a pending booking from its signed one-tap token."""
    token = (request.get_json(silent=True) or {}).get('token', '')
    result = _svc.confirm_booking(token, request.host_url.rstrip('/'))
    return _result_response(result)


@td_public_bp.route('/bookings/cancel', methods=['POST'])
def cancel_booking():
    """Cancel a pending/confirmed booking from its signed one-tap token."""
    token = (request.get_json(silent=True) or {}).get('token', '')
    result = _svc.cancel_booking(token)
    return _result_response(result)
