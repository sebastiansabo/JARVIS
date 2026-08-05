"""Field Sales client routes — 360, fiscal, refresh_fiscal, enrich, search."""

from ._shared import *  # noqa: F401, F403


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/360', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_360(client_id):
    """Get comprehensive 360-degree client view."""
    try:
        data = _client_repo.get_360(client_id)
        if not data.get('client'):
            return jsonify({'success': False, 'error': 'Client not found'}), 404
        return jsonify({'success': True, **data})
    except Exception as e:
        logger.exception('Error fetching client 360')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/fiscal', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_fiscal(client_id):
    """Get ANAF fiscal data for a client. Requires field_sales.fiscal.view."""
    try:
        if not _has_permission('field_sales', 'fiscal', 'view'):
            return jsonify({'success': False, 'error': 'Fiscal data access denied'}), 403

        profile = _client_repo.get_or_create_profile(client_id)
        cui = profile.get('cui')

        if not cui:
            return jsonify({'success': True, 'fiscal': None, 'message': 'No CUI on profile'})

        anaf_data = segmentation_service.get_or_refresh_anaf(client_id, cui, _client_repo)
        return jsonify({
            'success': True,
            'fiscal': anaf_data,
            'cui': cui,
            'fetched_at': profile.get('anaf_fetched_at'),
        })
    except Exception as e:
        logger.exception('Error fetching fiscal data')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/refresh-fiscal', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_client_refresh_fiscal(client_id):
    """Force-refresh ANAF fiscal data for a client. Requires field_sales.fiscal.view."""
    try:
        if not _has_permission('field_sales', 'fiscal', 'view'):
            return jsonify({'success': False, 'error': 'Fiscal data access denied'}), 403

        profile = _client_repo.get_or_create_profile(client_id)
        cui = profile.get('cui')

        if not cui:
            return jsonify({'success': True, 'fiscal': None, 'message': 'No CUI on profile'})

        # Force refresh by clearing the cache timestamp
        _client_repo.update_profile(client_id, {'anaf_fetched_at': None})
        anaf_data = segmentation_service.get_or_refresh_anaf(client_id, cui, _client_repo)
        return jsonify({
            'success': True,
            'fiscal': anaf_data,
            'cui': cui,
        })
    except Exception as e:
        logger.exception('Error refreshing fiscal data')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/enrich', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_client_enrich(client_id):
    """Trigger full client profile enrichment."""
    try:
        data = request.get_json(silent=True) or {}

        client = _client_repo.get_by_id(client_id)
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        company_name = data.get('company_name') or client.get('company_name') or client.get('display_name')
        cui = data.get('cui')

        if not cui:
            profile = _client_repo.get_or_create_profile(client_id)
            cui = profile.get('cui')

        # Check previous client_type before enrichment
        profile_before = _client_repo.get_or_create_profile(client_id)
        was_business = profile_before.get('client_type') == 'business'

        updated = segmentation_service.enrich_client_profile(
            client_id, company_name, cui, _client_repo
        )

        # Notify if client was newly identified as business
        if not was_business and updated and updated.get('client_type') == 'business':
            app = current_app._get_current_object()

            def _send_business_notification():
                notify_business_client_detected(
                    client_id,
                    client.get('display_name') or client.get('company_name') or 'Client',
                    updated,
                    triggered_by_user_id=_get_current_user().id,
                )

            _run_background(app, _send_business_notification)

        return jsonify({'success': True, 'profile': updated})
    except Exception as e:
        logger.exception('Error enriching client')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/companies', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_field_sales_companies():
    """List companies the current user may pick for tenant scoping, plus their default."""
    try:
        user = _get_current_user()
        is_admin = getattr(user, 'role_id', None) == 1
        companies = _client_repo.get_allowed_companies(user.id, is_admin)
        return jsonify({
            'success': True,
            'companies': companies,
            'default_company_id': user.company_id,
        })
    except Exception as e:
        logger.exception('Error fetching allowed companies')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/search', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_search():
    """Search clients by name, company, nr_reg, or CUI."""
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify({'success': False, 'error': 'Search query must be at least 2 characters'}), 400

        limit = request.args.get('limit', 20, type=int)
        limit = min(max(limit, 1), 100)
        company_id = request.args.get('company_id', type=int)

        results = _client_repo.search_clients(query, limit=limit, company_id=company_id)
        return jsonify({'success': True, 'clients': results, 'count': len(results)})
    except Exception as e:
        logger.exception('Error searching clients')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
