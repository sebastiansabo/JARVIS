"""Invoice, allocation, and summary API routes."""
import os
from flask import jsonify, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from . import invoices_bp
from .repositories import InvoiceRepository, AllocationRepository, SummaryRepository
from core.utils.api_helpers import safe_error_response, handle_api_errors

_invoice_repo = InvoiceRepository()
_allocation_repo = AllocationRepository()
_summary_repo = SummaryRepository()


def _log_event(event_type, description=None, entity_type=None, entity_id=None, details=None):
    """Helper to log user events with current user info."""
    from core.auth.repositories import EventRepository
    user_id = current_user.id if current_user.is_authenticated else None
    user_email = current_user.email if current_user.is_authenticated else None
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent', '')[:500] if request else None
    EventRepository().log_event(
        event_type=event_type,
        event_description=description,
        user_id=user_id,
        user_email=user_email,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details
    )


def _user_can_set_status(user_role_name, status_value, dropdown_type='invoice_status'):
    """Check if a user's role meets the min_role requirement for a specific status."""
    from core.settings.dropdowns.repositories import DropdownRepository
    ROLE_HIERARCHY = ['Viewer', 'Manager', 'Admin']
    options = DropdownRepository().get_options(dropdown_type, active_only=True)
    status_option = next((opt for opt in options if opt['value'] == status_value), None)
    if not status_option:
        return False
    min_role = status_option.get('min_role')
    if not min_role:
        return True
    user_level = ROLE_HIERARCHY.index(user_role_name) if user_role_name in ROLE_HIERARCHY else -1
    min_level = ROLE_HIERARCHY.index(min_role) if min_role in ROLE_HIERARCHY else 0
    return user_level >= min_level


# ============== PAGE ROUTES ==============

@invoices_bp.route('/add-invoice')
@login_required
def add_invoice():
    """Redirect to React add invoice page."""
    return redirect('/app/accounting/add')


@invoices_bp.route('/accounting')
@login_required
def accounting():
    """Redirect to React accounting dashboard."""
    return redirect('/app/accounting')


# ============== INVOICE SUBMISSION ==============

