"""
Marketing Indexer Mixin

Provides marketing and DMS document indexing methods for RAGService:
  - marketing:     index_marketing, index_marketing_batch, _fetch_marketing_data, _build_marketing_content
  - dms_document:  index_dms_document, index_dms_documents_batch, _build_dms_document_content
"""

from typing import Optional, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ...models import RAGSourceType, ServiceResult

logger = get_logger('jarvis.ai_agent.services.rag')


class MarketingIndexerMixin:
    """Mixin providing marketing project and DMS document indexing methods for RAGService."""

    # ============== Marketing Project Indexing ==============

    def _fetch_marketing_data(self, project_id: int) -> Optional[Dict]:
        """Fetch marketing project data with budget lines, KPIs, and team."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT p.*,
                       u.name as owner_name,
                       c.company as company_name,
                       COALESCE(SUM(bl.planned_amount), 0) as total_planned,
                       COALESCE(SUM(bl.spent_amount), 0) as total_spent,
                       COUNT(DISTINCT pk.id) as kpi_count
                FROM mkt_projects p
                LEFT JOIN users u ON u.id = p.owner_id
                LEFT JOIN companies c ON c.id = p.company_id
                LEFT JOIN mkt_budget_lines bl ON bl.project_id = p.id
                LEFT JOIN mkt_project_kpis pk ON pk.project_id = p.id
                WHERE p.id = %s AND p.deleted_at IS NULL
                GROUP BY p.id, u.name, c.company
            """, (project_id,))
            project = cursor.fetchone()
            if not project:
                return None
            data = dict(project)
            # Budget lines
            cursor.execute("""
                SELECT channel, description, planned_amount, spent_amount, currency, agency_name
                FROM mkt_budget_lines WHERE project_id = %s ORDER BY planned_amount DESC
            """, (project_id,))
            data['budget_lines'] = [dict(r) for r in cursor.fetchall()]
            # KPIs
            cursor.execute("""
                SELECT kd.name as kpi_name, kd.unit, pk.target_value, pk.current_value, pk.channel, pk.status
                FROM mkt_project_kpis pk
                JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                WHERE pk.project_id = %s
            """, (project_id,))
            data['kpis'] = [dict(r) for r in cursor.fetchall()]
            # Team members
            cursor.execute("""
                SELECT u.name, pm.role FROM mkt_project_members pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = %s
            """, (project_id,))
            data['members'] = [dict(r) for r in cursor.fetchall()]
            return data
        finally:
            release_db(conn)

    def _build_marketing_content(self, data: Dict) -> str:
        """Build searchable content from marketing project data, enriched via Claude."""
        parts = []
        if data.get('name'):
            parts.append(f"Marketing Project: {data['name']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        if data.get('project_type'):
            parts.append(f"Type: {data['project_type']}")
        if data.get('company_name'):
            parts.append(f"Company: {data['company_name']}")
        if data.get('owner_name'):
            parts.append(f"Owner: {data['owner_name']}")
        if data.get('description'):
            parts.append(f"Description: {data['description'][:500]}")
        if data.get('objective'):
            parts.append(f"Objective: {data['objective'][:300]}")
        if data.get('target_audience'):
            parts.append(f"Target Audience: {data['target_audience'][:200]}")
        if data.get('start_date'):
            parts.append(f"Start: {data['start_date']}")
        if data.get('end_date'):
            parts.append(f"End: {data['end_date']}")
        if data.get('total_planned'):
            parts.append(f"Planned Budget: {data['total_planned']}")
        if data.get('total_spent'):
            parts.append(f"Spent Budget: {data['total_spent']}")
        for bl in data.get('budget_lines', []):
            line = f"Budget: {bl.get('channel', '?')} — planned {bl.get('planned_amount', 0)}, spent {bl.get('spent_amount', 0)} {bl.get('currency', 'RON')}"
            if bl.get('agency_name'):
                line += f" (agency: {bl['agency_name']})"
            parts.append(line)
        for kpi in data.get('kpis', []):
            parts.append(f"KPI: {kpi.get('kpi_name', '?')} — target {kpi.get('target_value', '?')}, current {kpi.get('current_value', 0)} {kpi.get('unit', '')} [{kpi.get('status', '')}]")
        for m in data.get('members', []):
            parts.append(f"Team: {m.get('name', '?')} ({m.get('role', '?')})")
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "marketing project with budget and KPIs")

    def index_marketing(self, project_id: int) -> ServiceResult:
        """Index a marketing project for RAG search."""
        data = self._fetch_marketing_data(project_id)
        if not data:
            return ServiceResult(success=False, error="Marketing project not found")

        content = self._build_marketing_content(data)
        metadata = {
            'name': data.get('name'),
            'status': data.get('status'),
            'type': data.get('project_type'),
            'company': data.get('company_name'),
            'owner': data.get('owner_name'),
            'budget': str(data.get('total_planned', 0)),
        }
        return self._index_document(
            RAGSourceType.MARKETING, project_id, 'mkt_projects', content, metadata, data.get('company_id')
        )

    def index_marketing_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index marketing projects."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT p.id FROM mkt_projects p
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'marketing' AND r.source_id = p.id AND r.is_active = TRUE
                    WHERE p.deleted_at IS NULL
                      AND (r.id IS NULL OR r.updated_at < p.updated_at)
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_marketing(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} marketing projects")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Marketing batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== DMS Document Indexing ==============

    def _build_dms_document_content(self, data: dict) -> str:
        """Build searchable content from DMS document data."""
        parts = []
        parts.append(f"Document: {data.get('title', '')}")
        if data.get('doc_number'):
            parts.append(f"Nr. Document: {data['doc_number']}")
        if data.get('category_name'):
            parts.append(f"Categorie: {data['category_name']}")
        if data.get('company_name'):
            parts.append(f"Companie: {data['company_name']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        if data.get('description'):
            parts.append(f"Descriere: {data['description'][:500]}")
        if data.get('doc_date'):
            parts.append(f"Data document: {data['doc_date']}")
        if data.get('expiry_date'):
            parts.append(f"Data expirare: {data['expiry_date']}")
        if data.get('created_by_name'):
            parts.append(f"Creat de: {data['created_by_name']}")
        if data.get('file_count'):
            parts.append(f"Fisiere: {data['file_count']}")
        if data.get('children_count'):
            parts.append(f"Documente copil: {data['children_count']}")
        # Parties
        for party in data.get('parties', []):
            parts.append(f"Parte ({party.get('party_role', '?')}): {party.get('entity_name', '?')}")
        # Signature
        if data.get('signature_status'):
            parts.append(f"Semnatura: {data['signature_status']}")
        return '\n'.join(parts)

    def index_dms_document(self, doc_id: int) -> ServiceResult:
        """Index a DMS document for RAG search."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT d.*,
                           c.name AS category_name,
                           co.company AS company_name,
                           u.name AS created_by_name,
                           (SELECT COUNT(*) FROM dms_files WHERE document_id = d.id) AS file_count,
                           (SELECT COUNT(*) FROM dms_documents
                            WHERE parent_id = d.id AND deleted_at IS NULL) AS children_count
                    FROM dms_documents d
                    LEFT JOIN dms_categories c ON c.id = d.category_id
                    LEFT JOIN companies co ON co.id = d.company_id
                    LEFT JOIN users u ON u.id = d.created_by
                    WHERE d.id = %s AND d.deleted_at IS NULL
                """, (doc_id,))
                data = cursor.fetchone()
                if not data:
                    return ServiceResult(success=False, error='DMS document not found')
                data = dict(data)
                # Fetch parties if table exists
                try:
                    cursor.execute("""
                        SELECT party_role, entity_name
                        FROM document_parties
                        WHERE document_id = %s
                        ORDER BY sort_order
                    """, (doc_id,))
                    data['parties'] = [dict(r) for r in cursor.fetchall()]
                except Exception:
                    data['parties'] = []
            finally:
                release_db(conn)

            content = self._build_dms_document_content(data)
            party_names = [p['entity_name'] for p in data.get('parties', [])]
            metadata = {
                'doc_number': data.get('doc_number'),
                'category': data.get('category_name'),
                'company': data.get('company_name'),
                'status': data.get('status'),
                'expiry_date': str(data.get('expiry_date') or ''),
                'date': str(data.get('doc_date') or data.get('created_at') or ''),
                'parties': ', '.join(party_names) if party_names else None,
            }
            return self._index_document(
                RAGSourceType.DMS_DOCUMENT, doc_id, 'dms_documents',
                content, metadata, data.get('company_id')
            )
        except Exception as e:
            logger.error(f"DMS document indexing failed for {doc_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_dms_documents_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index DMS documents."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT d.id FROM dms_documents d
                    WHERE d.deleted_at IS NULL
                      AND d.parent_id IS NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM ai_agent.rag_documents r
                        WHERE r.source_type = 'dms_document'
                          AND r.source_id = d.id
                          AND r.is_active = TRUE
                          AND r.updated_at >= d.updated_at
                      )
                    ORDER BY d.updated_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_dms_document(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} DMS documents")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"DMS document batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))
