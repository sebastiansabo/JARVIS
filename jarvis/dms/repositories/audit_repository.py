"""DMS Audit Log Repository — change tracking for DMS entities."""
import json
from core.base_repository import BaseRepository


class AuditRepository(BaseRepository):

    def log(self, entity_type, entity_id, action, user_id, company_id,
            changes=None, ip_address=None):
        """Write an audit log entry."""
        return self.execute('''
            INSERT INTO dms_audit_log
                (entity_type, entity_id, action, changes, user_id, company_id, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (entity_type, entity_id, action,
              json.dumps(changes) if changes else None,
              user_id, company_id, ip_address), returning=True)

    def get_by_entity(self, entity_type, entity_id, limit=50, offset=0):
        """Get audit trail for a specific entity."""
        return self.query_all('''
            SELECT a.*, u.name as user_name, u.email as user_email
            FROM dms_audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.entity_type = %s AND a.entity_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        ''', (entity_type, entity_id, limit, offset))

    def get_by_company(self, company_id, entity_type=None, limit=50, offset=0):
        """Get audit trail for a company, optionally filtered by entity type."""
        conditions = ['a.company_id = %s']
        params = [company_id]

        if entity_type:
            conditions.append('a.entity_type = %s')
            params.append(entity_type)

        where = ' AND '.join(conditions)
        params.extend([limit, offset])

        return self.query_all(f'''
            SELECT a.*, u.name as user_name, u.email as user_email
            FROM dms_audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE {where}
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        ''', params)

    def get_by_user(self, user_id, limit=50, offset=0):
        """Get audit trail for a specific user."""
        return self.query_all('''
            SELECT a.*, u.name as user_name
            FROM dms_audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.user_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        ''', (user_id, limit, offset))

    def get_folder_activity(self, folder_id, limit=50, offset=0):
        """Get audit trail for a folder and all documents within it."""
        return self.query_all('''
            SELECT a.*, u.name as user_name, u.email as user_email
            FROM dms_audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE (a.entity_type = 'folder' AND a.entity_id = %s)
               OR (a.entity_type = 'document' AND a.entity_id IN (
                    SELECT id FROM dms_documents WHERE folder_id = %s
                  ))
               OR (a.entity_type = 'acl' AND a.entity_id IN (
                    SELECT id FROM dms_folder_acl WHERE folder_id = %s
                  ))
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        ''', (folder_id, folder_id, folder_id, limit, offset))
