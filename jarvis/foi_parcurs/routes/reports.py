"""Analytics / reports for Foi de Parcurs (driving sessions).

Read-only aggregates over foi_de_parcurs + fp_vehicles for the "Rapoarte" tab,
plus a drill-down that returns the individual sessions behind a leaderboard row.

Company scope is a HARD boundary here — unlike the group-wide session lists,
aggregated business metrics (utilization, revenue, per-company performance) must
not leak across tenants:

  * Group viewers (admin / superadmin / board) may report on any single company
    (?company_id=) or omit it for the whole group (company_id → None = all).
  * Everyone else is forced to their OWN company_id, whatever they pass; a user
    with no company on file is denied (403).

Rental revenue ("Venit închiriere") lives only on the Service pool, so it is
queried and returned ONLY when document_type == 'service'.
"""
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user, logger,
    _fp_repo, _vehicle_repo,
)
from core.roles.repositories import PermissionRepository
from ..services.route_sheet_service import overlap_rows, date_inversion_rows

# Roles that may pick any company / see the whole group, unconditionally.
_GROUP_ROLES = ('admin', 'superadmin', 'board')
# Any OTHER role can be opened up to the whole-group report view per-role via the
# Test Drive permission matrix: test_drive.reports.view_all. Instantiated at
# import like the repos in _shared (no DB work until a method is called).
_perm_repo = PermissionRepository()
_MAX_TOP = 50
_MAX_DRILL = 200


def _is_group_viewer():
    """True when the current user may report across companies (pass any company_id
    or omit it for the whole group); False pins them to their own company.

    Admin / superadmin / board keep group scope unconditionally. Every other role
    is own-company by default, unless its role is granted test_drive.reports.view_all
    in the permission matrix — letting admins hand the group report view to specific
    roles (e.g. a brand/sales lead) without a code change."""
    if (getattr(current_user, 'role_name', '') or '').lower() in _GROUP_ROLES:
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'test_drive', 'reports', 'view_all')
    return bool(perm.get('has_permission'))


def _scoped_company():
    """Resolve the company scope for the current user.

    Returns (company_id, is_group, error). Group viewers may pass any company_id
    (or None for the whole group); everyone else is pinned to their own company
    and gets a ready 403 tuple if they have none."""
    if _is_group_viewer():
        return request.args.get('company_id', type=int), True, None
    cid = getattr(current_user, 'company_id', None)
    if cid is None:
        return None, False, (jsonify({'success': False,
                                      'error': 'Nu aveți o companie asociată pentru rapoarte.'}), 403)
    return cid, False, None


@foi_parcurs_bp.route('/api/foi-parcurs/reports/summary', methods=['GET'])
@login_required
def api_reports_summary():
    """One-shot analytics payload for the Rapoarte tab (all blocks in a single
    round-trip), scoped and filtered by the query string."""
    company_id, is_group, err = _scoped_company()
    if err:
        return err

    document_type = (request.args.get('document_type') or 'sales').strip() or 'sales'
    date_from = (request.args.get('date_from') or '').strip() or None
    date_to = (request.args.get('date_to') or '').strip() or None
    odo_order = 'low' if (request.args.get('odo_order') or 'high').strip().lower() == 'low' else 'high'
    perf_status = (request.args.get('status') or '').strip() or None
    drive_type = (request.args.get('drive_type') or '').strip() or None
    brand = (request.args.get('brand') or '').strip() or None
    top = request.args.get('top', type=int) or 5
    top = max(1, min(top, _MAX_TOP))

    bundle = _fp_repo.report_bundle(company_id=company_id, date_from=date_from,
                                    date_to=date_to, document_type=document_type, top=top,
                                    perf_status=perf_status, drive_type=drive_type, brand=brand)
    fleet = _vehicle_repo.report_fleet(company_id=company_id, document_type=document_type,
                                       odo_order=odo_order, top=top, brand=brand)
    rental = (_fp_repo.report_rental(company_id=company_id, date_from=date_from, date_to=date_to, brand=brand)
              if document_type == 'service' else None)

    return jsonify({
        'success': True,
        'scope': {'company_id': company_id, 'is_group': is_group, 'document_type': document_type},
        **bundle,
        **fleet,
        'rental': rental,
    })


