"""Field Sales manager routes — overview, clients."""

from ._shared import *  # noqa: F401, F403


@field_sales_bp.route('/api/field-sales/manager/overview', methods=['GET'])
@jwt_or_login_required
@field_sales_manager_required
def api_manager_overview():
    """Get manager overview of all KAM visits in a date range."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        if not date_from or not date_to:
            return jsonify({'success': False, 'error': 'date_from and date_to are required'}), 400

        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        kam_id = request.args.get('kam_id', type=int)
        company_id = request.args.get('company_id', type=int)

        # Enforce the manager's team.view scope: 'own' → only self; 'department'
        # → only the manager's own company (overrides any requested company_id);
        # 'all' → unrestricted. Fail closed if a scoped manager has no company.
        scope = getattr(g, 'permission_scope', 'all')
        if scope == 'own':
            kam_id = _get_current_user().id
        elif scope == 'department':
            company_id = getattr(_get_current_user(), 'company_id', None)
            if company_id is None:
                return jsonify({'success': True, 'visits': [],
                                'summary': {'total': 0, 'by_status': {}, 'by_kam': {}}})

        visits = _visit_repo.get_team_visits(date_from, date_to, kam_id=kam_id, company_id=company_id)

        # Compute summary stats
        total = len(visits)
        by_status = {}
        by_kam = {}
        for v in visits:
            st = v.get('status', 'unknown')
            by_status[st] = by_status.get(st, 0) + 1

            kam_name = v.get('kam_name', 'Unknown')
            if kam_name not in by_kam:
                by_kam[kam_name] = {'total': 0, 'completed': 0, 'in_progress': 0, 'planned': 0}
            by_kam[kam_name]['total'] += 1
            if st in by_kam[kam_name]:
                by_kam[kam_name][st] += 1

        return jsonify({
            'success': True,
            'visits': visits,
            'summary': {
                'total': total,
                'by_status': by_status,
                'by_kam': by_kam,
            },
        })
    except Exception as e:
        logger.exception('Error fetching manager overview')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/manager/clients', methods=['GET'])
@jwt_or_login_required
@field_sales_manager_required
def api_manager_clients():
    """Get clients with profiles for manager view, with filtering."""
    try:
        priority = request.args.get('priority')
        country_code = request.args.get('country_code')
        min_renewal_score = request.args.get('min_renewal_score', type=int)
        assigned_kam_id = request.args.get('assigned_kam_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        if priority and priority not in ('low', 'medium', 'high'):
            return jsonify({'success': False, 'error': 'Invalid priority. Use low/medium/high'}), 400

        clients, total = _client_repo.get_managed_clients(
            priority=priority,
            country_code=country_code,
            min_renewal_score=min_renewal_score,
            assigned_kam_id=assigned_kam_id,
            limit=min(max(limit, 1), 200),
            offset=max(offset, 0),
        )

        return jsonify({
            'success': True,
            'clients': clients,
            'total': total,
        })
    except Exception as e:
        logger.exception('Error fetching manager clients')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
