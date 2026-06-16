"""Bugetare Bulk Processing Routes.

Part of JARVIS Accounting Section > Bugetare Application.
Routes for bulk invoice processing, export, and AI campaign matching.
"""
import json
import re
from datetime import datetime
from flask import render_template, jsonify, request, redirect, url_for, flash, Response, stream_with_context
from flask_login import login_required, current_user

from . import bugetare_bp
from core.utils.api_helpers import safe_error_response


# ============== Page Routes ==============

@bugetare_bp.route('/bulk')
@login_required
def bulk_processor():
    """Redirect to React accounting dashboard."""
    return redirect('/app/accounting')


# ============== API Routes ==============

@bugetare_bp.route('/api/bulk/process', methods=['POST'])
@login_required
def api_bulk_process():
    """Process multiple uploaded invoices and return summary."""
    from accounting.bugetare.bulk_processor import process_bulk_invoices
    from database import refresh_connection_pool

    if 'files[]' not in request.files:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400

    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'error': 'No files selected'}), 400

    # Collect file data
    file_data = []
    for f in files:
        if f.filename and f.filename.lower().endswith('.pdf'):
            file_bytes = f.read()
            file_data.append((file_bytes, f.filename))

    if not file_data:
        return jsonify({'success': False, 'error': 'No valid PDF files found'}), 400

    try:
        report = process_bulk_invoices(file_data)
        # Refresh connection pool after bulk processing
        refresh_connection_pool()
        return jsonify({
            'success': True,
            'report': {
                'invoices': [{
                    'filename': inv.get('filename'),
                    'invoice_number': inv.get('invoice_number'),
                    'invoice_date': inv.get('invoice_date'),
                    'invoice_value': inv.get('invoice_value'),
                    'currency': inv.get('currency'),
                    'supplier': inv.get('supplier'),
                    'customer_vat': inv.get('customer_vat'),
                    'customer_name': inv.get('customer_name'),
                    'invoice_type': inv.get('invoice_type'),
                    'campaigns': inv.get('campaigns', {})
                } for inv in report.get('invoices', [])],
                'total': report.get('total', 0),
                'count': report.get('count', 0),
                'currency': report.get('currency', 'RON'),
                'by_month': report.get('by_month', {}),
                'by_campaign': report.get('by_campaign', {}),
                'by_supplier': report.get('by_supplier', {})
            }
        })
    except Exception as e:
        return safe_error_response(e)


@bugetare_bp.route('/api/bulk/export', methods=['POST'])
@login_required
def api_bulk_export():
    """Export bulk processing results to Excel."""
    from accounting.bugetare.bulk_processor import generate_excel_report, process_bulk_invoices

    if 'files[]' not in request.files:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400

    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'error': 'No files selected'}), 400

    # Collect file data
    file_data = []
    for f in files:
        if f.filename and f.filename.lower().endswith('.pdf'):
            file_bytes = f.read()
            file_data.append((file_bytes, f.filename))

    if not file_data:
        return jsonify({'success': False, 'error': 'No valid PDF files found'}), 400

    try:
        report = process_bulk_invoices(file_data)
        excel_bytes = generate_excel_report(report)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'Invoice_Report_{timestamp}.xlsx'

        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return safe_error_response(e)


@bugetare_bp.route('/api/bulk/export-json', methods=['POST'])
@login_required
def api_bulk_export_json():
    """Export bulk processing results from JSON data to Excel."""
    from accounting.bugetare.bulk_processor import generate_excel_report

    data = request.get_json()
    if not data or 'report' not in data:
        return jsonify({'success': False, 'error': 'No report data provided'}), 400

    try:
        report = data['report']

        # Parse date strings back to datetime objects for invoices
        for inv in report.get('invoices', []):
            if inv.get('invoice_date'):
                try:
                    inv['date_parsed'] = datetime.strptime(inv['invoice_date'].split('T')[0], '%Y-%m-%d')
                except Exception:
                    inv['date_parsed'] = None

        excel_bytes = generate_excel_report(report)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'Invoice_Report_{timestamp}.xlsx'

        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return safe_error_response(e)


@bugetare_bp.route('/api/bulk/match-campaigns', methods=['POST'])
@login_required
def api_bulk_match_campaigns():
    """Use AI to match campaign names — SSE streaming to avoid blocking workers."""
    from accounting.bugetare.invoice_parser import match_campaigns_with_ai

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    source_campaigns = data.get('source_campaigns', [])
    target_campaigns = data.get('target_campaigns', [])

    if not source_campaigns or not target_campaigns:
        return jsonify({'success': False, 'error': 'Both source and target campaigns are required'}), 400

    def _generate():
        yield 'data: {"status":"running"}\n\n'
        try:
            mapping = match_campaigns_with_ai(source_campaigns, target_campaigns)
            yield f'data: {json.dumps({"success": True, "mapping": mapping})}\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"success": False, "error": str(exc)})}\n\n'

    return Response(stream_with_context(_generate()), content_type='text/event-stream')


@bugetare_bp.route('/api/bulk/group-similar-items', methods=['POST'])
@login_required
def api_bulk_group_similar_items():
    """Use AI to group similar items — SSE streaming to avoid blocking workers."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    items = data.get('items', [])
    if len(items) < 2:
        return jsonify({'success': True, 'groups': []})

    items_snapshot = list(items)

    def _generate():
        yield 'data: {"status":"running"}\n\n'
        try:
            from ai_agent.services.llm_client import ask
            items_list = "\n".join([f"{i}: {item}" for i, item in enumerate(items_snapshot)])
            prompt = (
                "Analyze these campaign/item names and group together items that should be merged "
                "because they represent the SAME type of campaign/service for the SAME brand/product.\n\n"
                f"Items to analyze:\n{items_list}\n\n"
                "GROUPING RULES:\n"
                "1. Same item type (Traffic, Leads, etc.) AND same brand (Mazda, Volvo, etc.)\n"
                "2. Items from different invoice positions CAN be grouped\n"
                "3. Be conservative — only group items you are confident should be merged\n\n"
                "Return ONLY a JSON array of groups, e.g. [[0,3],[1,4,7]]. "
                "Only include groups with 2+ items."
            )
            result_text = ask(prompt, model="claude-sonnet-4-6-20250514", max_tokens=1024).strip()
            json_match = re.search(r'\[[\s\S]*\]', result_text)
            if json_match:
                groups = json.loads(json_match.group())
                valid_groups = [
                    g for g in groups
                    if isinstance(g, list) and len(g) >= 2
                    and all(isinstance(idx, int) and 0 <= idx < len(items_snapshot) for idx in g)
                ]
                yield f'data: {json.dumps({"success": True, "groups": valid_groups})}\n\n'
            else:
                yield 'data: {"success":true,"groups":[]}\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"success": False, "error": str(exc)})}\n\n'

    return Response(stream_with_context(_generate()), content_type='text/event-stream')
