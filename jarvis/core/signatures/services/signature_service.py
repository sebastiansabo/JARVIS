"""Signature service — orchestrates signature request lifecycle."""
import logging
import os

from core.signatures.repositories import SignatureRepository
from core.signatures.services.pdf_utils import embed_signature_image, hash_pdf

logger = logging.getLogger('jarvis.core.signatures.signature_service')

# Base directory for signed PDFs
SIGNED_PDF_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'static', 'signed_pdfs',
)


class SignatureService:

    def __init__(self):
        self._repo = SignatureRepository()

    def request_signature(self, document_type, document_id, signed_by,
                          original_pdf_path=None, callback_url=None):
        """Create a new signature request.

        Args:
            document_type: Type of document ('approval', 'invoice', etc.)
            document_id: ID of the document.
            signed_by: User ID who should sign.
            original_pdf_path: Optional path to PDF to embed signature into.
            callback_url: Optional URL to redirect after signing.

        Returns:
            dict with signature request data.
        """
        sig = self._repo.create(
            document_type, document_id, signed_by,
            original_pdf_path, callback_url,
        )
        logger.info(
            f'Signature request created: id={sig["id"]} '
            f'type={document_type} doc={document_id} signer={signed_by}'
        )
        return sig

    def process_signature(self, signature_id, base64_image, ip_address):
        """Process a submitted signature — embed into PDF if applicable, hash, and save.

        Args:
            signature_id: ID of the signature request.
            base64_image: Base64-encoded PNG of the drawn signature.
            ip_address: IP address of the signer.

        Returns:
            Updated signature dict.

        Raises:
            ValueError: If signature not found or already processed.
        """
        sig = self._repo.get_by_id(signature_id)
        if not sig:
            raise ValueError(f'Signature request {signature_id} not found')
        if sig['status'] != 'pending':
            raise ValueError(
                f'Signature {signature_id} is {sig["status"]}, expected pending'
            )

        signed_pdf_path = None
        document_hash = None

        # If there's an original PDF, embed the signature into it
        if sig.get('original_pdf_path') and os.path.exists(sig['original_pdf_path']):
            os.makedirs(SIGNED_PDF_DIR, exist_ok=True)
            signed_pdf_path = os.path.join(
                SIGNED_PDF_DIR,
                f'signed_{sig["document_type"]}_{sig["document_id"]}_{signature_id}.pdf',
            )
            embed_signature_image(
                sig['original_pdf_path'], base64_image, signed_pdf_path,
            )
            document_hash = hash_pdf(signed_pdf_path)

        self._repo.save_signed(
            signature_id, base64_image, signed_pdf_path,
            document_hash, ip_address,
        )

        updated = self._repo.get_by_id(signature_id)
        logger.info(
            f'Signature {signature_id} signed by user '
            f'from {ip_address}'
        )
        return updated

    def get_status(self, signature_id):
        """Get the current status of a signature request."""
        sig = self._repo.get_by_id(signature_id)
        if not sig:
            raise ValueError(f'Signature request {signature_id} not found')
        return sig

    def verify_integrity(self, signed_pdf_path, stored_hash):
        """Verify a signed PDF hasn't been tampered with.

        Args:
            signed_pdf_path: Path to the signed PDF.
            stored_hash: The SHA-256 hash stored at signing time.

        Returns:
            True if hash matches, False otherwise.
        """
        if not signed_pdf_path or not stored_hash:
            return False
        try:
            current_hash = hash_pdf(signed_pdf_path)
            return current_hash == stored_hash
        except FileNotFoundError:
            logger.warning(f'Signed PDF not found for verification: {signed_pdf_path}')
            return False
