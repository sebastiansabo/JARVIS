"""Document Repository — Data access for carpark_vehicle_documents."""
from typing import Optional, Dict, Any, List

from core.base_repository import BaseRepository


DOCUMENT_FIELDS = (
    'document_type', 'title', 'file_url', 'dms_document_id',
    'file_size', 'mime_type', 'notes', 'uploaded_by',
)


class DocumentRepository(BaseRepository):
    """Data access for vehicle document records."""

    def list_for_vehicle(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """All documents for a vehicle, most recently uploaded first."""
        return self.query_all('''
            SELECT * FROM carpark_vehicle_documents
            WHERE vehicle_id = %s
            ORDER BY upload_date DESC, id DESC
        ''', (vehicle_id,))

    def get(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Single document record by id."""
        return self.query_one(
            'SELECT * FROM carpark_vehicle_documents WHERE id = %s', (doc_id,)
        )

    def create(self, vehicle_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a document record for a vehicle. `document_type` is required."""
        safe = {k: data[k] for k in DOCUMENT_FIELDS if k in data and data[k] is not None}
        if 'document_type' not in safe:
            raise ValueError('document_type is required')

        cols = ['vehicle_id'] + list(safe.keys())
        vals = [vehicle_id] + list(safe.values())
        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_vehicle_documents ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def delete(self, doc_id: int) -> bool:
        """Delete a single document record. Returns True if a row was removed."""
        return self.execute(
            'DELETE FROM carpark_vehicle_documents WHERE id = %s', (doc_id,)
        ) > 0

    def has_type(self, vehicle_id: int, document_type: str) -> bool:
        """True if the vehicle has at least one uploaded document of this type."""
        row = self.query_one('''
            SELECT 1 AS present FROM carpark_vehicle_documents
            WHERE vehicle_id = %s AND document_type = %s
            LIMIT 1
        ''', (vehicle_id, document_type))
        return row is not None

    def distinct_types(self, vehicle_id: int) -> List[str]:
        """Distinct document_type values uploaded for a vehicle, sorted."""
        rows = self.query_all('''
            SELECT DISTINCT document_type FROM carpark_vehicle_documents
            WHERE vehicle_id = %s
            ORDER BY document_type
        ''', (vehicle_id,))
        return [r['document_type'] for r in rows]
