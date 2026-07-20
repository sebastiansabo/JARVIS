"""Routes for Foi de Parcurs settings: KM configs, company config, itinerary routes."""

from ._shared import foi_parcurs_bp, jsonify, request, login_required, logger, _dealer_repo, _vehicle_repo
from ..repositories import FoiParcursRepository

_repo = FoiParcursRepository()


# ════════════════════════════════════════════════════════════════
# Dealer config per company + brand (review link + contact for the email)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/dealer-config/<int:company_id>', methods=['GET'])
@login_required
def api_get_dealer_config(company_id):
    """Per-brand review link + contact for a company's linked brands."""
    return jsonify({'success': True, 'configs': _dealer_repo.list_for_company(company_id)})


@foi_parcurs_bp.route('/api/foi-parcurs/dealer-config/<int:company_id>/<int:brand_id>', methods=['PUT'])
@login_required
def api_put_dealer_config(company_id, brand_id):
    """Upsert the review link + contact for one (company, brand)."""
    data = request.get_json(silent=True) or {}
    _dealer_repo.upsert(
        company_id, brand_id,
        (data.get('review_url') or '').strip() or None,
        (data.get('address') or '').strip() or None,
        (data.get('phone') or '').strip() or None,
        (data.get('email') or '').strip() or None,
        show_in_foi_parcurs=bool(data.get('show_in_foi_parcurs', True)),
        general_conditions=(data.get('general_conditions') or '').strip() or None,
    )
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/general-conditions', methods=['GET'])
@login_required
def api_get_general_conditions():
    """Resolve the general-conditions text for the mobile Test Drive form.
    Brand is resolved from the vehicle (vin); a `brand` name param is accepted
    as a fallback. Returns '' when nothing is configured."""
    company_id = request.args.get('company_id', type=int)
    vin = (request.args.get('vin') or '').strip()
    brand = (request.args.get('brand') or '').strip()
    if vin and not brand:
        try:
            veh = _vehicle_repo.get_by_vin(vin)
            brand = (veh or {}).get('brand') or ''
        except Exception:
            logger.warning('general-conditions: vehicle lookup failed for vin=%s', vin, exc_info=True)
            brand = ''
    text = ''
    if company_id and brand:
        text = _dealer_repo.get_general_conditions(company_id, brand)
    return jsonify({'success': True, 'text': text, 'brand': brand})


def _company_gdpr_lookup(company_id: int) -> str:
    """The company's configured GDPR text ('' when unset/missing)."""
    try:
        from core.organization.repositories.company_repository import CompanyRepository
        row = CompanyRepository().get(company_id)
        return ((row or {}).get('gdpr_text') or '')
    except Exception:
        logger.warning('company-gdpr lookup failed for company_id=%s', company_id, exc_info=True)
        return ''


@foi_parcurs_bp.route('/api/foi-parcurs/company-gdpr', methods=['GET'])
@login_required
def api_get_company_gdpr():
    """Per-company GDPR text for the mobile Test Drive GDPR modal."""
    company_id = request.args.get('company_id', type=int)
    text = _company_gdpr_lookup(company_id) if company_id else ''
    return jsonify({'success': True, 'text': text})


# ════════════════════════════════════════════════════════════════
# KM Configs per company
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/km-configs', methods=['GET'])
@login_required
def api_get_km_configs():
    rows = _repo.query_all(
        'SELECT * FROM fp_km_configs ORDER BY company_id'
    )
    return jsonify({'configs': rows or []})


@foi_parcurs_bp.route('/api/foi-parcurs/km-configs/<int:company_id>', methods=['PUT'])
@login_required
def api_update_km_config(company_id):
    data = request.get_json(silent=True) or {}
    sql = '''
        INSERT INTO fp_km_configs (company_id, td_km_min, td_km_max, comodat_km_min, comodat_km_max, km_gap)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id) DO UPDATE SET
            td_km_min = EXCLUDED.td_km_min,
            td_km_max = EXCLUDED.td_km_max,
            comodat_km_min = EXCLUDED.comodat_km_min,
            comodat_km_max = EXCLUDED.comodat_km_max,
            km_gap = EXCLUDED.km_gap,
            updated_at = NOW()
    '''
    _repo.execute(sql, (
        company_id,
        data.get('td_km_min', 5),
        data.get('td_km_max', 50),
        data.get('comodat_km_min', 10),
        data.get('comodat_km_max', 200),
        data.get('km_gap', 20),
    ))
    return jsonify({'success': True})


