"""Routes for the courtesy-car rental tariff scheme: duration intervals,
categories, and the category×interval €/day price grid. GET feeds the Settings
"Tarife închiriere" editor + the car-form category dropdown; writes are admin
only. Mirrors routes/document_types.py."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..repositories.rental_category_repository import RentalCategoryRepository

_repo = RentalCategoryRepository()


def _is_admin():
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


def _admin_guard():
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    return None


# ── intervals ───────────────────────────────────────────────────────────────
@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/intervals', methods=['GET'])
@login_required
def api_list_rental_intervals():
    company_id = request.args.get('company_id', type=int)
    return jsonify({'success': True, 'intervals': _repo.list_intervals(company_id)})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/intervals', methods=['PUT'])
@login_required
def api_put_rental_interval():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        row = _repo.upsert_interval(
            d.get('company_id'), d.get('id'), (d.get('label') or '').strip(),
            d.get('min_days'), d.get('max_days'), d.get('sort_order'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'id': (row or {}).get('id')})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/intervals', methods=['DELETE'])
@login_required
def api_delete_rental_interval():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        _repo.delete_interval(d.get('company_id'), d.get('id'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


# ── categories ────────────────────────────────────────────────────────────────
@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['GET'])
@login_required
def api_list_rental_categories():
    company_id = request.args.get('company_id', type=int)
    active_only = request.args.get('active') in ('1', 'true', 'True')
    return jsonify({'success': True,
                    'categories': _repo.list_categories(company_id, active_only=active_only)})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['POST'])
@login_required
def api_add_rental_category():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        row = _repo.add_category(d.get('company_id'), d.get('name'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'id': (row or {}).get('id')})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['PUT'])
@login_required
def api_put_rental_category():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        _repo.upsert_category(
            d.get('company_id'), d.get('id'), d.get('name'), d.get('models_note'),
            d.get('franchise_eur'), d.get('extra_km_eur'),
            d.get('sort_order'), d.get('is_active', True))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['DELETE'])
@login_required
def api_delete_rental_category():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        _repo.delete_category(d.get('company_id'), d.get('id'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


# ── price cell ────────────────────────────────────────────────────────────────
@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/prices', methods=['PUT'])
@login_required
def api_set_rental_price():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    _repo.set_price(d.get('company_id'), d.get('category_id'),
                    d.get('interval_id'), d.get('eur_per_day'))
    logger.info('rental price set company=%s cat=%s iv=%s by %s',
                d.get('company_id'), d.get('category_id'), d.get('interval_id'),
                getattr(current_user, 'email', '?'))
    return jsonify({'success': True})
