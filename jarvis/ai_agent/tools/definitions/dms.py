"""DMS AI Tools — search documents for the AI agent."""

import logging
from ..registry import tool_registry

logger = logging.getLogger('jarvis.ai_agent.tools.dms')


def _get_user_company_id(cursor, user_id):
    """Look up the company_id for a user. Returns None if no company restriction."""
    if not user_id:
        return None
    cursor.execute('SELECT company_id FROM users WHERE id = %s', (user_id,))
    row = cursor.fetchone()
    return row['company_id'] if row else None


# ════════════════════════════════════════════════════════════════
# Search DMS Documents
# ════════════════════════════════════════════════════════════════

def search_dms_documents(params: dict, user_id: int) -> dict:
    """Search DMS documents by title, category, company, status, date range."""
    from core.database import get_db, get_cursor, release_db
    conditions = ['d.deleted_at IS NULL', 'd.parent_id IS NULL']
    sql_params = []

    if params.get('query'):
        conditions.append("(d.title ILIKE %s OR d.description ILIKE %s OR d.doc_number ILIKE %s)")
        like = f"%{params['query']}%"
        sql_params.extend([like, like, like])

    if params.get('category'):
        conditions.append("c.slug = %s")
        sql_params.append(params['category'])

    if params.get('company_id'):
        conditions.append("d.company_id = %s")
        sql_params.append(params['company_id'])

    if params.get('status'):
        conditions.append("d.status = %s")
        sql_params.append(params['status'])

    if params.get('date_from'):
        conditions.append("d.doc_date >= %s")
        sql_params.append(params['date_from'])

    if params.get('date_to'):
        conditions.append("d.doc_date <= %s")
        sql_params.append(params['date_to'])

    if params.get('has_expiry'):
        conditions.append("d.expiry_date IS NOT NULL")

    if params.get('expiring_within_days'):
        conditions.append("d.expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s * INTERVAL '1 day'")
        sql_params.append(int(params['expiring_within_days']))

    limit = min(params.get('limit', 20), 50)

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Company isolation: restrict to user's company if set
        user_company = _get_user_company_id(cursor, user_id)
        if user_company:
            conditions.append("d.company_id = %s")
            sql_params.append(user_company)

        where = ' AND '.join(conditions)
        sql_params.append(limit)
        cursor.execute(f"""
            SELECT d.id, d.title, d.doc_number, d.status, d.doc_date, d.expiry_date,
                   d.expiry_date - CURRENT_DATE AS days_to_expiry,
                   c.name AS category_name, co.company AS company_name,
                   u.name AS created_by_name,
                   (SELECT COUNT(*) FROM dms_files WHERE document_id = d.id) AS file_count,
                   (SELECT COUNT(*) FROM dms_documents
                    WHERE parent_id = d.id AND deleted_at IS NULL) AS children_count
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies co ON co.id = d.company_id
            LEFT JOIN users u ON u.id = d.created_by
            WHERE {where}
            ORDER BY d.created_at DESC
            LIMIT %s
        """, tuple(sql_params))
        rows = cursor.fetchall()
        return {
            'documents': [{
                'id': r['id'], 'title': r['title'],
                'doc_number': r.get('doc_number'),
                'status': r['status'],
                'category': r.get('category_name'),
                'company': r.get('company_name'),
                'doc_date': str(r.get('doc_date') or ''),
                'expiry_date': str(r.get('expiry_date') or ''),
                'days_to_expiry': r.get('days_to_expiry'),
                'file_count': r.get('file_count', 0),
                'children_count': r.get('children_count', 0),
                'created_by': r.get('created_by_name'),
            } for r in rows],
            'total': len(rows),
        }
    finally:
        release_db(conn)


