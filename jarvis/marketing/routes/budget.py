"""Marketing budget lines + transactions routes."""

import logging
from datetime import datetime
from flask import jsonify, request, g
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import BudgetRepository, ActivityRepository, ProjectRepository, ProjectEventRepository
from marketing.decorators import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response
from core.services.currency_converter import get_exchange_rate

logger = logging.getLogger('jarvis.marketing.routes.budget')

_budget_repo = BudgetRepository()
_activity_repo = ActivityRepository()
_project_repo = ProjectRepository()
_event_repo = ProjectEventRepository()


# ---- Budget Lines ----

@marketing_bp.route('/api/projects/<int:project_id>/budget-lines', methods=['GET'])
@login_required
@mkt_permission_required('budget', 'view')
def api_get_budget_lines(project_id):
    """Get all budget lines for a project, auto-syncing event costs."""
    _sync_event_line_costs(project_id)
    lines = _budget_repo.get_lines_by_project(project_id)
    return jsonify({'budget_lines': lines})


def _sync_event_line_costs(project_id):
    """Re-sync event-sourced budget lines with current event cost + BNR rate."""
    try:
        lines = _budget_repo.get_lines_by_project(project_id)
        event_lines = [l for l in lines if (l.get('metadata') or {}).get('source') == 'event']
        if not event_lines:
            return

        project = _project_repo.get_by_id(project_id)
        project_currency = (project.get('currency') or 'EUR').upper() if project else 'EUR'

        eur_rate = None
        if project_currency != 'RON':
            today = datetime.now().strftime('%Y-%m-%d')
            eur_rate = get_exchange_rate('EUR', today)

        for line in event_lines:
            event_id = (line.get('metadata') or {}).get('event_id')
            if not event_id:
                continue
            info = _event_repo.get_event_info(int(event_id))
            if not info:
                continue
            cost_ron = float(info.get('event_cost') or 0)
            if project_currency != 'RON' and cost_ron > 0 and eur_rate and eur_rate > 0:
                new_cost = round(cost_ron / eur_rate, 2)
                new_currency = project_currency
            else:
                new_cost = cost_ron
                new_currency = 'RON' if project_currency == 'RON' else project_currency

            current = float(line.get('planned_amount') or 0)
            if abs(current - new_cost) > 0.01:
                _budget_repo.update_line(line['id'], planned_amount=new_cost, currency=new_currency)
    except Exception as e:
        logger.warning('Event line cost sync failed for project %s: %s', project_id, e)


@marketing_bp.route('/api/projects/<int:project_id>/budget-lines', methods=['POST'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_create_budget_line(project_id):
    """Add a budget line to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    channel = data.get('channel')
    if not channel:
        return jsonify({'success': False, 'error': 'channel is required'}), 400

    try:
        line_id = _budget_repo.create_line(
            project_id=project_id,
            channel=channel,
            description=data.get('description'),
            department_structure_id=data.get('department_structure_id'),
            agency_name=data.get('agency_name'),
            planned_amount=data.get('planned_amount', 0),
            currency=data.get('currency', 'RON'),
            period_type=data.get('period_type', 'campaign'),
            period_start=data.get('period_start'),
            period_end=data.get('period_end'),
            notes=data.get('notes'),
        )
        _activity_repo.log(project_id, 'budget_added', actor_id=current_user.id,
                           details={'channel': channel, 'amount': data.get('planned_amount', 0)})
        return jsonify({'success': True, 'id': line_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/budget-lines/<int:line_id>', methods=['PUT'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_update_budget_line(project_id, line_id):
    """Update a budget line."""
    data, error = get_json_or_error()
    if error:
        return error

    try:
        updated = _budget_repo.update_line(line_id, **data)
        if updated:
            _activity_repo.log(project_id, 'budget_modified', actor_id=current_user.id,
                               details={'line_id': line_id, 'fields': list(data.keys())})
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Budget line not found'}), 404
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/budget-lines/<int:line_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_delete_budget_line(project_id, line_id):
    """Delete a budget line."""
    if _budget_repo.delete_line(line_id):
        _activity_repo.log(project_id, 'budget_modified', actor_id=current_user.id,
                           details={'action': 'deleted', 'line_id': line_id})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Budget line not found'}), 404


# ---- Budget Transactions ----

@marketing_bp.route('/api/budget-lines/<int:line_id>/transactions', methods=['GET'])
@login_required
@mkt_permission_required('budget', 'view')
def api_get_transactions(line_id):
    """Get transactions for a budget line."""
    txs = _budget_repo.get_transactions(line_id)
    return jsonify({'transactions': txs})


@marketing_bp.route('/api/budget-lines/<int:line_id>/transactions', methods=['POST'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_create_transaction(line_id):
    """Record a spend transaction against a budget line."""
    data, error = get_json_or_error()
    if error:
        return error

    amount = data.get('amount')
    transaction_date = data.get('transaction_date')
    if amount is None or not transaction_date:
        return jsonify({'success': False, 'error': 'amount and transaction_date are required'}), 400

    try:
        tx_id = _budget_repo.create_transaction(
            budget_line_id=line_id,
            amount=amount,
            transaction_date=transaction_date,
            recorded_by=current_user.id,
            direction=data.get('direction', 'debit'),
            source=data.get('source', 'manual'),
            reference_id=data.get('reference_id'),
            invoice_id=data.get('invoice_id'),
            description=data.get('description'),
        )

        # Log activity on parent project
        line = _budget_repo.get_line_by_id(line_id)
        if line:
            _activity_repo.log(line['project_id'], 'spend_recorded', actor_id=current_user.id,
                               details={'channel': line['channel'], 'amount': float(amount)})

        return jsonify({'success': True, 'id': tx_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/budget-transactions/<int:tx_id>/link-invoice', methods=['PUT'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_link_transaction_invoice(tx_id):
    """Link or unlink an invoice to a budget transaction."""
    data, error = get_json_or_error()
    if error:
        return error
    invoice_id = data.get('invoice_id')  # null to unlink
    if _budget_repo.link_transaction_invoice(tx_id, invoice_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Transaction not found'}), 404


@marketing_bp.route('/api/budget-transactions/<int:tx_id>/link-file', methods=['PUT'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_link_transaction_file(tx_id):
    """Link or unlink a project file to a budget transaction."""
    data, error = get_json_or_error()
    if error:
        return error
    file_id = data.get('file_id')  # null to unlink
    if _budget_repo.link_transaction_file(tx_id, file_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Transaction not found'}), 404


@marketing_bp.route('/api/budget-transactions/<int:tx_id>', methods=['PUT'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_update_transaction(tx_id):
    """Update a budget transaction (amount, date, description)."""
    data, error = get_json_or_error()
    if error:
        return error
    try:
        if _budget_repo.update_transaction(tx_id, **data):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Transaction not found or no changes'}), 404
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/budget-transactions/<int:tx_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('budget', 'edit')
def api_delete_transaction(tx_id):
    """Delete a budget transaction."""
    if _budget_repo.delete_transaction(tx_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Transaction not found'}), 404