@invoices_bp.route('/api/submit', methods=['POST'])
@login_required
def submit_invoice():
    """Submit an invoice with its cost distribution."""
    if not current_user.can_add_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to add invoices'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400

    try:
        invoice_id = _invoice_repo.save(
            supplier=data['supplier'],
            invoice_template=data.get('invoice_template', ''),
            invoice_number=data['invoice_number'],
            invoice_date=data['invoice_date'],
            invoice_value=float(data['invoice_value']),
            currency=data.get('currency', 'RON'),
            drive_link=data.get('drive_link', ''),
            distributions=data['distributions'],
            value_ron=data.get('value_ron'),
            value_eur=data.get('value_eur'),
            exchange_rate=data.get('exchange_rate'),
            comment=data.get('comment', ''),
            payment_status=data.get('payment_status', 'not_paid'),
            subtract_vat=data.get('subtract_vat', False),
            vat_rate=data.get('vat_rate'),
            net_value=data.get('net_value'),
            line_items=data.get('_line_items'),
            invoice_type=data.get('_invoice_type', 'standard')
        )

        # Correction tracking: compare AI parse result vs submitted values
        parse_result = data.get('_parse_result')
        if parse_result and data.get('invoice_template'):
            corrections = {}
            if parse_result.get('supplier') and parse_result['supplier'] != data['supplier']:
                corrections['supplier'] = {'parsed': parse_result['supplier'], 'submitted': data['supplier']}
            if parse_result.get('invoice_number') and parse_result['invoice_number'] != data['invoice_number']:
                corrections['invoice_number'] = {'parsed': parse_result['invoice_number'], 'submitted': data['invoice_number']}
            if parse_result.get('invoice_value') and float(parse_result['invoice_value']) != float(data['invoice_value']):
                corrections['invoice_value'] = {'parsed': parse_result['invoice_value'], 'submitted': data['invoice_value']}
            if corrections:
                _log_event('parse_correction',
                           f'User corrected {len(corrections)} field(s) from template parse: {", ".join(corrections.keys())}',
                           entity_type='invoice', entity_id=invoice_id,
                           details={'corrections': corrections, 'template': data.get('invoice_template')})

        # e-Factura auto-link
        efactura_match_id = data.get('_efactura_match_id')
        if efactura_match_id:
            try:
                from core.connectors.efactura.repositories.invoice_repo import EFacturaInvoiceRepository
                EFacturaInvoiceRepository().mark_allocated(int(efactura_match_id), invoice_id)
            except Exception:
                pass

        # Send email notifications to responsables
        notifications_sent = 0
        try:
            from core.services.notification_service import notify_invoice_allocations, is_smtp_configured
            if is_smtp_configured():
                invoice_data = {
                    'id': invoice_id,
                    'invoice_number': data['invoice_number'],
                    'supplier': data['supplier'],
                    'invoice_date': data['invoice_date'],
                    'invoice_value': float(data['invoice_value']),
                    'currency': data.get('currency', 'RON'),
                }
                results = notify_invoice_allocations(invoice_data, data['distributions'])
                notifications_sent = sum(1 for r in results if r.get('success'))
        except ImportError:
            pass

        # Auto-tag rules (fire-and-forget)
        try:
            from core.tags.auto_tag_service import AutoTagService
            AutoTagService().evaluate_rules_for_entity('invoice', invoice_id, current_user.id)
        except Exception:
            pass

        _log_event('invoice_created',
                   f'Created invoice {data["invoice_number"]} from {data["supplier"]}',
                   entity_type='invoice', entity_id=invoice_id)

        from database import refresh_connection_pool
        refresh_connection_pool()

        return jsonify({
            'success': True,
            'message': f'Successfully saved {len(data["distributions"])} allocation(s)',
            'allocations': len(data['distributions']),
            'invoice_id': invoice_id,
            'notifications_sent': notifications_sent
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


# ============== INVOICE PARSING ==============

@invoices_bp.route('/api/parse-invoice', methods=['POST'])
@login_required
def api_parse_invoice():
    """Parse an uploaded invoice using AI or template (with auto-detection)."""
    if not current_user.can_add_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    template_id = request.form.get('template_id')

    try:
        from accounting.bugetare.invoice_parser import parse_invoice_with_template_from_bytes, auto_detect_and_parse

        file_bytes = file.read()

        if template_id:
            from accounting.templates.repositories import TemplateRepository
            template = TemplateRepository().get(int(template_id))
            if not template:
                return jsonify({'success': False, 'error': 'Template not found'}), 404
            result = parse_invoice_with_template_from_bytes(file_bytes, file.filename, template)
            result['auto_detected_template'] = None
            result['auto_detected_template_id'] = None
        else:
            from accounting.templates.repositories import TemplateRepository
            templates = TemplateRepository().get_all()
            result = auto_detect_and_parse(file_bytes, file.filename, templates)

        result['drive_link'] = None

        # Add currency conversion
        try:
            from core.services.currency_converter import get_eur_ron_conversion
            if result.get('invoice_value') and result.get('currency') and result.get('invoice_date'):
                conversion = get_eur_ron_conversion(
                    float(result['invoice_value']),
                    result['currency'],
                    result['invoice_date']
                )
                result['value_ron'] = conversion.get('value_ron')
                result['value_eur'] = conversion.get('value_eur')
                result['exchange_rate'] = conversion.get('exchange_rate')
            else:
                result['value_ron'] = None
                result['value_eur'] = None
                result['exchange_rate'] = None
        except (ImportError, Exception):
            result['value_ron'] = None
            result['value_eur'] = None
            result['exchange_rate'] = None

        # e-Factura cross-reference: check if a matching record exists
        try:
            if result.get('invoice_number'):
                from database import get_db, get_cursor, release_db
                conn = get_db()
                try:
                    cur = get_cursor(conn)
                    supplier_vat = result.get('supplier_vat', '')
                    supplier_name = result.get('supplier', '')
                    cur.execute('''
                        SELECT id, partner_name, partner_cif, invoice_number, issue_date,
                               total_amount, currency, jarvis_invoice_id
                        FROM efactura_invoices
                        WHERE deleted_at IS NULL AND invoice_number = %s
                          AND (partner_cif = %s OR LOWER(partner_name) = LOWER(%s))
                        LIMIT 1
                    ''', (result['invoice_number'], supplier_vat, supplier_name))
                    match = cur.fetchone()
                    if match:
                        result['efactura_match'] = {
                            'id': match['id'],
                            'partner_name': match['partner_name'],
                            'partner_cif': match['partner_cif'],
                            'invoice_number': match['invoice_number'],
                            'issue_date': str(match['issue_date']) if match['issue_date'] else None,
                            'total_amount': float(match['total_amount']) if match['total_amount'] else None,
                            'currency': match['currency'],
                            'jarvis_invoice_id': match['jarvis_invoice_id'],
                        }
                finally:
                    release_db(conn)
        except Exception:
            pass

        from database import refresh_connection_pool
        refresh_connection_pool()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)


@invoices_bp.route('/api/parse-existing/<path:filepath>')
@login_required
@handle_api_errors
def api_parse_existing(filepath):
    """Parse an existing invoice from the Invoices folder."""
    from core.config import INVOICES_DIR
    from accounting.bugetare.invoice_parser import parse_invoice
    file_path = os.path.join(INVOICES_DIR, filepath)

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': 'File not found'}), 404

    result = parse_invoice(file_path)
    return jsonify({'success': True, 'data': result})


@invoices_bp.route('/api/suggest-department')
@login_required
@handle_api_errors
def api_suggest_department():
    """Suggest department based on historical allocations for the same supplier."""
    supplier = request.args.get('supplier', '').strip()
    if not supplier:
        return jsonify({'suggestions': []})

    from database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('''
            SELECT a.company, a.brand, a.department, a.subdepartment, COUNT(*) as freq
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE LOWER(i.supplier) = LOWER(%s) AND i.deleted_at IS NULL
            GROUP BY a.company, a.brand, a.department, a.subdepartment
            ORDER BY freq DESC
            LIMIT 5
        ''', (supplier,))
        rows = cur.fetchall()
        suggestions = [
            {
                'company': r['company'],
                'brand': r['brand'],
                'department': r['department'],
                'subdepartment': r['subdepartment'],
                'frequency': r['freq'],
            }
            for r in rows
        ]
        return jsonify({'suggestions': suggestions})
    finally:
        release_db(conn)


@invoices_bp.route('/api/invoices')
@login_required
def api_list_invoices():
    """List available invoices in the Invoices folder (including subfolders)."""
    from core.config import INVOICES_DIR
    if not os.path.exists(INVOICES_DIR):
        return jsonify([])

    files = []
    for root, dirs, filenames in os.walk(INVOICES_DIR):
        for f in filenames:
            if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                rel_path = os.path.relpath(os.path.join(root, f), INVOICES_DIR)
                files.append(rel_path)
    return jsonify(sorted(files))


# ============== INVOICE CRUD ==============

@invoices_bp.route('/api/db/invoices')
@login_required
def api_db_invoices():
    """Get all invoices from database with pagination and optional filters."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    limit = request.args.get('limit', 10000, type=int)
    offset = request.args.get('offset', 0, type=int)
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    status = request.args.get('status')
    payment_status = request.args.get('payment_status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    include_allocations = request.args.get('include_allocations', 'false').lower() == 'true'

    if include_allocations:
        invoices = _invoice_repo.get_all_with_allocations(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status
        )
    else:
        invoices = _invoice_repo.get_all(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status
        )
    return jsonify(invoices)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>')
@login_required
def api_db_invoice_detail(invoice_id):
    """Get invoice with all allocations."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    invoice = _invoice_repo.get_with_allocations(invoice_id)
    if invoice:
        return jsonify(invoice)
    return jsonify({'error': 'Invoice not found'}), 404


@invoices_bp.route('/api/db/invoices/<int:invoice_id>', methods=['DELETE'])
@login_required
def api_db_delete_invoice(invoice_id):
    """Soft delete an invoice (move to bin)."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    if _invoice_repo.delete(invoice_id):
        _log_event('invoice_deleted', f'Moved invoice ID {invoice_id} to bin',
                   entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found'}), 404


@invoices_bp.route('/api/db/invoices/<int:invoice_id>/restore', methods=['POST'])
@login_required
def api_db_restore_invoice(invoice_id):
    """Restore a soft-deleted invoice from the bin."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to restore invoices'}), 403
    if _invoice_repo.restore(invoice_id):
        _log_event('invoice_restored', f'Restored invoice ID {invoice_id} from bin',
                   entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found in bin'}), 404


@invoices_bp.route('/api/db/invoices/<int:invoice_id>/permanent', methods=['DELETE'])
@login_required
def api_db_permanently_delete_invoice(invoice_id):
    """Permanently delete an invoice. Also deletes from Google Drive."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403

    drive_link = _invoice_repo.get_drive_link(invoice_id)

    if _invoice_repo.permanently_delete(invoice_id):
        drive_deleted = False
        try:
            from core.services.drive_service import delete_file_from_drive
            if drive_link:
                drive_deleted = delete_file_from_drive(drive_link)
        except ImportError:
            pass
        _log_event('invoice_permanently_deleted', f'Permanently deleted invoice ID {invoice_id}',
                   entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True, 'drive_deleted': drive_deleted})
    return jsonify({'error': 'Invoice not found'}), 404


@invoices_bp.route('/api/db/invoices/bulk-delete', methods=['POST'])
@login_required
def api_db_bulk_delete_invoices():
    """Soft delete multiple invoices."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400
    count = _invoice_repo.bulk_soft_delete(invoice_ids)
    return jsonify({'success': True, 'deleted_count': count})


@invoices_bp.route('/api/db/invoices/bulk-restore', methods=['POST'])
@login_required
def api_db_bulk_restore_invoices():
    """Restore multiple soft-deleted invoices."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to restore invoices'}), 403
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400
    count = _invoice_repo.bulk_restore(invoice_ids)
    return jsonify({'success': True, 'restored_count': count})


@invoices_bp.route('/api/db/invoices/bulk-permanent-delete', methods=['POST'])
@login_required
def api_db_bulk_permanently_delete_invoices():
    """Permanently delete multiple invoices. Also deletes from Google Drive."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400

    drive_links = _invoice_repo.get_drive_links(invoice_ids)
    count = _invoice_repo.bulk_permanently_delete(invoice_ids)

    drive_deleted_count = 0
    try:
        from core.services.drive_service import delete_files_from_drive
        if drive_links:
            drive_deleted_count = delete_files_from_drive(drive_links)
    except ImportError:
        pass

    return jsonify({'success': True, 'deleted_count': count, 'drive_deleted_count': drive_deleted_count})


@invoices_bp.route('/api/db/invoices/bin', methods=['GET'])
@login_required
def api_db_get_deleted_invoices():
    """Get all soft-deleted invoices (bin)."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    invoices = _invoice_repo.get_all(include_deleted=True, limit=500)
    return jsonify(invoices)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>', methods=['PUT'])
@login_required
def api_db_update_invoice(invoice_id):
    """Update an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()

    try:
        current_invoice = _invoice_repo.get_with_allocations(invoice_id)
        old_status = current_invoice.get('status') if current_invoice else None
        old_payment_status = current_invoice.get('payment_status') if current_invoice else None
        new_status = data.get('status')
        new_payment_status = data.get('payment_status')

        if new_status and new_status != old_status:
            if not _user_can_set_status(current_user.role_name, new_status, 'invoice_status'):
                return jsonify({'success': False, 'error': f'Permission denied: Your role cannot set status to "{new_status}"'}), 403

        if new_payment_status and new_payment_status != old_payment_status:
            if not _user_can_set_status(current_user.role_name, new_payment_status, 'payment_status'):
                return jsonify({'success': False, 'error': f'Permission denied: Your role cannot set payment status to "{new_payment_status}"'}), 403

        updated = _invoice_repo.update(
            invoice_id=invoice_id,
            supplier=data.get('supplier'),
            invoice_number=data.get('invoice_number'),
            invoice_date=data.get('invoice_date'),
            invoice_value=float(data['invoice_value']) if data.get('invoice_value') else None,
            currency=data.get('currency'),
            drive_link=data.get('drive_link'),
            comment=data.get('comment'),
            status=new_status,
            payment_status=new_payment_status,
            subtract_vat=data.get('subtract_vat'),
            vat_rate=float(data['vat_rate']) if data.get('vat_rate') else None,
            net_value=float(data['net_value']) if data.get('net_value') else None
        )
        if updated:
            if new_status is not None and old_status != new_status:
                _log_event('status_changed',
                           f'Invoice #{current_invoice.get("invoice_number", invoice_id)} status changed from "{old_status}" to "{new_status}"',
                           entity_type='invoice', entity_id=invoice_id,
                           details={'old_status': old_status, 'new_status': new_status})

                from core.settings.dropdowns.repositories import DropdownRepository
                if DropdownRepository().should_notify_on_status(new_status, 'invoice_status'):
                    try:
                        from core.services.notification_service import notify_invoice_allocations, is_smtp_configured
                        if is_smtp_configured():
                            allocations = current_invoice.get('allocations', [])
                            if allocations:
                                invoice_data = {
                                    'supplier': current_invoice.get('supplier'),
                                    'invoice_number': current_invoice.get('invoice_number'),
                                    'invoice_date': current_invoice.get('invoice_date'),
                                    'invoice_value': current_invoice.get('invoice_value'),
                                    'currency': current_invoice.get('currency'),
                                    'drive_link': current_invoice.get('drive_link'),
                                    'status': new_status,
                                }
                                notify_invoice_allocations(invoice_data, allocations)
                    except ImportError:
                        pass

            if new_payment_status is not None and old_payment_status != new_payment_status:
                _log_event('payment_status_changed',
                           f'Invoice #{current_invoice.get("invoice_number", invoice_id)} payment status changed from "{old_payment_status}" to "{new_payment_status}"',
                           entity_type='invoice', entity_id=invoice_id,
                           details={'old_payment_status': old_payment_status, 'new_payment_status': new_payment_status})
            _log_event('invoice_updated', f'Updated invoice ID {invoice_id}',
                       entity_type='invoice', entity_id=invoice_id)
            return jsonify({'success': True})
        return jsonify({'error': 'Invoice not found or no changes made'}), 404
    except Exception as e:
        return safe_error_response(e)


# ============== ALLOCATION ROUTES ==============

@invoices_bp.route('/api/db/invoices/<int:invoice_id>/allocations', methods=['PUT'])
@login_required
def api_db_update_allocations(invoice_id):
    """Update all allocations for an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    allocations = data.get('allocations', [])
    send_notification = data.get('send_notification', False)

    if not allocations:
        return jsonify({'success': False, 'error': 'At least one allocation is required'}), 400

    total_percent = sum(float(a.get('allocation_percent', 0)) for a in allocations)
    if abs(total_percent - 100) > 1.0:
        return jsonify({'success': False, 'error': f'Allocations must sum to 100%, got {round(total_percent, 2)}%'}), 400

    try:
        _allocation_repo.update_invoice_allocations(invoice_id, allocations)

        # Auto-set status to first invoice_status option when allocations are edited
        current_invoice = _invoice_repo.get_with_allocations(invoice_id)
        old_status = current_invoice.get('status') if current_invoice else None
        from core.settings.dropdowns.repositories import DropdownRepository
        status_options = DropdownRepository().get_options('invoice_status', active_only=True)
        default_status = status_options[0]['value'] if status_options else None
        if default_status and old_status != default_status:
            _invoice_repo.update(invoice_id, status=default_status)
            _log_event('status_changed',
                       f'Invoice #{current_invoice.get("invoice_number", invoice_id)} status auto-changed to "{default_status}" after allocation edit',
                       entity_type='invoice', entity_id=invoice_id,
                       details={'old_status': old_status, 'new_status': default_status})

        notifications_sent = 0
        if send_notification:
            try:
                from core.services.notification_service import notify_invoice_allocations, is_smtp_configured
                if is_smtp_configured():
                    if not current_invoice:
                        current_invoice = _invoice_repo.get_with_allocations(invoice_id)
                    if current_invoice:
                        invoice_data = {
                            'id': invoice_id,
                            'invoice_number': current_invoice.get('invoice_number'),
                            'supplier': current_invoice.get('supplier'),
                            'invoice_date': current_invoice.get('invoice_date'),
                            'invoice_value': current_invoice.get('invoice_value'),
                            'currency': current_invoice.get('currency', 'RON'),
                        }
                        results = notify_invoice_allocations(invoice_data, allocations)
                        notifications_sent = sum(1 for r in results if r.get('success'))
            except ImportError:
                pass

        _log_event('allocations_updated', f'Updated allocations for invoice ID {invoice_id}',
                   entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True, 'notifications_sent': notifications_sent})
    except Exception as e:
        return safe_error_response(e)


@invoices_bp.route('/api/allocations/<int:allocation_id>/comment', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_allocation_comment(allocation_id):
    """Update the comment for a specific allocation."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json()
    comment = data.get('comment', '')

    updated = _allocation_repo.update_comment(allocation_id, comment)
    if updated:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Allocation not found'}), 404


@invoices_bp.route('/api/invoices/<int:invoice_id>/drive-link', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_invoice_drive_link(invoice_id):
    """Update only the drive_link for an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json()
    drive_link = data.get('drive_link')

    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    updated = _invoice_repo.update(invoice_id=invoice_id, drive_link=drive_link)
    if updated:
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found'}), 404


# ============== SEARCH ==============

@invoices_bp.route('/api/db/search')
@login_required
def api_db_search():
    """Search invoices by supplier or invoice number, respecting active filters."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])

    filters = {
        'company': request.args.get('company'),
        'department': request.args.get('department'),
        'subdepartment': request.args.get('subdepartment'),
        'brand': request.args.get('brand'),
        'status': request.args.get('status'),
        'payment_status': request.args.get('payment_status'),
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
    }
    filters = {k: v for k, v in filters.items() if v}

    results = _invoice_repo.search(query, filters)
    return jsonify(results)


@invoices_bp.route('/api/invoices/search')
@login_required
def api_invoices_search():
    """Search invoices by supplier, invoice number, or ID."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)

    if len(query) < 2:
        return jsonify({'success': True, 'invoices': [], 'message': 'Query too short'})

    if query.isdigit():
        invoice = _invoice_repo.get_with_allocations(int(query))
        if invoice:
            return jsonify({'success': True, 'invoices': [invoice]})

    results = _invoice_repo.search(query)[:limit]
    return jsonify({'success': True, 'invoices': results})


@invoices_bp.route('/api/db/check-invoice-number')
@login_required
def api_check_invoice_number():
    """Check if an invoice number already exists in the database."""
    invoice_number = request.args.get('invoice_number', '').strip()
    exclude_id = request.args.get('exclude_id', type=int)

    if not invoice_number:
        return jsonify({'exists': False, 'invoice': None})

    result = _invoice_repo.check_number_exists(invoice_number, exclude_id)
    return jsonify(result)


# ============== SUMMARY ROUTES ==============

@invoices_bp.route('/api/db/summary/company')
@login_required
def api_db_summary_company():
    """Get summary grouped by company."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_company(start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/department')
@login_required
def api_db_summary_department():
    """Get summary grouped by department."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_department(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/brand')
@login_required
def api_db_summary_brand():
    """Get summary grouped by brand (Linie de business)."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_brand(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/supplier')
@login_required
def api_db_summary_supplier():
    """Get summary grouped by supplier."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_supplier(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)