# ════════════════════════════════════════════════════════════════
# Company config (base location, td radius, comodat avg km)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/company-config/<int:company_id>', methods=['GET'])
@login_required
def api_get_company_config(company_id):
    row = _repo.query_one(
        'SELECT * FROM fp_company_config WHERE company_id = %s', (company_id,)
    )
    if not row:
        row = {'company_id': company_id, 'base_location': '', 'td_radius_km': 50, 'comodat_avg_km': 150}
    return jsonify({'config': row})


@foi_parcurs_bp.route('/api/foi-parcurs/company-config/<int:company_id>', methods=['PUT'])
@login_required
def api_update_company_config(company_id):
    data = request.get_json(silent=True) or {}
    sql = '''
        INSERT INTO fp_company_config (company_id, base_location, td_radius_km, comodat_avg_km)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (company_id) DO UPDATE SET
            base_location = EXCLUDED.base_location,
            td_radius_km = EXCLUDED.td_radius_km,
            comodat_avg_km = EXCLUDED.comodat_avg_km,
            updated_at = NOW()
    '''
    _repo.execute(sql, (
        company_id,
        data.get('base_location', ''),
        data.get('td_radius_km', 50),
        data.get('comodat_avg_km', 150),
    ))
    return jsonify({'success': True})


# ════════════════════════════════════════════════════════════════
# Itinerary routes per company (Comodat manual routes)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/routes/<int:company_id>', methods=['GET'])
@login_required
def api_get_routes(company_id):
    route_type = request.args.get('route_type')
    if route_type:
        rows = _repo.query_all(
            'SELECT * FROM fp_routes WHERE company_id = %s AND route_type = %s ORDER BY id',
            (company_id, route_type),
        )
    else:
        rows = _repo.query_all(
            'SELECT * FROM fp_routes WHERE company_id = %s ORDER BY id',
            (company_id,),
        )
    return jsonify({'routes': rows or []})


@foi_parcurs_bp.route('/api/foi-parcurs/routes/<int:company_id>', methods=['POST'])
@login_required
def api_add_route(company_id):
    data = request.get_json(silent=True) or {}
    itinerary = (data.get('itinerary') or '').strip()
    route_type = data.get('route_type', 'Comodat')
    estimated_km = data.get('estimated_km')

    if not itinerary:
        return jsonify({'success': False, 'error': 'Itinerary is required'}), 400

    row = _repo.execute(
        'INSERT INTO fp_routes (company_id, route_type, itinerary, estimated_km) VALUES (%s, %s, %s, %s) RETURNING *',
        (company_id, route_type, itinerary, estimated_km),
        returning=True,
    )
    return jsonify({'success': True, 'route': row})


@foi_parcurs_bp.route('/api/foi-parcurs/routes/<int:route_id>', methods=['DELETE'])
@login_required
def api_delete_route(route_id):
    _repo.execute('DELETE FROM fp_routes WHERE id = %s', (route_id,))
    return jsonify({'success': True})


# ════════════════════════════════════════════════════════════════
# AI Itinerary generation (placeholder)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/generate-itinerary', methods=['POST'])
@login_required
def api_generate_itinerary():
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    route_type = data.get('route_type', 'TD')
    distance_km = data.get('distance_km', 30)

    # Get company config for base location
    config = _repo.query_one(
        'SELECT * FROM fp_company_config WHERE company_id = %s', (company_id,)
    )
    base = config['base_location'] if config and config.get('base_location') else 'Cluj-Napoca'

    # Simple placeholder: generate a round-trip itinerary
    if route_type == 'TD':
        itinerary = f"{base} - Test Drive ({distance_km}km) - {base}"
    else:
        itinerary = f"{base} - Comodat ({distance_km}km) - {base}"

    return jsonify({'success': True, 'itinerary': itinerary})
