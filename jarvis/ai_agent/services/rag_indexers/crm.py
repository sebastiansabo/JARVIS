"""
CRM Indexer Mixin

Provides CRM-related indexing methods for RAGService:
  - crm_client:  index_crm_client, index_crm_clients_batch, _build_crm_client_content
  - car_dossier: index_car_dossier, index_car_dossiers_batch, _build_car_dossier_content
"""

from typing import Optional, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ...models import RAGSourceType, ServiceResult

logger = get_logger('jarvis.ai_agent.services.rag')


class CRMIndexerMixin:
    """Mixin providing CRM indexing methods for RAGService."""

    # ============== CRM Client Indexing ==============

    def _build_crm_client_content(self, data: dict) -> str:
        parts = [f"Client CRM: {data.get('display_name', '')}"]
        if data.get('client_type'):
            parts.append(f"Tip: {'Persoana fizica' if data['client_type'] == 'person' else 'Persoana juridica'}")
        for key, label in [('phone', 'Telefon'), ('email', 'Email'), ('street', 'Adresa'),
                           ('city', 'Oras'), ('region', 'Judet'), ('responsible', 'Responsabil')]:
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        return '\n'.join(parts)

    def index_crm_client(self, client_id: int) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('SELECT * FROM crm_clients WHERE id = %s', (client_id,))
                data = cursor.fetchone()
            finally:
                release_db(conn)
            if not data:
                return ServiceResult(success=False, error='Client not found')
            if data.get('is_blacklisted'):
                return ServiceResult(success=False, error='Client is blacklisted — skipping indexing')
            content = self._build_crm_client_content(data)
            metadata = {
                'name': data.get('display_name'), 'type': data.get('client_type'),
                'phone': data.get('phone'), 'email': data.get('email'),
                'responsible': data.get('responsible'),
            }
            return self._index_document(
                RAGSourceType.CRM_CLIENT, client_id, 'crm_clients',
                content, metadata, company_id=None,
            )
        except Exception as e:
            logger.error(f"CRM client indexing failed for {client_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_crm_clients_batch(self, limit: int = 500) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT c.id FROM crm_clients c
                    WHERE c.merged_into_id IS NULL
                      AND (c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)
                      AND NOT EXISTS (
                        SELECT 1 FROM ai_agent.rag_documents r
                        WHERE r.source_type = 'crm_client'
                          AND r.source_id = c.id
                          AND r.is_active = TRUE
                          AND r.updated_at >= c.updated_at
                      )
                    ORDER BY c.updated_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_crm_client(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} CRM clients")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"CRM client batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Car Dossier Indexing ==============

    def _build_car_dossier_content(self, data: dict) -> str:
        dtype = 'noua' if data.get('source') == 'nw' else 'second-hand'
        parts = [f"Dosar masina {dtype} Nr. {data.get('dossier_number', '')}"]
        for key, label in [('model_name', 'Model'), ('brand', 'Marca'),
                           ('dossier_status', 'Status dosar'), ('buyer_name', 'Client'),
                           ('owner_name', 'Proprietar'), ('fuel_type', 'Combustibil'),
                           ('color', 'Culoare'), ('vin', 'VIN'),
                           ('dealer_name', 'Dealer'), ('sales_person', 'Vanzator'),
                           ('customer_group', 'Grup client')]:
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        # Financials
        for key, label in [('list_price', 'Pret lista'), ('sale_price_net', 'Pret vanzare net'),
                           ('purchase_price_net', 'Pret achizitie net'), ('gross_profit', 'Profit brut'),
                           ('gw_gross_value', 'PV brut')]:
            val = data.get(key)
            if val is not None and val != 0:
                parts.append(f"{label}: {val}")
        # Dates
        for key, label in [('contract_date', 'Data contract'), ('delivery_date', 'Data livrare'),
                           ('registration_date', 'Data inmatriculare')]:
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        return '\n'.join(parts)

    def index_car_dossier(self, dossier_id: int) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('SELECT * FROM crm_deals WHERE id = %s', (dossier_id,))
                data = cursor.fetchone()
            finally:
                release_db(conn)
            if not data:
                return ServiceResult(success=False, error='Dossier not found')
            content = self._build_car_dossier_content(data)
            price = data.get('sale_price_net') or data.get('list_price') or data.get('gw_gross_value')
            metadata = {
                'dossier_number': data.get('dossier_number'), 'model': data.get('model_name'),
                'brand': data.get('brand'), 'client': data.get('buyer_name'),
                'status': data.get('dossier_status'), 'price': str(price) if price else None,
                'dossier_type': data.get('source'),
                'date': str(data.get('contract_date') or data.get('delivery_date') or ''),
            }
            return self._index_document(
                RAGSourceType.CAR_DOSSIER, dossier_id, 'crm_deals',
                content, metadata, company_id=None,
            )
        except Exception as e:
            logger.error(f"Car dossier indexing failed for {dossier_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_car_dossiers_batch(self, limit: int = 500) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                # Use NOT EXISTS to avoid duplicates from LEFT JOIN
                # when multiple RAG docs exist for the same source_id
                cursor.execute("""
                    SELECT d.id FROM crm_deals d
                    WHERE (d.client_id IS NULL OR d.client_id NOT IN (
                        SELECT id FROM crm_clients WHERE is_blacklisted = TRUE
                    ))
                    AND NOT EXISTS (
                        SELECT 1 FROM ai_agent.rag_documents r
                        WHERE r.source_type = 'car_dossier'
                          AND r.source_id = d.id
                          AND r.is_active = TRUE
                          AND r.updated_at >= d.updated_at
                    )
                    ORDER BY d.updated_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_car_dossier(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} car dossiers")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Car dossier batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))
