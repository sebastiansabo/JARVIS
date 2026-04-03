"""Vehicle Link Repository — cross-module entity linking for CarPark vehicles."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


ALLOWED_ENTITY_TYPES = {
    'invoice', 'dms_document', 'dms_folder', 'project',
    'hr_event', 'crm_deal', 'crm_client',
}

# SQL fragments to resolve display labels per entity type
_ENTITY_JOINS = {
    'invoice': (
        'LEFT JOIN invoices inv ON inv.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(inv.invoice_number, 'Factura #' || vl.linked_entity_id::text)",
        "COALESCE(inv.supplier, '')",
        'invoice',
    ),
    'dms_document': (
        'LEFT JOIN dms_documents dd ON dd.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(dd.title, 'Document #' || vl.linked_entity_id::text)",
        "COALESCE(dd.status, '')",
        'dms_document',
    ),
    'dms_folder': (
        'LEFT JOIN dms_folders df ON df.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(df.name, 'Dosar #' || vl.linked_entity_id::text)",
        "''",
        'dms_folder',
    ),
    'project': (
        'LEFT JOIN mkt_projects mp ON mp.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(mp.name, 'Proiect #' || vl.linked_entity_id::text)",
        "COALESCE(mp.status, '')",
        'project',
    ),
    'hr_event': (
        'LEFT JOIN hr.events he ON he.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(he.name, 'Eveniment #' || vl.linked_entity_id::text)",
        "''",
        'hr_event',
    ),
    'crm_deal': (
        'LEFT JOIN crm_deals cd ON cd.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(cd.brand || ' ' || cd.model_name, 'Deal #' || vl.linked_entity_id::text)",
        "COALESCE(cd.dossier_status, '')",
        'crm_deal',
    ),
    'crm_client': (
        'LEFT JOIN crm_clients cc ON cc.id = vl.linked_entity_id AND vl.linked_entity_type = %s',
        "COALESCE(cc.display_name, 'Client #' || vl.linked_entity_id::text)",
        "COALESCE(cc.company_name, '')",
        'crm_client',
    ),
}


class VehicleLinkRepository(BaseRepository):
    """Data access for cross-module vehicle entity links."""

    def get_by_vehicle(self, vehicle_id: int,
                       entity_type: str = None) -> List[Dict[str, Any]]:
        """Get all linked entities for a vehicle with display labels."""
        sql = '''
            SELECT vl.*,
                   u.name AS linked_by_name,
                   CASE vl.linked_entity_type
        '''
        # Build CASE expression for entity_label
        label_cases = []
        sublabel_cases = []
        join_clauses = []
        join_params = []

        for etype, (join_sql, label_expr, sublabel_expr, param) in _ENTITY_JOINS.items():
            label_cases.append(f"WHEN '{etype}' THEN {label_expr}")
            sublabel_cases.append(f"WHEN '{etype}' THEN {sublabel_expr}")
            join_clauses.append(join_sql)
            join_params.append(param)

        sql += '\n'.join(f'                       {c}' for c in label_cases)
        sql += f"\n                       ELSE 'Entity #' || vl.linked_entity_id::text"
        sql += '\n                   END AS entity_label,'
        sql += '\n                   CASE vl.linked_entity_type\n'
        sql += '\n'.join(f'                       {c}' for c in sublabel_cases)
        sql += "\n                       ELSE ''"
        sql += '\n                   END AS entity_sublabel'
        sql += '\n            FROM carpark_vehicle_links vl'
        sql += '\n            LEFT JOIN users u ON u.id = vl.linked_by'

        for join_sql in join_clauses:
            sql += f'\n            {join_sql}'

        sql += '\n            WHERE vl.vehicle_id = %s'
        params = join_params + [vehicle_id]

        if entity_type:
            sql += ' AND vl.linked_entity_type = %s'
            params.append(entity_type)

        sql += '\n            ORDER BY vl.created_at DESC'

        return self.query_all(sql, tuple(params))

    def link(self, vehicle_id: int, entity_type: str,
             entity_id: int, linked_by: int,
             notes: str = None) -> Optional[Dict[str, Any]]:
        """Create a link between a vehicle and an entity. Returns None on duplicate."""
        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise ValueError(f'Invalid entity_type: {entity_type}')
        return self.execute('''
            INSERT INTO carpark_vehicle_links
                (vehicle_id, linked_entity_type, linked_entity_id, notes, linked_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (vehicle_id, linked_entity_type, linked_entity_id) DO NOTHING
            RETURNING *
        ''', (vehicle_id, entity_type, entity_id, notes, linked_by),
            returning=True)

    def unlink(self, link_id: int) -> bool:
        """Remove a vehicle link by its ID."""
        return self.execute(
            'DELETE FROM carpark_vehicle_links WHERE id = %s', (link_id,)
        ) > 0

    def search_entities(self, entity_type: str, query: str = '',
                        company_id: int = None,
                        limit: int = 20) -> List[Dict[str, Any]]:
        """Search for linkable entities by type and optional query text."""
        if entity_type == 'invoice':
            sql = '''
                SELECT id, invoice_number AS label,
                       COALESCE(supplier, '') AS sublabel
                FROM invoices
                WHERE deleted_at IS NULL
            '''
            params: list = []
            if query:
                sql += " AND (invoice_number ILIKE %s OR supplier ILIKE %s)"
                params.extend([f'%{query}%', f'%{query}%'])
            if company_id:
                sql += ' AND company_id = %s'
                params.append(company_id)
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        elif entity_type == 'dms_document':
            sql = '''
                SELECT id, title AS label,
                       COALESCE(status, '') AS sublabel
                FROM dms_documents
                WHERE 1=1
            '''
            params = []
            if query:
                sql += " AND title ILIKE %s"
                params.append(f'%{query}%')
            if company_id:
                sql += ' AND company_id = %s'
                params.append(company_id)
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        elif entity_type == 'dms_folder':
            sql = '''
                SELECT id, name AS label,
                       COALESCE(path, '') AS sublabel
                FROM dms_folders
                WHERE 1=1
            '''
            params = []
            if query:
                sql += " AND name ILIKE %s"
                params.append(f'%{query}%')
            if company_id:
                sql += ' AND company_id = %s'
                params.append(company_id)
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        elif entity_type == 'project':
            sql = '''
                SELECT id, name AS label,
                       COALESCE(status, '') AS sublabel
                FROM mkt_projects
                WHERE 1=1
            '''
            params = []
            if query:
                sql += " AND name ILIKE %s"
                params.append(f'%{query}%')
            if company_id:
                sql += ' AND company_id = %s'
                params.append(company_id)
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        elif entity_type == 'hr_event':
            sql = '''
                SELECT id, name AS label,
                       '' AS sublabel
                FROM hr.events
                WHERE 1=1
            '''
            params = []
            if query:
                sql += " AND name ILIKE %s"
                params.append(f'%{query}%')
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        elif entity_type == 'crm_deal':
            sql = '''
                SELECT id,
                       COALESCE(brand || ' ' || model_name, 'Deal #' || id::text) AS label,
                       COALESCE(dossier_status, '') AS sublabel
                FROM crm_deals
                WHERE 1=1
            '''
            params = []
            if query:
                sql += " AND (brand ILIKE %s OR model_name ILIKE %s)"
                params.extend([f'%{query}%', f'%{query}%'])
            if company_id:
                sql += ' AND company_id = %s'
                params.append(company_id)
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        elif entity_type == 'crm_client':
            sql = '''
                SELECT id, display_name AS label,
                       COALESCE(company_name, '') AS sublabel
                FROM crm_clients
                WHERE 1=1
            '''
            params = []
            if query:
                sql += " AND (display_name ILIKE %s OR company_name ILIKE %s)"
                params.extend([f'%{query}%', f'%{query}%'])
            if company_id:
                sql += ' AND company_id = %s'
                params.append(company_id)
            sql += ' ORDER BY display_name ASC LIMIT %s'
            params.append(limit)
            return self.query_all(sql, tuple(params))

        else:
            raise ValueError(f'Unsupported entity_type for search: {entity_type}')
