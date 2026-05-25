"""Marketing project ↔ HR event linking routes + invoice search for budget."""

import logging
from datetime import datetime
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import ProjectEventRepository, ActivityRepository, BudgetRepository, ProjectRepository
from marketing.decorators import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response
from core.services.currency_converter import get_exchange_rate

logger = logging.getLogger('jarvis.marketing.routes.events')

_event_repo = ProjectEventRepository()
_activity_repo = ActivityRepository()
_budget_repo = BudgetRepository()
_project_repo = ProjectRepository()


# ---- Project ↔ HR Event links ----

@marketing_bp.route('/api/projects/<int:project_id>/events', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_project_events(project_id):
    """List HR events linked to a project."""
    events = _event_repo.get_by_project(project_id)
    return jsonify({'events': events})


@marketing_bp.route('/api/projects/<int:project_id>/events', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_link_event(project_id):
    """Link an HR event to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    event_id = data.get('event_id')
    if not event_id:
        return jsonify({'success': False, 'error': 'event_id is required'}), 400

    try:
        link_id = _event_repo.link(project_id, event_id, current_user.id, notes=data.get('notes'))
        if link_id is None:
            return jsonify({'success': False, 'error': 'Event already linked'}), 409
        _activity_repo.log(project_id, 'event_linked', actor_id=current_user.id,
                           details={'event_id': event_id})

        # Auto-create a budget line tracking this event's total cost.
        budget_line_id = None
        try:
            info = _event_repo.get_event_info(event_id)
            if info:
                cost_ron = float(info.get('event_cost') or 0)
                project = _project_repo.get_by_id(project_id)
                project_currency = (project.get('currency') or 'EUR').upper() if project else 'EUR'

                if project_currency != 'RON' and cost_ron > 0:
                    today = datetime.now().strftime('%Y-%m-%d')
                    eur_rate = get_exchange_rate('EUR', today)
                    if eur_rate and eur_rate > 0:
                        budget_cost = round(cost_ron / eur_rate, 2)
                    else:
                        budget_cost = cost_ron
                        project_currency = 'RON'
                else:
                    budget_cost = cost_ron

                budget_line_id = _budget_repo.create_for_event(
                    project_id=project_id,
                    event_id=event_id,
                    event_name=info.get('name') or f'Event #{event_id}',
                    event_cost=budget_cost,
                    currency=project_currency,
                )
        except Exception as budget_err:
            # Don't fail the link if budget-line creation hits an edge case.
            logger.warning('Auto budget line for event %s failed: %s', event_id, budget_err)

        return jsonify({'success': True, 'id': link_id, 'budget_line_id': budget_line_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/events/<int:event_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_unlink_event(project_id, event_id):
    """Remove an HR event link from a project."""
    if _event_repo.unlink(project_id, event_id):
        _activity_repo.log(project_id, 'event_unlinked', actor_id=current_user.id,
                           details={'event_id': event_id})
        # Remove the auto-generated budget line for this event (if any).
        try:
            _budget_repo.delete_for_event(project_id, event_id)
        except Exception as budget_err:
            logger.warning('Auto budget-line cleanup for event %s failed: %s', event_id, budget_err)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


@marketing_bp.route('/api/events/<int:event_id>/participants', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_event_participants(event_id):
    """Get participants for an HR event."""
    participants = _event_repo.get_event_participants(event_id)
    return jsonify({'participants': participants})


@marketing_bp.route('/api/hr-events/search', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_search_hr_events():
    """Search HR events for the linking picker."""
    q = request.args.get('q', '')
    limit = min(int(request.args.get('limit', 20)), 50)
    events = _event_repo.search_hr_events(query=q if q else None, limit=limit)
    return jsonify({'events': events})


# ---- Invoice search for budget linking ----

@marketing_bp.route('/api/invoices/search', methods=['GET'])
@login_required
@mkt_permission_required('budget', 'view')
def api_search_invoices():
    """Search invoices for linking to budget transactions."""
    q = request.args.get('q', '').strip()
    company = request.args.get('company')
    limit = min(int(request.args.get('limit', 20)), 50)

    invoices = _event_repo.search_invoices(query=q, company=company, limit=limit)
    return jsonify({'invoices': invoices})
