"""
Duplicate Detection Service - manual and AI-based invoice duplicate detection.
"""
from typing import List, Dict, Any

from core.utils.logging_config import get_logger
from ..repositories import EFacturaInvoiceRepository
from .base import ServiceResult

logger = get_logger('jarvis.core.connectors.efactura.duplicate_service')


class DuplicateDetectionService:
    def __init__(self):
        self.invoice_repo = EFacturaInvoiceRepository()

    def detect_unallocated_duplicates(self) -> List[Dict[str, Any]]:
        """
        Detect unallocated e-Factura invoices that already exist in the main invoices table.

        Called after sync to notify user of potential duplicates.

        Returns:
            List of duplicate invoices with their matching existing invoice info
        """
        from core.database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Find unallocated e-Factura invoices that match existing invoices
            # by supplier name + invoice number
            cursor.execute("""
                SELECT
                    e.id as efactura_id,
                    e.partner_name,
                    e.invoice_number,
                    e.issue_date,
                    e.total_amount,
                    e.currency,
                    i.id as existing_invoice_id,
                    i.invoice_date as existing_date,
                    i.invoice_value as existing_value
                FROM efactura_invoices e
                INNER JOIN invoices i
                    ON LOWER(e.partner_name) = LOWER(i.supplier)
                    AND e.invoice_number = i.invoice_number
                    AND i.deleted_at IS NULL
                WHERE e.jarvis_invoice_id IS NULL
                    AND e.deleted_at IS NULL
                    AND e.ignored = FALSE
                ORDER BY e.partner_name, e.invoice_number
            """)

            duplicates = []
            for row in cursor.fetchall():
                duplicates.append({
                    'efactura_id': row['efactura_id'],
                    'partner_name': row['partner_name'],
                    'invoice_number': row['invoice_number'],
                    'issue_date': str(row['issue_date']) if row['issue_date'] else None,
                    'total_amount': float(row['total_amount']),
                    'currency': row['currency'],
                    'existing_invoice_id': row['existing_invoice_id'],
                    'existing_date': str(row['existing_date']) if row['existing_date'] else None,
                    'existing_value': float(row['existing_value']) if row['existing_value'] else None,
                })

            if duplicates:
                logger.info(f"Found {len(duplicates)} duplicate unallocated invoices")

            return duplicates

        finally:
            release_db(conn)

    def mark_duplicates(self, efactura_ids: List[int]) -> ServiceResult:
        """
        Mark e-Factura invoices as duplicates by linking to existing invoices.

        Finds the matching invoice in the main table and sets jarvis_invoice_id.

        Args:
            efactura_ids: List of e-Factura invoice IDs to mark as duplicates

        Returns:
            ServiceResult with count of marked duplicates
        """
        if not efactura_ids:
            return ServiceResult(success=True, data={'marked': 0})

        from core.database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Find matching invoices and create mappings
            cursor.execute("""
                SELECT
                    e.id as efactura_id,
                    i.id as jarvis_id
                FROM efactura_invoices e
                INNER JOIN invoices i
                    ON LOWER(e.partner_name) = LOWER(i.supplier)
                    AND e.invoice_number = i.invoice_number
                    AND i.deleted_at IS NULL
                WHERE e.id = ANY(%s)
                    AND e.jarvis_invoice_id IS NULL
                    AND e.deleted_at IS NULL
            """, (efactura_ids,))

            mappings = [(row['efactura_id'], row['jarvis_id']) for row in cursor.fetchall()]

            if mappings:
                self.invoice_repo.bulk_mark_allocated(mappings)
                logger.info(f"Marked {len(mappings)} e-Factura invoices as duplicates")

            return ServiceResult(success=True, data={'marked': len(mappings)})

        except Exception as e:
            logger.error(f"Error marking duplicates: {e}")
            return ServiceResult(success=False, error=str(e))
        finally:
            release_db(conn)

    def detect_duplicates_with_ai(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Detect potential duplicate invoices using AI similarity matching.

        This is a fallback for when exact supplier+invoice_number matching fails.
        Uses Claude to analyze similar invoices based on:
        - Similar supplier names (fuzzy matching)
        - Similar amounts
        - Date proximity

        Args:
            limit: Maximum number of e-Factura invoices to analyze (for cost control)

        Returns:
            List of potential duplicates with AI confidence scores
        """
        import json
        import os
        from difflib import SequenceMatcher
        from ai_agent.providers.base_provider import BaseProvider
        from ai_agent.services.llm_client import ask

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            logger.warning('ANTHROPIC_API_KEY not set, skipping AI duplicate detection')
            return []

        from core.database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Get unallocated e-Factura invoices that DON'T have exact matches
            # (exact matches are already found by detect_unallocated_duplicates)
            cursor.execute("""
                SELECT e.id, e.partner_name, e.invoice_number, e.issue_date,
                       e.total_amount, e.currency
                FROM efactura_invoices e
                WHERE e.jarvis_invoice_id IS NULL
                    AND e.deleted_at IS NULL
                    AND e.ignored = FALSE
                    AND NOT EXISTS (
                        SELECT 1 FROM invoices i
                        WHERE LOWER(e.partner_name) = LOWER(i.supplier)
                          AND e.invoice_number = i.invoice_number
                          AND i.deleted_at IS NULL
                    )
                ORDER BY e.issue_date DESC
                LIMIT %s
            """, (limit,))

            efactura_invoices = cursor.fetchall()

            if not efactura_invoices:
                return []

            # Get main invoices from the last 180 days for comparison
            cursor.execute("""
                SELECT id, supplier, invoice_number, invoice_date, invoice_value, currency
                FROM invoices
                WHERE deleted_at IS NULL
                    AND invoice_date >= CURRENT_DATE - INTERVAL '180 days'
                ORDER BY invoice_date DESC
                LIMIT 500
            """)

            main_invoices = cursor.fetchall()

            if not main_invoices:
                return []

            ai_duplicates = []

            # Pre-filter: find invoices with similar amounts (within 5%)
            for ef_inv in efactura_invoices:
                ef_amount = float(ef_inv['total_amount'] or 0)
                ef_supplier = ef_inv['partner_name'] or ''

                # Find candidates with similar amounts
                candidates = []
                for main_inv in main_invoices:
                    main_amount = float(main_inv['invoice_value'] or 0)
                    main_supplier = main_inv['supplier'] or ''

                    # Check amount similarity (within 5%)
                    if main_amount > 0 and ef_amount > 0:
                        amount_diff = abs(ef_amount - main_amount) / main_amount * 100
                        if amount_diff > 5:
                            continue
                    else:
                        amount_diff = 100.0

                    # Check supplier name similarity (at least 50%)
                    similarity = SequenceMatcher(
                        None,
                        ef_supplier.lower(),
                        main_supplier.lower()
                    ).ratio()
                    if similarity < 0.5:
                        continue

                    candidates.append({
                        'id': main_inv['id'],
                        'supplier': main_supplier,
                        'invoice_number': main_inv['invoice_number'],
                        'invoice_date': str(main_inv['invoice_date']) if main_inv['invoice_date'] else None,
                        'invoice_value': main_amount,
                        'currency': main_inv['currency'],
                        'similarity': round(similarity, 2),
                        'amount_diff': round(amount_diff, 2)
                    })

                # If we have candidates, ask AI to evaluate
                if candidates:
                    candidates = candidates[:5]  # Limit to top 5 candidates

                    prompt = f"""Analyze if this e-Factura invoice is a DUPLICATE of any existing invoice.

E-FACTURA INVOICE (new import):
- Supplier: {ef_inv['partner_name']}
- Invoice Number: {ef_inv['invoice_number']}
- Date: {ef_inv['issue_date']}
- Amount: {ef_amount} {ef_inv['currency'] or 'RON'}

EXISTING INVOICES (candidates):
{json.dumps(candidates, indent=2)}

IMPORTANT: Return ONLY valid JSON with this format:
{{
    "is_duplicate": true/false,
    "matching_invoice_id": <id or null>,
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

Consider:
- Same supplier with different name format (SRL vs S.R.L., abbreviations)
- Invoice number may have different formatting
- Amounts should be nearly identical for duplicates
- Dates should be close (within a few days)

Only mark as duplicate if you're confident (>0.7) it's the same invoice."""

                    try:
                        response_text = ask(prompt, model="claude-sonnet-4-6-20250514",
                                            max_tokens=256, api_key=api_key)
                        result = BaseProvider._extract_json(response_text)

                        if result.get('is_duplicate') and result.get('confidence', 0) >= 0.7:
                            ai_duplicates.append({
                                'efactura_id': ef_inv['id'],
                                'partner_name': ef_inv['partner_name'],
                                'invoice_number': ef_inv['invoice_number'],
                                'issue_date': str(ef_inv['issue_date']) if ef_inv['issue_date'] else None,
                                'total_amount': ef_amount,
                                'currency': ef_inv['currency'],
                                'existing_invoice_id': result.get('matching_invoice_id'),
                                'confidence': result.get('confidence', 0),
                                'reasoning': result.get('reasoning', 'AI detected duplicate'),
                                'ai_detected': True
                            })

                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f'AI duplicate detection JSON error: {e}')
                    except Exception as e:
                        logger.error(f'AI duplicate detection error: {e}')

            if ai_duplicates:
                logger.info(f"AI detected {len(ai_duplicates)} potential duplicates")

            return ai_duplicates

        finally:
            release_db(conn)

    def mark_ai_duplicates(self, mappings: List[Dict[str, int]]) -> ServiceResult:
        """
        Mark AI-detected duplicates by linking to specified existing invoices.

        Unlike mark_duplicates() which finds the match by supplier+invoice_number,
        this method uses the explicit mapping provided by the AI detection.

        Args:
            mappings: List of {'efactura_id': int, 'existing_invoice_id': int}

        Returns:
            ServiceResult with count of marked duplicates
        """
        if not mappings:
            return ServiceResult(success=True, data={'marked': 0})

        pairs = [(m['efactura_id'], m['existing_invoice_id']) for m in mappings]
        self.invoice_repo.bulk_mark_allocated(pairs)
        logger.info(f"Marked {len(pairs)} AI-detected duplicates")

        return ServiceResult(success=True, data={'marked': len(pairs)})
