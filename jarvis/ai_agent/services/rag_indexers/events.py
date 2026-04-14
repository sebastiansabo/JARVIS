"""
Event Indexer Mixin

Provides HR event, approval request, and tag indexing methods for RAGService:
  - event:    index_event, index_events_batch, _fetch_event_data, _build_event_content
  - approval: index_approval, index_approvals_batch, _fetch_approval_data, _build_approval_content
  - tag:      index_tag, index_tags_batch, _fetch_tag_data, _build_tag_content
"""

from typing import Optional, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ...models import RAGSourceType, ServiceResult

logger = get_logger('jarvis.ai_agent.services.rag')


class EventIndexerMixin:
    """Mixin providing HR event, approval, and tag indexing methods for RAGService."""

    # ============== HR Event Indexing ==============

    def _fetch_event_data(self, event_id: int) -> Optional[Dict]:
        """Fetch HR event data with individual bonus details."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT e.*,
                       COUNT(b.id) as bonus_count,
                       COALESCE(SUM(b.bonus_net), 0) as total_bonus_net
                FROM hr.events e
                LEFT JOIN hr.event_bonuses b ON b.event_id = e.id
                WHERE e.id = %s
                GROUP BY e.id
            """, (event_id,))
            event = cursor.fetchone()
            if not event:
                return None
            data = dict(event)
            # Fetch individual bonuses
            cursor.execute("""
                SELECT u.name as employee, b.year, b.month,
                       b.bonus_days, b.bonus_net, b.details,
                       b.participation_start, b.participation_end
                FROM hr.event_bonuses b
                LEFT JOIN users u ON u.id = b.user_id
                WHERE b.event_id = %s
                ORDER BY u.name
            """, (event_id,))
            data['bonuses'] = [dict(r) for r in cursor.fetchall()]
            return data
        finally:
            release_db(conn)

    def _build_event_content(self, data: Dict) -> str:
        """Build searchable content from HR event data, enriched via Claude."""
        parts = []
        if data.get('name'):
            parts.append(f"HR Event: {data['name']}")
        if data.get('company'):
            parts.append(f"Company: {data['company']}")
        if data.get('brand'):
            parts.append(f"Brand: {data['brand']}")
        if data.get('start_date'):
            parts.append(f"Start: {data['start_date']}")
        if data.get('end_date'):
            parts.append(f"End: {data['end_date']}")
        if data.get('description'):
            parts.append(f"Description: {data['description']}")
        if data.get('bonus_count'):
            parts.append(f"Bonuses: {data['bonus_count']} entries, Total: {data.get('total_bonus_net', 0)} RON")
        for b in data.get('bonuses', []):
            line = f"Bonus: {b.get('employee', '?')} — {b.get('bonus_net', 0)} RON"
            if b.get('bonus_days'):
                line += f", {b['bonus_days']} days"
            if b.get('year') and b.get('month'):
                line += f" ({b['year']}/{b['month']:02d})"
            parts.append(line)
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "HR event with employee bonuses")

    def index_event(self, event_id: int) -> ServiceResult:
        """Index an HR event for RAG search."""
        data = self._fetch_event_data(event_id)
        if not data:
            return ServiceResult(success=False, error="HR event not found")

        content = self._build_event_content(data)
        metadata = {
            'name': data.get('name'),
            'company': data.get('company'),
            'brand': data.get('brand'),
            'start_date': str(data.get('start_date', '')),
            'end_date': str(data.get('end_date', '')),
            'bonus_count': data.get('bonus_count', 0),
        }
        company_id = self._lookup_company_id(data.get('company'))
        return self._index_document(
            RAGSourceType.EVENT, event_id, 'hr.events', content, metadata, company_id
        )

    def index_events_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index HR events."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT e.id FROM hr.events e
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'event' AND r.source_id = e.id AND r.is_active = TRUE
                    WHERE r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_event(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} HR events")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"HR event batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Approval Request Indexing ==============

    def _fetch_approval_data(self, request_id: int) -> Optional[Dict]:
        """Fetch approval request data with flow and decision info."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT ar.*,
                       af.name as flow_name,
                       af.entity_type,
                       u.name as requester_name,
                       (SELECT COUNT(*) FROM approval_decisions ad WHERE ad.request_id = ar.id) as decision_count
                FROM approval_requests ar
                LEFT JOIN approval_flows af ON af.id = ar.flow_id
                LEFT JOIN users u ON u.id = ar.requested_by
                WHERE ar.id = %s
            """, (request_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_approval_content(self, data: Dict) -> str:
        """Build searchable content from approval request data."""
        parts = []
        if data.get('flow_name'):
            parts.append(f"Approval Flow: {data['flow_name']}")
        if data.get('entity_type'):
            parts.append(f"Entity Type: {data['entity_type']}")
        if data.get('entity_id'):
            parts.append(f"Entity ID: {data['entity_id']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        if data.get('priority'):
            parts.append(f"Priority: {data['priority']}")
        if data.get('requester_name'):
            parts.append(f"Requested By: {data['requester_name']}")
        if data.get('requested_at'):
            parts.append(f"Requested: {data['requested_at']}")
        if data.get('resolved_at'):
            parts.append(f"Resolved: {data['resolved_at']}")
        if data.get('resolution_note'):
            parts.append(f"Resolution: {data['resolution_note'][:300]}")
        if data.get('decision_count'):
            parts.append(f"Decisions: {data['decision_count']}")
        # Include context snapshot summary
        ctx = data.get('context_snapshot')
        if ctx and isinstance(ctx, dict):
            for key in ('name', 'title', 'supplier', 'amount', 'invoice_number'):
                if ctx.get(key):
                    parts.append(f"Context {key}: {ctx[key]}")
        return "\n".join(parts)

    def index_approval(self, request_id: int) -> ServiceResult:
        """Index an approval request for RAG search."""
        data = self._fetch_approval_data(request_id)
        if not data:
            return ServiceResult(success=False, error="Approval request not found")

        content = self._build_approval_content(data)
        metadata = {
            'flow': data.get('flow_name'),
            'entity_type': data.get('entity_type'),
            'status': data.get('status'),
            'priority': data.get('priority'),
            'requester': data.get('requester_name'),
        }
        return self._index_document(
            RAGSourceType.APPROVAL, request_id, 'approval_requests', content, metadata
        )

    def index_approvals_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index approval requests."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT ar.id FROM approval_requests ar
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'approval' AND r.source_id = ar.id AND r.is_active = TRUE
                    WHERE r.id IS NULL OR r.updated_at < ar.updated_at
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_approval(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} approval requests")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Approval batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Tag Indexing ==============

    def _fetch_tag_data(self, tag_id: int) -> Optional[Dict]:
        """Fetch tag data with group and usage count."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT t.*,
                       tg.name as group_name,
                       tg.color as group_color,
                       COUNT(et.id) as usage_count
                FROM tags t
                LEFT JOIN tag_groups tg ON tg.id = t.group_id
                LEFT JOIN entity_tags et ON et.tag_id = t.id
                WHERE t.id = %s AND t.is_active = TRUE
                GROUP BY t.id, tg.name, tg.color
            """, (tag_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_tag_content(self, data: Dict) -> str:
        """Build searchable content from tag data."""
        parts = []
        if data.get('name'):
            parts.append(f"Tag: {data['name']}")
        if data.get('group_name'):
            parts.append(f"Group: {data['group_name']}")
        if data.get('color'):
            parts.append(f"Color: {data['color']}")
        if data.get('usage_count'):
            parts.append(f"Used on: {data['usage_count']} entities")
        return "\n".join(parts)

    def index_tag(self, tag_id: int) -> ServiceResult:
        """Index a tag for RAG search."""
        data = self._fetch_tag_data(tag_id)
        if not data:
            return ServiceResult(success=False, error="Tag not found")

        content = self._build_tag_content(data)
        metadata = {
            'name': data.get('name'),
            'group': data.get('group_name'),
            'color': data.get('color'),
            'usage_count': data.get('usage_count', 0),
        }
        return self._index_document(
            RAGSourceType.TAG, tag_id, 'tags', content, metadata
        )

    def index_tags_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index tags."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT t.id FROM tags t
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'tag' AND r.source_id = t.id AND r.is_active = TRUE
                    WHERE t.is_active = TRUE AND r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_tag(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} tags")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Tag batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))
