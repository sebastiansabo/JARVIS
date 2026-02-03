"""
EFactura Service - Unified business logic for e-Factura connector.

This service coordinates all e-Factura operations through the repository layer.
Routes should call this service instead of accessing repositories directly.
"""

import os
import io
import zipfile
import hashlib
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from datetime import date

from core.utils.logging_config import get_logger
from core.database import get_db, get_cursor, release_db
from services import match_company_by_vat, get_companies_with_vat
from core.services.notification_service import notify_invoice_allocations, is_smtp_configured

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

logger = get_logger('jarvis.core.connectors.efactura.service')

# Check if mock mode is enabled
MOCK_MODE = os.environ.get('EFACTURA_MOCK_MODE', 'true').lower() == 'true'


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


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
            from database import get_efactura_oauth_tokens
            tokens = get_efactura_oauth_tokens(company_cif)

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
                'last_sync_at': c.last_sync_at.isoformat() if c.last_sync_at else None,
                'cert_expires_at': c.cert_expires_at.isoformat() if c.cert_expires_at else None,
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
            'last_sync_at': connection.last_sync_at.isoformat() if connection.last_sync_at else None,
            'cert_fingerprint': connection.cert_fingerprint,
            'cert_expires_at': connection.cert_expires_at.isoformat() if connection.cert_expires_at else None,
            'created_at': connection.created_at.isoformat() if connection.created_at else None,
            'updated_at': connection.updated_at.isoformat() if connection.updated_at else None,
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
                    'issue_date': inv.issue_date.isoformat() if inv.issue_date else None,
                    'due_date': inv.due_date.isoformat() if inv.due_date else None,
                    'total_amount': str(inv.total_amount),
                    'total_vat': str(inv.total_vat),
                    'currency': inv.currency,
                    'status': inv.status.value,
                    'created_at': inv.created_at.isoformat() if inv.created_at else None,
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
            'issue_date': invoice.issue_date.isoformat() if invoice.issue_date else None,
            'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
            'total_amount': str(invoice.total_amount),
            'total_vat': str(invoice.total_vat),
            'total_without_vat': str(invoice.total_without_vat),
            'currency': invoice.currency,
            'status': invoice.status.value,
            'created_at': invoice.created_at.isoformat() if invoice.created_at else None,
            'updated_at': invoice.updated_at.isoformat() if invoice.updated_at else None,
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

    # ============== Sync Operations ==============

    def trigger_sync(self, cif: str) -> ServiceResult:
        """Manually trigger sync for a company."""
        # For now, return a placeholder
        # In Phase 2, this will trigger the actual sync worker
        logger.info("Manual sync triggered", extra={'cif': cif})

        return ServiceResult(success=True, data={
            'message': f"Sync triggered for CIF: {cif}",
            'note': "Sync worker not yet implemented (Phase 2)",
        })

    def get_sync_history(
        self,
        cif: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get sync run history."""
        runs = self.sync_repo.get_recent_runs(cif, limit)

        return [
            {
                'id': r.id,
                'run_id': r.run_id,
                'company_cif': r.company_cif,
                'direction': r.direction,
                'started_at': r.started_at.isoformat() if r.started_at else None,
                'finished_at': r.finished_at.isoformat() if r.finished_at else None,
                'success': r.success,
                'invoices_created': r.invoices_created,
                'invoices_skipped': r.invoices_skipped,
                'errors_count': r.errors_count,
                'error_summary': r.error_summary,
            }
            for r in runs
        ]

    def get_sync_errors(self, run_id: str) -> List[Dict[str, Any]]:
        """Get errors for a sync run."""
        errors = self.sync_repo.get_run_errors(run_id)

        return [
            {
                'id': e.id,
                'error_type': e.error_type,
                'error_code': e.error_code,
                'error_message': e.error_message,
                'message_id': e.message_id,
                'invoice_ref': e.invoice_ref,
                'is_retryable': e.is_retryable,
                'created_at': e.created_at.isoformat() if e.created_at else None,
            }
            for e in errors
        ]

    def get_error_stats(
        self,
        cif: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get error statistics for monitoring."""
        return self.sync_repo.get_error_stats(cif, hours)

    # ============== ANAF Message Operations ==============

    def fetch_anaf_messages(
        self,
        cif: str,
        days: int = 60,
        page: int = 1,
        filter_type: Optional[str] = None
    ) -> ServiceResult:
        """Fetch messages directly from ANAF API (or mock)."""
        try:
            client = self.get_anaf_client(cif)

            result = client.list_messages(
                company_cif=cif,
                days=days,
                page=page,
                filter_type=filter_type,
            )

            return ServiceResult(success=True, data={
                'mock_mode': MOCK_MODE,
                'messages': result.get('messages', []),
                'pagination': {
                    'current_page': result.get('current_page', page),
                    'total_pages': result.get('total_pages', 1),
                    'total_records': result.get('total_records', 0),
                    'records_per_page': result.get('records_per_page', 10),
                    'has_more': result.get('has_more', False),
                },
                'serial': result.get('serial'),
                'title': result.get('title'),
            })

        except ValueError as e:
            return ServiceResult(success=False, error=f"Configuration error: {e}")
        except Exception as e:
            logger.error(f"Error fetching ANAF messages: {e}")
            return ServiceResult(success=False, error=str(e))

    def download_anaf_message(self, cif: str, message_id: str) -> bytes:
        """Download invoice ZIP from ANAF (or mock)."""
        client = self.get_anaf_client(cif)
        return client.download_message(message_id)

    # ============== Import from ANAF ==============

    def import_from_anaf(
        self,
        cif: str,
        message_ids: List[str]
    ) -> ServiceResult:
        """
        Import invoices from ANAF into local storage.

        Args:
            cif: Company CIF
            message_ids: List of ANAF message IDs to import
        """
        from ..xml_parser import parse_invoice_xml

        # Get ANAF client
        client = self.get_anaf_client(cif)

        # Match CIF against companies table to auto-identify company
        matched_company = match_company_by_vat(cif)
        company_id = matched_company.get('id') if matched_company else None

        if company_id:
            logger.info(
                "Company auto-identified for e-Factura import",
                extra={'cif': cif, 'company_id': company_id, 'company': matched_company.get('company')}
            )
        else:
            logger.warning("No matching company found for CIF", extra={'cif': cif})

        imported = 0
        skipped = 0
        errors = []

        for message_id in message_ids:
            try:
                # Check if already imported
                existing = self.invoice_repo.get_by_message_id_simple(message_id)
                if existing:
                    skipped += 1
                    continue

                # Download ZIP from ANAF
                zip_data = client.download_message(message_id)

                # Extract XML from ZIP
                xml_content = None
                xml_filename = None
                with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                    for filename in zf.namelist():
                        if filename.endswith('.xml') and not filename.endswith('.p7s'):
                            xml_content = zf.read(filename).decode('utf-8')
                            xml_filename = filename
                            break

                if not xml_content:
                    errors.append(f"No XML in message {message_id}")
                    continue

                # Parse XML to extract invoice data
                parsed = parse_invoice_xml(xml_content)

                # Validate that this is actually an invoice (not a signature or other XML)
                if not parsed.invoice_number:
                    # Check if it's a signature XML
                    if '<Signature' in xml_content or '<ds:Signature' in xml_content:
                        errors.append(f"Message {message_id} contains signature XML, not invoice")
                    else:
                        errors.append(f"Message {message_id} contains invalid/empty invoice XML")
                    continue

                # Determine direction based on CIF
                direction = InvoiceDirection.RECEIVED
                if parsed.seller_cif and parsed.seller_cif.replace('RO', '') == cif:
                    direction = InvoiceDirection.SENT

                # Create invoice record
                invoice = Invoice(
                    cif_owner=cif,
                    company_id=company_id,
                    direction=direction,
                    partner_cif=parsed.buyer_cif if direction == InvoiceDirection.SENT else parsed.seller_cif,
                    partner_name=parsed.buyer_name if direction == InvoiceDirection.SENT else parsed.seller_name,
                    invoice_number=parsed.invoice_number,
                    invoice_series=parsed.invoice_series,
                    issue_date=parsed.issue_date,
                    due_date=parsed.due_date,
                    total_amount=parsed.total_amount,
                    total_vat=parsed.total_vat,
                    total_without_vat=parsed.total_without_vat,
                    currency=parsed.currency,
                )

                # Create external reference
                xml_hash = hashlib.sha256(xml_content.encode()).hexdigest()
                external_ref = InvoiceExternalRef(
                    message_id=message_id,
                    xml_hash=xml_hash,
                )

                # Create artifact for XML storage
                artifact = InvoiceArtifact(
                    artifact_type=ArtifactType.XML,
                    storage_uri=f"efactura/{cif}/{message_id}.xml",
                    original_filename=xml_filename,
                    mime_type="application/xml",
                    checksum=xml_hash,
                    size_bytes=len(xml_content.encode()),
                )

                # Save to database
                created_invoice = self.invoice_repo.create_with_refs(
                    invoice, external_ref, artifact, xml_content
                )

                if created_invoice:
                    imported += 1
                    # Note: No auto-hide here - visibility is now controlled dynamically
                    # by partner type settings (hide_in_filter flag)
                else:
                    errors.append(f"Failed to save message {message_id}")

            except Exception as e:
                logger.error(f"Error importing message {message_id}: {e}")
                errors.append(f"Error with {message_id}: {str(e)}")

        return ServiceResult(success=True, data={
            'imported': imported,
            'skipped': skipped,
            'errors': errors if errors else None,
            'company_matched': matched_company.get('company') if matched_company else None,
            'company_id': company_id,
        })

    def sync_all(self, days: int = 60) -> ServiceResult:
        """
        Sync all invoices from all connected companies.

        Fetches messages from ANAF for all active connections and imports them.
        Automatically skips duplicates (already imported invoices).

        Args:
            days: Number of days to look back (default 60)

        Returns:
            ServiceResult with summary of sync operation
        """
        logger.info("Starting sync_all operation", extra={'days': days})

        # Get all active company connections
        connections = self.get_all_connections()

        if not connections:
            return ServiceResult(
                success=False,
                error="No active company connections found. Go to Connector Settings to add a connection."
            )

        total_fetched = 0
        total_imported = 0
        total_skipped = 0
        all_errors = []
        company_results = []

        for conn in connections:
            cif = conn['cif']
            display_name = conn.get('display_name', cif)

            try:
                logger.info(f"Syncing company {display_name} ({cif})")

                # Fetch all messages from ANAF (all pages)
                all_message_ids = []
                page = 1
                max_pages = 50  # Safety limit

                while page <= max_pages:
                    fetch_result = self.fetch_anaf_messages(
                        cif=cif,
                        days=days,
                        page=page,
                        filter_type='P',  # Only fetch Received (Primite) invoices
                    )

                    if not fetch_result.success:
                        all_errors.append(f"{display_name}: Failed to fetch - {fetch_result.error}")
                        break

                    messages = fetch_result.data.get('messages', [])
                    if not messages:
                        break

                    # Extract message IDs
                    for msg in messages:
                        msg_id = str(msg.get('id', ''))
                        if msg_id:
                            all_message_ids.append(msg_id)

                    # Check if there are more pages
                    pagination = fetch_result.data.get('pagination', {})
                    if not pagination.get('has_more', False):
                        break

                    page += 1

                total_fetched += len(all_message_ids)

                if not all_message_ids:
                    company_results.append({
                        'company': display_name,
                        'cif': cif,
                        'fetched': 0,
                        'imported': 0,
                        'skipped': 0,
                        'errors': 0,
                    })
                    continue

                # Import all messages (duplicates are automatically skipped)
                import_result = self.import_from_anaf(cif, all_message_ids)

                if import_result.success:
                    imported = import_result.data.get('imported', 0)
                    skipped = import_result.data.get('skipped', 0)
                    errors = import_result.data.get('errors', [])

                    total_imported += imported
                    total_skipped += skipped

                    if errors:
                        all_errors.extend([f"{display_name}: {e}" for e in errors])

                    company_results.append({
                        'company': display_name,
                        'cif': cif,
                        'fetched': len(all_message_ids),
                        'imported': imported,
                        'skipped': skipped,
                        'errors': len(errors) if errors else 0,
                    })
                else:
                    all_errors.append(f"{display_name}: Import failed - {import_result.error}")
                    company_results.append({
                        'company': display_name,
                        'cif': cif,
                        'fetched': len(all_message_ids),
                        'imported': 0,
                        'skipped': 0,
                        'errors': 1,
                    })

            except Exception as e:
                logger.error(f"Error syncing company {cif}: {e}")
                all_errors.append(f"{display_name}: {str(e)}")
                company_results.append({
                    'company': display_name,
                    'cif': cif,
                    'fetched': 0,
                    'imported': 0,
                    'skipped': 0,
                    'errors': 1,
                })

        logger.info(
            "Sync_all completed",
            extra={
                'companies_synced': len(connections),
                'total_fetched': total_fetched,
                'total_imported': total_imported,
                'total_skipped': total_skipped,
                'total_errors': len(all_errors),
            }
        )

        # After sync, detect duplicates in unallocated invoices
        duplicates = self.detect_unallocated_duplicates()

        return ServiceResult(success=True, data={
            'companies_synced': len(connections),
            'total_fetched': total_fetched,
            'total_imported': total_imported,
            'total_skipped': total_skipped,
            'errors': all_errors if all_errors else None,
            'company_results': company_results,
            'duplicates_found': duplicates,
        })

    def sync_single_company(self, cif: str, days: int = 60) -> ServiceResult:
        """
        Sync invoices for a single company.

        Fetches messages from ANAF and imports them.
        Used by frontend for progress-aware sync.

        Args:
            cif: Company CIF to sync
            days: Number of days to look back (default 60)

        Returns:
            ServiceResult with sync results for this company
        """
        logger.info(f"Syncing single company", extra={'cif': cif, 'days': days})

        # Find company display name
        connections = self.get_all_connections()
        display_name = cif
        for conn in connections:
            if conn['cif'] == cif:
                display_name = conn.get('display_name', cif)
                break

        try:
            # Fetch all messages from ANAF (all pages)
            all_message_ids = []
            page = 1
            max_pages = 50  # Safety limit

            while page <= max_pages:
                fetch_result = self.fetch_anaf_messages(
                    cif=cif,
                    days=days,
                    page=page,
                    filter_type='P',  # Only fetch Received (Primite) invoices
                )

                if not fetch_result.success:
                    return ServiceResult(
                        success=False,
                        error=f"Failed to fetch messages: {fetch_result.error}"
                    )

                messages = fetch_result.data.get('messages', [])
                if not messages:
                    break

                # Extract message IDs
                for msg in messages:
                    msg_id = str(msg.get('id', ''))
                    if msg_id:
                        all_message_ids.append(msg_id)

                # Check if there are more pages
                pagination = fetch_result.data.get('pagination', {})
                if not pagination.get('has_more', False):
                    break

                page += 1

            if not all_message_ids:
                return ServiceResult(success=True, data={
                    'company': display_name,
                    'cif': cif,
                    'fetched': 0,
                    'imported': 0,
                    'skipped': 0,
                    'errors': [],
                })

            # Import all messages (duplicates are automatically skipped)
            import_result = self.import_from_anaf(cif, all_message_ids)

            if import_result.success:
                imported = import_result.data.get('imported', 0)
                skipped = import_result.data.get('skipped', 0)
                import_errors = import_result.data.get('errors', []) or []

                return ServiceResult(success=True, data={
                    'company': display_name,
                    'cif': cif,
                    'fetched': len(all_message_ids),
                    'imported': imported,
                    'skipped': skipped,
                    'errors': import_errors,
                })
            else:
                return ServiceResult(
                    success=False,
                    error=f"Import failed: {import_result.error}"
                )

        except Exception as e:
            logger.error(f"Error syncing company {cif}: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Unallocated Invoices ==============

    def list_unallocated_invoices(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        hide_typed: bool = False,
        page: int = 1,
        limit: int = 50,
        sort_by: str = 'issue_date',
        sort_dir: str = 'desc',
    ) -> ServiceResult:
        """List invoices that have not been sent to the Invoice Module."""
        offset = (page - 1) * limit

        invoices, total, hidden_by_filter = self.invoice_repo.list_unallocated(
            cif_owner=cif_owner,
            company_id=company_id,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            search=search,
            hide_typed=hide_typed,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        total_pages = max(1, (total + limit - 1) // limit)

        # Load companies for name lookup
        companies = get_companies_with_vat()
        company_map = {c['id']: c['company'] for c in companies}

        # Build invoice response list (invoices are dicts with type_name from repo)
        invoice_list = []
        for inv in invoices:
            # inv is a dict from the repository
            inv_direction = inv.get('direction')
            if hasattr(inv_direction, 'value'):
                inv_direction = inv_direction.value

            inv_issue_date = inv.get('issue_date')
            if hasattr(inv_issue_date, 'isoformat'):
                inv_issue_date = inv_issue_date.isoformat()

            inv_created_at = inv.get('created_at')
            if hasattr(inv_created_at, 'isoformat'):
                inv_created_at = inv_created_at.isoformat()

            # Build full invoice number
            inv_number = inv.get('invoice_number', '')
            inv_series = inv.get('invoice_series')
            full_invoice_number = f"{inv_series}-{inv_number}" if inv_series else inv_number

            inv_company_id = inv.get('company_id')

            invoice_list.append({
                'id': inv.get('id'),
                'cif_owner': inv.get('cif_owner'),
                'company_id': inv_company_id,
                'company_name': company_map.get(inv_company_id) if inv_company_id else None,
                'direction': inv_direction,
                'partner_cif': inv.get('partner_cif'),
                'partner_name': inv.get('partner_name'),
                'invoice_number': full_invoice_number,
                'issue_date': inv_issue_date,
                'total_amount': str(inv.get('total_amount', 0)),
                'total_vat': str(inv.get('total_vat', 0)),
                'currency': inv.get('currency'),
                'created_at': inv_created_at,
                'type_name': inv.get('type_name'),
                'type_names': inv.get('type_names', []),
                'type_override': inv.get('type_override'),
                'department': inv.get('department'),
                'department_override': inv.get('department_override'),
                'mapping_department': inv.get('mapping_department'),
                'subdepartment': inv.get('subdepartment'),
                'subdepartment_override': inv.get('subdepartment_override'),
                'mapping_subdepartment': inv.get('mapping_subdepartment'),
            })

        return ServiceResult(success=True, data={
            'invoices': invoice_list,
            'companies': [{'id': c['id'], 'name': c['company']} for c in companies],
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': page < total_pages,
                'hidden_by_filter': hidden_by_filter,
            },
        })

    def get_unallocated_count(self) -> int:
        """Get count of unallocated invoices for badge."""
        return self.invoice_repo.count_unallocated()

    def ignore_invoice(self, invoice_id: int, ignored: bool = True) -> ServiceResult:
        """
        Mark an invoice as ignored (soft delete) or restore it.

        Args:
            invoice_id: ID of the invoice to ignore/restore
            ignored: True to ignore, False to restore

        Returns:
            ServiceResult with success status
        """
        # Check if invoice exists
        invoice = self.invoice_repo.get_by_id(invoice_id)
        if not invoice:
            return ServiceResult(success=False, error=f"Invoice {invoice_id} not found")

        # Check if already allocated
        if self.invoice_repo.is_allocated(invoice_id):
            return ServiceResult(
                success=False,
                error=f"Invoice {invoice_id} is already allocated and cannot be ignored"
            )

        success = self.invoice_repo.ignore_invoice(invoice_id, ignored)
        if success:
            return ServiceResult(success=True, data={
                'invoice_id': invoice_id,
                'ignored': ignored,
            })
        else:
            return ServiceResult(success=False, error="Failed to update invoice")

    # ============== Hidden Invoices (Ignored) ==============

    def list_hidden_invoices(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> ServiceResult:
        """List hidden (ignored) invoices."""
        offset = (page - 1) * limit

        invoices, total = self.invoice_repo.list_hidden(
            cif_owner=cif_owner,
            company_id=company_id,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            search=search,
            limit=limit,
            offset=offset,
        )

        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        return ServiceResult(success=True, data={
            'invoices': [
                {
                    'id': inv['id'],
                    'company_name': None,  # Could add lookup if needed
                    'direction': inv['direction'].value if hasattr(inv['direction'], 'value') else inv['direction'],
                    'partner_name': inv['partner_name'],
                    'partner_cif': inv['partner_cif'],
                    'invoice_number': inv['invoice_number'],
                    'invoice_series': inv['invoice_series'],
                    'issue_date': inv['issue_date'].isoformat() if inv.get('issue_date') else None,
                    'total_amount': str(inv['total_amount']),
                    'total_vat': str(inv['total_vat']),
                    'currency': inv['currency'],
                    'created_at': inv['created_at'].isoformat() if inv.get('created_at') else None,
                    'type_name': inv.get('type_name'),
                    'type_names': inv.get('type_names', []),
                }
                for inv in invoices
            ],
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': page < total_pages,
            },
        })

    def get_hidden_count(self) -> int:
        """Get count of hidden invoices for badge."""
        return self.invoice_repo.count_hidden()

    def bulk_hide_invoices(self, invoice_ids: List[int]) -> ServiceResult:
        """Hide multiple invoices."""
        count = self.invoice_repo.bulk_hide(invoice_ids)
        return ServiceResult(success=True, data={'hidden': count})

    def bulk_restore_from_hidden(self, invoice_ids: List[int]) -> ServiceResult:
        """Restore multiple invoices from hidden."""
        count = self.invoice_repo.bulk_restore_from_hidden(invoice_ids)
        return ServiceResult(success=True, data={'restored': count})

    # ============== Bin (Deleted Invoices) ==============

    def list_deleted_invoices(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> ServiceResult:
        """List deleted invoices (bin)."""
        offset = (page - 1) * limit

        invoices, total = self.invoice_repo.list_deleted(
            cif_owner=cif_owner,
            company_id=company_id,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            search=search,
            limit=limit,
            offset=offset,
        )

        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        return ServiceResult(success=True, data={
            'invoices': [
                {
                    'id': inv.get('id'),
                    'direction': inv.get('direction').value if hasattr(inv.get('direction'), 'value') else inv.get('direction'),
                    'partner_name': inv.get('partner_name'),
                    'partner_cif': inv.get('partner_cif'),
                    'invoice_number': inv.get('invoice_number'),
                    'invoice_series': inv.get('invoice_series'),
                    'issue_date': inv.get('issue_date').isoformat() if inv.get('issue_date') else None,
                    'total_amount': str(inv.get('total_amount', 0)),
                    'total_vat': str(inv.get('total_vat', 0)),
                    'currency': inv.get('currency'),
                    'created_at': inv.get('created_at').isoformat() if inv.get('created_at') else None,
                    'deleted_at': inv.get('deleted_at').isoformat() if inv.get('deleted_at') else None,
                    'type_name': inv.get('type_name'),
                    'type_names': inv.get('type_names', []),
                }
                for inv in invoices
            ],
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': page < total_pages,
            },
        })

    def get_bin_count(self) -> int:
        """Get count of deleted invoices for badge."""
        return self.invoice_repo.count_deleted()

    def delete_invoice(self, invoice_id: int) -> ServiceResult:
        """Move an invoice to the bin."""
        invoice = self.invoice_repo.get_by_id(invoice_id)
        if not invoice:
            return ServiceResult(success=False, error=f"Invoice {invoice_id} not found")

        success = self.invoice_repo.delete_invoice(invoice_id)
        if success:
            return ServiceResult(success=True, data={'invoice_id': invoice_id})
        else:
            return ServiceResult(success=False, error="Failed to delete invoice")

    def restore_from_bin(self, invoice_id: int) -> ServiceResult:
        """Restore an invoice from the bin."""
        success = self.invoice_repo.restore_from_bin(invoice_id)
        if success:
            return ServiceResult(success=True, data={'invoice_id': invoice_id})
        else:
            return ServiceResult(success=False, error="Invoice not found in bin")

    def permanent_delete(self, invoice_id: int) -> ServiceResult:
        """Permanently delete an invoice from the bin."""
        success = self.invoice_repo.permanent_delete(invoice_id)
        if success:
            return ServiceResult(success=True, data={'invoice_id': invoice_id})
        else:
            return ServiceResult(success=False, error="Invoice not found in bin")

    def bulk_delete_invoices(self, invoice_ids: List[int]) -> ServiceResult:
        """Move multiple invoices to the bin."""
        count = self.invoice_repo.bulk_delete(invoice_ids)
        return ServiceResult(success=True, data={'deleted': count})

    def bulk_restore_from_bin(self, invoice_ids: List[int]) -> ServiceResult:
        """Restore multiple invoices from the bin."""
        count = self.invoice_repo.bulk_restore_from_bin(invoice_ids)
        return ServiceResult(success=True, data={'restored': count})

    def bulk_permanent_delete(self, invoice_ids: List[int]) -> ServiceResult:
        """Permanently delete multiple invoices from the bin."""
        count = self.invoice_repo.bulk_permanent_delete(invoice_ids)
        return ServiceResult(success=True, data={'deleted': count})

    # ============== Duplicate Detection ==============

    def detect_unallocated_duplicates(self) -> List[Dict[str, Any]]:
        """
        Detect unallocated e-Factura invoices that already exist in the main invoices table.

        Called after sync to notify user of potential duplicates.

        Returns:
            List of duplicate invoices with their matching existing invoice info
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Find unallocated e-Factura invoices that match existing invoices
            # by supplier name + invoice number
            cursor.execute("""
                SELECT
                    e.id as efactura_id,
                    e.partner_name,
                    e.invoice_number,
                    e.issue_date,
                    e.total_amount,
                    e.currency,
                    i.id as existing_invoice_id,
                    i.invoice_date as existing_date,
                    i.invoice_value as existing_value
                FROM efactura_invoices e
                INNER JOIN invoices i
                    ON LOWER(e.partner_name) = LOWER(i.supplier)
                    AND e.invoice_number = i.invoice_number
                    AND i.deleted_at IS NULL
                WHERE e.jarvis_invoice_id IS NULL
                    AND e.deleted_at IS NULL
                    AND e.ignored = FALSE
                ORDER BY e.partner_name, e.invoice_number
            """)

            duplicates = []
            for row in cursor.fetchall():
                duplicates.append({
                    'efactura_id': row['efactura_id'],
                    'partner_name': row['partner_name'],
                    'invoice_number': row['invoice_number'],
                    'issue_date': str(row['issue_date']) if row['issue_date'] else None,
                    'total_amount': float(row['total_amount']),
                    'currency': row['currency'],
                    'existing_invoice_id': row['existing_invoice_id'],
                    'existing_date': str(row['existing_date']) if row['existing_date'] else None,
                    'existing_value': float(row['existing_value']) if row['existing_value'] else None,
                })

            if duplicates:
                logger.info(f"Found {len(duplicates)} duplicate unallocated invoices")

            return duplicates

        finally:
            release_db(conn)

    def mark_duplicates(self, efactura_ids: List[int]) -> ServiceResult:
        """
        Mark e-Factura invoices as duplicates by linking to existing invoices.

        Finds the matching invoice in the main table and sets jarvis_invoice_id.

        Args:
            efactura_ids: List of e-Factura invoice IDs to mark as duplicates

        Returns:
            ServiceResult with count of marked duplicates
        """
        if not efactura_ids:
            return ServiceResult(success=True, data={'marked': 0})

        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Find matching invoices and create mappings
            cursor.execute("""
                SELECT
                    e.id as efactura_id,
                    i.id as jarvis_id
                FROM efactura_invoices e
                INNER JOIN invoices i
                    ON LOWER(e.partner_name) = LOWER(i.supplier)
                    AND e.invoice_number = i.invoice_number
                    AND i.deleted_at IS NULL
                WHERE e.id = ANY(%s)
                    AND e.jarvis_invoice_id IS NULL
                    AND e.deleted_at IS NULL
            """, (efactura_ids,))

            mappings = [(row['efactura_id'], row['jarvis_id']) for row in cursor.fetchall()]

            if mappings:
                self.invoice_repo.bulk_mark_allocated(mappings)
                logger.info(f"Marked {len(mappings)} e-Factura invoices as duplicates")

            return ServiceResult(success=True, data={'marked': len(mappings)})

        except Exception as e:
            logger.error(f"Error marking duplicates: {e}")
            return ServiceResult(success=False, error=str(e))
        finally:
            release_db(conn)

    def detect_duplicates_with_ai(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Detect potential duplicate invoices using AI similarity matching.

        This is a fallback for when exact supplier+invoice_number matching fails.
        Uses Claude to analyze similar invoices based on:
        - Similar supplier names (fuzzy matching)
        - Similar amounts
        - Date proximity

        Args:
            limit: Maximum number of e-Factura invoices to analyze (for cost control)

        Returns:
            List of potential duplicates with AI confidence scores
        """
        import json
        import os
        import anthropic
        from difflib import SequenceMatcher

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            logger.warning('ANTHROPIC_API_KEY not set, skipping AI duplicate detection')
            return []

        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Get unallocated e-Factura invoices that DON'T have exact matches
            # (exact matches are already found by detect_unallocated_duplicates)
            cursor.execute("""
                SELECT e.id, e.partner_name, e.invoice_number, e.issue_date,
                       e.total_amount, e.currency
                FROM efactura_invoices e
                WHERE e.jarvis_invoice_id IS NULL
                    AND e.deleted_at IS NULL
                    AND e.ignored = FALSE
                    AND NOT EXISTS (
                        SELECT 1 FROM invoices i
                        WHERE LOWER(e.partner_name) = LOWER(i.supplier)
                          AND e.invoice_number = i.invoice_number
                          AND i.deleted_at IS NULL
                    )
                ORDER BY e.issue_date DESC
                LIMIT %s
            """, (limit,))

            efactura_invoices = cursor.fetchall()

            if not efactura_invoices:
                return []

            # Get main invoices from the last 180 days for comparison
            cursor.execute("""
                SELECT id, supplier, invoice_number, invoice_date, invoice_value, currency
                FROM invoices
                WHERE deleted_at IS NULL
                    AND invoice_date >= CURRENT_DATE - INTERVAL '180 days'
                ORDER BY invoice_date DESC
                LIMIT 500
            """)

            main_invoices = cursor.fetchall()

            if not main_invoices:
                return []

            ai_duplicates = []

            # Pre-filter: find invoices with similar amounts (within 5%)
            for ef_inv in efactura_invoices:
                ef_amount = float(ef_inv['total_amount'] or 0)
                ef_supplier = ef_inv['partner_name'] or ''

                # Find candidates with similar amounts
                candidates = []
                for main_inv in main_invoices:
                    main_amount = float(main_inv['invoice_value'] or 0)
                    main_supplier = main_inv['supplier'] or ''

                    # Check amount similarity (within 5%)
                    if main_amount > 0 and ef_amount > 0:
                        amount_diff = abs(ef_amount - main_amount) / main_amount * 100
                        if amount_diff > 5:
                            continue

                    # Check supplier name similarity (at least 50%)
                    similarity = SequenceMatcher(
                        None,
                        ef_supplier.lower(),
                        main_supplier.lower()
                    ).ratio()
                    if similarity < 0.5:
                        continue

                    candidates.append({
                        'id': main_inv['id'],
                        'supplier': main_supplier,
                        'invoice_number': main_inv['invoice_number'],
                        'invoice_date': str(main_inv['invoice_date']) if main_inv['invoice_date'] else None,
                        'invoice_value': main_amount,
                        'currency': main_inv['currency'],
                        'similarity': round(similarity, 2),
                        'amount_diff': round(amount_diff, 2)
                    })

                # If we have candidates, ask AI to evaluate
                if candidates:
                    candidates = candidates[:5]  # Limit to top 5 candidates

                    prompt = f"""Analyze if this e-Factura invoice is a DUPLICATE of any existing invoice.

E-FACTURA INVOICE (new import):
- Supplier: {ef_inv['partner_name']}
- Invoice Number: {ef_inv['invoice_number']}
- Date: {ef_inv['issue_date']}
- Amount: {ef_amount} {ef_inv['currency'] or 'RON'}

EXISTING INVOICES (candidates):
{json.dumps(candidates, indent=2)}

IMPORTANT: Return ONLY valid JSON with this format:
{{
    "is_duplicate": true/false,
    "matching_invoice_id": <id or null>,
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

Consider:
- Same supplier with different name format (SRL vs S.R.L., abbreviations)
- Invoice number may have different formatting
- Amounts should be nearly identical for duplicates
- Dates should be close (within a few days)

Only mark as duplicate if you're confident (>0.7) it's the same invoice."""

                    try:
                        client = anthropic.Anthropic(api_key=api_key)
                        response = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=256,
                            messages=[{"role": "user", "content": prompt}]
                        )

                        response_text = response.content[0].text.strip()

                        # Clean markdown code blocks
                        if '```json' in response_text:
                            response_text = response_text.split('```json')[1].split('```')[0]
                        elif '```' in response_text:
                            response_text = response_text.split('```')[1].split('```')[0]

                        result = json.loads(response_text)

                        if result.get('is_duplicate') and result.get('confidence', 0) >= 0.7:
                            ai_duplicates.append({
                                'efactura_id': ef_inv['id'],
                                'partner_name': ef_inv['partner_name'],
                                'invoice_number': ef_inv['invoice_number'],
                                'issue_date': str(ef_inv['issue_date']) if ef_inv['issue_date'] else None,
                                'total_amount': ef_amount,
                                'currency': ef_inv['currency'],
                                'existing_invoice_id': result.get('matching_invoice_id'),
                                'confidence': result.get('confidence', 0),
                                'reasoning': result.get('reasoning', 'AI detected duplicate'),
                                'ai_detected': True
                            })

                    except json.JSONDecodeError as e:
                        logger.error(f'AI duplicate detection JSON error: {e}')
                    except Exception as e:
                        logger.error(f'AI duplicate detection error: {e}')

            if ai_duplicates:
                logger.info(f"AI detected {len(ai_duplicates)} potential duplicates")

            return ai_duplicates

        finally:
            release_db(conn)

    def mark_ai_duplicates(self, mappings: List[Dict[str, int]]) -> ServiceResult:
        """
        Mark AI-detected duplicates by linking to specified existing invoices.

        Unlike mark_duplicates() which finds the match by supplier+invoice_number,
        this method uses the explicit mapping provided by the AI detection.

        Args:
            mappings: List of {'efactura_id': int, 'existing_invoice_id': int}

        Returns:
            ServiceResult with count of marked duplicates
        """
        if not mappings:
            return ServiceResult(success=True, data={'marked': 0})

        pairs = [(m['efactura_id'], m['existing_invoice_id']) for m in mappings]
        self.invoice_repo.bulk_mark_allocated(pairs)
        logger.info(f"Marked {len(pairs)} AI-detected duplicates")

        return ServiceResult(success=True, data={'marked': len(pairs)})

    def send_to_invoice_module(self, invoice_ids: List[int]) -> ServiceResult:
        """
        Send selected invoices to the main JARVIS Invoice Module.

        Creates records in the main invoices table and marks these as allocated.

        Optimized for batch operations:
        - 1 query to fetch all unallocated invoices
        - 1 query to bulk insert into invoices table
        - 1 query to bulk mark as allocated

        Performance: 3 queries total vs 4*N queries (99% reduction for 100+ invoices)
        """
        errors = []

        try:
            # Step 1: Batch fetch all unallocated invoices (1 query)
            # This filters out already-allocated and returns only needed columns
            invoices = self.invoice_repo.get_invoices_for_module(invoice_ids)

            if not invoices:
                # Check if all were already allocated
                return ServiceResult(success=True, data={
                    'sent': 0,
                    'errors': ['All selected invoices are already allocated or not found'],
                })

            # Track which IDs were not found/already allocated
            found_ids = {inv['id'] for inv in invoices}
            skipped_ids = [id for id in invoice_ids if id not in found_ids]
            if skipped_ids:
                errors.append(f"Skipped {len(skipped_ids)} already allocated/not found invoices")

            # Step 2: Bulk insert into main invoices table (1 query)
            # Returns (mappings, skipped_duplicates)
            mappings, skipped_duplicates = self._bulk_create_main_invoices(invoices)

            # Track duplicates in errors
            if skipped_duplicates:
                errors.append(f"Skipped {len(skipped_duplicates)} duplicate invoice(s): {', '.join(skipped_duplicates)}")

            if not mappings:
                if skipped_duplicates:
                    return ServiceResult(success=True, data={
                        'sent': 0,
                        'duplicates': len(skipped_duplicates),
                        'errors': errors,
                    })
                return ServiceResult(success=False, error="Failed to create invoices in module")

            # Step 3: Bulk mark as allocated (1 query)
            self.invoice_repo.bulk_mark_allocated(mappings)

            logger.info(
                f"Batch sent {len(mappings)} invoices to module",
                extra={'invoice_count': len(mappings)}
            )

            return ServiceResult(success=True, data={
                'sent': len(mappings),
                'duplicates': len(skipped_duplicates) if skipped_duplicates else 0,
                'errors': errors if errors else None,
            })

        except Exception as e:
            logger.error(f"Error in batch send to module: {e}")
            return ServiceResult(success=False, error=str(e))

    def _create_main_invoice(self, invoice: Invoice) -> Optional[int]:
        """Create a record in the main invoices table."""
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Calculate value_ron based on currency
            invoice_value = float(invoice.total_amount)
            value_ron = invoice_value if invoice.currency == 'RON' else None

            cursor.execute('''
                INSERT INTO invoices (
                    supplier, invoice_template, invoice_number, invoice_date,
                    invoice_value, currency, value_ron, comment, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            ''', (
                invoice.partner_name,
                invoice.partner_name,  # Use supplier name as template for matching
                invoice.full_invoice_number,
                invoice.issue_date,
                invoice_value,
                invoice.currency,
                value_ron,
                f"e-Factura import | CIF: {invoice.partner_cif}",  # Store VAT in comment
            ))

            jarvis_invoice_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(
                "Created main invoice from e-Factura",
                extra={
                    'efactura_invoice_id': invoice.id,
                    'jarvis_invoice_id': jarvis_invoice_id,
                }
            )

            return jarvis_invoice_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create main invoice: {e}")
            return None
        finally:
            release_db(conn)

    def _bulk_create_main_invoices(
        self,
        invoices: List[Dict[str, Any]],
    ) -> List[Tuple[int, int]]:
        """
        Bulk create records in the main invoices table WITH allocations.

        Uses multi-row INSERTs for optimal performance:
        - 1 INSERT for invoices
        - 1 INSERT for allocations (preserving department structure)

        Args:
            invoices: List of invoice dicts from get_invoices_for_module()

        Returns:
            List of (efactura_id, jarvis_invoice_id) tuples
        """
        if not invoices:
            return []

        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Check for duplicates first by invoice_number (unique constraint)
            # Build list of invoice_numbers to check
            check_numbers = [inv['invoice_number'] for inv in invoices]

            # Query existing invoices with same invoice_number (include ID for linking)
            cursor.execute("""
                SELECT id, supplier, invoice_number
                FROM invoices
                WHERE invoice_number = ANY(%s)
                AND deleted_at IS NULL
            """, (check_numbers,))

            # Map invoice_number -> jarvis_invoice_id
            existing = {row['invoice_number']: row['id'] for row in cursor.fetchall()}

            # Filter out duplicates and collect duplicate mappings for marking
            invoices_to_create = []
            skipped_duplicates = []
            duplicate_mappings = []  # (efactura_id, existing_jarvis_id) for marking
            for inv in invoices:
                key = inv['invoice_number']
                if key in existing:
                    skipped_duplicates.append(inv['invoice_number'])
                    duplicate_mappings.append((inv['id'], existing[key]))
                    logger.warning(f"Skipping duplicate invoice: {inv['partner_name']} - {inv['invoice_number']}")
                else:
                    invoices_to_create.append(inv)

            # Mark duplicate e-Factura invoices by linking to existing jarvis invoice
            if duplicate_mappings:
                self.invoice_repo.bulk_mark_allocated(duplicate_mappings)
                logger.info(f"Marked {len(duplicate_mappings)} duplicate e-Factura invoices as allocated")

            if not invoices_to_create:
                logger.info(f"All {len(invoices)} invoices already exist, nothing to create")
                return [], skipped_duplicates

            # Build values for multi-row INSERT into invoices
            values = []
            params = []
            efactura_ids = []

            for inv in invoices_to_create:
                invoice_value = inv['total_amount']  # Gross value (with VAT)
                net_value = inv.get('total_without_vat')  # Net value (without VAT)
                value_ron = invoice_value if inv['currency'] == 'RON' else None
                comment = f"e-Factura import | CIF: {inv['partner_cif']}"

                # PDF link to e-Factura export endpoint
                drive_link = f"/efactura/api/invoices/{inv['id']}/pdf"

                # Calculate VAT rate if we have both gross and net values
                vat_rate = None
                subtract_vat = False
                if net_value and net_value > 0:
                    subtract_vat = True
                    # VAT rate = (gross - net) / net * 100
                    vat_rate = round((invoice_value - net_value) / net_value * 100, 2)

                values.append(f"(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())")
                params.extend([
                    inv['partner_name'],      # supplier
                    inv['partner_name'],      # invoice_template
                    inv['invoice_number'],    # invoice_number
                    inv['issue_date'],        # invoice_date
                    invoice_value,            # invoice_value (gross)
                    net_value,                # net_value
                    inv['currency'],          # currency
                    value_ron,                # value_ron
                    drive_link,               # drive_link (PDF export)
                    comment,                  # comment
                    'Nebugetata',             # status
                    subtract_vat,             # subtract_vat
                    vat_rate,                 # vat_rate
                ])
                efactura_ids.append(inv['id'])

            # Execute multi-row INSERT for invoices
            cursor.execute(f'''
                INSERT INTO invoices (
                    supplier, invoice_template, invoice_number, invoice_date,
                    invoice_value, net_value, currency, value_ron, drive_link,
                    comment, status, subtract_vat, vat_rate, created_at
                ) VALUES {', '.join(values)}
                RETURNING id
            ''', params)

            # Get created IDs in order
            jarvis_ids = [row['id'] for row in cursor.fetchall()]

            # Create mapping tuples
            mappings = list(zip(efactura_ids, jarvis_ids))

            # Now create allocations for invoices that have company and department info
            alloc_values = []
            alloc_params = []

            # Pre-fetch user IDs for responsible names to enable FK-based queries
            responsible_names = set()
            for inv in invoices_to_create:
                if inv.get('responsible'):
                    responsible_names.add(inv['responsible'].lower())

            responsible_user_ids = {}
            if responsible_names:
                placeholders = ','.join(['%s'] * len(responsible_names))
                cursor.execute(f'SELECT id, LOWER(name) as name_lower FROM users WHERE LOWER(name) IN ({placeholders})', list(responsible_names))
                for row in cursor.fetchall():
                    responsible_user_ids[row['name_lower']] = row['id']

            for inv, (_, jarvis_id) in zip(invoices_to_create, mappings):
                company_name = inv.get('company_name')
                department = inv.get('department')

                # Only create allocation if we have company and department
                if company_name and department:
                    # Use net_value for allocation if available, otherwise gross
                    net_value = inv.get('total_without_vat')
                    allocation_value = net_value if net_value else inv['total_amount']
                    subdepartment = inv.get('subdepartment')
                    brand = inv.get('brand')  # From supplier mapping
                    responsible = inv.get('responsible')  # From department_structure
                    responsible_user_id = responsible_user_ids.get(responsible.lower()) if responsible else None

                    alloc_values.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                    alloc_params.extend([
                        jarvis_id,        # invoice_id
                        company_name,     # company
                        brand,            # brand (from supplier mapping)
                        department,       # department
                        subdepartment,    # subdepartment
                        100.0,            # allocation_percent (100% to single dept)
                        allocation_value, # allocation_value (net if available)
                        responsible,      # responsible (manager from department_structure)
                        responsible_user_id,  # responsible_user_id (FK for fast queries)
                    ])

            # Bulk insert allocations if any
            allocations_created = []
            if alloc_values:
                cursor.execute(f'''
                    INSERT INTO allocations (
                        invoice_id, company, brand, department, subdepartment,
                        allocation_percent, allocation_value, responsible, responsible_user_id
                    ) VALUES {', '.join(alloc_values)}
                ''', alloc_params)

                # Track created allocations for notifications
                for inv, (_, jarvis_id) in zip(invoices_to_create, mappings):
                    has_company = bool(inv.get('company_name'))
                    has_dept = bool(inv.get('department'))
                    if has_company and has_dept:
                        allocations_created.append({
                            'invoice': inv,
                            'jarvis_id': jarvis_id,
                        })
                    else:
                        logger.debug(
                            f"Invoice {inv['invoice_number']} skipped for notification: "
                            f"company={inv.get('company_name')}, dept={inv.get('department')}"
                        )

                logger.info(
                    f"Created {len(alloc_values)} allocations for e-Factura invoices"
                )

            conn.commit()

            # Send notifications for created allocations (after commit)
            logger.info(
                f"Notification check: allocations_created={len(allocations_created)}, "
                f"smtp_configured={is_smtp_configured()}"
            )
            if allocations_created and is_smtp_configured():
                notifications_sent = 0
                for alloc_info in allocations_created:
                    inv = alloc_info['invoice']
                    jarvis_id = alloc_info['jarvis_id']

                    invoice_data = {
                        'id': jarvis_id,
                        'invoice_number': inv['invoice_number'],
                        'supplier': inv['partner_name'],
                        'invoice_date': str(inv['issue_date']),
                        'invoice_value': inv['total_amount'],
                        'currency': inv['currency'],
                    }

                    allocation_data = {
                        'company': inv.get('company_name'),
                        'brand': inv.get('brand'),
                        'department': inv.get('department'),
                        'subdepartment': inv.get('subdepartment'),
                        'allocation_percent': 100.0,
                        'allocation_value': inv.get('total_without_vat') or inv['total_amount'],
                    }

                    logger.info(
                        f"Sending notification for {inv['invoice_number']}: "
                        f"company='{allocation_data['company']}', dept='{allocation_data['department']}'"
                    )

                    try:
                        results = notify_invoice_allocations(invoice_data, [allocation_data])
                        sent_count = sum(1 for r in results if r.get('success'))
                        notifications_sent += sent_count
                        if results:
                            logger.info(
                                f"Notification results for {inv['invoice_number']}: "
                                f"{sent_count}/{len(results)} sent successfully"
                            )
                        else:
                            logger.info(
                                f"No responsables found for invoice {inv['invoice_number']} "
                                f"(dept: {inv.get('department')})"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to send notification for invoice {inv['invoice_number']}: {e}")

                if notifications_sent > 0:
                    logger.info(f"Sent {notifications_sent} allocation notifications for e-Factura imports")

            logger.info(
                f"Bulk created {len(mappings)} main invoices from e-Factura"
                + (f" (skipped {len(skipped_duplicates)} duplicates)" if skipped_duplicates else "")
            )

            return mappings, skipped_duplicates

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to bulk create main invoices: {e}")
            # Check for unique constraint violation (duplicate invoice)
            error_str = str(e)
            if 'invoices_invoice_number_key' in error_str or 'duplicate key' in error_str.lower():
                # Extract invoice number from error message if possible
                import re
                match = re.search(r'\(([^)]+)\)', error_str)
                invoice_num = match.group(1) if match else 'unknown'
                raise ValueError(f"Factura {invoice_num} există deja în Contabilitate")
            raise
        finally:
            release_db(conn)

    # ============== PDF Operations ==============

    def get_invoice_pdf(self, invoice_id: int) -> ServiceResult:
        """
        Get PDF for a stored e-Factura invoice.

        Retrieves the XML from storage and converts to PDF via ANAF API.
        """
        invoice = self.invoice_repo.get_by_id(invoice_id)

        if not invoice:
            return ServiceResult(success=False, error="Invoice not found")

        # Get the XML content
        xml_content = self.invoice_repo.get_xml_content(invoice_id)

        if not xml_content:
            return ServiceResult(success=False, error="XML content not found")

        try:
            # Convert to PDF
            client = self.get_anaf_client(invoice.cif_owner)
            pdf_data = client.xml_to_pdf(xml_content, standard='FACT1', validate=True)

            return ServiceResult(success=True, data={
                'pdf_data': pdf_data,
                'filename': f'invoice_{invoice.full_invoice_number}.pdf',
            })

        except Exception as e:
            logger.error(f"Error converting to PDF: {e}")
            return ServiceResult(success=False, error=str(e))

    def export_anaf_pdf(
        self,
        cif: str,
        message_id: str,
        standard: str = 'FACT1',
        validate: bool = True
    ) -> ServiceResult:
        """
        Export invoice as PDF from ANAF message.

        Downloads the ZIP from ANAF, extracts the XML, and converts it to PDF.
        """
        try:
            # Get client (mock or real)
            client = self.get_anaf_client(cif)

            # Step 1: Download the ZIP file
            logger.info(f"Downloading message {message_id} for PDF export")
            zip_data = client.download_message(message_id)

            # Step 2: Extract XML from ZIP
            xml_content = None
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                for filename in zf.namelist():
                    if filename.endswith('.xml') and not filename.endswith('.p7s'):
                        xml_content = zf.read(filename).decode('utf-8')
                        break

            if not xml_content:
                return ServiceResult(success=False, error="No XML file found in downloaded ZIP")

            # Step 3: Convert XML to PDF using ANAF API
            logger.info(f"Converting XML to PDF using standard {standard}")
            pdf_data = client.xml_to_pdf(xml_content, standard=standard, validate=validate)

            return ServiceResult(success=True, data={
                'pdf_data': pdf_data,
                'filename': f'invoice_{message_id}.pdf',
                'mock_mode': MOCK_MODE,
            })

        except ValueError as e:
            return ServiceResult(success=False, error=f"Configuration error: {e}")
        except Exception as e:
            logger.error(f"Error exporting PDF: {e}")
            return ServiceResult(success=False, error=str(e))
