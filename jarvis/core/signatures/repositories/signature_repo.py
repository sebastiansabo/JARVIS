"""Repository for document_signatures table."""
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.signatures.signature_repo')


class SignatureRepository(BaseRepository):

    def create(self, document_type, document_id, signed_by,
               original_pdf_path=None, callback_url=None):
        """Create a new signature request. Returns dict with id."""
        return self.execute(
            '''INSERT INTO document_signatures
               (document_type, document_id, signed_by, original_pdf_path, callback_url)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, document_type, document_id, signed_by, status, created_at''',
            (document_type, document_id, signed_by, original_pdf_path, callback_url),
            returning=True,
        )

    def get_by_id(self, sig_id):
        """Get a signature by ID. Returns dict or None."""
        return self.query_one(
            'SELECT * FROM document_signatures WHERE id = %s',
            (sig_id,),
        )

    def get_for_document(self, document_type, document_id):
        """Get all signatures for a specific document."""
        return self.query_all(
            '''SELECT ds.*, u.name as signer_name
               FROM document_signatures ds
               JOIN users u ON u.id = ds.signed_by
               WHERE ds.document_type = %s AND ds.document_id = %s
               ORDER BY ds.created_at DESC''',
            (document_type, document_id),
        )

    def get_pending_for_user(self, user_id):
        """Get all pending signature requests for a user."""
        return self.query_all(
            '''SELECT * FROM document_signatures
               WHERE signed_by = %s AND status = 'pending'
               ORDER BY created_at DESC''',
            (user_id,),
        )

    def update_status(self, sig_id, status):
        """Update signature status. Returns rowcount."""
        return self.execute(
            '''UPDATE document_signatures
               SET status = %s, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s''',
            (status, sig_id),
        )

    def save_signed(self, sig_id, signature_image, signed_pdf_path,
                    document_hash, ip_address):
        """Save completed signature data. Returns rowcount."""
        return self.execute(
            '''UPDATE document_signatures
               SET signature_image = %s, signed_pdf_path = %s,
                   document_hash = %s, ip_address = %s,
                   status = 'signed', signed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s''',
            (signature_image, signed_pdf_path, document_hash,
             ip_address, sig_id),
        )
