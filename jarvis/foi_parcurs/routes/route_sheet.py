"""Monthly *Foaie de Parcurs* generation routes (per car): AI-drafted PDF
(persisted to fp_route_sheets), a deterministic Excel, and a list of stored
sheets for a period. Regenerating overwrites the stored copy."""
from flask import Response
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..services.route_sheet_service import generate_and_store, render_xlsx, list_stored, redistribute_gap


@foi_parcurs_bp.route('/api/foi-parcurs/route-sheet/pdf', methods=['POST'])
@login_required
def api_route_sheet_pdf():
    """Return the stored monthly sheet (or build + persist it). `regenerate`
    rebuilds from the current sessions and overwrites the stored copy."""
    data = request.get_json(silent=True) or {}
    vin = (data.get('vin') or '').strip()
    year, month = data.get('year'), data.get('month')
    if not vin or not year or not month:
        return jsonify({'success': False, 'error': 'vin, year, month sunt obligatorii'}), 400
    try:
        pdf = generate_and_store(
            vin, int(year), int(month),
            user_id=getattr(current_user, 'id', None),
            user_name=(getattr(current_user, 'name', None) or getattr(current_user, 'email', None)),
            regenerate=bool(data.get('regenerate')),
            norma=data.get('norma'),
            alimentari=data.get('alimentari') or [],
            events=data.get('events') or [],
        )
    except Exception as e:
        logger.exception('Route-sheet PDF failed for %s %s-%s', vin, year, month)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return Response(pdf, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="foaie-parcurs-{vin}-{year}-{int(month):02d}.pdf"',
    })


@foi_parcurs_bp.route('/api/foi-parcurs/route-sheet/xlsx', methods=['GET'])
@login_required
def api_route_sheet_xlsx():
    """Deterministic monthly route-sheet workbook for one car (no AI)."""
    vin = (request.args.get('vin') or '').strip()
    year, month = request.args.get('year', type=int), request.args.get('month', type=int)
    if not vin or not year or not month:
        return jsonify({'success': False, 'error': 'vin, year, month sunt obligatorii'}), 400
    try:
        content = render_xlsx(vin, year, month)
    except Exception as e:
        logger.exception('Route-sheet XLSX failed for %s %s-%s', vin, year, month)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return Response(
        content,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="foaie-parcurs-{vin}-{year}-{month:02d}.xlsx"'},
    )


@foi_parcurs_bp.route('/api/foi-parcurs/route-sheet/redistribute-gap', methods=['POST'])
@login_required
def api_redistribute_gap():
    """Split an odometer gap's mileage into up to 3 synthetic 'gap-fill'
    sessions (date / driver / km range). They then appear as normal sessions and
    the gap shrinks/closes on the next route-sheet regeneration."""
    data = request.get_json(silent=True) or {}
    vin = (data.get('vin') or '').strip()
    year, month = data.get('year'), data.get('month')
    contracts = data.get('contracts') or []
    if not vin or not year or not month or not contracts:
        return jsonify({'success': False, 'error': 'vin, year, month și minim un contract sunt obligatorii'}), 400
    if len(contracts) > 3:
        return jsonify({'success': False, 'error': 'Maxim 3 șoferi per gap'}), 400
    try:
        n = redistribute_gap(vin, int(year), int(month), contracts,
                             user_name=(getattr(current_user, 'name', None) or getattr(current_user, 'email', None)))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Gap redistribute failed for %s %s-%s', vin, year, month)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return jsonify({'success': True, 'inserted': n})


@foi_parcurs_bp.route('/api/foi-parcurs/route-sheets', methods=['GET'])
@login_required
def api_route_sheets_list():
    """Stored monthly sheets for a period — used to flag which cars are saved."""
    company_id = request.args.get('company_id', type=int)
    year, month = request.args.get('year', type=int), request.args.get('month', type=int)
    if not year or not month:
        return jsonify({'success': False, 'error': 'year, month sunt obligatorii'}), 400
    try:
        sheets = list_stored(company_id or None, year, month)
    except Exception as e:
        logger.exception('Route-sheet list failed for %s %s-%s', company_id, year, month)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return jsonify({'success': True, 'sheets': sheets})
