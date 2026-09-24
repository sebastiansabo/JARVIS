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
from marketing.repositories.td_booking_repository import TdBookingRepository, TdConflict
from marketing.services.td_slot_service import TdSlotService
from marketing.services.td_booking_service import TdBookingService
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from core.organization.manager_utils import get_actable_company_ids

_repo = TdBookingRepository()
_slots = TdSlotService()
_svc = TdBookingService()
_fp = FoiParcursRepository()


def _allowed_companies():
    """The caller's company scope: None means "all" (Admin/superadmin bypass),
    otherwise the get_actable_company_ids() set. List endpoints call this once and
    filter against the returned set (rather than _may_act_on_company per row)."""
    if (getattr(current_user, 'role_name', '') or '').lower() in ('admin', 'superadmin'):
        return None
    return get_actable_company_ids(current_user.id)


def _may_act_on_company(company_id):
    allowed = _allowed_companies()
    return allowed is None or company_id in allowed


def _scoped_page(pid):
    """Load a page and enforce the caller may act on its company. Returns
    (page, None) or (None, error_response). 404 (not 403) everywhere so an outsider
    can't enumerate which ids exist across companies."""
    page = _repo.get_page(pid)
    if not page or not _may_act_on_company(page['company_id']):
        return None, (jsonify({'error': 'not found'}), 404)
    return page, None


def _scoped_by_page_id(page_id):
    """Scope an entity whose page_id was resolved from a child row (car/window/
    waitlist)."""
    if page_id is None:
        return None, (jsonify({'error': 'not found'}), 404)
    return _scoped_page(page_id)


def _scoped_booking(bid):
    """Load a booking and enforce the caller may act on its page's company."""
    booking = _repo.get_booking(bid)
    if not booking:
        return None, (jsonify({'error': 'not found'}), 404)
    _, err = _scoped_page(booking['page_id'])
    if err:
        return None, err
    return booking, None


# ---- pages ----

@marketing_bp.route('/api/td/pages', methods=['POST'])
@login_required
def td_create_page():
    data = request.get_json(silent=True) or {}
    try:
        company_id = int(data.get('company_id'))
    except (TypeError, ValueError):
        company_id = None
    if not company_id or not data.get('slug'):
        return jsonify({'error': 'company_id and slug required'}), 400
    if not _may_act_on_company(company_id):
        return jsonify({'error': 'not found'}), 404
    data['created_by'] = current_user.id
    page = _repo.create_page(data)
    return jsonify(page), 201


@marketing_bp.route('/api/td/pages', methods=['GET'])
@login_required
def td_list_pages():
    allowed = _allowed_companies()
    pages = _repo.list_pages(request.args.get('company_id', type=int))
    if allowed is not None:
        pages = [p for p in pages if p['company_id'] in allowed]
    return jsonify({'pages': pages})


@marketing_bp.route('/api/td/pages/<int:pid>', methods=['PATCH'])
@login_required
def td_update_page(pid):
    _, err = _scoped_page(pid)
    if err:
        return err
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
    _, err = _scoped_page(pid)
    if err:
        return err
    page = _repo.set_page_status(pid, status)
    if not page:
        return jsonify({'error': 'not found'}), 404
    # Auto-materialize on open so a staff member never ends up with an "open"
    # event that shows zero slots because they forgot the Materialize step.
    if status == 'open':
        _slots.materialize_slots(pid)
    return jsonify(page)


# ---- cars ----

@marketing_bp.route('/api/td/pages/<int:pid>/cars', methods=['POST'])
@login_required
def td_add_car(pid):
    d = request.get_json(silent=True) or {}
    if not d.get('vin'):
        return jsonify({'error': 'vin required'}), 400
    _, err = _scoped_page(pid)
    if err:
        return err
    car = _repo.add_car(pid, d['vin'], d.get('vehicle_id'),
                         d.get('default_advisor_user_id'), d.get('sort_order', 0))
    # Keep slots in sync for the new car, and warn (non-blocking) if the car is
    # already committed to another driving session during the event's windows.
    _slots.materialize_slots(pid)
    conflicts = _fp.find_sessions_overlapping_event(d['vin'], pid)
    return jsonify({**car, 'conflicts': conflicts}), 201


@marketing_bp.route('/api/td/cars/<int:cid>', methods=['DELETE'])
@login_required
def td_remove_car(cid):
    car = _repo.get_car(cid)
    _, err = _scoped_by_page_id(car['page_id'] if car else None)
    if err:
        return err
    _repo.remove_car(cid)
    return jsonify({'ok': True})


@marketing_bp.route('/api/td/pages/<int:pid>/cars', methods=['GET'])
@login_required
def td_list_cars(pid):
    _, err = _scoped_page(pid)
    if err:
        return err
    # Attach any driving-session conflicts per car (a car already booked during
    # the event's windows shows no slots on the public form) so the admin can
    # flag it. Few cars per event, so the per-car check is fine.
    cars = _repo.list_cars(pid)
    for c in cars:
        c['conflicts'] = _fp.find_sessions_overlapping_event(c['vin'], pid)
    return jsonify({'cars': cars})


# ---- windows ----

@marketing_bp.route('/api/td/pages/<int:pid>/windows', methods=['POST'])
@login_required
def td_add_window(pid):
    d = request.get_json(silent=True) or {}
    if not d.get('window_date') or not d.get('start_time') or not d.get('end_time'):
        return jsonify({'error': 'window_date, start_time and end_time required'}), 400
    _, err = _scoped_page(pid)
    if err:
        return err
    w = _repo.add_window(pid, d['window_date'], d['start_time'], d['end_time'],
                          d.get('slot_minutes'))
    # A new window has no slots until materialized — do it now so the event is
    # immediately bookable.
    _slots.materialize_slots(pid)
    return jsonify(w), 201