tool_registry.register(
    name='search_dms_documents',
    description='Search the Document Management System (DMS). Find documents by title, '
                'category (contracte, facturi, autorizatii, devize, documente-hr, altele), '
                'company, status (draft/active/archived), date range, or expiry date. '
                'Documents may have child documents (annexes, estimates, proofs) and attached files. '
                'Use expiring_within_days to find documents expiring soon.',
    input_schema={
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search text (matches title, description, doc number)'},
            'category': {'type': 'string',
                        'description': 'Category slug (contracte, facturi, autorizatii, devize, documente-hr, altele)'},
            'company_id': {'type': 'integer', 'description': 'Company ID filter'},
            'status': {'type': 'string', 'enum': ['draft', 'active', 'archived'],
                      'description': 'Document status'},
            'date_from': {'type': 'string', 'description': 'Document date from (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'Document date to (YYYY-MM-DD)'},
            'has_expiry': {'type': 'boolean', 'description': 'Only documents with expiry dates'},
            'expiring_within_days': {'type': 'integer',
                                    'description': 'Find docs expiring within N days from today'},
            'limit': {'type': 'integer', 'description': 'Max results (default 20, max 50)'},
        },
    },
    handler=search_dms_documents,
    permission='dms.document.view',
)


# ════════════════════════════════════════════════════════════════
# Get DMS Document Details
# ════════════════════════════════════════════════════════════════

def get_dms_document(params: dict, user_id: int) -> dict:
    """Get full DMS document details with children, files, and parties."""
    from core.database import get_db, get_cursor, release_db
    doc_id = params.get('document_id')
    if not doc_id:
        return {'error': 'document_id is required'}

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Company isolation
        user_company = _get_user_company_id(cursor, user_id)
        conditions = ['d.id = %s', 'd.deleted_at IS NULL']
        params = [doc_id]
        if user_company:
            conditions.append('d.company_id = %s')
            params.append(user_company)

        cursor.execute(f"""
            SELECT d.*, c.name AS category_name, co.company AS company_name,
                   u.name AS created_by_name
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies co ON co.id = d.company_id
            LEFT JOIN users u ON u.id = d.created_by
            WHERE {' AND '.join(conditions)}
        """, tuple(params))
        doc = cursor.fetchone()
        if not doc:
            return {'error': 'Document not found'}
        doc = dict(doc)

        # Files
        cursor.execute("""
            SELECT id, file_name, file_type, file_size, storage_type
            FROM dms_files WHERE document_id = %s
        """, (doc_id,))
        files = [dict(r) for r in cursor.fetchall()]

        # Children
        cursor.execute("""
            SELECT id, title, relationship_type, status, doc_number
            FROM dms_documents
            WHERE parent_id = %s AND deleted_at IS NULL
            ORDER BY relationship_type, created_at
        """, (doc_id,))
        children = [dict(r) for r in cursor.fetchall()]

        # Parties (if table exists)
        parties = []
        try:
            cursor.execute("""
                SELECT party_role, entity_name, entity_type
                FROM document_parties WHERE document_id = %s ORDER BY sort_order
            """, (doc_id,))
            parties = [dict(r) for r in cursor.fetchall()]
        except Exception:
            pass

        return {
            'document': {
                'id': doc['id'], 'title': doc['title'],
                'description': doc.get('description'),
                'doc_number': doc.get('doc_number'),
                'status': doc['status'],
                'category': doc.get('category_name'),
                'company': doc.get('company_name'),
                'doc_date': str(doc.get('doc_date') or ''),
                'expiry_date': str(doc.get('expiry_date') or ''),
                'signature_status': doc.get('signature_status'),
                'created_by': doc.get('created_by_name'),
                'created_at': str(doc.get('created_at') or ''),
            },
            'files': [{'name': f['file_name'], 'type': f.get('file_type'),
                       'size': f.get('file_size')} for f in files],
            'children': [{'id': c['id'], 'title': c['title'],
                         'type': c.get('relationship_type'),
                         'status': c['status']} for c in children],
            'parties': [{'role': p['party_role'], 'name': p['entity_name'],
                        'type': p.get('entity_type')} for p in parties],
        }
    finally:
        release_db(conn)


tool_registry.register(
    name='get_dms_document',
    description='Get full details of a DMS document including attached files, '
                'child documents (annexes, estimates, proofs), and linked parties.',
    input_schema={
        'type': 'object',
        'properties': {
            'document_id': {'type': 'integer', 'description': 'DMS Document ID'},
        },
        'required': ['document_id'],
    },
    handler=get_dms_document,
    permission='dms.document.view',
)


# ════════════════════════════════════════════════════════════════
# Search DMS Document Content (WML Chunks)
# ════════════════════════════════════════════════════════════════

