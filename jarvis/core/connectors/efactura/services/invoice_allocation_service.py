"""
Invoice Allocation Service - unallocated invoice management and module integration.
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import date

from core.utils.logging_config import get_logger
from core.organization.repositories import CompanyRepository as _CompanyRepo
from core.services.notification_service import notify_invoice_allocations, is_smtp_configured

from ..config import InvoiceDirection
from ..repositories import InvoiceRepository
from ..models import Invoice
from .base import ServiceResult
from .invoice_service import InvoiceService

logger = get_logger('jarvis.core.connectors.efactura.invoice_allocation_service')

_company_repo = _CompanyRepo()
get_companies_with_vat = _company_repo.get_all_with_vat_and_brands


class InvoiceAllocationService:
    def __init__(self):
        self.invoice_repo = InvoiceRepository()
        self.invoice_service = InvoiceService()

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
                'total_without_vat': str(inv.get('total_without_vat', 0)),
                'due_date': inv.get('due_date').isoformat() if hasattr(inv.get('due_date'), 'isoformat') else inv.get('due_date'),
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
                'mapped_brand': inv.get('mapping_brand'),
                'department_override_2': inv.get('department_override_2'),
                'subdepartment_override_2': inv.get('subdepartment_override_2'),
                'observer_user_ids': inv.get('observer_user_ids') or [],
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

    def send_to_invoice_module(self, invoice_ids: List[int],
                               observer_user_ids: Optional[List[int]] = None) -> ServiceResult:
        """
        Send selected invoices to the main JARVIS Invoice Module.

        Creates records in the main invoices table and marks these as allocated.
        Optionally attaches observer users to every newly created invoice.

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

            # Step 4: Attach observers — union of dialog-level observers and per-invoice stored observers.
            def _normalize_ids(raw_list):
                out = []
                seen = set()
                for raw in raw_list or []:
                    try:
                        uid = int(raw)
                    except (TypeError, ValueError):
                        continue
                    if uid in seen:
                        continue
                    seen.add(uid)
                    out.append(uid)
                return out

            dialog_observers = _normalize_ids(observer_user_ids)
            # Build a lookup: efactura_id -> stored observer list
            efactura_observers_by_id = {
                inv['id']: _normalize_ids(inv.get('observer_user_ids'))
                for inv in invoices
            }

            if dialog_observers or any(efactura_observers_by_id.values()):
                try:
                    from accounting.invoices.repositories import InvoiceRepository as MainInvoiceRepository
                    main_invoice_repo = MainInvoiceRepository()
                    for efactura_id, jarvis_id in mappings:
                        stored = efactura_observers_by_id.get(efactura_id, [])
                        merged = list(dict.fromkeys([*dialog_observers, *stored]))
                        if merged:
                            main_invoice_repo.sync_observers(jarvis_id, merged)
                except Exception as obs_err:
                    logger.error(f"Failed to attach observers: {obs_err}")
                    errors.append(f"Observers not attached: {obs_err}")

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
        from core.database import get_db, get_cursor, release_db
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

        from core.database import get_db, get_cursor, release_db
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
                has_second_dept = bool(inv.get('department_override_2'))

                # Only create allocation if we have company and department
                if company_name and department:
                    # Use net_value for allocation if available, otherwise gross
                    net_value = inv.get('total_without_vat')
                    total_value = net_value if net_value else inv['total_amount']
                    subdepartment = inv.get('subdepartment')
                    brand = inv.get('brand')  # From supplier mapping
                    responsible = inv.get('responsible')  # From department_structure
                    responsible_user_id = responsible_user_ids.get(responsible.lower()) if responsible else None

                    if has_second_dept:
                        # Multi-department: create TWO allocations at 50% each
                        allocation_value_half = total_value / 2

                        # First allocation: primary department at 50%
                        alloc_values.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                        alloc_params.extend([
                            jarvis_id,
                            company_name,
                            brand,
                            department,
                            subdepartment,
                            50.0,              # 50% to first dept
                            allocation_value_half,
                            responsible,
                            responsible_user_id,
                        ])

                        # Second allocation: secondary department at 50%
                        dept2 = inv.get('department_override_2')
                        subdept2 = inv.get('subdepartment_override_2')

                        # Look up responsible for second department
                        responsible2 = None
                        responsible2_user_id = None
                        if dept2:
                            cursor.execute("""
                                SELECT ds.manager, u.id as user_id
                                FROM department_structure ds
                                LEFT JOIN users u ON LOWER(u.name) = LOWER(ds.manager)
                                WHERE ds.company = %s AND ds.department = %s
                                ORDER BY
                                    CASE WHEN ds.subdepartment = %s THEN 0 ELSE 1 END,
                                    ds.id
                                LIMIT 1
                            """, (company_name, dept2, subdept2))
                            row = cursor.fetchone()
                            if row and row['manager']:
                                responsible2 = row['manager']
                                responsible2_user_id = row['user_id']

                        alloc_values.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                        alloc_params.extend([
                            jarvis_id,
                            company_name,
                            brand,             # Same brand for both allocations
                            dept2,
                            subdept2,
                            50.0,              # 50% to second dept
                            allocation_value_half,
                            responsible2,
                            responsible2_user_id,
                        ])
                    else:
                        # Single department: create ONE allocation at 100%
                        alloc_values.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                        alloc_params.extend([
                            jarvis_id,
                            company_name,
                            brand,
                            department,
                            subdepartment,
                            100.0,             # 100% to single dept
                            total_value,
                            responsible,
                            responsible_user_id,
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
                    # Notify for all invoices with allocations (single or multi-dept)
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
