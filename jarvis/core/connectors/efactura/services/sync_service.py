"""
EFactura Sync Service - ANAF message fetching, import, and sync operations.
"""
import io
import zipfile
from typing import Optional, List, Dict, Any, Callable

from core.utils.logging_config import get_logger
from core.organization.repositories import CompanyRepository as _CompanyRepo

from ..config import InvoiceDirection
from ..repositories import InvoiceRepository, SyncRepository
from ..models import Invoice, InvoiceExternalRef, InvoiceArtifact
from .base import ServiceResult, MOCK_MODE

logger = get_logger('jarvis.core.connectors.efactura.sync_service')

_company_repo = _CompanyRepo()
match_company_by_vat = _company_repo.match_by_vat


class EFacturaSyncService:
    def __init__(self, anaf_client_factory: Optional[Callable] = None):
        self.invoice_repo = InvoiceRepository()
        self.sync_repo = SyncRepository()
        if anaf_client_factory is not None:
            self._get_client = anaf_client_factory
        else:
            def _lazy_client(cif):
                from .efactura_service import EFacturaService
                return EFacturaService().get_anaf_client(cif)
            self._get_client = _lazy_client

    def get_anaf_client(self, cif: str):
        return self._get_client(cif)

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
                'started_at': r.started_at.isoformat() if hasattr(r.started_at, 'isoformat') else r.started_at,
                'finished_at': r.finished_at.isoformat() if hasattr(r.finished_at, 'isoformat') else r.finished_at,
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
                'created_at': e.created_at.isoformat() if hasattr(e.created_at, 'isoformat') else e.created_at,
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
        import hashlib
        import traceback
        from ..xml_parser import parse_invoice_xml
        from ..config import ArtifactType

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

        # Create sync run to track this import operation
        sync_run = self.sync_repo.create_run(company_cif=cif, direction='received')
        run_id = sync_run.run_id

        imported = 0
        skipped = 0
        errors = []
        errors_count = 0

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
                # Note: ZIPs may contain multiple XMLs:
                # - semnatura_*.xml = digital signature (skip)
                # - *.xml = actual invoice (we want this)
                xml_content = None
                xml_filename = None
                with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                    for filename in zf.namelist():
                        # Skip signature files and .p7s files
                        if filename.startswith('semnatura') or filename.endswith('.p7s'):
                            continue
                        if filename.endswith('.xml'):
                            xml_content = zf.read(filename).decode('utf-8')
                            xml_filename = filename
                            break

                if not xml_content:
                    error_msg = f"No XML in message {message_id}"
                    errors.append(error_msg)
                    errors_count += 1
                    self.sync_repo.record_error(
                        run_id=run_id,
                        error_type='PARSE',
                        error_message=error_msg,
                        message_id=message_id,
                        is_retryable=True,
                    )
                    continue

                # Parse XML to extract invoice data
                parsed = parse_invoice_xml(xml_content)

                # Validate that this is actually an invoice (not a signature or other XML)
                if not parsed.invoice_number:
                    # Check if it's a signature XML
                    if '<Signature' in xml_content or '<ds:Signature' in xml_content:
                        error_msg = f"Message {message_id} contains signature XML, not invoice"
                    else:
                        error_msg = f"Message {message_id} contains invalid/empty invoice XML"
                    errors.append(error_msg)
                    errors_count += 1
                    self.sync_repo.record_error(
                        run_id=run_id,
                        error_type='PARSE',
                        error_message=error_msg,
                        message_id=message_id,
                        is_retryable=False,
                    )
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
                    error_msg = f"Failed to save message {message_id}"
                    errors.append(error_msg)
                    errors_count += 1
                    self.sync_repo.record_error(
                        run_id=run_id,
                        error_type='SYSTEM',
                        error_message=error_msg,
                        message_id=message_id,
                        invoice_ref=parsed.invoice_number,
                        is_retryable=True,
                    )

            except Exception as e:
                logger.error(f"Error importing message {message_id}: {e}")
                error_msg = f"Error with {message_id}: {str(e)}"
                errors.append(error_msg)
                errors_count += 1
                self.sync_repo.record_error(
                    run_id=run_id,
                    error_type='SYSTEM',
                    error_message=error_msg,
                    message_id=message_id,
                    stack_trace=traceback.format_exc(),
                    is_retryable=True,
                )

        # Complete the sync run with statistics
        sync_run.messages_checked = len(message_ids)
        sync_run.invoices_created = imported
        sync_run.invoices_skipped = skipped
        sync_run.errors_count = errors_count
        self.sync_repo.complete_run(
            run=sync_run,
            success=errors_count == 0,
            error_summary=f"{errors_count} errors" if errors_count > 0 else None,
        )

        return ServiceResult(success=True, data={
            'imported': imported,
            'skipped': skipped,
            'errors': errors if errors else None,
            'errors_count': errors_count,
            'sync_run_id': run_id,
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
        from .efactura_service import EFacturaService
        connections = EFacturaService().get_all_connections()

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
        from .duplicate_service import DuplicateDetectionService
        duplicates = DuplicateDetectionService().detect_unallocated_duplicates()

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
        from .efactura_service import EFacturaService
        connections = EFacturaService().get_all_connections()
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
