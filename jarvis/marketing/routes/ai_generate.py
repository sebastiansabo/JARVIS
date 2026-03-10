"""AI campaign generation route."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error

logger = logging.getLogger('jarvis.marketing.routes.ai_generate')


@marketing_bp.route('/api/projects/generate', methods=['POST'])
@login_required
@mkt_permission_required('project', 'create')
def api_generate_campaign():
    """Generate a complete campaign from an AI prompt.

    Expects JSON body:
    {
        "prompt": "Launch campaign for Audi Q5 Sportback ...",
        "total_budget": 50000,
        "currency": "EUR",
        "start_date": "2026-04-01",
        "end_date": "2026-06-30",
        "company_id": 1,
        "responsible_ids": [5, 12],       // optional
        "stakeholder_ids": [3, 8],        // optional
        "product": "Audi Q5 Sportback",   // optional extra context
        "scope": "Brand awareness + lead generation"  // optional
    }

    Returns:
        { success: true, id: <new_project_id>, preview: <ai_output> }
    """
    data, error = get_json_or_error()
    if error:
        return error

    # Validate required fields
    prompt = data.get('prompt', '').strip()
    total_budget = data.get('total_budget')
    currency = data.get('currency', 'RON')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    company_id = data.get('company_id')

    if not prompt:
        return jsonify({'success': False, 'error': 'prompt is required'}), 400
    if total_budget is None:
        return jsonify({'success': False, 'error': 'total_budget is required'}), 400
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'start_date and end_date are required'}), 400
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id is required'}), 400

    try:
        from marketing.services.campaign_generator import generate_campaign, persist_campaign
        from marketing.repositories import KpiRepository

        kpi_repo = KpiRepository()
        kpi_defs = kpi_repo.get_definitions(active_only=True)
        kpi_defs_list = [
            {
                'id': d['id'], 'name': d['name'], 'slug': d['slug'],
                'unit': d['unit'], 'direction': d['direction'],
                'formula': d.get('formula'),
            }
            for d in kpi_defs
        ]

        extra_context = {}
        if data.get('product'):
            extra_context['product'] = data['product']
        if data.get('scope'):
            extra_context['scope'] = data['scope']
        if data.get('area'):
            extra_context['area'] = data['area']

        # Step 1: Generate campaign structure via AI
        ai_result = generate_campaign(
            prompt=prompt,
            total_budget=total_budget,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            company_id=company_id,
            owner_id=current_user.id,
            kpi_definitions=kpi_defs_list,
            responsible_ids=data.get('responsible_ids'),
            stakeholder_ids=data.get('stakeholder_ids'),
            extra_context=extra_context,
        )

        # Step 2: Persist to database
        project_id = persist_campaign(
            ai_result=ai_result,
            company_id=company_id,
            owner_id=current_user.id,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            total_budget=total_budget,
            kpi_definitions=kpi_defs_list,
            responsible_ids=data.get('responsible_ids'),
            stakeholder_ids=data.get('stakeholder_ids'),
        )

        return jsonify({
            'success': True,
            'id': project_id,
            'preview': {
                'name': ai_result.get('name'),
                'description': ai_result.get('description'),
                'channels': ai_result.get('channel_mix', []),
                'budget_lines_count': len(ai_result.get('budget_lines', [])),
                'kpis_count': len(ai_result.get('kpis', [])),
                'objectives_count': len(ai_result.get('objectives', [])),
            },
        }), 201

    except ValueError as e:
        logger.error(f'Campaign generation failed: {e}')
        return jsonify({'success': False, 'error': str(e)}), 422
    except Exception as e:
        logger.error(f'Campaign generation error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Generation failed: {str(e)}'}), 500
