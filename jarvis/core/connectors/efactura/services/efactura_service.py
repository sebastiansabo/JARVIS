"""
EFactura Service - Unified business logic for e-Factura connector.

This service coordinates all e-Factura operations through the repository layer.
Routes should call this service instead of accessing repositories directly.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import date

from core.utils.logging_config import get_logger
from core.database import get_db, get_cursor, release_db
from core.organization.repositories import CompanyRepository as _CompanyRepo
_company_repo = _CompanyRepo()
match_company_by_vat = _company_repo.match_by_vat
get_companies_with_vat = _company_repo.get_all_with_vat_and_brands

from ..config import InvoiceDirection, ArtifactType
from ..repositories import (
    CompanyConnectionRepository,
    InvoiceRepository,
    SyncRepository,
)
from ..models import (
    CompanyConnection,
    Invoice,
    InvoiceExternalRef,
    InvoiceArtifact,
)
from .invoice_service import InvoiceService
from .base import ServiceResult, _iso, MOCK_MODE

logger = get_logger('jarvis.core.connectors.efactura.service')


class EFacturaService:
    """
    Unified service for e-Factura operations.

    Coordinates connections, invoices, sync operations, and ANAF API interactions.
    """

    def __init__(self):
        self.connection_repo = CompanyConnectionRepository()
        self.invoice_repo = InvoiceRepository()
        self.sync_repo = SyncRepository()
        self.invoice_service = InvoiceService()

    # ============== ANAF Client ==============

    def get_anaf_client(self, company_cif: str):
        """
        Get ANAF client instance - mock, OAuth, or certificate-based.

        Priority:
        1. Mock client if EFACTURA_MOCK_MODE=true (default for development)
        2. OAuth client if tokens are stored for the CIF
        3. Certificate client if certificate is configured
        """
        if MOCK_MODE:
            from ..client.mock_client import MockANAFClient
            logger.info("Using MOCK ANAF client", extra={'cif': company_cif})
            return MockANAFClient(company_cif)

        from ..config import Environment
        env = os.environ.get('EFACTURA_ENVIRONMENT', 'production')
        environment = Environment.PRODUCTION if env == 'production' else Environment.TEST

        # Try OAuth tokens first (preferred method)
        try:
            from core.connectors.efactura.repositories.oauth_repository import OAuthRepository
            tokens = OAuthRepository().get_tokens(company_cif)

            if tokens and tokens.get('access_token'):
                from ..client.oauth_client import ANAFOAuthClient
                logger.info("Using OAuth ANAF client", extra={'cif': company_cif})
                return ANAFOAuthClient.from_stored_tokens(
                    company_cif=company_cif,
                    environment=environment,
                )
        except Exception as e:
            logger.warning(
                "Failed to load OAuth tokens, trying certificate",
                extra={'cif': company_cif, 'error': str(e)}
            )

        # Fall back to certificate-based client
        cert_path = os.environ.get('EFACTURA_CERT_PATH')
        cert_password = os.environ.get('EFACTURA_CERT_PASSWORD')

        if not cert_path or not cert_password:
            raise ValueError(
                "No authentication available. Either authenticate with ANAF OAuth "
                "or configure EFACTURA_CERT_PATH and EFACTURA_CERT_PASSWORD."
            )

        from ..client.anaf_client import ANAFClient
        return ANAFClient(cert_path, cert_password, environment)

    def get_anaf_status(self) -> Dict[str, Any]:
        """Get ANAF client status (mock mode, OAuth, rate limits, etc.)."""
        status = {
            'mock_mode': MOCK_MODE,
            'mock_mode_reason': 'EFACTURA_MOCK_MODE=true (default for development)' if MOCK_MODE else 'Using real ANAF API',
            'environment': os.environ.get('EFACTURA_ENVIRONMENT', 'production'),
            'cert_configured': bool(os.environ.get('EFACTURA_CERT_PATH')),
            'oauth_connections': [],
        }

        # Get list of companies with OAuth tokens
        try:
            from database import get_db, get_cursor, release_db
            conn = get_db()
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT name as cif, credentials->>'expires_at' as expires_at
                FROM connectors
                WHERE connector_type = 'efactura' AND status = 'connected'
            ''')
            rows = cursor.fetchall()
            release_db(conn)

            for row in rows:
                status['oauth_connections'].append({
                    'cif': row['cif'],
                    'expires_at': row['expires_at'],
                })
        except Exception as e:
            logger.warning(f"Failed to get OAuth connections: {e}")

        return status

    # ============== ANAF Company Lookup ==============

    def lookup_company_by_cif(self, cif: str) -> ServiceResult:
        """
        Lookup company information from ANAF public API.

        Uses the ANAF PlatitorTva API to get company name, address, VAT status.
        This is a public API - no authentication required.

        Args:
            cif: Company CIF (without RO prefix)

        Returns:
            ServiceResult with company info or error
        """
        import requests
        from datetime import date

        # Clean CIF - remove RO prefix and spaces
        clean_cif = cif.replace('RO', '').replace(' ', '').strip()

        try:
            response = requests.post(
                'https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva',
                json=[{
                    'cui': int(clean_cif),
                    'data': date.today().strftime('%Y-%m-%d')
                }],
                headers={'Content-Type': 'application/json'},
                timeout=10,
            )

            if response.status_code != 200:
                return ServiceResult(
                    success=False,
                    error=f"ANAF API returned {response.status_code}"
                )

            data = response.json()

            if not data.get('found') or not data['found']:
                return ServiceResult(
                    success=False,
                    error=f"CIF {cif} not found in ANAF database"
                )

            company = data['found'][0]
            # v9 API response structure: data is nested in date_generale, etc.
            general = company.get('date_generale', {})
            vat_info = company.get('inregistrare_scop_Tva', {})
            inactive_info = company.get('stare_inactiv', {})

            return ServiceResult(success=True, data={
                'cif': clean_cif,
                'name': general.get('denumire', ''),
                'address': general.get('adresa', ''),
                'is_vat_payer': vat_info.get('scpTVA', False),
                'is_active': inactive_info.get('statusInactivi', False) is False,
                'registration_date': general.get('data_inregistrare'),
            })

        except requests.exceptions.Timeout:
            return ServiceResult(success=False, error="ANAF API timeout")
        except requests.exceptions.RequestException as e:
            return ServiceResult(success=False, error=f"ANAF API error: {e}")
        except Exception as e:
            logger.error(f"Error looking up company {cif}: {e}")
            return ServiceResult(success=False, error=str(e))

    def lookup_companies_by_cifs(self, cifs: List[str]) -> ServiceResult:
        """
        Lookup multiple companies from ANAF in one request.

        Args:
            cifs: List of CIFs to lookup

        Returns:
            ServiceResult with dict mapping CIF -> company info
        """
        import requests
        from datetime import date

        if not cifs:
            return ServiceResult(success=True, data={})

        # Build request payload
        today = date.today().strftime('%Y-%m-%d')
        payload = []
        for cif in cifs:
            clean_cif = str(cif).replace('RO', '').replace(' ', '').strip()
            try:
                payload.append({
                    'cui': int(clean_cif),
                    'data': today
                })
            except ValueError:
                logger.warning(f"Invalid CIF format: {cif}")
                continue

        if not payload:
            return ServiceResult(success=True, data={})

        try:
            response = requests.post(
                'https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva',
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=15,
            )

            if response.status_code != 200:
                return ServiceResult(
                    success=False,
                    error=f"ANAF API returned {response.status_code}"
                )

            data = response.json()
            result = {}

            # v9 API response structure: data is nested in date_generale and inregistrare_scop_Tva
            for company in data.get('found', []):
                general = company.get('date_generale', {})
                vat_info = company.get('inregistrare_scop_Tva', {})
                cif = str(general.get('cui', ''))
                result[cif] = {
                    'cif': cif,
                    'name': general.get('denumire', ''),
                    'address': general.get('adresa', ''),
                    'is_vat_payer': vat_info.get('scpTVA', False),
                }

            return ServiceResult(success=True, data=result)

        except Exception as e:
            logger.error(f"Error looking up companies: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Company Connections ==============

    def get_all_connections(self) -> List[Dict[str, Any]]:
        """Get all active company connections."""
        connections = self.connection_repo.get_all_active()
        return [
            {
                'id': c.id,
                'cif': c.cif,
                'display_name': c.display_name,
                'environment': c.environment,
                'status': c.status,
                'status_message': c.status_message,
                'last_sync_at': _iso(c.last_sync_at),
                'cert_expires_at': _iso(c.cert_expires_at),
                'cert_expiring_soon': c.is_cert_expiring_soon(),
            }
            for c in connections
        ]

    def get_connection(self, cif: str) -> ServiceResult:
        """Get connection details by CIF."""
        connection = self.connection_repo.get_by_cif(cif)

        if connection is None:
            return ServiceResult(success=False, error=f"Connection not found: {cif}")

        return ServiceResult(success=True, data={
            'id': connection.id,
            'cif': connection.cif,
            'display_name': connection.display_name,
            'environment': connection.environment,
            'status': connection.status,
            'status_message': connection.status_message,
            'config': connection.config,
            'last_sync_at': _iso(connection.last_sync_at),
            'cert_fingerprint': connection.cert_fingerprint,
            'cert_expires_at': _iso(connection.cert_expires_at),
            'created_at': _iso(connection.created_at),
            'updated_at': _iso(connection.updated_at),
        })

    def create_connection(
        self,
        cif: str,
        display_name: str,
        environment: str = 'test',
        config: Dict = None
    ) -> ServiceResult:
        """Create a new company connection."""
        # Check if already exists
        existing = self.connection_repo.get_by_cif(cif)
        if existing:
            return ServiceResult(
                success=False,
                error=f"Connection already exists for CIF: {cif}"
            )

        connection = CompanyConnection(
            cif=cif.strip(),
            display_name=display_name.strip(),
            environment=environment,
            status='active',
            config=config or {},
        )

        created = self.connection_repo.create(connection)

        logger.info("Company connection created via API", extra={'cif': created.cif})

        return ServiceResult(success=True, data={
            'id': created.id,
            'cif': created.cif,
        })

    def delete_connection(self, cif: str) -> ServiceResult:
        """Delete a company connection."""
        deleted = self.connection_repo.delete(cif)

        if not deleted:
            return ServiceResult(success=False, error=f"Connection not found: {cif}")

        return ServiceResult(success=True)

    # ============== Invoices ==============

    def list_invoices(
        self,
        cif_owner: str,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        partner_cif: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ServiceResult:
        """List invoices with filters."""
        invoices, total = self.invoice_repo.list_invoices(
            cif_owner=cif_owner,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            partner_cif=partner_cif,
            limit=limit,
            offset=offset,
        )

        return ServiceResult(success=True, data={
            'invoices': [
                {
                    'id': inv.id,
                    'cif_owner': inv.cif_owner,
                    'direction': inv.direction.value,
                    'partner_cif': inv.partner_cif,
                    'partner_name': inv.partner_name,
                    'invoice_number': inv.full_invoice_number,
                    'issue_date': _iso(inv.issue_date),
                    'due_date': _iso(inv.due_date),
                    'total_amount': str(inv.total_amount),
                    'total_vat': str(inv.total_vat),
                    'currency': inv.currency,
                    'status': inv.status.value,
                    'created_at': _iso(inv.created_at),
                }
                for inv in invoices
            ],
            'pagination': {
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < total,
            },
        })

    def get_invoice(self, invoice_id: int) -> ServiceResult:
        """Get invoice details with artifacts and full partner info from XML."""
        invoice = self.invoice_repo.get_by_id(invoice_id)

        if invoice is None:
            return ServiceResult(success=False, error=f"Invoice not found: {invoice_id}")

        external_ref = self.invoice_repo.get_external_ref(invoice_id)
        artifacts = self.invoice_repo.get_artifacts(invoice_id)

        # Parse XML to get full seller/buyer details
        seller_info = {}
        buyer_info = {}
        try:
            xml_content = self.invoice_repo.get_xml_content(invoice_id)
            if xml_content:
                from ..xml_parser import parse_efactura_xml
                parsed = parse_efactura_xml(xml_content)
                if parsed:
                    seller_info = {
                        'name': parsed.seller_name,
                        'cif': parsed.seller_cif,
                        'address': parsed.seller_address,
                        'reg_number': parsed.seller_reg_number,
                    }
                    buyer_info = {
                        'name': parsed.buyer_name,
                        'cif': parsed.buyer_cif,
                        'address': parsed.buyer_address,
                    }
        except Exception as e:
            logger.warning(f"Could not parse XML for invoice {invoice_id}: {e}")

        return ServiceResult(success=True, data={
            'id': invoice.id,
            'cif_owner': invoice.cif_owner,
            'direction': invoice.direction.value,
            'partner_cif': invoice.partner_cif,
            'partner_name': invoice.partner_name,
            'invoice_number': invoice.full_invoice_number,
            'invoice_series': invoice.invoice_series,
            'issue_date': _iso(invoice.issue_date),
            'due_date': _iso(invoice.due_date),
            'total_amount': str(invoice.total_amount),
            'total_vat': str(invoice.total_vat),
            'total_without_vat': str(invoice.total_without_vat),
            'currency': invoice.currency,
            'status': invoice.status.value,
            'created_at': _iso(invoice.created_at),
            'updated_at': _iso(invoice.updated_at),
            'seller': seller_info,
            'buyer': buyer_info,
            'external_ref': {
                'message_id': external_ref.message_id,
                'upload_id': external_ref.upload_id,
                'download_id': external_ref.download_id,
                'xml_hash': external_ref.xml_hash,
            } if external_ref else None,
            'artifacts': [
                {
                    'id': a.id,
                    'type': a.artifact_type.value,
                    'filename': a.original_filename,
                    'size_bytes': a.size_bytes,
                    'checksum': a.checksum,
                }
                for a in artifacts
            ],
        })

    def get_artifact(
        self,
        invoice_id: int,
        artifact_type: ArtifactType
    ) -> ServiceResult:
        """Get specific artifact for an invoice."""
        artifact = self.invoice_repo.get_artifact_by_type(invoice_id, artifact_type)

        if artifact is None:
            return ServiceResult(success=False, error=f"Artifact not found: {artifact_type}")

        return ServiceResult(success=True, data={
            'storage_uri': artifact.storage_uri,
            'filename': artifact.original_filename,
            'mime_type': artifact.mime_type,
        })

    def get_invoice_summary(
        self,
        cif_owner: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Get invoice summary statistics."""
        summary = self.invoice_repo.get_summary(cif_owner, start_date, end_date)

        return {
            'received': {
                'count': summary['received']['count'],
                'total': str(summary['received']['total']),
                'vat': str(summary['received']['vat']),
            },
            'sent': {
                'count': summary['sent']['count'],
                'total': str(summary['sent']['total']),
                'vat': str(summary['sent']['vat']),
            },
        }
