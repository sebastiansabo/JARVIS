"""Bugetare Bulk Processing Routes.

Part of JARVIS Accounting Section > Bugetare Application.
Routes for bulk invoice processing, export, and AI campaign matching.
"""
import json
import re
from datetime import datetime

from flask import render_template, jsonify, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from . import bugetare_bp


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


@bugetare_bp.route('/api/bulk/match-campaigns', methods=['POST'])
@login_required
def api_bulk_match_campaigns():
    """Use AI to match campaign names between source and target invoices."""
    from accounting.bugetare.invoice_parser import match_campaigns_with_ai

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    source_campaigns = data.get('source_campaigns', [])
    target_campaigns = data.get('target_campaigns', [])

    if not source_campaigns or not target_campaigns:
        return jsonify({'success': False, 'error': 'Both source and target campaigns are required'}), 400

    try:
        mapping = match_campaigns_with_ai(source_campaigns, target_campaigns)
        return jsonify({
            'success': True,
            'mapping': mapping
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bugetare_bp.route('/api/bulk/group-similar-items', methods=['POST'])
@login_required
def api_bulk_group_similar_items():
    """Use AI to group similar items that should be merged together.

    Groups items by same item type (Leads, Traffic, etc.) AND same brand/product.
    Items from different invoice positions can be grouped if they represent the same campaign type.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    items = data.get('items', [])
    if len(items) < 2:
        return jsonify({'success': True, 'groups': []})

    try:
        import anthropic
        client = anthropic.Anthropic()

        items_list = "\n".join([f"{i}: {item}" for i, item in enumerate(items)])

        prompt = f"""Analyze these campaign/item names and group together items that should be merged because they represent the SAME type of campaign/service for the SAME brand/product.

Items to analyze:
{items_list}

GROUPING RULES:
1. Group items that have the SAME item type (e.g., "Traffic", "Leads", "Conversions", "Brand", etc.) AND the SAME brand/product (e.g., "Mazda", "Volvo", "MG", etc.)
2. Items from different invoice line positions CAN be grouped together if they represent the same campaign type
3. Examples of items that SHOULD be grouped together:
   - "[CA] Traffic - Mazda CX60" and "[CA] Traffic - Mazda CX80" (same type: Traffic, same brand: Mazda)
   - "[CA] Leads - Modele Volvo 0 km" and "[CA] Leads - Volvo EX30" (same type: Leads, same brand: Volvo)
4. Examples of items that should NOT be grouped:
   - "[CA] Leads - Mazda CX80" and "[CA] Traffic - Mazda CX60" (different types: Leads vs Traffic)
   - "[CA] Leads - Mazda CX80" and "[CA] Leads - Volvo EX30" (different brands: Mazda vs Volvo)
5. If an item has no clear brand/product match with others, leave it ungrouped
6. Be conservative - only group items you are confident should be merged

Return ONLY a JSON array of groups, where each group is an array of item indices that should be merged.
Only include groups with 2+ items. Items that don't belong to any group should be omitted.

Example response format:
[[0, 3], [1, 4, 7]]

This means: items 0 and 3 should be merged together, items 1, 4, and 7 should be merged together."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()

        # Extract JSON array from response (handle markdown code blocks)
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            groups = json.loads(json_match.group())
            valid_groups = []
            for group in groups:
                if isinstance(group, list) and len(group) >= 2:
                    if all(isinstance(idx, int) and 0 <= idx < len(items) for idx in group):
                        valid_groups.append(group)

            return jsonify({
                'success': True,
                'groups': valid_groups
            })
        else:
            return jsonify({'success': True, 'groups': []})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