@marketing_bp.route('/api/td/pages/<int:pid>/windows', methods=['GET'])
@login_required
def td_list_windows(pid):
    _, err = _scoped_page(pid)
    if err:
        return err
    return jsonify({'windows': _repo.list_windows(pid), 'slot_count': _repo.count_slots(pid)})


@marketing_bp.route('/api/td/windows/<int:wid>', methods=['DELETE'])
@login_required
def td_remove_window(wid):
    w = _repo.query_one('SELECT page_id FROM mkt_td_booking_windows WHERE id=%s', (wid,))
    _, err = _scoped_by_page_id(w['page_id'] if w else None)
    if err:
        return err
    _repo.delete_window(wid)
    return jsonify({'ok': True})


# ---- materialize ----

@marketing_bp.route('/api/td/pages/<int:pid>/materialize', methods=['POST'])
@login_required
def td_materialize(pid):
    _, err = _scoped_page(pid)
    if err:
        return err
    return jsonify({'inserted': _slots.materialize_slots(pid)})


# ---- calendar overlay ----

@marketing_bp.route('/api/td/calendar-events', methods=['GET'])
@login_required
def td_calendar_events():
    """Active Event TD pages (one band per event car) overlapping [from, to],
    for the Driving Hub Calendar overlay. Mirrors the calendar's own filters:
    company_id + date range."""
    company_id = request.args.get('company_id', type=int)
    frm = request.args.get('from')
    to = request.args.get('to')
    if not company_id or not frm or not to:
        return jsonify({'error': 'company_id, from and to required'}), 400
    if not _may_act_on_company(company_id):
        return jsonify({'error': 'not found'}), 404
    return jsonify({'events': _repo.list_events_for_calendar(company_id, frm, to)})


# ---- bookings ----

@marketing_bp.route('/api/td/pages/<int:pid>/bookings', methods=['GET'])
@login_required
def td_list_bookings(pid):
    _, err = _scoped_page(pid)
    if err:
        return err
    return jsonify({'bookings': _repo.list_bookings(pid, request.args.get('status'))})


@marketing_bp.route('/api/td/pages/<int:pid>/open-slots', methods=['GET'])
@login_required
def td_list_open_slots(pid):
    """Open (unbooked) slots for the reservation editor's move/swap picker.
    Company-scoped like the mutation endpoints."""
    page = _repo.get_page(pid)
    if not page or not _may_act_on_company(page['company_id']):
        return jsonify({'error': 'not found'}), 404
    return jsonify({'slots': _repo.list_open_slots(pid)})


# ---- waitlist ----

@marketing_bp.route('/api/td/pages/<int:pid>/waitlist', methods=['GET'])
@login_required
def td_list_waitlist(pid):
    _, err = _scoped_page(pid)
    if err:
        return err
    return jsonify({'waitlist': _repo.list_waitlist(pid)})


@marketing_bp.route('/api/td/waitlist/<int:wid>', methods=['PATCH'])
@login_required
def td_update_waitlist(wid):
    status = (request.get_json(silent=True) or {}).get('status')
    if status not in ('new', 'contacted', 'done', 'dismissed'):
        return jsonify({'error': 'bad status'}), 400
    wl = _repo.query_one('SELECT page_id FROM mkt_td_waitlist WHERE id=%s', (wid,))
    _, err = _scoped_by_page_id(wl['page_id'] if wl else None)
    if err:
        return err
    row = _repo.set_waitlist_status(wid, status, getattr(current_user, 'id', None))
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(row)


@marketing_bp.route('/api/td/bookings/<int:bid>/advisor', methods=['PATCH'])
@login_required
def td_reassign_advisor(bid):
    uid = (request.get_json(silent=True) or {}).get('advisor_user_id')
    if not uid:
        return jsonify({'error': 'advisor_user_id required'}), 400
    booking, err = _scoped_booking(bid)
    if err:
        return err
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


@marketing_bp.route('/api/td/bookings/<int:bid>', methods=['DELETE'])
@login_required
def td_delete_booking(bid):
    """Remove a reservation (any status, even confirmed): soft-cancel the booking
    (frees the slot) + hard-delete its linked PLANNED fișă. Company-scoped."""
    booking, err = _scoped_booking(bid)
    if err:
        return err
    _svc.admin_delete_booking(booking)
    return jsonify({'ok': True})


@marketing_bp.route('/api/td/bookings/<int:bid>', methods=['PATCH'])
@login_required
def td_edit_booking(bid):
    """Edit a reservation (any status). Applies whichever fields are present, each
    cascading onto the linked fișă: client contact (name/phone/email), slot_id
    (move time / swap car -- a slot is car+interval), and status (confirm/cancel).
    Company-scoped; 400 on bad input, 409 on a slot/car conflict."""
    booking, err = _scoped_booking(bid)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        if any(k in data for k in ('name', 'phone', 'email')):
            _svc.admin_update_contact(booking, name=data.get('name'),
                                      phone=data.get('phone'), email=data.get('email'))
            booking = _repo.get_booking(bid)
        if data.get('slot_id') is not None:
            _svc.admin_reassign_slot(booking, int(data['slot_id']))
            booking = _repo.get_booking(bid)
        if data.get('status') is not None:
            _svc.admin_set_status(booking, data['status'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except TdConflict as e:
        return jsonify({'error': str(e)}), 409
    return jsonify({'ok': True, 'booking': _repo.get_booking(bid)})
