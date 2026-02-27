"""DMS text extraction routes — extract content from uploaded files."""
import os
import logging
from flask import jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import DocumentRepository, FileRepository, WmlRepository
from dms.services.wml_extraction_service import WmlExtractionService
from dms.routes.documents import dms_permission_required

logger = logging.getLogger('jarvis.dms.routes.extraction')

_doc_repo = DocumentRepository()
_file_repo = FileRepository()
_wml_repo = WmlRepository()
_extractor = WmlExtractionService()

# Base upload directory (same as document_service.py)
_UPLOAD_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'static', 'uploads', 'dms')


def _check_doc_access(doc_id):
    """Check document exists and user has company access. Returns (doc, error_response)."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return None, (jsonify({'success': False, 'error': 'Document not found'}), 404)
    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return None, (jsonify({'success': False, 'error': 'Document not found'}), 404)
    return doc, None


@dms_bp.route('/api/documents/<int:doc_id>/extract', methods=['POST'])
@login_required
@dms_permission_required('document', 'edit')
def api_extract_document(doc_id):
    """Extract text from all files of a document."""
    _doc, err = _check_doc_access(doc_id)
    if err:
        return err

    files = _file_repo.get_by_document(doc_id)
    results = []
    errors = []

    for file_row in files:
        try:
            # Only process local files (drive files need download first)
            if file_row['storage_type'] != 'local':
                errors.append({'file': file_row['file_name'], 'error': 'Drive files not supported yet'})
                continue

            # Resolve local path
            file_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                file_row['storage_uri'].lstrip('/')
            )
            file_path = os.path.realpath(file_path)

            # Security: ensure path is within upload directory
            if not file_path.startswith(os.path.realpath(_UPLOAD_BASE)):
                errors.append({'file': file_row['file_name'], 'error': 'Invalid file path'})
                continue

            if not os.path.exists(file_path):
                errors.append({'file': file_row['file_name'], 'error': 'File not found on disk'})
                continue

            # Extract
            extraction = _extractor.extract_from_file(file_path, file_row.get('mime_type'))

            if extraction.get('error'):
                errors.append({'file': file_row['file_name'], 'error': extraction['error']})
                continue

            if not extraction.get('raw_text'):
                errors.append({'file': file_row['file_name'], 'error': 'No text extracted'})
                continue

            # Store in document_wml
            wml_row = _wml_repo.upsert(
                document_id=doc_id,
                file_id=file_row['id'],
                raw_text=extraction['raw_text'],
                structured_json=extraction.get('structured_json'),
                extraction_method=extraction.get('method', 'unknown'),
            )

            # Chunk the text
            chunks = _extractor.chunk_text(
                extraction['raw_text'],
                extraction.get('structured_json'),
            )
            if chunks and wml_row:
                _wml_repo.replace_chunks(wml_row['id'], chunks)

            results.append({
                'file': file_row['file_name'],
                'wml_id': wml_row['id'] if wml_row else None,
                'method': extraction.get('method'),
                'text_length': len(extraction.get('raw_text', '')),
                'chunk_count': len(chunks),
            })

        except Exception:
            logger.exception(f"Extraction failed for file {file_row['id']}")
            errors.append({'file': file_row['file_name'], 'error': 'Extraction failed'})

    return jsonify({
        'success': len(results) > 0 or len(errors) == 0,
        'extractions': results,
        'errors': errors,
    })


@dms_bp.route('/api/documents/<int:doc_id>/text', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_get_document_text(doc_id):
    """Get extracted text for a document."""
    _doc, err = _check_doc_access(doc_id)
    if err:
        return err

    wml_records = _wml_repo.get_by_document(doc_id)
    return jsonify({
        'success': True,
        'extractions': [{
            'id': w['id'],
            'file_id': w['file_id'],
            'raw_text': w['raw_text'][:5000] if w.get('raw_text') else None,
            'method': w.get('extraction_method'),
            'extracted_at': str(w.get('extracted_at') or ''),
        } for w in wml_records],
    })


@dms_bp.route('/api/documents/<int:doc_id>/chunks', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_get_document_chunks(doc_id):
    """Get text chunks for a document."""
    _doc, err = _check_doc_access(doc_id)
    if err:
        return err

    chunks = _wml_repo.get_chunks_by_document(doc_id)
    return jsonify({
        'success': True,
        'chunks': [{
            'id': c['id'],
            'chunk_index': c['chunk_index'],
            'heading': c.get('heading'),
            'content': c['content'][:2000],
            'token_count': c.get('token_count'),
        } for c in chunks],
    })
