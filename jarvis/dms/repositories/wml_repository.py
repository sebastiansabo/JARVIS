"""Repository for document_wml and document_wml_chunks tables."""
from psycopg2.extras import Json, execute_values
from core.base_repository import BaseRepository


class WmlRepository(BaseRepository):

    # ── document_wml ──

    def get_by_file(self, file_id):
        return self.query_one(
            'SELECT * FROM document_wml WHERE file_id = %s', (file_id,)
        )

    def get_by_document(self, document_id):
        return self.query_all(
            'SELECT * FROM document_wml WHERE document_id = %s ORDER BY id',
            (document_id,)
        )

    def upsert(self, document_id, file_id, raw_text, structured_json=None,
               extraction_method='mammoth'):
        return self.execute('''
            INSERT INTO document_wml (document_id, file_id, raw_text, structured_json, extraction_method)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (file_id) DO UPDATE SET
                raw_text = EXCLUDED.raw_text,
                structured_json = EXCLUDED.structured_json,
                extraction_method = EXCLUDED.extraction_method,
                extracted_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (
            document_id, file_id, raw_text,
            Json(structured_json) if structured_json else None,
            extraction_method,
        ), returning=True)

    def delete_by_file(self, file_id):
        return self.execute(
            'DELETE FROM document_wml WHERE file_id = %s', (file_id,)
        )

    # ── document_wml_chunks ──

    def get_chunks(self, wml_id):
        return self.query_all(
            'SELECT * FROM document_wml_chunks WHERE wml_id = %s ORDER BY chunk_index',
            (wml_id,)
        )

    def get_chunks_by_document(self, document_id):
        return self.query_all('''
            SELECT c.* FROM document_wml_chunks c
            JOIN document_wml w ON w.id = c.wml_id
            WHERE w.document_id = %s
            ORDER BY c.chunk_index
        ''', (document_id,))

    def replace_chunks(self, wml_id, chunks):
        """Delete existing chunks and batch-insert new ones."""
        def _work(cursor):
            cursor.execute('DELETE FROM document_wml_chunks WHERE wml_id = %s', (wml_id,))
            if not chunks:
                return 0
            values = [
                (wml_id, i, chunk.get('heading'), chunk['content'], chunk.get('token_count'))
                for i, chunk in enumerate(chunks)
            ]
            execute_values(cursor, '''
                INSERT INTO document_wml_chunks (wml_id, chunk_index, heading, content, token_count)
                VALUES %s
            ''', values)
            return len(chunks)
        return self.execute_many(_work)

    def search_chunks(self, query, document_id=None, limit=10):
        """Full-text search across chunks."""
        conditions = ["to_tsvector('simple', c.content) @@ plainto_tsquery('simple', %s)"]
        params = [query]
        if document_id:
            conditions.append('w.document_id = %s')
            params.append(document_id)
        params.extend([query, limit])
        where = ' AND '.join(conditions)
        return self.query_all(f'''
            SELECT c.*, w.document_id, w.file_id,
                   ts_rank(to_tsvector('simple', c.content), plainto_tsquery('simple', %s)) AS score
            FROM document_wml_chunks c
            JOIN document_wml w ON w.id = c.wml_id
            WHERE {where}
            ORDER BY score DESC
            LIMIT %s
        ''', tuple(params))
