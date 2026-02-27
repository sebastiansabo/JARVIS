"""Repository for dms_documents table."""
from core.base_repository import BaseRepository


class DocumentRepository(BaseRepository):

    def list_documents(self, company_id=None, category_id=None, status=None,
                       search=None, limit=50, offset=0,
                       user_id=None, role_id=None):
        """List root documents (parent_id IS NULL) with filters and visibility."""
        conditions = ['d.parent_id IS NULL', 'd.deleted_at IS NULL']
        params = []

        if company_id:
            conditions.append('d.company_id = %s')
            params.append(company_id)

        if category_id:
            conditions.append('d.category_id = %s')
            params.append(category_id)
        if status:
            conditions.append('d.status = %s')
            params.append(status)
        if search:
            conditions.append("(d.title ILIKE %s OR d.description ILIKE %s)")
            like = f'%{search}%'
            params.extend([like, like])

        # Visibility: non-admin users only see permitted documents + categories
        if user_id and role_id:
            conditions.append(
                "(d.visibility = 'all' OR d.created_by = %s"
                " OR %s = ANY(d.allowed_user_ids)"
                " OR %s = ANY(d.allowed_role_ids))"
            )
            params.extend([user_id, user_id, role_id])
            conditions.append(
                '(c.allowed_role_ids IS NULL OR %s = ANY(c.allowed_role_ids))'
            )
            params.append(role_id)

        where = 'WHERE ' + ' AND '.join(conditions)

        # Get total count (needs category JOIN for visibility filter)
        count_row = self.query_one(f'''
            SELECT COUNT(*) AS total
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            {where}
        ''', tuple(params))
        total = count_row['total'] if count_row else 0

        # Get page
        params.extend([limit, offset])
        documents = self.query_all(f'''
            SELECT d.*,
                   c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                   co.company AS company_name,
                   u.name AS created_by_name,
                   nu.name AS notify_user_name,
                   d.expiry_date - CURRENT_DATE AS days_to_expiry,
                   (SELECT COUNT(*) FROM dms_files WHERE document_id = d.id) AS file_count,
                   (SELECT COUNT(*) FROM dms_documents
                    WHERE parent_id = d.id AND deleted_at IS NULL) AS children_count
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies co ON co.id = d.company_id
            LEFT JOIN users u ON u.id = d.created_by
            LEFT JOIN users nu ON nu.id = d.notify_user_id
            {where}
            ORDER BY d.created_at DESC
            LIMIT %s OFFSET %s
        ''', tuple(params))

        return {'documents': documents, 'total': total}

    def get_by_id(self, doc_id):
        return self.query_one('''
            SELECT d.*,
                   c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                   co.company AS company_name,
                   u.name AS created_by_name,
                   nu.name AS notify_user_name,
                   d.expiry_date - CURRENT_DATE AS days_to_expiry,
                   (SELECT COUNT(*) FROM dms_files WHERE document_id = d.id) AS file_count,
                   (SELECT COUNT(*) FROM dms_documents
                    WHERE parent_id = d.id AND deleted_at IS NULL) AS children_count
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies co ON co.id = d.company_id
            LEFT JOIN users u ON u.id = d.created_by
            LEFT JOIN users nu ON nu.id = d.notify_user_id
            WHERE d.id = %s AND d.deleted_at IS NULL
        ''', (doc_id,))

    def get_ancestors(self, doc_id):
        """Walk up parent chain and return list from root → immediate parent."""
        return self.query_all('''
            WITH RECURSIVE chain AS (
                SELECT id, title, parent_id, 0 AS depth
                FROM dms_documents WHERE id = (
                    SELECT parent_id FROM dms_documents WHERE id = %s
                )
                UNION ALL
                SELECT d.id, d.title, d.parent_id, c.depth + 1
                FROM dms_documents d
                JOIN chain c ON c.parent_id = d.id
            )
            SELECT id, title FROM chain ORDER BY depth DESC
        ''', (doc_id,))

    def get_children(self, parent_id):
        """Get children of a document, including their file counts."""
        return self.query_all('''
            SELECT d.*,
                   c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                   u.name AS created_by_name,
                   (SELECT COUNT(*) FROM dms_files WHERE document_id = d.id) AS file_count
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN users u ON u.id = d.created_by
            WHERE d.parent_id = %s AND d.deleted_at IS NULL
            ORDER BY d.relationship_type, d.created_at DESC
        ''', (parent_id,))

    def get_stats(self, company_id=None):
        """Get document counts by category and status."""
        if company_id:
            by_category = self.query_all('''
                SELECT c.id AS category_id, c.name AS category_name, c.icon, c.color,
                       COUNT(d.id) AS count
                FROM dms_categories c
                LEFT JOIN dms_documents d ON d.category_id = c.id
                    AND d.deleted_at IS NULL AND d.parent_id IS NULL
                    AND d.company_id = %s
                WHERE c.is_active = TRUE AND (c.company_id = %s OR c.company_id IS NULL)
                GROUP BY c.id, c.name, c.icon, c.color
                ORDER BY c.sort_order
            ''', (company_id, company_id))

            by_status = self.query_one('''
                SELECT
                    COUNT(*) FILTER (WHERE TRUE) AS total,
                    COUNT(*) FILTER (WHERE status = 'draft') AS draft,
                    COUNT(*) FILTER (WHERE status = 'active') AS active,
                    COUNT(*) FILTER (WHERE status = 'archived') AS archived
                FROM dms_documents
                WHERE deleted_at IS NULL AND parent_id IS NULL AND company_id = %s
            ''', (company_id,))
        else:
            by_category = self.query_all('''
                SELECT c.id AS category_id, c.name AS category_name, c.icon, c.color,
                       COUNT(d.id) AS count
                FROM dms_categories c
                LEFT JOIN dms_documents d ON d.category_id = c.id
                    AND d.deleted_at IS NULL AND d.parent_id IS NULL
                WHERE c.is_active = TRUE
                GROUP BY c.id, c.name, c.icon, c.color
                ORDER BY c.sort_order
            ''')

            by_status = self.query_one('''
                SELECT
                    COUNT(*) FILTER (WHERE TRUE) AS total,
                    COUNT(*) FILTER (WHERE status = 'draft') AS draft,
                    COUNT(*) FILTER (WHERE status = 'active') AS active,
                    COUNT(*) FILTER (WHERE status = 'archived') AS archived
                FROM dms_documents
                WHERE deleted_at IS NULL AND parent_id IS NULL
            ''')

        return {'by_category': by_category, 'by_status': by_status or {}}

    def create(self, title, company_id, created_by, **kwargs):
        return self.execute('''
            INSERT INTO dms_documents (title, description, category_id, company_id, status,
                                       parent_id, relationship_type, metadata,
                                       doc_number, doc_date, expiry_date, notify_user_id,
                                       created_by, visibility, allowed_role_ids, allowed_user_ids)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            title,
            kwargs.get('description'),
            kwargs.get('category_id'),
            company_id,
            kwargs.get('status', 'draft'),
            kwargs.get('parent_id'),
            kwargs.get('relationship_type'),
            kwargs.get('metadata', '{}'),
            kwargs.get('doc_number'),
            kwargs.get('doc_date'),
            kwargs.get('expiry_date'),
            kwargs.get('notify_user_id'),
            created_by,
            kwargs.get('visibility', 'all'),
            kwargs.get('allowed_role_ids'),
            kwargs.get('allowed_user_ids'),
        ), returning=True)

    def update(self, doc_id, **fields):
        sets = []
        params = []
        for key in ('title', 'description', 'category_id', 'status', 'metadata',
                     'doc_number', 'doc_date', 'expiry_date', 'notify_user_id',
                     'visibility', 'allowed_role_ids', 'allowed_user_ids'):
            if key in fields:
                if key == 'metadata':
                    sets.append(f'{key} = %s::jsonb')
                else:
                    sets.append(f'{key} = %s')
                params.append(fields[key])
        if not sets:
            return None
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(doc_id)
        return self.execute(
            f'UPDATE dms_documents SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        )

    def soft_delete(self, doc_id):
        return self.execute(
            'UPDATE dms_documents SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s',
            (doc_id,)
        )

    def restore(self, doc_id):
        return self.execute(
            'UPDATE dms_documents SET deleted_at = NULL WHERE id = %s',
            (doc_id,)
        )

    def permanent_delete(self, doc_id):
        return self.execute(
            'DELETE FROM dms_documents WHERE id = %s AND deleted_at IS NOT NULL',
            (doc_id,)
        )

    # ---- Batch operations ----

    def batch_soft_delete(self, doc_ids, company_id=None):
        """Soft-delete multiple documents, scoped by company."""
        if not doc_ids:
            return 0
        placeholders = ','.join(['%s'] * len(doc_ids))
        params = list(doc_ids)
        where_extra = ''
        if company_id:
            where_extra = ' AND company_id = %s'
            params.append(company_id)
        return self.execute(
            f'UPDATE dms_documents SET deleted_at = CURRENT_TIMESTAMP'
            f' WHERE id IN ({placeholders}) AND deleted_at IS NULL{where_extra}',
            tuple(params)
        )

    def batch_update_category(self, doc_ids, category_id, company_id=None):
        """Update category for multiple documents."""
        if not doc_ids:
            return 0
        placeholders = ','.join(['%s'] * len(doc_ids))
        params = [category_id] + list(doc_ids)
        where_extra = ''
        if company_id:
            where_extra = ' AND company_id = %s'
            params.append(company_id)
        return self.execute(
            f'UPDATE dms_documents SET category_id = %s, updated_at = CURRENT_TIMESTAMP'
            f' WHERE id IN ({placeholders}) AND deleted_at IS NULL{where_extra}',
            tuple(params)
        )

    def batch_update_status(self, doc_ids, status, company_id=None):
        """Update status for multiple documents."""
        if not doc_ids:
            return 0
        placeholders = ','.join(['%s'] * len(doc_ids))
        params = [status] + list(doc_ids)
        where_extra = ''
        if company_id:
            where_extra = ' AND company_id = %s'
            params.append(company_id)
        return self.execute(
            f'UPDATE dms_documents SET status = %s, updated_at = CURRENT_TIMESTAMP'
            f' WHERE id IN ({placeholders}) AND deleted_at IS NULL{where_extra}',
            tuple(params)
        )
