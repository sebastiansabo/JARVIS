"""Data access for the mandatory consent-documents gate."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


class ConsentRepository(BaseRepository):
    # ---------- documents ----------
    def list_active_mandatory(self) -> List[Dict[str, Any]]:
        return self.query_all('''
            SELECT id, doc_key, title, body, sort_order, version, requires_signature
            FROM consent_documents
            WHERE is_active = TRUE AND is_mandatory = TRUE
            ORDER BY sort_order, id
        ''')

    def list_all(self) -> List[Dict[str, Any]]:
        return self.query_all('''
            SELECT id, doc_key, title, body, sort_order, requires_signature,
                   is_mandatory, is_active, version, updated_at, updated_by
            FROM consent_documents
            ORDER BY sort_order, id
        ''')

    def get_by_id(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one('''
            SELECT id, doc_key, title, body, sort_order, requires_signature,
                   is_mandatory, is_active, version
            FROM consent_documents WHERE id = %s
        ''', (doc_id,))

    def get_by_key(self, doc_key: str) -> Optional[Dict[str, Any]]:
        return self.query_one('''
            SELECT id, doc_key, title, body, sort_order, requires_signature,
                   is_mandatory, is_active, version
            FROM consent_documents WHERE doc_key = %s AND is_active = TRUE
        ''', (doc_key,))

    def create_document(self, doc_key, title, body, sort_order,
                        requires_signature, is_mandatory, is_active, updated_by):
        return self.execute('''
            INSERT INTO consent_documents
                (doc_key, title, body, sort_order, requires_signature,
                 is_mandatory, is_active, version, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)
            RETURNING id, doc_key, title, version, is_active
        ''', (doc_key, title, body, sort_order, requires_signature,
              is_mandatory, is_active, updated_by), returning=True)

    def update_document(self, doc_id, title, body, sort_order, is_active,
                        bump_version, updated_by):
        return self.execute('''
            UPDATE consent_documents
               SET title = %s, body = %s, sort_order = %s, is_active = %s,
                   version = version + %s, updated_at = NOW(), updated_by = %s
             WHERE id = %s
            RETURNING id, doc_key, title, version, is_active
        ''', (title, body, sort_order, is_active, 1 if bump_version else 0,
              updated_by, doc_id), returning=True)

    # ---------- signatures ----------
    def get_user_signed_ids(self, user_id: int) -> List[int]:
        rows = self.query_all('''
            SELECT document_id FROM user_consent_signatures
            WHERE user_id = %s AND response = 'accepted'
        ''', (user_id,))
        return [r['document_id'] for r in rows]

    def insert_signature(self, user_id, document_id, version, signature_image,
                         document_hash, ip, user_agent) -> None:
        self.execute('''
            INSERT INTO user_consent_signatures
                (user_id, document_id, document_version, response,
                 signature_image, document_hash, ip_address, user_agent)
            VALUES (%s, %s, %s, 'accepted', %s, %s, %s, %s)
            ON CONFLICT (user_id, document_id) DO NOTHING
        ''', (user_id, document_id, version, signature_image,
              document_hash, ip, user_agent))

    def count_active_mandatory(self) -> int:
        row = self.query_one('''
            SELECT COUNT(*) AS n FROM consent_documents
            WHERE is_active = TRUE AND is_mandatory = TRUE
        ''')
        return int(row['n']) if row else 0

    def count_user_accepted_mandatory(self, user_id: int) -> int:
        row = self.query_one('''
            SELECT COUNT(*) AS n
            FROM user_consent_signatures s
            JOIN consent_documents d ON d.id = s.document_id
            WHERE s.user_id = %s AND s.response = 'accepted'
              AND d.is_active = TRUE AND d.is_mandatory = TRUE
        ''', (user_id,))
        return int(row['n']) if row else 0

    def get_compliance(self) -> List[Dict[str, Any]]:
        return self.query_all('''
            SELECT u.id AS user_id, u.name, u.email, u.company,
                   d.doc_key, d.title, s.signed_at,
                   (s.id IS NOT NULL) AS signed
            FROM users u
            CROSS JOIN consent_documents d
            LEFT JOIN user_consent_signatures s
              ON s.user_id = u.id AND s.document_id = d.id
             AND s.response = 'accepted'
            WHERE d.is_active = TRUE AND d.is_mandatory = TRUE
              AND u.is_active = TRUE
            ORDER BY u.name, d.sort_order
        ''')
