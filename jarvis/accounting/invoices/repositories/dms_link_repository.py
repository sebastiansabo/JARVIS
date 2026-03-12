"""Repository for invoice_dms_links — links DMS documents to invoices."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.invoices.dms_link_repo')


class InvoiceDmsLinkRepository(BaseRepository):

    def get_by_invoice(self, invoice_id):
        """Get all linked DMS documents for an invoice."""
        return self.query_all('''
            SELECT l.id, l.invoice_id, l.document_id, l.linked_by,
                   u.name as linked_by_name, l.created_at,
                   d.title, d.description, d.status,
                   d.doc_number, d.doc_date, d.expiry_date,
                   d.category_id, c.name as category_name, c.color as category_color,
                   d.signature_status, d.company_id,
                   comp.company as company_name,
                   d.created_by, cb.name as created_by_name,
                   d.created_at as doc_created_at,
                   d.visibility,
                   (SELECT COUNT(*) FROM dms_files df WHERE df.document_id = d.id) as file_count,
                   (SELECT COUNT(*) FROM dms_documents ch
                    WHERE ch.parent_id = d.id AND ch.deleted_at IS NULL) as children_count,
                   CASE WHEN d.expiry_date IS NOT NULL
                        THEN (d.expiry_date::date - CURRENT_DATE)::integer
                        ELSE NULL END as days_to_expiry
            FROM invoice_dms_links l
            JOIN dms_documents d ON d.id = l.document_id
            JOIN users u ON u.id = l.linked_by
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies comp ON comp.id = d.company_id
            LEFT JOIN users cb ON cb.id = d.created_by
            WHERE l.invoice_id = %s AND d.deleted_at IS NULL
            ORDER BY l.created_at DESC
        ''', (invoice_id,))

    def get_by_document(self, document_id):
        """Reverse lookup: get all invoices linked to a DMS document."""
        return self.query_all('''
            SELECT l.id, l.invoice_id, l.document_id, l.linked_by,
                   u.name as linked_by_name, l.created_at,
                   i.supplier, i.invoice_number, i.invoice_date,
                   i.invoice_value, i.currency, i.status, i.payment_status
            FROM invoice_dms_links l
            JOIN invoices i ON i.id = l.invoice_id
            JOIN users u ON u.id = l.linked_by
            WHERE l.document_id = %s AND i.deleted_at IS NULL
            ORDER BY i.invoice_date DESC
        ''', (document_id,))

    def link(self, invoice_id, document_id, linked_by):
        """Link a DMS document to an invoice. Returns link ID or None if already linked."""
        row = self.execute('''
            INSERT INTO invoice_dms_links (invoice_id, document_id, linked_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (invoice_id, document_id) DO NOTHING
            RETURNING id
        ''', (invoice_id, document_id, linked_by), returning=True)
        return row['id'] if row else None

    def unlink(self, invoice_id, document_id):
        """Remove a DMS document link from an invoice."""
        return self.execute(
            'DELETE FROM invoice_dms_links WHERE invoice_id = %s AND document_id = %s',
            (invoice_id, document_id),
        ) > 0

    def search_documents(self, query=None, limit=20):
        """Search DMS documents for the linking picker."""
        sql = '''
            SELECT d.id, d.title, d.status, d.doc_number, d.doc_date,
                   d.expiry_date, c.name as category_name, c.color as category_color,
                   (SELECT COUNT(*) FROM dms_files df WHERE df.document_id = d.id) as file_count
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            WHERE d.deleted_at IS NULL AND d.parent_id IS NULL
        '''
        params = []
        if query:
            sql += " AND (d.title ILIKE %s OR d.doc_number ILIKE %s)"
            like = f'%{query}%'
            params.extend([like, like])
        sql += ' ORDER BY d.created_at DESC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, params)
