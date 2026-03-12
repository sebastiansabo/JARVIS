"""DMS Module Link Repository — universal cross-module linking."""
from core.base_repository import BaseRepository


class ModuleLinkRepository(BaseRepository):

    # ── Folder links ──

    def get_folder_links(self, folder_id):
        """Get all module links for a folder."""
        return self.query_all('''
            SELECT ml.*, u.name as linked_by_name
            FROM dms_module_links ml
            LEFT JOIN users u ON u.id = ml.linked_by
            WHERE ml.link_type = 'folder' AND ml.folder_id = %s
            ORDER BY ml.created_at DESC
        ''', (folder_id,))

    def link_folder(self, folder_id, module, module_entity_id, linked_by):
        """Link a folder to a module entity."""
        return self.execute('''
            INSERT INTO dms_module_links (link_type, folder_id, module, module_entity_id, linked_by)
            VALUES ('folder', %s, %s, %s, %s)
            ON CONFLICT (folder_id, module, module_entity_id)
                WHERE folder_id IS NOT NULL
            DO NOTHING
            RETURNING *
        ''', (folder_id, module, module_entity_id, linked_by), returning=True)

    def unlink_folder(self, folder_id, module, module_entity_id):
        """Remove a folder-module link."""
        return self.execute('''
            DELETE FROM dms_module_links
            WHERE link_type = 'folder'
              AND folder_id = %s AND module = %s AND module_entity_id = %s
        ''', (folder_id, module, module_entity_id))

    # ── Document links ──

    def get_document_links(self, document_id):
        """Get all module links for a document."""
        return self.query_all('''
            SELECT ml.*, u.name as linked_by_name
            FROM dms_module_links ml
            LEFT JOIN users u ON u.id = ml.linked_by
            WHERE ml.link_type = 'document' AND ml.document_id = %s
            ORDER BY ml.created_at DESC
        ''', (document_id,))

    def link_document(self, document_id, module, module_entity_id, linked_by):
        """Link a document to a module entity."""
        return self.execute('''
            INSERT INTO dms_module_links (link_type, document_id, module, module_entity_id, linked_by)
            VALUES ('document', %s, %s, %s, %s)
            ON CONFLICT (document_id, module, module_entity_id)
                WHERE document_id IS NOT NULL
            DO NOTHING
            RETURNING *
        ''', (document_id, module, module_entity_id, linked_by), returning=True)

    def unlink_document(self, document_id, module, module_entity_id):
        """Remove a document-module link."""
        return self.execute('''
            DELETE FROM dms_module_links
            WHERE link_type = 'document'
              AND document_id = %s AND module = %s AND module_entity_id = %s
        ''', (document_id, module, module_entity_id))

    # ── Reverse lookups ──

    def get_by_module(self, module, module_entity_id):
        """Get all DMS links (folders + documents) for a module entity."""
        return self.query_all('''
            SELECT ml.*,
                   f.name as folder_name, f.path as folder_path,
                   d.title as document_title, d.status as document_status,
                   u.name as linked_by_name
            FROM dms_module_links ml
            LEFT JOIN dms_folders f ON f.id = ml.folder_id
            LEFT JOIN dms_documents d ON d.id = ml.document_id
            LEFT JOIN users u ON u.id = ml.linked_by
            WHERE ml.module = %s AND ml.module_entity_id = %s
            ORDER BY ml.created_at DESC
        ''', (module, module_entity_id))

    def search_folders(self, query, company_id, limit=20):
        """Search folders for linking picker."""
        return self.query_all('''
            SELECT id, name, path, icon, color, depth
            FROM dms_folders
            WHERE company_id = %s
              AND deleted_at IS NULL
              AND name ILIKE %s
            ORDER BY depth, name
            LIMIT %s
        ''', (company_id, f'%{query}%', limit))