def search_dms_content(params: dict, user_id: int) -> dict:
    """Search inside extracted document text (WML chunks) using full-text search."""
    from core.database import get_db, get_cursor, release_db
    query = params.get('query', '').strip()
    if not query:
        return {'error': 'query is required'}

    limit = min(params.get('limit', 10), 30)
    doc_id = params.get('document_id')

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = ["to_tsvector('simple', c.content) @@ plainto_tsquery('simple', %s)"]
        sql_params = [query]

        if doc_id:
            conditions.append("w.document_id = %s")
            sql_params.append(doc_id)

        # Company isolation
        user_company = _get_user_company_id(cursor, user_id)
        if user_company:
            conditions.append("d.company_id = %s")
            sql_params.append(user_company)

        where = ' AND '.join(conditions)
        sql_params.append(limit)

        cursor.execute(f"""
            SELECT c.id, c.heading, c.chunk_index,
                   ts_rank(to_tsvector('simple', c.content), plainto_tsquery('simple', %s)) AS rank,
                   LEFT(c.content, 300) AS snippet,
                   w.document_id,
                   d.title AS doc_title, d.doc_number
            FROM document_wml_chunks c
            JOIN document_wml w ON w.id = c.wml_id
            JOIN dms_documents d ON d.id = w.document_id AND d.deleted_at IS NULL
            WHERE {where}
            ORDER BY rank DESC
            LIMIT %s
        """, (query, *sql_params))
        rows = cursor.fetchall()
        return {
            'results': [{
                'document_id': r['document_id'],
                'doc_title': r['doc_title'],
                'doc_number': r.get('doc_number'),
                'heading': r.get('heading'),
                'chunk_index': r['chunk_index'],
                'snippet': r['snippet'],
                'relevance': round(float(r['rank']), 4),
            } for r in rows],
            'total': len(rows),
        }
    finally:
        release_db(conn)


tool_registry.register(
    name='search_dms_content',
    description='Search inside the actual text content of DMS documents. '
                'Uses full-text search on extracted document text (from DOCX, PDF, XLSX files). '
                'Returns matching text snippets with headings and relevance scores. '
                'Use this to find specific clauses, terms, or data within documents.',
    input_schema={
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search text to find within document content'},
            'document_id': {'type': 'integer', 'description': 'Limit search to a specific document'},
            'limit': {'type': 'integer', 'description': 'Max results (default 10, max 30)'},
        },
        'required': ['query'],
    },
    handler=search_dms_content,
    permission='dms.document.view',
)


# ════════════════════════════════════════════════════════════════
# DMS Stats
# ════════════════════════════════════════════════════════════════

def get_dms_stats(params: dict, user_id: int) -> dict:
    """Get DMS summary statistics."""
    from core.database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Company isolation
        user_company = _get_user_company_id(cursor, user_id)
        company_filter = ''
        company_join_filter = ''
        stats_params = ()
        if user_company:
            company_filter = ' AND company_id = %s'
            company_join_filter = ' AND d.company_id = %s'
            stats_params = (user_company,)

        cursor.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE TRUE) AS total,
                COUNT(*) FILTER (WHERE status = 'draft') AS draft,
                COUNT(*) FILTER (WHERE status = 'active') AS active,
                COUNT(*) FILTER (WHERE status = 'archived') AS archived,
                COUNT(*) FILTER (WHERE expiry_date IS NOT NULL
                    AND expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days') AS expiring_soon
            FROM dms_documents
            WHERE deleted_at IS NULL AND parent_id IS NULL{company_filter}
        """, stats_params)
        stats = dict(cursor.fetchone())
        cursor.execute(f"""
            SELECT c.name, COUNT(d.id) AS count
            FROM dms_categories c
            LEFT JOIN dms_documents d ON d.category_id = c.id
                AND d.deleted_at IS NULL AND d.parent_id IS NULL{company_join_filter}
            WHERE c.is_active = TRUE
            GROUP BY c.name, c.sort_order
            ORDER BY c.sort_order
        """, stats_params)
        stats['by_category'] = {r['name']: r['count'] for r in cursor.fetchall()}
        return stats
    finally:
        release_db(conn)


tool_registry.register(
    name='get_dms_stats',
    description='Get DMS summary: total documents, by status (draft/active/archived), '
                'by category, and count of documents expiring within 30 days.',
    input_schema={
        'type': 'object',
        'properties': {},
    },
    handler=get_dms_stats,
    permission='dms.document.view',
)
