"""Repository for mkt_project_clients — links CRM clients to marketing projects."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.client_link_repo')


class ProjectClientLinkRepository(BaseRepository):

    def get_by_project(self, project_id):
        """Get all linked CRM clients for a project, with deal count and total revenue."""
        return self.query_all('''
            SELECT pc.id, pc.project_id, pc.client_id, pc.linked_by,
                   u.name as linked_by_name, pc.created_at,
                   c.display_name, c.client_type, c.phone, c.email,
                   c.city, c.region, c.responsible,
                   (SELECT COUNT(*) FROM crm_deals d WHERE d.client_id = c.id) as deal_count,
                   (SELECT COALESCE(SUM(d.sale_price_net), 0)
                    FROM crm_deals d WHERE d.client_id = c.id) as total_revenue
            FROM mkt_project_clients pc
            JOIN crm_clients c ON c.id = pc.client_id
            JOIN users u ON u.id = pc.linked_by
            WHERE pc.project_id = %s
            ORDER BY c.display_name
        ''', (project_id,))

    def link(self, project_id, client_id, linked_by):
        """Link a CRM client to a project. Returns link ID or None if already linked."""
        row = self.execute('''
            INSERT INTO mkt_project_clients (project_id, client_id, linked_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_id, client_id) DO NOTHING
            RETURNING id
        ''', (project_id, client_id, linked_by), returning=True)
        return row['id'] if row else None

    def unlink(self, project_id, client_id):
        """Remove a CRM client link from a project."""
        return self.execute(
            'DELETE FROM mkt_project_clients WHERE project_id = %s AND client_id = %s',
            (project_id, client_id),
        ) > 0

    def get_client_deals(self, client_id):
        """Get all deals for a specific client (for expanded row display)."""
        return self.query_all('''
            SELECT d.id, d.source, d.brand, d.model_name,
                   d.sale_price_net, d.gross_profit,
                   d.contract_date, d.dossier_status, d.sales_person,
                   d.vin, d.dealer_name, d.buyer_name
            FROM crm_deals d
            WHERE d.client_id = %s
            ORDER BY d.contract_date DESC
        ''', (client_id,))

    def search_clients(self, query=None, limit=20):
        """Search CRM clients for the linking picker."""
        sql = '''
            SELECT c.id, c.display_name, c.client_type, c.phone, c.email,
                   c.city, c.responsible,
                   (SELECT COUNT(*) FROM crm_deals d WHERE d.client_id = c.id) as deal_count
            FROM crm_clients c
            WHERE c.merged_into_id IS NULL
              AND (c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)
        '''
        params = []
        if query:
            sql += " AND (c.display_name ILIKE %s OR c.phone ILIKE %s OR c.email ILIKE %s)"
            like = f'%{query}%'
            params.extend([like, like, like])
        sql += ' ORDER BY c.display_name LIMIT %s'
        params.append(limit)
        return self.query_all(sql, params)

    def get_linked_client_ids(self, project_id):
        """Get just the client IDs linked to a project (used by KPI sync)."""
        rows = self.query_all(
            'SELECT client_id FROM mkt_project_clients WHERE project_id = %s',
            (project_id,)
        )
        return [r['client_id'] for r in rows]

    def get_projects_for_client(self, client_id):
        """Get all marketing projects linked to a client (for client profile view)."""
        return self.query_all('''
            SELECT pc.id, pc.project_id, pc.created_at,
                   p.name as project_name, p.status as project_status,
                   p.start_date, p.end_date, p.total_budget, p.currency
            FROM mkt_project_clients pc
            JOIN mkt_projects p ON p.id = pc.project_id
            WHERE pc.client_id = %s AND p.deleted_at IS NULL
            ORDER BY p.start_date DESC
        ''', (client_id,))
