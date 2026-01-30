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
                    cif_owner, direction, partner_cif, partner_name,
                    invoice_number, invoice_series, issue_date, due_date,
                    total_amount, total_vat, total_without_vat, currency,
                    status, created_at, updated_at
                ) VALUES (
                    %(cif_owner)s, %(direction)s, %(partner_cif)s, %(partner_name)s,
                    %(invoice_number)s, %(invoice_series)s, %(issue_date)s, %(due_date)s,
                    %(total_amount)s, %(total_vat)s, %(total_without_vat)s, %(currency)s,
                    %(status)s, NOW(), NOW()
                )
                RETURNING id, created_at, updated_at
            """, {
                'cif_owner': invoice.cif_owner,
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

    def get_by_id(self, invoice_id: int) -> Optional[Invoice]:
        """Get invoice by ID."""
        conn = get_db()
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT * FROM efactura_invoices
            WHERE id = %s
        """, (invoice_id,))

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_invoice(row)

    def get_by_message_id(
        self,
        cif_owner: str,
        direction: InvoiceDirection,
        message_id: str,
    ) -> Optional[Invoice]:
        """Get invoice by ANAF message ID (for deduplication)."""
        conn = get_db()
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

    def exists_by_message_id(
        self,
        cif_owner: str,
        direction: InvoiceDirection,
        message_id: str,
    ) -> bool:
        """Check if invoice exists (fast dedup check)."""
        conn = get_db()
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

    def get_external_ref(self, invoice_id: int) -> Optional[InvoiceExternalRef]:
        """Get external reference for an invoice."""
        conn = get_db()
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

    def get_artifacts(self, invoice_id: int) -> List[InvoiceArtifact]:
        """Get artifacts for an invoice."""
        conn = get_db()
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

    def get_artifact_by_type(
        self,
        invoice_id: int,
        artifact_type: ArtifactType,
    ) -> Optional[InvoiceArtifact]:
        """Get specific artifact type for an invoice."""
        conn = get_db()
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

    def update_artifact_uri(
        self,
        artifact_id: int,
        storage_uri: str,
    ):
        """Update artifact storage URI after upload."""
        conn = get_db()
        cursor = get_cursor(conn)

        try:
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

    def get_summary(
        self,
        cif_owner: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get invoice summary statistics."""
        conn = get_db()
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

    def _row_to_invoice(self, row: Dict[str, Any]) -> Invoice:
        """Convert database row to Invoice model."""
        from ..config import EFacturaStatus

        return Invoice(
            id=row['id'],
            cif_owner=row['cif_owner'],
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
