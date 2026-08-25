"""Analytics / reports for Foi de Parcurs (driving sessions).

Read-only aggregates over foi_de_parcurs + fp_vehicles for the "Rapoarte" tab.

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

# Roles that may pick any company / see the whole group. Board is included per
# the role-scoped design; everyone else is pinned to their own company.
_GROUP_ROLES = ('admin', 'superadmin', 'board')
_MAX_TOP = 50


def _is_group_viewer():
    return (getattr(current_user, 'role_name', '') or '').lower() in _GROUP_ROLES


@foi_parcurs_bp.route('/api/foi-parcurs/reports/summary', methods=['GET'])
@login_required
def api_reports_summary():
    """One-shot analytics payload for the Rapoarte tab (all blocks in a single
    round-trip), scoped and filtered by the query string."""
    is_group = _is_group_viewer()
    if is_group:
        company_id = request.args.get('company_id', type=int)  # may be None → whole group
    else:
        company_id = getattr(current_user, 'company_id', None)
        if company_id is None:
            return jsonify({'success': False,
                            'error': 'Nu aveți o companie asociată pentru rapoarte.'}), 403

    document_type = (request.args.get('document_type') or 'sales').strip() or 'sales'
    date_from = (request.args.get('date_from') or '').strip() or None
    date_to = (request.args.get('date_to') or '').strip() or None
    odo_order = 'low' if (request.args.get('odo_order') or 'high').strip().lower() == 'low' else 'high'
    top = request.args.get('top', type=int) or 5
    top = max(1, min(top, _MAX_TOP))

    bundle = _fp_repo.report_bundle(company_id=company_id, date_from=date_from,
                                    date_to=date_to, document_type=document_type, top=top)
    fleet = _vehicle_repo.report_fleet(company_id=company_id, document_type=document_type,
                                       odo_order=odo_order, top=top)
    rental = (_fp_repo.report_rental(company_id=company_id, date_from=date_from, date_to=date_to)
              if document_type == 'service' else None)

    return jsonify({
        'success': True,
        'scope': {'company_id': company_id, 'is_group': is_group, 'document_type': document_type},
        **bundle,
        **fleet,
        'rental': rental,
    })
