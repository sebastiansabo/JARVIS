"""Staff admin for public test-drive booking pages (Driving Hub home).

Attached to the shared `marketing_bp` (so URLs are `/marketing/api/td/...`),
gated `@login_required` only -- matching the existing foi_parcurs TD routes'
auth level (foi_parcurs/routes/test_drive.py), not the marketing module's
`mkt_permission_required` scheme. Tightening this to a v2 permission is a
follow-up (see spec Sec.8 note).

Routes stay thin: all persistence goes through TdBookingRepository /
TdSlotService / FoiParcursRepository. The one bit of cross-module logic here
is `td_reassign_advisor`, which keeps a confirmed booking's linked
`foi_de_parcurs.advisor_name` in sync with `mkt_td_bookings.advisor_user_id`
so the no-show cron (which reads `advisor_name` off the FP row) notifies the
newly-assigned advisor instead of the original one.
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories.td_booking_repository import TdBookingRepository
from marketing.services.td_slot_service import TdSlotService
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository

_repo = TdBookingRepository()
_slots = TdSlotService()
_fp = FoiParcursRepository()


# ---- pages ----

@marketing_bp.route('/api/td/pages', methods=['POST'])
@login_required
def td_create_page():
    data = request.get_json(silent=True) or {}
    if not data.get('company_id') or not data.get('slug'):
        return jsonify({'error': 'company_id and slug required'}), 400
    data['created_by'] = current_user.id
    page = _repo.create_page(data)
    return jsonify(page), 201


@marketing_bp.route('/api/td/pages', methods=['GET'])
@login_required
def td_list_pages():
    return jsonify({'pages': _repo.list_pages(request.args.get('company_id', type=int))})


@marketing_bp.route('/api/td/pages/<int:pid>', methods=['PATCH'])
@login_required
def td_update_page(pid):
    page = _repo.update_page(pid, request.get_json(silent=True) or {})
    if not page:
        return jsonify({'error': 'not found'}), 404
    return jsonify(page)


@marketing_bp.route('/api/td/pages/<int:pid>/status', methods=['POST'])
@login_required
def td_set_status(pid):
    status = (request.get_json(silent=True) or {}).get('status')
    if status not in ('draft', 'open', 'closed'):
        return jsonify({'error': 'bad status'}), 400
    page = _repo.set_page_status(pid, status)
    if not page:
        return jsonify({'error': 'not found'}), 404
    return jsonify(page)


# ---- cars ----

@marketing_bp.route('/api/td/pages/<int:pid>/cars', methods=['POST'])
@login_required
def td_add_car(pid):
    d = request.get_json(silent=True) or {}
    if not d.get('vin'):
        return jsonify({'error': 'vin required'}), 400
    car = _repo.add_car(pid, d['vin'], d.get('vehicle_id'),
                         d.get('default_advisor_user_id'), d.get('sort_order', 0))
    return jsonify(car), 201


@marketing_bp.route('/api/td/cars/<int:cid>', methods=['DELETE'])
@login_required
def td_remove_car(cid):
    _repo.remove_car(cid)
    return jsonify({'ok': True})


@marketing_bp.route('/api/td/pages/<int:pid>/cars', methods=['GET'])
@login_required
def td_list_cars(pid):
    return jsonify({'cars': _repo.list_cars(pid)})


# ---- windows ----

@marketing_bp.route('/api/td/pages/<int:pid>/windows', methods=['POST'])
@login_required
def td_add_window(pid):
    d = request.get_json(silent=True) or {}
    if not d.get('window_date') or not d.get('start_time') or not d.get('end_time'):
        return jsonify({'error': 'window_date, start_time and end_time required'}), 400
    w = _repo.add_window(pid, d['window_date'], d['start_time'], d['end_time'],
                          d.get('slot_minutes'))
    return jsonify(w), 201


@marketing_bp.route('/api/td/pages/<int:pid>/windows', methods=['GET'])
@login_required
def td_list_windows(pid):
    return jsonify({'windows': _repo.list_windows(pid)})


# ---- materialize ----

@marketing_bp.route('/api/td/pages/<int:pid>/materialize', methods=['POST'])
@login_required
def td_materialize(pid):
    return jsonify({'inserted': _slots.materialize_slots(pid)})


# ---- bookings ----

@marketing_bp.route('/api/td/pages/<int:pid>/bookings', methods=['GET'])
@login_required
def td_list_bookings(pid):
    return jsonify({'bookings': _repo.list_bookings(pid, request.args.get('status'))})


@marketing_bp.route('/api/td/bookings/<int:bid>/advisor', methods=['PATCH'])
@login_required
def td_reassign_advisor(bid):
    uid = (request.get_json(silent=True) or {}).get('advisor_user_id')
    if not uid:
        return jsonify({'error': 'advisor_user_id required'}), 400
    booking = _repo.get_booking(bid)
    if not booking:
        return jsonify({'error': 'not found'}), 404
    _repo.execute(
        'UPDATE mkt_td_bookings SET advisor_user_id=%s, updated_at=NOW() WHERE id=%s',
        (uid, bid))
    # Keep the FP row's advisor_name in sync so the no-show cron (which reads
    # advisor_name off foi_de_parcurs, not the booking) notifies the new user.
    if booking.get('foi_de_parcurs_id'):
        user = _repo.query_one('SELECT name FROM users WHERE id=%s', (uid,))
        _fp.execute('UPDATE foi_de_parcurs SET advisor_name=%s WHERE id=%s',
                    ((user or {}).get('name', ''), booking['foi_de_parcurs_id']))
    return jsonify({'ok': True})
