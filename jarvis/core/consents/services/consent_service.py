"""Business logic for the mandatory consent-documents gate."""
import hashlib
from typing import Dict, Any, Optional
from core.consents.repositories.consent_repository import ConsentRepository

_MAX_SIGNATURE_BYTES = 700_000  # ~500KB PNG in base64


def _valid_png(data: str) -> bool:
    return bool(data) and data.startswith('data:image/png;base64,') and len(data) < _MAX_SIGNATURE_BYTES


class ConsentService:
    def __init__(self, repo: Optional[ConsentRepository] = None):
        self.repo = repo or ConsentRepository()

    @staticmethod
    def compute_hash(body: str) -> str:
        return hashlib.sha256((body or '').encode('utf-8')).hexdigest()

    def get_pending_for_user(self, user_id: int) -> Dict[str, Any]:
        docs = self.repo.list_active_mandatory()
        signed = set(self.repo.get_user_signed_ids(user_id))
        pending = [d for d in docs if d['id'] not in signed]
        return {'complete': len(pending) == 0, 'pending': pending}

    def is_complete(self, user_id: int) -> bool:
        return self.repo.count_user_accepted_mandatory(user_id) >= self.repo.count_active_mandatory()

    def pending_count(self, user_id: int) -> int:
        return max(0, self.repo.count_active_mandatory() - self.repo.count_user_accepted_mandatory(user_id))

    def get_status(self, user_id: int) -> Dict[str, Any]:
        """Combined is_complete + pending_count in a single pass (2 queries
        instead of 4) — used by the hot current-user endpoints, which must
        not call is_complete()/pending_count() separately."""
        active = self.repo.count_active_mandatory()
        accepted = self.repo.count_user_accepted_mandatory(user_id)
        return {'complete': accepted >= active, 'pending_count': max(0, active - accepted)}

    def sign(self, user_id: int, document_id: int, signature_image: str,
             ip: str, user_agent: str) -> Dict[str, Any]:
        doc = self.repo.get_by_id(document_id)
        if not doc or not doc.get('is_active') or not doc.get('is_mandatory'):
            raise ValueError('invalid_document')
        if doc.get('requires_signature') and not _valid_png(signature_image):
            raise ValueError('signature_required')
        self.repo.insert_signature(
            user_id, document_id, doc['version'], signature_image,
            self.compute_hash(doc['body']), ip, user_agent)
        return {'complete': self.is_complete(user_id),
                'pending_count': self.pending_count(user_id)}
