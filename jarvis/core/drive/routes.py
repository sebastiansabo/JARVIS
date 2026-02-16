"""Google Drive API Routes.

Upload invoices and attachments to Google Drive, check status, get folder links.
"""
import os

from flask import jsonify, request
from flask_login import login_required

from . import drive_bp
from core.utils.api_helpers import safe_error_response

# Google Drive integration (optional)
try:
    from core.services.drive_service import (
        upload_invoice_to_drive, check_drive_auth,
        get_folder_id_from_file_link, get_folder_link_from_file, upload_attachment_to_folder
    )
    DRIVE_ENABLED = True
except ImportError:
    DRIVE_ENABLED = False
    check_drive_auth = None
    get_folder_id_from_file_link = None
    get_folder_link_from_file = None
    upload_attachment_to_folder = None

# Image compression (TinyPNG)
try:
    from core.services.image_compressor import compress_if_image
    IMAGE_COMPRESSION_ENABLED = True
except ImportError:
    IMAGE_COMPRESSION_ENABLED = False
    compress_if_image = None


def is_drive_enabled():
    """Check if Drive integration is available."""
    return DRIVE_ENABLED


def is_drive_authenticated():
    """Check if Drive is authenticated."""
    if not DRIVE_ENABLED:
        return False
    try:
        return check_drive_auth()
    except Exception:
        return False


@drive_bp.route('/api/drive/status')
@login_required
def api_drive_status():
    """Check if Google Drive is configured and authenticated."""
    if not DRIVE_ENABLED:
        return jsonify({'enabled': False, 'error': 'Google Drive packages not installed'})
    try:
        authenticated = check_drive_auth()
        return jsonify({'enabled': True, 'authenticated': authenticated})
    except Exception as e:
        return jsonify({'enabled': True, 'authenticated': False, 'error': str(e)})


@drive_bp.route('/api/drive/upload', methods=['POST'])
@login_required
def api_drive_upload():
    """Upload invoice to Google Drive organized by Year/Month/Company/InvoiceNo."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    invoice_date = request.form.get('invoice_date', '')
    company = request.form.get('company', 'Unknown Company')
    invoice_number = request.form.get('invoice_number', 'Unknown Invoice')

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    try:
        file_bytes = file.read()

        ext = os.path.splitext(file.filename)[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png'
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')

        drive_link = upload_invoice_to_drive(
            file_bytes=file_bytes,
            filename=file.filename,
            invoice_date=invoice_date,
            company=company,
            invoice_number=invoice_number,
            mime_type=mime_type
        )

        from database import refresh_connection_pool
        refresh_connection_pool()
        return jsonify({'success': True, 'drive_link': drive_link})
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e), 'need_auth': True}), 400
    except Exception as e:
        return safe_error_response(e)


@drive_bp.route('/api/drive/upload-attachment', methods=['POST'])
@login_required
def api_drive_upload_attachment():
    """Upload an attachment to the same Drive folder as an existing invoice file."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    drive_link = request.form.get('drive_link', '')

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    # Check file size (5MB limit)
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > 5 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File size exceeds 5MB limit'}), 400

    try:
        folder_id = get_folder_id_from_file_link(drive_link)
        if not folder_id:
            return jsonify({'success': False, 'error': 'Could not determine folder from drive link'}), 400

        file_bytes = file.read()
        mime_type = file.content_type or 'application/octet-stream'
        compression_stats = None

        if IMAGE_COMPRESSION_ENABLED and compress_if_image:
            file_bytes, compression_stats = compress_if_image(file_bytes, file.filename, mime_type)

        attachment_link = upload_attachment_to_folder(
            file_bytes=file_bytes,
            filename=file.filename,
            folder_id=folder_id,
            mime_type=mime_type
        )

        if attachment_link:
            from database import refresh_connection_pool
            refresh_connection_pool()
            result = {'success': True, 'attachment_link': attachment_link}
            if compression_stats:
                result['compression'] = compression_stats
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': 'Failed to upload attachment'}), 500

    except Exception as e:
        return safe_error_response(e)


@drive_bp.route('/api/drive/folder-link', methods=['GET'])
@login_required
def api_drive_folder_link():
    """Get the Google Drive folder link from a file's drive link."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    drive_link = request.args.get('drive_link', '')
    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    try:
        folder_link = get_folder_link_from_file(drive_link)
        if folder_link:
            return jsonify({'success': True, 'folder_link': folder_link})
        else:
            return jsonify({'success': False, 'error': 'Could not determine folder'}), 404
    except Exception as e:
        return safe_error_response(e)