@foi_parcurs_bp.route('/api/foi-parcurs/reports/sessions', methods=['GET'])
@login_required
def api_reports_sessions():
    """Drill-down behind a leaderboard row: the individual sessions for ONE
    advisor (?advisor=) or ONE car (?vin=), same date/company/document scope as
    the summary. Powers the expandable Performanță consilieri / mașini cards."""
    company_id, _is_group, err = _scoped_company()
    if err:
        return err

    document_type = (request.args.get('document_type') or 'sales').strip() or 'sales'
    date_from = (request.args.get('date_from') or '').strip() or None
    date_to = (request.args.get('date_to') or '').strip() or None
    advisor = (request.args.get('advisor') or '').strip() or None
    vin = (request.args.get('vin') or '').strip() or None
    status = (request.args.get('status') or '').strip() or None
    drive_type = (request.args.get('drive_type') or '').strip() or None
    client_type = (request.args.get('client_type') or '').strip() or None
    brand = (request.args.get('brand') or '').strip() or None
    fuel_type = (request.args.get('fuel_type') or '').strip() or None
    if not any((advisor, vin, client_type, brand, fuel_type)):
        return jsonify({'success': True, 'sessions': []})

    sessions = _fp_repo.report_sessions(company_id=company_id, date_from=date_from,
                                        date_to=date_to, document_type=document_type,
                                        advisor=advisor, vin=vin, limit=_MAX_DRILL,
                                        status=status, drive_type=drive_type,
                                        client_type=client_type, brand=brand, fuel_type=fuel_type)
    return jsonify({'success': True, 'sessions': sessions})


@foi_parcurs_bp.route('/api/foi-parcurs/reports/reconciliation', methods=['GET'])
@login_required
def api_reports_reconciliation():
    """Reconciliation report for the Rapoarte tab — the two odometer anomalies the
    route-sheet ⚠️ badge fires on, per car: OVERLAPS (overlap_rows — a start km
    below where the car already was) and DATE INVERSIONS (date_inversion_rows — a
    higher-odometer drive dated before a lower-odometer one). Same scope/filters as
    the summary; both walks are pure, tested helpers."""
    company_id, is_group, err = _scoped_company()
    if err:
        return err

    document_type = (request.args.get('document_type') or 'sales').strip() or 'sales'
    date_from = (request.args.get('date_from') or '').strip() or None
    date_to = (request.args.get('date_to') or '').strip() or None
    brand = (request.args.get('brand') or '').strip() or None

    sessions = _fp_repo.sessions_for_reconciliation(
        company_id=company_id, date_from=date_from, date_to=date_to,
        document_type=document_type, brand=brand)

    by_vin = {}
    for s in sessions:
        by_vin.setdefault(s['vin'], []).append(s)
    cars = []
    for vin, rows in by_vin.items():
        overlaps = overlap_rows(rows)
        inversions = date_inversion_rows(rows)
        if not overlaps and not inversions:
            continue
        cars.append({
            'vin': vin,
            'model': rows[0].get('model') or '—',
            'count': len(overlaps),
            'total_overlap_km': sum(o['overlap_km'] for o in overlaps),
            'sessions': overlaps,
            'inversion_count': len(inversions),
            'inversions': inversions,
        })
    # Worst first: most overlap km, then most date inversions.
    cars.sort(key=lambda c: (c['total_overlap_km'], c['inversion_count']), reverse=True)

    return jsonify({
        'success': True,
        'scope': {'company_id': company_id, 'is_group': is_group, 'document_type': document_type},
        'cars': cars,
    })
