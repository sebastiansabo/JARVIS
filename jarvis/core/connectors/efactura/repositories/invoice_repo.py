"""
Invoice Repository

Database operations for e-Factura invoices and related entities.
"""

import json
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ..config import InvoiceDirection, ArtifactType
from ..models import (
    Invoice,
    InvoiceExternalRef,
    InvoiceArtifact,
)

logger = get_logger('jarvis.accounting.efactura.repo.invoice')


class InvoiceRepository:
    """Repository for Invoice and related entities."""

    def create(
        self,
        invoice: Invoice,
        external_ref: InvoiceExternalRef,
        artifacts: List[InvoiceArtifact],
    ) -> Invoice:
        """
        Create invoice with external reference and artifacts.

        Uses a transaction to ensure atomicity.

        Args:
            invoice: Invoice to create
            external_ref: External reference from ANAF
            artifacts: List of artifacts to store

        Returns:
            Created Invoice with ID
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Insert invoice
            cursor.execute("""
                INSERT INTO efactura_invoices (
                    cif_owner, company_id, direction, partner_cif, partner_name,
                    invoice_number, invoice_series, issue_date, due_date,
                    total_amount, total_vat, total_without_vat, currency,
                    status, created_at, updated_at
                ) VALUES (
                    %(cif_owner)s, %(company_id)s, %(direction)s, %(partner_cif)s, %(partner_name)s,
                    %(invoice_number)s, %(invoice_series)s, %(issue_date)s, %(due_date)s,
                    %(total_amount)s, %(total_vat)s, %(total_without_vat)s, %(currency)s,
                    %(status)s, NOW(), NOW()
                )
                RETURNING id, created_at, updated_at
            """, {
                'cif_owner': invoice.cif_owner,
                'company_id': invoice.company_id,
                'direction': invoice.direction.value,
                'partner_cif': invoice.partner_cif,
                'partner_name': invoice.partner_name,
                'invoice_number': invoice.invoice_number,
                'invoice_series': invoice.invoice_series,
                'issue_date': invoice.issue_date,
                'due_date': invoice.due_date,
                'total_amount': str(invoice.total_amount),
                'total_vat': str(invoice.total_vat),
                'total_without_vat': str(invoice.total_without_vat),
                'currency': invoice.currency,
                'status': invoice.status.value,
            })

            row = cursor.fetchone()
            invoice.id = row['id']
            invoice.created_at = row['created_at']
            invoice.updated_at = row['updated_at']

            # Insert external reference
            external_ref.invoice_id = invoice.id
            cursor.execute("""
                INSERT INTO efactura_invoice_refs (
                    invoice_id, external_system, message_id,
                    upload_id, download_id, xml_hash, signature_hash,
                    raw_response_hash, created_at
                ) VALUES (
                    %(invoice_id)s, %(external_system)s, %(message_id)s,
                    %(upload_id)s, %(download_id)s, %(xml_hash)s, %(signature_hash)s,
                    %(raw_response_hash)s, NOW()
                )
                RETURNING id, created_at
            """, {
                'invoice_id': external_ref.invoice_id,
                'external_system': external_ref.external_system,
                'message_id': external_ref.message_id,
                'upload_id': external_ref.upload_id,
                'download_id': external_ref.download_id,
                'xml_hash': external_ref.xml_hash,
                'signature_hash': external_ref.signature_hash,
                'raw_response_hash': external_ref.raw_response_hash,
            })

            ref_row = cursor.fetchone()
            external_ref.id = ref_row['id']
            external_ref.created_at = ref_row['created_at']

            # Insert artifacts
            for artifact in artifacts:
                artifact.invoice_id = invoice.id
                cursor.execute("""
                    INSERT INTO efactura_invoice_artifacts (
                        invoice_id, artifact_type, storage_uri,
                        original_filename, mime_type, checksum, size_bytes,
                        created_at
                    ) VALUES (
                        %(invoice_id)s, %(artifact_type)s, %(storage_uri)s,
                        %(original_filename)s, %(mime_type)s, %(checksum)s,
                        %(size_bytes)s, NOW()
                    )
                    RETURNING id, created_at
                """, {
                    'invoice_id': artifact.invoice_id,
                    'artifact_type': artifact.artifact_type.value,
                    'storage_uri': artifact.storage_uri,
                    'original_filename': artifact.original_filename,
                    'mime_type': artifact.mime_type,
                    'checksum': artifact.checksum,
                    'size_bytes': artifact.size_bytes,
                })

                art_row = cursor.fetchone()
                artifact.id = art_row['id']
                artifact.created_at = art_row['created_at']

            conn.commit()

            logger.info(
                "Invoice created",
                extra={
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'message_id': external_ref.message_id,
                    'artifact_count': len(artifacts),
                }
            )

            return invoice

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create invoice: {e}")
            raise
        finally:
            release_db(conn)

    def get_by_id(self, invoice_id: int) -> Optional[Invoice]:
        """Get invoice by ID."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT * FROM efactura_invoices
                WHERE id = %s
            """, (invoice_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_invoice(row)
        finally:
            release_db(conn)

    def get_by_message_id(
        self,
        cif_owner: str,
        direction: InvoiceDirection,
        message_id: str,
    ) -> Optional[Invoice]:
        """Get invoice by ANAF message ID (for deduplication)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT i.* FROM efactura_invoices i
                JOIN efactura_invoice_refs r ON r.invoice_id = i.id
                WHERE i.cif_owner = %s
                AND i.direction = %s
                AND r.message_id = %s
            """, (cif_owner, direction.value, message_id))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_invoice(row)
        finally:
            release_db(conn)

    def exists_by_message_id(
        self,
        cif_owner: str,
        direction: InvoiceDirection,
        message_id: str,
    ) -> bool:
        """Check if invoice exists (fast dedup check)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT 1 FROM efactura_invoices i
                JOIN efactura_invoice_refs r ON r.invoice_id = i.id
                WHERE i.cif_owner = %s
                AND i.direction = %s
                AND r.message_id = %s
                LIMIT 1
            """, (cif_owner, direction.value, message_id))
            return cursor.fetchone() is not None
        finally:
            release_db(conn)

    def list_invoices(
        self,
        cif_owner: str,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        partner_cif: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Invoice], int]:
        """
        List invoices with filters.

        Args:
            cif_owner: Company CIF
            direction: Filter by direction
            start_date: Filter by issue date start
            end_date: Filter by issue date end
            partner_cif: Filter by partner CIF
            limit: Page size
            offset: Page offset

        Returns:
            Tuple of (invoices, total_count)
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Build WHERE clause
            conditions = ['cif_owner = %(cif_owner)s']
            params = {'cif_owner': cif_owner, 'limit': limit, 'offset': offset}

            if direction is not None:
                conditions.append('direction = %(direction)s')
                params['direction'] = direction.value

            if start_date is not None:
                conditions.append('issue_date >= %(start_date)s')
                params['start_date'] = start_date

            if end_date is not None:
                conditions.append('issue_date <= %(end_date)s')
                params['end_date'] = end_date

            if partner_cif is not None:
                conditions.append('partner_cif = %(partner_cif)s')
                params['partner_cif'] = partner_cif

            where_clause = ' AND '.join(conditions)

            # Get total count
            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            # Get invoices
            cursor.execute(f"""
                SELECT * FROM efactura_invoices
                WHERE {where_clause}
                ORDER BY issue_date DESC, id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)

            invoices = [self._row_to_invoice(row) for row in cursor.fetchall()]

            return invoices, total
        finally:
            release_db(conn)

    def get_external_ref(self, invoice_id: int) -> Optional[InvoiceExternalRef]:
        """Get external reference for an invoice."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT * FROM efactura_invoice_refs
                WHERE invoice_id = %s
            """, (invoice_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return InvoiceExternalRef(
                id=row['id'],
                invoice_id=row['invoice_id'],
                external_system=row['external_system'],
                message_id=row['message_id'],
                upload_id=row.get('upload_id'),
                download_id=row.get('download_id'),
                xml_hash=row.get('xml_hash'),
                signature_hash=row.get('signature_hash'),
                raw_response_hash=row.get('raw_response_hash'),
                created_at=row['created_at'],
            )
        finally:
            release_db(conn)

    def get_artifacts(self, invoice_id: int) -> List[InvoiceArtifact]:
        """Get artifacts for an invoice."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT * FROM efactura_invoice_artifacts
                WHERE invoice_id = %s
                ORDER BY artifact_type
            """, (invoice_id,))
            return [
                InvoiceArtifact(
                    id=row['id'],
                    invoice_id=row['invoice_id'],
                    artifact_type=ArtifactType(row['artifact_type']),
                    storage_uri=row['storage_uri'],
                    original_filename=row.get('original_filename'),
                    mime_type=row.get('mime_type'),
                    checksum=row.get('checksum'),
                    size_bytes=row.get('size_bytes', 0),
                    created_at=row['created_at'],
                )
                for row in cursor.fetchall()
            ]
        finally:
            release_db(conn)

    def get_artifact_by_type(
        self,
        invoice_id: int,
        artifact_type: ArtifactType,
    ) -> Optional[InvoiceArtifact]:
        """Get specific artifact type for an invoice."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT * FROM efactura_invoice_artifacts
                WHERE invoice_id = %s AND artifact_type = %s
            """, (invoice_id, artifact_type.value))
            row = cursor.fetchone()
            if row is None:
                return None
            return InvoiceArtifact(
                id=row['id'],
                invoice_id=row['invoice_id'],
                artifact_type=ArtifactType(row['artifact_type']),
                storage_uri=row['storage_uri'],
                original_filename=row.get('original_filename'),
                mime_type=row.get('mime_type'),
                checksum=row.get('checksum'),
                size_bytes=row.get('size_bytes', 0),
                created_at=row['created_at'],
            )
        finally:
            release_db(conn)

    def update_artifact_uri(
        self,
        artifact_id: int,
        storage_uri: str,
    ):
        """Update artifact storage URI after upload."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoice_artifacts
                SET storage_uri = %s
                WHERE id = %s
            """, (storage_uri, artifact_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update artifact URI: {e}")
            raise
        finally:
            release_db(conn)

    def get_summary(
        self,
        cif_owner: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get invoice summary statistics."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            params = {'cif_owner': cif_owner}
            date_filter = ''

            if start_date:
                date_filter += ' AND issue_date >= %(start_date)s'
                params['start_date'] = start_date
            if end_date:
                date_filter += ' AND issue_date <= %(end_date)s'
                params['end_date'] = end_date

            cursor.execute(f"""
                SELECT
                    direction,
                    COUNT(*) as count,
                    SUM(total_amount) as total_amount,
                    SUM(total_vat) as total_vat,
                    MIN(issue_date) as earliest_date,
                    MAX(issue_date) as latest_date
                FROM efactura_invoices
                WHERE cif_owner = %(cif_owner)s {date_filter}
                GROUP BY direction
            """, params)

            summary = {
                'received': {'count': 0, 'total': Decimal('0'), 'vat': Decimal('0')},
                'sent': {'count': 0, 'total': Decimal('0'), 'vat': Decimal('0')},
            }

            for row in cursor.fetchall():
                direction = row['direction']
                summary[direction] = {
                    'count': row['count'],
                    'total': Decimal(str(row['total_amount'] or 0)),
                    'vat': Decimal(str(row['total_vat'] or 0)),
                    'earliest_date': row['earliest_date'],
                    'latest_date': row['latest_date'],
                }

            return summary
        finally:
            release_db(conn)

    # ============================================
    # Unallocated Invoices (for JARVIS integration)
    # ============================================

    def get_by_message_id_simple(self, message_id: str) -> Optional[Invoice]:
        """Get invoice by ANAF message ID only (simpler version for import)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT i.* FROM efactura_invoices i
                JOIN efactura_invoice_refs r ON r.invoice_id = i.id
                WHERE r.message_id = %s
            """, (message_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_invoice(row)
        finally:
            release_db(conn)

    def ignore_invoice(self, invoice_id: int, ignored: bool = True) -> bool:
        """
        Mark an invoice as ignored (soft delete).

        Args:
            invoice_id: ID of the invoice to ignore
            ignored: True to ignore, False to restore

        Returns:
            True if successful, False otherwise
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoices
                SET ignored = %s, updated_at = NOW()
                WHERE id = %s
            """, (ignored, invoice_id))
            conn.commit()
            logger.info(
                f"Invoice {'ignored' if ignored else 'restored'}",
                extra={'invoice_id': invoice_id}
            )
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to ignore invoice: {e}")
            return False
        finally:
            release_db(conn)

    def partner_has_hidden_types(self, partner_name: str) -> bool:
        """
        Check if a partner has ONLY hidden types (all types have hide_in_filter=TRUE).

        Returns False if the partner has any non-hidden type (mixed types = not hidden).

        Args:
            partner_name: Name of the partner (supplier/customer)

        Returns:
            True if partner has types AND all are hidden, False otherwise
        """
        if not partner_name:
            return False

        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT
                    EXISTS (
                        SELECT 1
                        FROM efactura_supplier_mappings sm
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm.id
                        JOIN efactura_partner_types pt ON pt.id = smt.type_id
                        WHERE LOWER(sm.partner_name) = LOWER(%s)
                            AND sm.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                    ) as has_hidden_types,
                    EXISTS (
                        SELECT 1
                        FROM efactura_supplier_mappings sm
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm.id
                        JOIN efactura_partner_types pt ON pt.id = smt.type_id
                        WHERE LOWER(sm.partner_name) = LOWER(%s)
                            AND sm.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                    ) as has_visible_types
            """, (partner_name, partner_name))
            result = cursor.fetchone()
            if not result:
                return False
            # Only hidden if has hidden types AND no visible types
            return result['has_hidden_types'] and not result['has_visible_types']
        except Exception as e:
            logger.error(f"Failed to check partner hidden types: {e}")
            return False
        finally:
            release_db(conn)

    def auto_hide_if_typed(self, invoice_id: int, partner_name: str) -> bool:
        """
        Automatically hide an invoice if its partner has types with hide_in_filter=TRUE.

        Skips invoices that have a manual type override (type_override IS NOT NULL).

        Args:
            invoice_id: ID of the invoice
            partner_name: Name of the partner

        Returns:
            True if invoice was auto-hidden, False otherwise
        """
        # Check if invoice has manual type override - don't auto-hide if so
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                'SELECT type_override FROM efactura_invoices WHERE id = %s',
                (invoice_id,)
            )
            row = cursor.fetchone()
            if row and row.get('type_override'):
                return False  # Has manual override, skip auto-hide
        finally:
            release_db(conn)

        if self.partner_has_hidden_types(partner_name):
            logger.info(
                "Auto-hiding invoice due to partner having hidden types",
                extra={'invoice_id': invoice_id, 'partner_name': partner_name}
            )
            return self.ignore_invoice(invoice_id, ignored=True)
        return False

    def auto_hide_all_by_partner(self, partner_name: str) -> int:
        """
        Auto-hide all unallocated, non-ignored invoices for a partner.

        Called when a supplier mapping is created/updated with hidden types.
        Only affects invoices without manual type override (type_override IS NULL).

        Args:
            partner_name: Name of the partner

        Returns:
            Number of invoices auto-hidden
        """
        if not partner_name:
            return 0

        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoices
                SET ignored = TRUE, updated_at = NOW()
                WHERE LOWER(partner_name) = LOWER(%s)
                    AND jarvis_invoice_id IS NULL
                    AND ignored = FALSE
                    AND deleted_at IS NULL
                    AND type_override IS NULL
            """, (partner_name,))
            count = cursor.rowcount
            conn.commit()
            if count > 0:
                logger.info(
                    f"Auto-hidden {count} invoices for partner with hidden types",
                    extra={'partner_name': partner_name, 'count': count}
                )
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to auto-hide invoices for partner: {e}")
            return 0
        finally:
            release_db(conn)

    def update_overrides(
        self,
        invoice_id: int,
        type_override: Optional[str] = None,
        department_override: Optional[str] = None,
        subdepartment_override: Optional[str] = None,
    ) -> bool:
        """
        Update invoice-level overrides for Type, Department, and Subdepartment.

        These overrides take precedence over the mapping defaults.
        Passing None clears the override.
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoices
                SET type_override = %s,
                    department_override = %s,
                    subdepartment_override = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (type_override, department_override, subdepartment_override, invoice_id))
            conn.commit()
            logger.info(
                f"Invoice overrides updated",
                extra={
                    'invoice_id': invoice_id,
                    'type_override': type_override,
                    'department_override': department_override,
                    'subdepartment_override': subdepartment_override,
                }
            )
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update invoice overrides: {e}")
            return False
        finally:
            release_db(conn)

    def bulk_update_overrides(
        self,
        invoice_ids: List[int],
        updates: Dict[str, Any],
    ) -> int:
        """
        Bulk update invoice-level overrides for multiple invoices.

        Args:
            invoice_ids: List of invoice IDs to update
            updates: Dict of field -> value pairs to update. Only fields present in the dict will be updated.
                     Supported fields: type_override, department_override, subdepartment_override

        Returns the number of invoices updated.
        """
        if not invoice_ids or not updates:
            return 0

        # Build SET clause dynamically based on provided updates
        allowed_fields = {'type_override', 'department_override', 'subdepartment_override'}
        set_clauses = []
        params = []

        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = %s")
                params.append(value)

        if not set_clauses:
            return 0

        set_clauses.append("updated_at = NOW()")
        params.append(invoice_ids)

        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(f"""
                UPDATE efactura_invoices
                SET {', '.join(set_clauses)}
                WHERE id = ANY(%s)
            """, params)
            conn.commit()
            count = cursor.rowcount
            logger.info(
                f"Bulk updated {count} invoice overrides",
                extra={
                    'invoice_ids': invoice_ids,
                    'updates': updates,
                }
            )
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk update invoice overrides: {e}")
            return 0
        finally:
            release_db(conn)

    # Valid sort columns mapping (frontend name -> DB column)
    SORT_COLUMNS = {
        'company': 'i.company_id',
        'direction': 'i.direction',
        'invoice_number': 'i.invoice_number',
        'partner_name': 'i.partner_name',
        'partner_cif': 'i.partner_cif',
        'type': 'i.type_override',
        'department': 'COALESCE(i.department_override, sm.department)',
        'subdepartment': 'COALESCE(i.subdepartment_override, sm.subdepartment)',
        'issue_date': 'i.issue_date',
        'amount': 'i.total_amount',
        'total_amount': 'i.total_amount',
        'vat': 'i.total_vat',
        'total_vat': 'i.total_vat',
        'currency': 'i.currency',
        'imported': 'i.created_at',
        'created_at': 'i.created_at',
    }

    def list_unallocated(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        hide_typed: bool = False,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = 'issue_date',
        sort_dir: str = 'desc',
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List invoices that haven't been sent to the main Invoice Module.

        Unallocated = jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL
        Returns invoices with type_name from supplier mappings.
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Build WHERE clause - exclude ignored and deleted invoices
            conditions = ['i.jarvis_invoice_id IS NULL', 'i.ignored = FALSE', 'i.deleted_at IS NULL']
            params = {'limit': limit, 'offset': offset}

            if cif_owner:
                conditions.append('i.cif_owner = %(cif_owner)s')
                params['cif_owner'] = cif_owner

            if company_id is not None:
                conditions.append('i.company_id = %(company_id)s')
                params['company_id'] = company_id

            if direction is not None:
                conditions.append('i.direction = %(direction)s')
                params['direction'] = direction.value

            if start_date:
                conditions.append('i.issue_date >= %(start_date)s')
                params['start_date'] = start_date

            if end_date:
                conditions.append('i.issue_date <= %(end_date)s')
                params['end_date'] = end_date

            if search:
                # Elasticsearch-style: split into words, ALL words must match somewhere
                words = [w.strip() for w in search.split() if w.strip()]
                for i, word in enumerate(words):
                    param_name = f'search_{i}'
                    conditions.append(
                        f"(i.invoice_number ILIKE %({param_name})s OR i.partner_name ILIKE %({param_name})s OR i.partner_cif ILIKE %({param_name})s)"
                    )
                    params[param_name] = f'%{word}%'

            if hide_typed:
                # Hide invoices where ALL types have hide_in_filter=TRUE
                # If partner has mixed types (some hidden, some not), don't hide
                # Note: Use %% to escape % in psycopg2 with named parameters
                conditions.append("""
                    NOT (
                        -- All types are hidden via override (has hidden AND no non-hidden)
                        (i.type_override IS NOT NULL AND EXISTS (
                            SELECT 1 FROM efactura_partner_types pt
                            WHERE pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                                AND i.type_override ILIKE '%%' || pt.name || '%%'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM efactura_partner_types pt
                            WHERE pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                                AND i.type_override ILIKE '%%' || pt.name || '%%'
                        ))
                        OR
                        -- All types are hidden via supplier mapping (has hidden AND no non-hidden)
                        (i.type_override IS NULL AND EXISTS (
                            SELECT 1 FROM efactura_supplier_mappings sm2
                            JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                            JOIN efactura_partner_types pt ON pt.id = smt.type_id
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                        ) AND NOT EXISTS (
                            SELECT 1 FROM efactura_supplier_mappings sm2
                            JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                            JOIN efactura_partner_types pt ON pt.id = smt.type_id
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                        ))
                    )
                """)

            where_clause = ' AND '.join(conditions)

            # Build ORDER BY clause (validate column to prevent SQL injection)
            db_column = self.SORT_COLUMNS.get(sort_by, 'i.issue_date')
            sort_direction = 'ASC' if sort_dir.lower() == 'asc' else 'DESC'
            order_clause = f"{db_column} {sort_direction}, i.id {sort_direction}"

            # Get total count
            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            # If hide_typed is active, also count how many are hidden by the filter
            hidden_by_filter = 0
            if hide_typed:
                # Build conditions WITHOUT the hide_typed filter to count what would be hidden
                base_conditions = [c for c in conditions if 'hide_in_filter' not in c]
                base_where = ' AND '.join(base_conditions)
                cursor.execute(f"""
                    SELECT COUNT(*) as total FROM efactura_invoices i
                    WHERE {base_where}
                """, params)
                total_without_filter = cursor.fetchone()['total']
                hidden_by_filter = total_without_filter - total

            # OPTIMIZED: Fetch invoices and mappings without correlated subquery
            # Step 1: Get invoices with basic mapping data (dept/subdept only)
            cursor.execute(f"""
                SELECT i.*,
                    sm.id as mapping_id,
                    sm.department as mapping_department,
                    sm.subdepartment as mapping_subdepartment
                FROM efactura_invoices i
                LEFT JOIN efactura_supplier_mappings sm
                    ON LOWER(i.partner_name) = LOWER(sm.partner_name) AND sm.is_active = TRUE
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)

            rows = cursor.fetchall()

            # Step 2: Collect mapping IDs and fetch type_names in batch (single query)
            mapping_ids = [r['mapping_id'] for r in rows if r.get('mapping_id')]
            type_names_map = {}
            if mapping_ids:
                cursor.execute("""
                    SELECT smt.mapping_id, array_agg(pt.name ORDER BY pt.name) as type_names
                    FROM efactura_supplier_mapping_types smt
                    JOIN efactura_partner_types pt ON smt.type_id = pt.id
                    WHERE smt.mapping_id = ANY(%s)
                    GROUP BY smt.mapping_id
                """, (mapping_ids,))
                for type_row in cursor.fetchall():
                    type_names_map[type_row['mapping_id']] = type_row['type_names'] or []

            # Step 3: Build invoice list with merged data
            invoices = []
            for row in rows:
                inv = self._row_to_invoice(row)
                inv_dict = inv.__dict__.copy()
                mapping_id = row.get('mapping_id')
                type_names = type_names_map.get(mapping_id, []) if mapping_id else []
                inv_dict['type_names'] = type_names
                # Use override if set, otherwise use mapping types
                inv_dict['type_override'] = row.get('type_override')
                inv_dict['type_name'] = row.get('type_override') or (', '.join(type_names) if type_names else None)
                # Department: use override if set, otherwise use mapping
                inv_dict['department_override'] = row.get('department_override')
                inv_dict['mapping_department'] = row.get('mapping_department')  # Keep mapping value separate for frontend
                inv_dict['department'] = row.get('department_override') or row.get('mapping_department')
                # Subdepartment: use override if set, otherwise use mapping
                inv_dict['subdepartment_override'] = row.get('subdepartment_override')
                inv_dict['mapping_subdepartment'] = row.get('mapping_subdepartment')  # Keep mapping value separate for frontend
                inv_dict['subdepartment'] = row.get('subdepartment_override') or row.get('mapping_subdepartment')
                invoices.append(inv_dict)

            return invoices, total, hidden_by_filter
        finally:
            release_db(conn)

    def count_unallocated(self, cif_owner: Optional[str] = None) -> int:
        """Count unallocated invoices (excluding ignored and deleted)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            if cif_owner:
                cursor.execute("""
                    SELECT COUNT(*) as total FROM efactura_invoices
                    WHERE jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL AND cif_owner = %s
                """, (cif_owner,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as total FROM efactura_invoices
                    WHERE jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL
                """)
            return cursor.fetchone()['total']
        finally:
            release_db(conn)

    def get_unallocated_ids(
        self,
        company_id: Optional[int] = None,
        direction: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        hide_typed: bool = False,
    ) -> List[int]:
        """
        Get all IDs of unallocated invoices (for select all functionality).

        Args:
            company_id: Filter by company ID
            direction: Filter by direction
            start_date: Filter by start date
            end_date: Filter by end date
            search: Search by partner name or invoice number
            hide_typed: If True, hide invoices with types that have hide_in_filter=TRUE

        Returns:
            List of invoice IDs
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            where_clauses = ["i.jarvis_invoice_id IS NULL", "i.deleted_at IS NULL", "i.ignored = FALSE"]
            params = {}

            if company_id:
                where_clauses.append("i.company_id = %(company_id)s")
                params['company_id'] = company_id
            if direction:
                where_clauses.append("i.direction = %(direction)s")
                params['direction'] = direction
            if start_date:
                where_clauses.append("i.issue_date >= %(start_date)s")
                params['start_date'] = start_date
            if end_date:
                where_clauses.append("i.issue_date <= %(end_date)s")
                params['end_date'] = end_date
            if search:
                where_clauses.append("(i.partner_name ILIKE %(search)s OR i.invoice_number ILIKE %(search)s)")
                params['search'] = f"%{search}%"

            if hide_typed:
                # Hide invoices where ALL types have hide_in_filter=TRUE
                # If partner has mixed types (some hidden, some not), don't hide
                where_clauses.append("""
                    NOT (
                        (i.type_override IS NOT NULL AND EXISTS (
                            SELECT 1 FROM efactura_partner_types pt
                            WHERE pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                                AND i.type_override ILIKE '%%' || pt.name || '%%'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM efactura_partner_types pt
                            WHERE pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                                AND i.type_override ILIKE '%%' || pt.name || '%%'
                        ))
                        OR
                        (i.type_override IS NULL AND EXISTS (
                            SELECT 1 FROM efactura_supplier_mappings sm2
                            JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                            JOIN efactura_partner_types pt ON pt.id = smt.type_id
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                        ) AND NOT EXISTS (
                            SELECT 1 FROM efactura_supplier_mappings sm2
                            JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                            JOIN efactura_partner_types pt ON pt.id = smt.type_id
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                        ))
                    )
                """)

            where_clause = " AND ".join(where_clauses)
            cursor.execute(f"SELECT i.id FROM efactura_invoices i WHERE {where_clause}", params)
            return [row['id'] for row in cursor.fetchall()]
        finally:
            release_db(conn)

    # ============================================
    # Hidden Invoices (soft delete / ignored)
    # ============================================

    def list_hidden(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Invoice], int]:
        """
        List hidden invoices based on type settings.

        Hidden = invoices whose type has hide_in_filter = TRUE
        (Dynamic filtering based on partner type settings)
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Base conditions: not deleted, not allocated
            conditions = ['i.deleted_at IS NULL', 'i.jarvis_invoice_id IS NULL']
            params = {'limit': limit, 'offset': offset}

            # Hidden = manually ignored OR has ONLY hidden types (all types have hide_in_filter=TRUE)
            # If partner has mixed types (some hidden, some not), don't count as hidden
            conditions.append("""
                (
                    -- Manually ignored by user
                    i.ignored = TRUE
                    OR
                    -- All types are hidden via override (has hidden type AND no non-hidden type)
                    (i.type_override IS NOT NULL AND EXISTS (
                        SELECT 1 FROM efactura_partner_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_partner_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ))
                    OR
                    -- All types are hidden via supplier mapping (has hidden type AND no non-hidden type)
                    (i.type_override IS NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_mappings sm2
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                        JOIN efactura_partner_types pt ON pt.id = smt.type_id
                        WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                            AND sm2.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_mappings sm2
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                        JOIN efactura_partner_types pt ON pt.id = smt.type_id
                        WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                            AND sm2.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                    ))
                )
            """)

            if cif_owner:
                conditions.append('i.cif_owner = %(cif_owner)s')
                params['cif_owner'] = cif_owner

            if company_id is not None:
                conditions.append('i.company_id = %(company_id)s')
                params['company_id'] = company_id

            if direction is not None:
                conditions.append('i.direction = %(direction)s')
                params['direction'] = direction.value

            if start_date:
                conditions.append('i.issue_date >= %(start_date)s')
                params['start_date'] = start_date

            if end_date:
                conditions.append('i.issue_date <= %(end_date)s')
                params['end_date'] = end_date

            if search:
                # Elasticsearch-style: split into words, ALL words must match somewhere
                words = [w.strip() for w in search.split() if w.strip()]
                for i, word in enumerate(words):
                    param_name = f'search_{i}'
                    conditions.append(
                        f"(i.invoice_number ILIKE %({param_name})s OR i.partner_name ILIKE %({param_name})s OR i.partner_cif ILIKE %({param_name})s)"
                    )
                    params[param_name] = f'%{word}%'

            where_clause = ' AND '.join(conditions)

            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            # Get invoices with type_names from supplier mappings (via junction table)
            cursor.execute(f"""
                SELECT i.*,
                    COALESCE(
                        (SELECT array_agg(pt.name ORDER BY pt.name)
                         FROM efactura_supplier_mapping_types smt
                         JOIN efactura_partner_types pt ON smt.type_id = pt.id
                         WHERE smt.mapping_id = sm.id),
                        ARRAY[]::text[]
                    ) as type_names
                FROM efactura_invoices i
                LEFT JOIN efactura_supplier_mappings sm
                    ON LOWER(i.partner_name) = LOWER(sm.partner_name) AND sm.is_active = TRUE
                WHERE {where_clause}
                ORDER BY i.updated_at DESC, i.id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)

            invoices = []
            for row in cursor.fetchall():
                inv = self._row_to_invoice(row)
                inv_dict = inv.__dict__.copy()
                type_names = row.get('type_names') or []
                inv_dict['type_names'] = type_names
                inv_dict['type_name'] = ', '.join(type_names) if type_names else None
                invoices.append(inv_dict)

            return invoices, total
        finally:
            release_db(conn)

    def count_hidden(self) -> int:
        """Count hidden invoices (manually ignored OR all types hidden)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE i.deleted_at IS NULL
                    AND i.jarvis_invoice_id IS NULL
                    AND (
                        -- Manually ignored by user
                        i.ignored = TRUE
                        OR
                        -- All types are hidden via override (has hidden AND no non-hidden)
                        (i.type_override IS NOT NULL AND EXISTS (
                            SELECT 1 FROM efactura_partner_types pt
                            WHERE pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                                AND i.type_override ILIKE '%%' || pt.name || '%%'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM efactura_partner_types pt
                            WHERE pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                                AND i.type_override ILIKE '%%' || pt.name || '%%'
                        ))
                        OR
                        -- All types are hidden via supplier mapping (has hidden AND no non-hidden)
                        (i.type_override IS NULL AND EXISTS (
                            SELECT 1 FROM efactura_supplier_mappings sm2
                            JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                            JOIN efactura_partner_types pt ON pt.id = smt.type_id
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                        ) AND NOT EXISTS (
                            SELECT 1 FROM efactura_supplier_mappings sm2
                            JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                            JOIN efactura_partner_types pt ON pt.id = smt.type_id
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND pt.is_active = TRUE
                                AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                        ))
                    )
            """)
            return cursor.fetchone()['total']
        finally:
            release_db(conn)

    def restore_from_hidden(self, invoice_id: int) -> bool:
        """Restore an invoice from hidden (unignore)."""
        return self.ignore_invoice(invoice_id, ignored=False)

    def bulk_hide(self, invoice_ids: List[int]) -> int:
        """Hide multiple invoices (set ignored = TRUE)."""
        if not invoice_ids:
            return 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(invoice_ids))
            cursor.execute(f"""
                UPDATE efactura_invoices
                SET ignored = TRUE, updated_at = NOW()
                WHERE id IN ({placeholders}) AND ignored = FALSE AND deleted_at IS NULL
            """, invoice_ids)
            count = cursor.rowcount
            conn.commit()
            logger.info(f"Bulk hidden {count} invoices")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk hide invoices: {e}")
            return 0
        finally:
            release_db(conn)

    def bulk_restore_from_hidden(self, invoice_ids: List[int]) -> int:
        """Restore multiple invoices from hidden (set ignored = FALSE)."""
        if not invoice_ids:
            return 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(invoice_ids))
            cursor.execute(f"""
                UPDATE efactura_invoices
                SET ignored = FALSE, updated_at = NOW()
                WHERE id IN ({placeholders}) AND ignored = TRUE AND deleted_at IS NULL
            """, invoice_ids)
            count = cursor.rowcount
            conn.commit()
            logger.info(f"Bulk restored {count} invoices from hidden")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk restore invoices from hidden: {e}")
            return 0
        finally:
            release_db(conn)

    # ============================================
    # Bin (soft delete / deleted_at)
    # ============================================

    def list_deleted(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List deleted invoices (bin).

        Deleted = deleted_at IS NOT NULL
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            conditions = ['i.deleted_at IS NOT NULL']
            params = {'limit': limit, 'offset': offset}

            if cif_owner:
                conditions.append('i.cif_owner = %(cif_owner)s')
                params['cif_owner'] = cif_owner

            if company_id is not None:
                conditions.append('i.company_id = %(company_id)s')
                params['company_id'] = company_id

            if direction is not None:
                conditions.append('i.direction = %(direction)s')
                params['direction'] = direction.value

            if start_date:
                conditions.append('i.issue_date >= %(start_date)s')
                params['start_date'] = start_date

            if end_date:
                conditions.append('i.issue_date <= %(end_date)s')
                params['end_date'] = end_date

            if search:
                # Elasticsearch-style: split into words, ALL words must match somewhere
                words = [w.strip() for w in search.split() if w.strip()]
                for i, word in enumerate(words):
                    param_name = f'search_{i}'
                    conditions.append(
                        f"(i.invoice_number ILIKE %({param_name})s OR i.partner_name ILIKE %({param_name})s OR i.partner_cif ILIKE %({param_name})s)"
                    )
                    params[param_name] = f'%{word}%'

            where_clause = ' AND '.join(conditions)

            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            # Get invoices with type_names from supplier mappings (via junction table)
            cursor.execute(f"""
                SELECT i.*, i.deleted_at,
                    COALESCE(
                        (SELECT array_agg(pt.name ORDER BY pt.name)
                         FROM efactura_supplier_mapping_types smt
                         JOIN efactura_partner_types pt ON smt.type_id = pt.id
                         WHERE smt.mapping_id = sm.id),
                        ARRAY[]::text[]
                    ) as type_names
                FROM efactura_invoices i
                LEFT JOIN efactura_supplier_mappings sm
                    ON LOWER(i.partner_name) = LOWER(sm.partner_name) AND sm.is_active = TRUE
                WHERE {where_clause}
                ORDER BY i.deleted_at DESC, i.id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)

            invoices = []
            for row in cursor.fetchall():
                inv = self._row_to_invoice(row)
                type_names = row.get('type_names') or []
                invoices.append({
                    **inv.__dict__,
                    'deleted_at': row.get('deleted_at'),
                    'type_names': type_names,
                    'type_name': ', '.join(type_names) if type_names else None,
                })

            return invoices, total
        finally:
            release_db(conn)

    def count_deleted(self) -> int:
        """Count deleted invoices (bin)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT COUNT(*) as total FROM efactura_invoices
                WHERE deleted_at IS NOT NULL
            """)
            return cursor.fetchone()['total']
        finally:
            release_db(conn)

    def delete_invoice(self, invoice_id: int) -> bool:
        """Move an invoice to the bin (set deleted_at)."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoices
                SET deleted_at = NOW(), updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
            """, (invoice_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"Invoice {invoice_id} moved to bin")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete invoice: {e}")
            return False
        finally:
            release_db(conn)

    def restore_from_bin(self, invoice_id: int) -> bool:
        """Restore an invoice from the bin."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoices
                SET deleted_at = NULL, updated_at = NOW()
                WHERE id = %s AND deleted_at IS NOT NULL
            """, (invoice_id,))
            restored = cursor.rowcount > 0
            conn.commit()
            if restored:
                logger.info(f"Invoice {invoice_id} restored from bin")
            return restored
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to restore invoice from bin: {e}")
            return False
        finally:
            release_db(conn)

    def permanent_delete(self, invoice_id: int) -> bool:
        """Permanently delete an invoice from the bin."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            # Only allow permanent delete if already in bin
            cursor.execute("""
                DELETE FROM efactura_invoices
                WHERE id = %s AND deleted_at IS NOT NULL
            """, (invoice_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"Invoice {invoice_id} permanently deleted")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to permanently delete invoice: {e}")
            return False
        finally:
            release_db(conn)

    def bulk_delete(self, invoice_ids: List[int]) -> int:
        """Move multiple invoices to the bin."""
        if not invoice_ids:
            return 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(invoice_ids))
            cursor.execute(f"""
                UPDATE efactura_invoices
                SET deleted_at = NOW(), updated_at = NOW()
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
            """, invoice_ids)
            count = cursor.rowcount
            conn.commit()
            logger.info(f"Bulk deleted {count} invoices to bin")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk delete invoices: {e}")
            return 0
        finally:
            release_db(conn)

    def bulk_restore_from_bin(self, invoice_ids: List[int]) -> int:
        """Restore multiple invoices from the bin."""
        if not invoice_ids:
            return 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(invoice_ids))
            cursor.execute(f"""
                UPDATE efactura_invoices
                SET deleted_at = NULL, updated_at = NOW()
                WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL
            """, invoice_ids)
            count = cursor.rowcount
            conn.commit()
            logger.info(f"Bulk restored {count} invoices from bin")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk restore invoices from bin: {e}")
            return 0
        finally:
            release_db(conn)

    def bulk_permanent_delete(self, invoice_ids: List[int]) -> int:
        """Permanently delete multiple invoices from the bin."""
        if not invoice_ids:
            return 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(invoice_ids))
            # Only delete if already in bin
            cursor.execute(f"""
                DELETE FROM efactura_invoices
                WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL
            """, invoice_ids)
            count = cursor.rowcount
            conn.commit()
            logger.info(f"Bulk permanently deleted {count} invoices")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk permanently delete invoices: {e}")
            return 0
        finally:
            release_db(conn)

    def is_allocated(self, invoice_id: int) -> bool:
        """Check if an invoice has been allocated to the main Invoice Module."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT jarvis_invoice_id FROM efactura_invoices
                WHERE id = %s
            """, (invoice_id,))
            row = cursor.fetchone()
            if row is None:
                return False
            return row['jarvis_invoice_id'] is not None
        finally:
            release_db(conn)

    def mark_allocated(self, invoice_id: int, jarvis_invoice_id: int):
        """Mark an invoice as allocated to the main Invoice Module."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_invoices
                SET jarvis_invoice_id = %s, updated_at = NOW()
                WHERE id = %s
            """, (jarvis_invoice_id, invoice_id))
            conn.commit()
            logger.info(
                "Invoice marked as allocated",
                extra={
                    'efactura_invoice_id': invoice_id,
                    'jarvis_invoice_id': jarvis_invoice_id,
                }
            )
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to mark invoice as allocated: {e}")
            raise
        finally:
            release_db(conn)

    def get_invoices_for_module(
        self,
        invoice_ids: List[int],
    ) -> List[Dict[str, Any]]:
        """
        Batch fetch invoices for sending to Invoice Module.

        Fetches only unallocated invoices (jarvis_invoice_id IS NULL) with
        all columns needed for creating main invoices AND allocations.

        Includes:
        - Invoice data (supplier, number, date, amount, currency)
        - Company info (from company_id FK to companies table)
        - Department info (from overrides or supplier mapping defaults)

        Args:
            invoice_ids: List of e-Factura invoice IDs

        Returns:
            List of dicts with invoice data needed for module creation
        """
        if not invoice_ids:
            return []

        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT
                    i.id,
                    i.partner_name,
                    i.partner_cif,
                    i.invoice_number,
                    i.invoice_series,
                    i.issue_date,
                    i.total_amount,
                    i.total_vat,
                    i.total_without_vat,
                    i.currency,
                    i.company_id,
                    c.company as company_name,
                    i.department_override,
                    i.subdepartment_override,
                    sm.department as mapping_department,
                    sm.subdepartment as mapping_subdepartment,
                    sm.brand as mapping_brand,
                    (
                        SELECT ds.manager
                        FROM department_structure ds
                        WHERE ds.company = c.company
                            AND ds.department = COALESCE(i.department_override, sm.department)
                        ORDER BY
                            CASE WHEN ds.subdepartment = COALESCE(i.subdepartment_override, sm.subdepartment) THEN 0 ELSE 1 END,
                            ds.id
                        LIMIT 1
                    ) as responsible
                FROM efactura_invoices i
                LEFT JOIN companies c ON c.id = i.company_id
                LEFT JOIN efactura_supplier_mappings sm
                    ON LOWER(i.partner_name) = LOWER(sm.partner_name) AND sm.is_active = TRUE
                WHERE i.id = ANY(%s)
                AND i.jarvis_invoice_id IS NULL
                AND i.deleted_at IS NULL
            """, (invoice_ids,))
            rows = cursor.fetchall()

            result = []
            for row in rows:
                # Build full invoice number
                full_number = row['invoice_number']
                if row['invoice_series']:
                    full_number = f"{row['invoice_series']}-{row['invoice_number']}"

                # Use override if set, otherwise use mapping default
                effective_department = row['department_override'] or row['mapping_department']
                effective_subdepartment = row['subdepartment_override'] or row['mapping_subdepartment']

                result.append({
                    'id': row['id'],
                    'partner_name': row['partner_name'],
                    'partner_cif': row['partner_cif'],
                    'invoice_number': full_number,
                    'issue_date': row['issue_date'],
                    'total_amount': float(row['total_amount']),
                    'total_vat': float(row['total_vat']) if row['total_vat'] else 0.0,
                    'total_without_vat': float(row['total_without_vat']) if row['total_without_vat'] else None,
                    'currency': row['currency'],
                    'company_id': row['company_id'],
                    'company_name': row['company_name'],
                    'department': effective_department,
                    'subdepartment': effective_subdepartment,
                    'brand': row['mapping_brand'],
                    'responsible': row['responsible'],
                })

            logger.info(
                f"Batch fetched {len(result)} invoices for module (requested: {len(invoice_ids)})"
            )
            return result
        finally:
            release_db(conn)

    def bulk_mark_allocated(
        self,
        mappings: List[Tuple[int, int]],
    ) -> int:
        """
        Bulk mark invoices as allocated to main Invoice Module.

        Uses a single UPDATE with unnest for optimal performance.

        Args:
            mappings: List of (efactura_id, jarvis_invoice_id) tuples

        Returns:
            Number of rows updated
        """
        if not mappings:
            return 0

        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Extract separate lists for unnest
            efactura_ids = [m[0] for m in mappings]
            jarvis_ids = [m[1] for m in mappings]

            cursor.execute("""
                UPDATE efactura_invoices
                SET
                    jarvis_invoice_id = mapping.jarvis_id,
                    updated_at = NOW()
                FROM (
                    SELECT
                        unnest(%s::int[]) AS efactura_id,
                        unnest(%s::int[]) AS jarvis_id
                ) AS mapping
                WHERE efactura_invoices.id = mapping.efactura_id
            """, (efactura_ids, jarvis_ids))

            updated = cursor.rowcount
            conn.commit()

            logger.info(f"Bulk marked {updated} invoices as allocated")
            return updated

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk mark invoices as allocated: {e}")
            raise
        finally:
            release_db(conn)

    def create_with_refs(
        self,
        invoice: Invoice,
        external_ref: InvoiceExternalRef,
        artifact: InvoiceArtifact,
        xml_content: str,
    ) -> Optional[Invoice]:
        """
        Create invoice with external reference, artifact, and store XML content.

        This is a simplified version that stores the XML directly.
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Insert invoice
            cursor.execute("""
                INSERT INTO efactura_invoices (
                    cif_owner, company_id, direction, partner_cif, partner_name,
                    invoice_number, invoice_series, issue_date, due_date,
                    total_amount, total_vat, total_without_vat, currency,
                    status, xml_content, created_at, updated_at
                ) VALUES (
                    %(cif_owner)s, %(company_id)s, %(direction)s, %(partner_cif)s, %(partner_name)s,
                    %(invoice_number)s, %(invoice_series)s, %(issue_date)s, %(due_date)s,
                    %(total_amount)s, %(total_vat)s, %(total_without_vat)s, %(currency)s,
                    %(status)s, %(xml_content)s, NOW(), NOW()
                )
                RETURNING id, created_at, updated_at
            """, {
                'cif_owner': invoice.cif_owner,
                'company_id': invoice.company_id,
                'direction': invoice.direction.value,
                'partner_cif': invoice.partner_cif,
                'partner_name': invoice.partner_name,
                'invoice_number': invoice.invoice_number,
                'invoice_series': invoice.invoice_series,
                'issue_date': invoice.issue_date,
                'due_date': invoice.due_date,
                'total_amount': str(invoice.total_amount),
                'total_vat': str(invoice.total_vat),
                'total_without_vat': str(invoice.total_without_vat),
                'currency': invoice.currency,
                'status': invoice.status.value,
                'xml_content': xml_content,
            })

            row = cursor.fetchone()
            invoice.id = row['id']
            invoice.created_at = row['created_at']
            invoice.updated_at = row['updated_at']

            # Insert external reference
            external_ref.invoice_id = invoice.id
            cursor.execute("""
                INSERT INTO efactura_invoice_refs (
                    invoice_id, external_system, message_id,
                    upload_id, download_id, xml_hash,
                    created_at
                ) VALUES (
                    %(invoice_id)s, %(external_system)s, %(message_id)s,
                    %(upload_id)s, %(download_id)s, %(xml_hash)s, NOW()
                )
            """, {
                'invoice_id': external_ref.invoice_id,
                'external_system': external_ref.external_system,
                'message_id': external_ref.message_id,
                'upload_id': external_ref.upload_id,
                'download_id': external_ref.download_id,
                'xml_hash': external_ref.xml_hash,
            })

            # Insert artifact reference
            artifact.invoice_id = invoice.id
            cursor.execute("""
                INSERT INTO efactura_invoice_artifacts (
                    invoice_id, artifact_type, storage_uri,
                    original_filename, mime_type, checksum, size_bytes,
                    created_at
                ) VALUES (
                    %(invoice_id)s, %(artifact_type)s, %(storage_uri)s,
                    %(original_filename)s, %(mime_type)s, %(checksum)s,
                    %(size_bytes)s, NOW()
                )
            """, {
                'invoice_id': artifact.invoice_id,
                'artifact_type': artifact.artifact_type.value,
                'storage_uri': artifact.storage_uri,
                'original_filename': artifact.original_filename,
                'mime_type': artifact.mime_type,
                'checksum': artifact.checksum,
                'size_bytes': artifact.size_bytes,
            })

            conn.commit()

            logger.info(
                "Invoice created with XML content",
                extra={
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'message_id': external_ref.message_id,
                }
            )

            return invoice

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create invoice: {e}")
            return None
        finally:
            release_db(conn)

    def get_xml_content(self, invoice_id: int) -> Optional[str]:
        """Get stored XML content for an invoice."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT xml_content FROM efactura_invoices
                WHERE id = %s
            """, (invoice_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return row.get('xml_content')
        finally:
            release_db(conn)

    def _row_to_invoice(self, row: Dict[str, Any]) -> Invoice:
        """Convert database row to Invoice model."""
        from ..config import EFacturaStatus

        return Invoice(
            id=row['id'],
            cif_owner=row['cif_owner'],
            company_id=row.get('company_id'),
            direction=InvoiceDirection(row['direction']),
            partner_cif=row['partner_cif'],
            partner_name=row['partner_name'],
            invoice_number=row['invoice_number'],
            invoice_series=row.get('invoice_series'),
            issue_date=row.get('issue_date'),
            due_date=row.get('due_date'),
            total_amount=Decimal(str(row['total_amount'])),
            total_vat=Decimal(str(row['total_vat'])),
            total_without_vat=Decimal(str(row['total_without_vat'])),
            currency=row['currency'],
            status=EFacturaStatus(row['status']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )


class SupplierMappingRepository:
    """Repository for e-Factura supplier mappings."""

    def get_all(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all supplier mappings with their types.

        Args:
            active_only: If True, only return active mappings

        Returns:
            List of mapping dictionaries with type_ids and type_names arrays
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            # Get mappings with aggregated types from junction table
            where_clause = "WHERE m.is_active = TRUE" if active_only else ""
            cursor.execute(f"""
                SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                       m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                       m.brand, m.department, m.subdepartment,
                       COALESCE(
                           (SELECT array_agg(pt.id ORDER BY pt.name)
                            FROM efactura_supplier_mapping_types smt
                            JOIN efactura_partner_types pt ON smt.type_id = pt.id
                            WHERE smt.mapping_id = m.id),
                           ARRAY[]::integer[]
                       ) as type_ids,
                       COALESCE(
                           (SELECT array_agg(pt.name ORDER BY pt.name)
                            FROM efactura_supplier_mapping_types smt
                            JOIN efactura_partner_types pt ON smt.type_id = pt.id
                            WHERE smt.mapping_id = m.id),
                           ARRAY[]::text[]
                       ) as type_names
                FROM efactura_supplier_mappings m
                {where_clause}
                ORDER BY m.partner_name
            """)
            results = []
            for row in cursor.fetchall():
                mapping = dict(row)
                # Convert arrays to lists for JSON serialization
                mapping['type_ids'] = list(mapping['type_ids']) if mapping['type_ids'] else []
                mapping['type_names'] = list(mapping['type_names']) if mapping['type_names'] else []
                # Keep type_name for backward compatibility (first type or None)
                mapping['type_name'] = mapping['type_names'][0] if mapping['type_names'] else None
                results.append(mapping)
            return results
        finally:
            release_db(conn)

    def get_by_id(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """Get a single supplier mapping by ID with its types."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                       m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                       m.brand, m.department, m.subdepartment,
                       COALESCE(
                           (SELECT array_agg(pt.id ORDER BY pt.name)
                            FROM efactura_supplier_mapping_types smt
                            JOIN efactura_partner_types pt ON smt.type_id = pt.id
                            WHERE smt.mapping_id = m.id),
                           ARRAY[]::integer[]
                       ) as type_ids,
                       COALESCE(
                           (SELECT array_agg(pt.name ORDER BY pt.name)
                            FROM efactura_supplier_mapping_types smt
                            JOIN efactura_partner_types pt ON smt.type_id = pt.id
                            WHERE smt.mapping_id = m.id),
                           ARRAY[]::text[]
                       ) as type_names
                FROM efactura_supplier_mappings m
                WHERE m.id = %s
            """, (mapping_id,))
            row = cursor.fetchone()
            if not row:
                return None
            mapping = dict(row)
            mapping['type_ids'] = list(mapping['type_ids']) if mapping['type_ids'] else []
            mapping['type_names'] = list(mapping['type_names']) if mapping['type_names'] else []
            mapping['type_name'] = mapping['type_names'][0] if mapping['type_names'] else None
            return mapping
        finally:
            release_db(conn)

    def find_by_partner(
        self,
        partner_name: str,
        partner_cif: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find a mapping by partner name and optionally CIF.

        Tries exact CIF match first, then falls back to name-only match.
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Try exact match with CIF first
            if partner_cif:
                cursor.execute("""
                    SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                           m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                           pt.name as type_name
                    FROM efactura_supplier_mappings m
                    LEFT JOIN efactura_partner_types pt ON m.type_id = pt.id
                    WHERE LOWER(m.partner_name) = LOWER(%s) AND m.partner_cif = %s AND m.is_active = TRUE
                    LIMIT 1
                """, (partner_name, partner_cif))
                row = cursor.fetchone()
                if row:
                    return dict(row)

            # Fallback to name-only match
            cursor.execute("""
                SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                       m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                       pt.name as type_name
                FROM efactura_supplier_mappings m
                LEFT JOIN efactura_partner_types pt ON m.type_id = pt.id
                WHERE LOWER(m.partner_name) = LOWER(%s) AND m.is_active = TRUE
                LIMIT 1
            """, (partner_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def create(
        self,
        partner_name: str,
        supplier_name: str,
        partner_cif: Optional[str] = None,
        supplier_note: Optional[str] = None,
        supplier_vat: Optional[str] = None,
        kod_konto: Optional[str] = None,
        type_id: Optional[int] = None,
        type_ids: Optional[List[int]] = None,
        department: Optional[str] = None,
        subdepartment: Optional[str] = None,
        brand: Optional[str] = None,
    ) -> int:
        """Create a new supplier mapping.

        Args:
            partner_name: The e-Factura partner name (as it appears on invoices)
            supplier_name: The standardized supplier name to map to
            partner_cif: Optional VAT number from e-Factura
            supplier_note: Optional notes about the supplier
            supplier_vat: The standardized VAT number
            kod_konto: The accounting code
            type_id: Optional partner type ID (legacy, use type_ids instead)
            type_ids: Optional list of partner type IDs
            department: Optional default department for this supplier
            subdepartment: Optional default subdepartment for this supplier
            brand: Optional default brand for this supplier (from Settings brands)

        Returns:
            The new mapping ID
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                INSERT INTO efactura_supplier_mappings
                (partner_name, partner_cif, supplier_name, supplier_note, supplier_vat, kod_konto, type_id, department, subdepartment, brand)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (partner_name, partner_cif, supplier_name, supplier_note, supplier_vat, kod_konto, type_id, department, subdepartment, brand))
            mapping_id = cursor.fetchone()['id']

            # Insert types into junction table
            if type_ids:
                for tid in type_ids:
                    cursor.execute("""
                        INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                        VALUES (%s, %s)
                        ON CONFLICT (mapping_id, type_id) DO NOTHING
                    """, (mapping_id, tid))
            elif type_id:
                # Fallback to single type_id for backward compatibility
                cursor.execute("""
                    INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                    VALUES (%s, %s)
                    ON CONFLICT (mapping_id, type_id) DO NOTHING
                """, (mapping_id, type_id))

            conn.commit()
            logger.info(f"Created supplier mapping {mapping_id}: {partner_name} -> {supplier_name}")
            return mapping_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create supplier mapping: {e}")
            raise
        finally:
            release_db(conn)

    def update(
        self,
        mapping_id: int,
        partner_name: Optional[str] = None,
        partner_cif: Optional[str] = None,
        supplier_name: Optional[str] = None,
        supplier_note: Optional[str] = None,
        supplier_vat: Optional[str] = None,
        kod_konto: Optional[str] = None,
        type_id: Optional[int] = None,
        type_ids: Optional[List[int]] = None,
        is_active: Optional[bool] = None,
        department: Optional[str] = None,
        subdepartment: Optional[str] = None,
        brand: Optional[str] = None,
    ) -> bool:
        """Update a supplier mapping.

        Args:
            mapping_id: The mapping ID
            partner_name: New partner name
            partner_cif: New partner CIF
            supplier_name: New supplier name
            supplier_note: New supplier note
            supplier_vat: New supplier VAT
            kod_konto: New accounting code
            type_id: New partner type ID (legacy, use type_ids instead)
            type_ids: List of partner type IDs (pass empty list to clear types)
            is_active: Whether mapping is active
            department: New default department
            subdepartment: New default subdepartment
            brand: New default brand (from Settings brands)

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            updates = ['updated_at = NOW()']
            params = []

            if partner_name is not None:
                updates.append('partner_name = %s')
                params.append(partner_name)
            if partner_cif is not None:
                updates.append('partner_cif = %s')
                params.append(partner_cif if partner_cif else None)
            if supplier_name is not None:
                updates.append('supplier_name = %s')
                params.append(supplier_name)
            if supplier_note is not None:
                updates.append('supplier_note = %s')
                params.append(supplier_note if supplier_note else None)
            if supplier_vat is not None:
                updates.append('supplier_vat = %s')
                params.append(supplier_vat if supplier_vat else None)
            if kod_konto is not None:
                updates.append('kod_konto = %s')
                params.append(kod_konto if kod_konto else None)
            if type_id is not None:
                updates.append('type_id = %s')
                params.append(type_id if type_id else None)
            if is_active is not None:
                updates.append('is_active = %s')
                params.append(is_active)
            if department is not None:
                updates.append('department = %s')
                params.append(department if department else None)
            if subdepartment is not None:
                updates.append('subdepartment = %s')
                params.append(subdepartment if subdepartment else None)
            if brand is not None:
                updates.append('brand = %s')
                params.append(brand if brand else None)

            params.append(mapping_id)

            cursor.execute(f"""
                UPDATE efactura_supplier_mappings
                SET {', '.join(updates)}
                WHERE id = %s
            """, tuple(params))

            success = cursor.rowcount > 0

            # Update types in junction table if type_ids is provided
            if type_ids is not None:
                # Delete existing types
                cursor.execute("""
                    DELETE FROM efactura_supplier_mapping_types
                    WHERE mapping_id = %s
                """, (mapping_id,))

                # Insert new types
                for tid in type_ids:
                    cursor.execute("""
                        INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                        VALUES (%s, %s)
                        ON CONFLICT (mapping_id, type_id) DO NOTHING
                    """, (mapping_id, tid))

            conn.commit()
            if success:
                logger.info(f"Updated supplier mapping {mapping_id}")
            return success
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update supplier mapping: {e}")
            return False
        finally:
            release_db(conn)

    def delete(self, mapping_id: int) -> bool:
        """Delete a supplier mapping.

        Args:
            mapping_id: The mapping ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                DELETE FROM efactura_supplier_mappings WHERE id = %s
            """, (mapping_id,))
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Deleted supplier mapping {mapping_id}")
            return success
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete supplier mapping: {e}")
            return False
        finally:
            release_db(conn)

    def get_distinct_partners(self) -> List[Dict[str, Any]]:
        """
        Get distinct partner names and CIFs from e-Factura invoices.

        Returns:
            List of distinct partner name/CIF combinations from imported invoices
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT DISTINCT partner_name, partner_cif, COUNT(*) as invoice_count
                FROM efactura_invoices
                WHERE partner_name IS NOT NULL
                  AND deleted_at IS NULL
                GROUP BY partner_name, partner_cif
                ORDER BY COUNT(*) DESC, partner_name
            """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def migrate_junction_table(self) -> int:
        """
        One-time migration to create the supplier mapping types junction table.

        Returns:
            Number of records in the junction table after migration
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Create junction table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS efactura_supplier_mapping_types (
                    mapping_id INTEGER NOT NULL REFERENCES efactura_supplier_mappings(id) ON DELETE CASCADE,
                    type_id INTEGER NOT NULL REFERENCES efactura_partner_types(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (mapping_id, type_id)
                )
            ''')
            conn.commit()

            # Migrate existing type_id data
            cursor.execute('''
                INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                SELECT id, type_id FROM efactura_supplier_mappings
                WHERE type_id IS NOT NULL
                ON CONFLICT (mapping_id, type_id) DO NOTHING
            ''')
            conn.commit()

            # Count migrated records
            cursor.execute('SELECT COUNT(*) as count FROM efactura_supplier_mapping_types')
            result = cursor.fetchone()
            count = result['count'] if result else 0

            logger.info(f"Junction table migration completed. {count} records in table.")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Junction table migration failed: {e}")
            raise
        finally:
            release_db(conn)

    def bulk_set_types(self, mapping_ids: List[int], type_id: Optional[int]) -> Tuple[int, List[str]]:
        """
        Bulk set type for multiple supplier mappings.

        Args:
            mapping_ids: List of mapping IDs to update
            type_id: Type ID to set (None to clear types)

        Returns:
            Tuple of (updated_count, partner_names)
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            partner_names = []

            # Get partner names for these mappings (needed for auto-hide)
            if type_id:
                cursor.execute(
                    "SELECT id, partner_name FROM efactura_supplier_mappings WHERE id = ANY(%s)",
                    (mapping_ids,)
                )
                partner_names = [row['partner_name'] for row in cursor.fetchall()]

            updated_count = 0
            for mapping_id in mapping_ids:
                # Delete existing types for this mapping
                cursor.execute(
                    "DELETE FROM efactura_supplier_mapping_types WHERE mapping_id = %s",
                    (mapping_id,)
                )
                # Insert new type if provided
                if type_id:
                    cursor.execute(
                        "INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id) VALUES (%s, %s)",
                        (mapping_id, type_id)
                    )
                # Update timestamp on mapping
                cursor.execute(
                    "UPDATE efactura_supplier_mappings SET updated_at = NOW() WHERE id = %s",
                    (mapping_id,)
                )
                updated_count += 1

            conn.commit()
            logger.info(f"Bulk updated {updated_count} mappings with type_id={type_id}")
            return updated_count, partner_names
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk set types: {e}")
            raise
        finally:
            release_db(conn)


class PartnerTypeRepository:
    """Repository for e-Factura partner types (Service, Merchandise, etc.)."""

    def get_all(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all partner types.

        Args:
            active_only: If True, only return active types

        Returns:
            List of partner type dictionaries
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            if active_only:
                cursor.execute("""
                    SELECT id, name, description, is_active,
                           COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                           created_at, updated_at
                    FROM efactura_partner_types
                    WHERE is_active = TRUE
                    ORDER BY name
                """)
            else:
                cursor.execute("""
                    SELECT id, name, description, is_active,
                           COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                           created_at, updated_at
                    FROM efactura_partner_types
                    ORDER BY name
                """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_by_id(self, type_id: int) -> Optional[Dict[str, Any]]:
        """Get a single partner type by ID."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT id, name, description, is_active,
                       COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                       created_at, updated_at
                FROM efactura_partner_types
                WHERE id = %s
            """, (type_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a single partner type by name."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT id, name, description, is_active,
                       COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                       created_at, updated_at
                FROM efactura_partner_types
                WHERE name = %s AND is_active = TRUE
            """, (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def create(
        self,
        name: str,
        description: Optional[str] = None,
        hide_in_filter: bool = True,
    ) -> int:
        """Create a new partner type.

        Args:
            name: The type name (e.g., "Service", "Merchandise")
            description: Optional description
            hide_in_filter: Whether to hide invoices with this type when "Hide Typed" filter is on

        Returns:
            The new type ID
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                INSERT INTO efactura_partner_types (name, description, hide_in_filter)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (name, description, hide_in_filter))
            type_id = cursor.fetchone()['id']
            conn.commit()
            logger.info(f"Created partner type {type_id}: {name}")
            return type_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create partner type: {e}")
            raise
        finally:
            release_db(conn)

    def update(
        self,
        type_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        hide_in_filter: Optional[bool] = None,
    ) -> bool:
        """Update a partner type.

        Args:
            type_id: The type ID
            name: New name
            description: New description
            is_active: Whether type is active
            hide_in_filter: Whether to hide invoices with this type when "Hide Typed" filter is on

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            updates = ['updated_at = NOW()']
            params = []

            if name is not None:
                updates.append('name = %s')
                params.append(name)
            if description is not None:
                updates.append('description = %s')
                params.append(description if description else None)
            if is_active is not None:
                updates.append('is_active = %s')
                params.append(is_active)
            if hide_in_filter is not None:
                updates.append('hide_in_filter = %s')
                params.append(hide_in_filter)

            params.append(type_id)

            cursor.execute(f"""
                UPDATE efactura_partner_types
                SET {', '.join(updates)}
                WHERE id = %s
            """, tuple(params))

            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Updated partner type {type_id}")
            return success
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update partner type: {e}")
            return False
        finally:
            release_db(conn)

    def delete(self, type_id: int) -> bool:
        """Delete a partner type (soft delete by setting is_active = FALSE).

        Args:
            type_id: The type ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                UPDATE efactura_partner_types
                SET is_active = FALSE, updated_at = NOW()
                WHERE id = %s
            """, (type_id,))
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Soft-deleted partner type {type_id}")
            return success
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete partner type: {e}")
            return False
        finally:
            release_db(conn)
