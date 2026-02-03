"""Email notification service for invoice allocations."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from core.utils.logging_config import get_logger

from database import (
    get_notification_settings,
    get_responsables_by_department,
    get_all_responsables,
    log_notification,
    update_notification_status,
    get_department_cc_email,
)

logger = get_logger('jarvis.notification')


def get_smtp_config() -> dict:
    """Get SMTP configuration from notification settings."""
    settings = get_notification_settings()
    return {
        'host': settings.get('smtp_host', ''),
        'port': int(settings.get('smtp_port', 587) or 587),
        'use_tls': settings.get('smtp_tls', 'true').lower() == 'true',
        'username': settings.get('smtp_username', ''),
        'password': settings.get('smtp_password', ''),
        'from_email': settings.get('from_email', ''),
        'from_name': settings.get('from_name', 'Bugetare System'),
        'global_cc': settings.get('global_cc', ''),
    }


def is_smtp_configured() -> bool:
    """Check if SMTP is properly configured."""
    config = get_smtp_config()
    return bool(config['host'] and config['from_email'])


def is_notifications_enabled() -> bool:
    """Check if allocation notifications are globally enabled."""
    settings = get_notification_settings()
    # The setting is stored as string 'true'/'false'
    return settings.get('notify_on_allocation', 'true').lower() == 'true'


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    department_cc: Optional[str] = None
) -> tuple[bool, str]:
    """
    Send an email using configured SMTP settings.

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email content
        text_body: Optional plain text email content
        department_cc: Optional department-specific CC email address

    Returns:
        tuple: (success: bool, error_message: str)
    """
    config = get_smtp_config()

    if not config['host']:
        return False, "SMTP host not configured"

    if not config['from_email']:
        return False, "From email not configured"

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{config['from_name']} <{config['from_email']}>" if config['from_name'] else config['from_email']
        msg['To'] = to_email

        # Build CC list from global CC and department CC
        cc_addresses = []
        global_cc = config.get('global_cc', '').strip()
        if global_cc:
            cc_addresses.append(global_cc)
        if department_cc and department_cc.strip():
            dept_cc = department_cc.strip()
            # Avoid duplicate if department CC is same as global CC
            if dept_cc not in cc_addresses:
                cc_addresses.append(dept_cc)

        if cc_addresses:
            msg['Cc'] = ', '.join(cc_addresses)

        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        # Build recipient list (To + all CCs)
        recipients = [to_email]
        recipients.extend(cc_addresses)

        if config['use_tls']:
            context = ssl.create_default_context()
            with smtplib.SMTP(config['host'], config['port']) as server:
                server.starttls(context=context)
                if config['username'] and config['password']:
                    server.login(config['username'], config['password'])
                server.sendmail(config['from_email'], recipients, msg.as_string())
        else:
            with smtplib.SMTP(config['host'], config['port']) as server:
                if config['username'] and config['password']:
                    server.login(config['username'], config['password'])
                server.sendmail(config['from_email'], recipients, msg.as_string())

        logger.info(f"Email sent to {to_email}, CC: {cc_addresses if cc_addresses else 'none'}")
        return True, ""

    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"SMTP authentication failed: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def send_test_email(to_email: str) -> tuple[bool, str]:
    """Send a test email to verify SMTP configuration."""
    subject = "Test Email - Bugetare Notification System"
    html_body = """
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Test Email</h2>
        <p>This is a test email from the Bugetare notification system.</p>
        <p>If you received this email, your SMTP configuration is working correctly.</p>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
        <p style="color: #666; font-size: 12px;">This is an automated message from Bugetare.</p>
    </body>
    </html>
    """
    text_body = "This is a test email from the Bugetare notification system.\n\nIf you received this email, your SMTP configuration is working correctly."

    return send_email(to_email, subject, html_body, text_body)


def format_currency(value: float, currency: str = 'RON') -> str:
    """Format a value as currency."""
    return f"{value:,.2f} {currency}"


def create_allocation_email_html(
    responsable_name: str,
    invoice_data: dict,
    allocation: dict
) -> str:
    """Create HTML email body for allocation notification."""
    invoice_number = invoice_data.get('invoice_number', 'N/A')
    supplier = invoice_data.get('supplier', 'N/A')
    invoice_date = invoice_data.get('invoice_date', 'N/A')
    # Use net_value if available (VAT subtracted), otherwise fall back to invoice_value
    net_value = invoice_data.get('net_value') or invoice_data.get('invoice_value', 0)
    currency = invoice_data.get('currency', 'RON')

    company = allocation.get('company', 'N/A')
    brand = allocation.get('brand', '')
    department = allocation.get('department', 'N/A')
    subdepartment = allocation.get('subdepartment', '')
    allocation_percent = allocation.get('allocation_percent', 0)
    allocation_value = allocation.get('allocation_value', 0)

    # Reinvoice details
    reinvoice_to = allocation.get('reinvoice_to', '')
    reinvoice_brand = allocation.get('reinvoice_brand', '')
    reinvoice_department = allocation.get('reinvoice_department', '')
    reinvoice_subdepartment = allocation.get('reinvoice_subdepartment', '')

    # Build subdepartment row if exists
    subdepartment_html = ""
    if subdepartment:
        subdepartment_html = f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Subdepartament</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{subdepartment}</td>
            </tr>"""

    # Build brand row if exists
    brand_html = ""
    if brand:
        brand_html = f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Linie de business</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{brand}</td>
            </tr>"""

    # Build reinvoice section as separate table
    reinvoice_section_html = ""
    if reinvoice_to:
        reinvoice_brand_row = ""
        if reinvoice_brand:
            reinvoice_brand_row = f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Linie de business</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{reinvoice_brand}</td>
            </tr>"""
        reinvoice_dept_row = ""
        if reinvoice_department:
            reinvoice_dept_row = f"""
            <tr style="background-color: #fff3cd;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Departament</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{reinvoice_department}</td>
            </tr>"""
        reinvoice_subdept_row = ""
        if reinvoice_subdepartment:
            reinvoice_subdept_row = f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Subdepartament</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{reinvoice_subdepartment}</td>
            </tr>"""

        reinvoice_section_html = f"""
        <h3 style="color: #856404;">Refacturare</h3>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; border: 2px solid #ffc107;">
            <tr style="background-color: #fff3cd;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Companie</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{reinvoice_to}</td>
            </tr>{reinvoice_brand_row}{reinvoice_dept_row}{reinvoice_subdept_row}
        </table>"""

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
            O noua bugetare MKT
        </h2>

        <p>Buna ziua {responsable_name},</p>

        <p>O factura a fost alocata departamentului dumneavoastra:</p>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #f5f5f5;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Numar factura</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{invoice_number}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Furnizor</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{supplier}</td>
            </tr>
            <tr style="background-color: #f5f5f5;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Data factura</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{invoice_date}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Val. Neta Totala</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{format_currency(net_value, currency)}</td>
            </tr>
        </table>

        <h3 style="color: #333;">Alocare</h3>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #e8f5e9;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Companie</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{company}</td>
            </tr>{brand_html}
            <tr style="background-color: #e8f5e9;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Departament</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{department}</td>
            </tr>{subdepartment_html}
            <tr style="background-color: #e8f5e9;">
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Procent alocare</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{allocation_percent}%</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Val. Neta Alocata</td>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; color: #4CAF50;">
                    {format_currency(allocation_value, currency)}
                </td>
            </tr>
        </table>{reinvoice_section_html}

        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

        <p style="color: #666; font-size: 12px;">
            Aceasta este o notificare automata din sistemul Bugetare.<br>
            Va rugam sa nu raspundeti la acest email.
        </p>
    </body>
    </html>
    """


def create_allocation_email_text(
    responsable_name: str,
    invoice_data: dict,
    allocation: dict
) -> str:
    """Create plain text email body for allocation notification."""
    invoice_number = invoice_data.get('invoice_number', 'N/A')
    supplier = invoice_data.get('supplier', 'N/A')
    invoice_date = invoice_data.get('invoice_date', 'N/A')
    # Use net_value if available (VAT subtracted), otherwise fall back to invoice_value
    net_value = invoice_data.get('net_value') or invoice_data.get('invoice_value', 0)
    currency = invoice_data.get('currency', 'RON')

    company = allocation.get('company', 'N/A')
    brand = allocation.get('brand', '')
    department = allocation.get('department', 'N/A')
    subdepartment = allocation.get('subdepartment', '')
    allocation_percent = allocation.get('allocation_percent', 0)
    allocation_value = allocation.get('allocation_value', 0)

    # Reinvoice details
    reinvoice_to = allocation.get('reinvoice_to', '')
    reinvoice_brand = allocation.get('reinvoice_brand', '')
    reinvoice_department = allocation.get('reinvoice_department', '')
    reinvoice_subdepartment = allocation.get('reinvoice_subdepartment', '')

    # Build brand line if exists
    brand_line = ""
    if brand:
        brand_line = f"\n- Linie de business: {brand}"

    # Build subdepartment line if exists
    subdepartment_line = ""
    if subdepartment:
        subdepartment_line = f"\n- Subdepartament: {subdepartment}"

    # Build reinvoice section
    reinvoice_section = ""
    if reinvoice_to:
        reinvoice_section = f"\n\nRefacturare:\n- Companie: {reinvoice_to}"
        if reinvoice_brand:
            reinvoice_section += f"\n- Linie de business: {reinvoice_brand}"
        if reinvoice_department:
            reinvoice_section += f"\n- Departament: {reinvoice_department}"
        if reinvoice_subdepartment:
            reinvoice_section += f"\n- Subdepartament: {reinvoice_subdepartment}"

    return f"""
O noua bugetare MKT

Buna ziua {responsable_name},

O factura a fost alocata departamentului dumneavoastra:

Detalii factura:
- Numar factura: {invoice_number}
- Furnizor: {supplier}
- Data factura: {invoice_date}
- Val. Neta Totala: {format_currency(net_value, currency)}

Alocare:
- Companie: {company}{brand_line}
- Departament: {department}{subdepartment_line}
- Procent alocare: {allocation_percent}%
- Val. Neta Alocata: {format_currency(allocation_value, currency)}{reinvoice_section}

---
Aceasta este o notificare automata din sistemul Bugetare.
Va rugam sa nu raspundeti la acest email.
"""


def find_responsables_for_allocation(allocation: dict) -> list[dict]:
    """
    Find all responsables that should be notified for a given allocation.

    Matches responsables based on their company AND department assignments.
    If reinvoice_to is set, also notifies the reinvoice company/department's responsables.
    """
    all_responsables = []
    seen_ids = set()

    # Get responsables for the main department, filtered by company
    company = allocation.get('company', '')
    department = allocation.get('department', '')
    logger.info(f"Finding responsables for allocation: company='{company}', department='{department}'")
    if department:
        # Pass company to filter responsables by both company AND department
        responsables = get_responsables_by_department(department, company)
        logger.info(f"Found {len(responsables)} responsables for company='{company}', dept='{department}'")
        for r in responsables:
            if r.get('is_active', True) and r.get('notify_on_allocation', True):
                if r.get('id') not in seen_ids:
                    all_responsables.append(r)
                    seen_ids.add(r.get('id'))
                else:
                    logger.debug(f"Skipped responsable {r.get('name')}: already seen")
            else:
                logger.debug(
                    f"Skipped responsable {r.get('name')}: "
                    f"is_active={r.get('is_active')}, notify={r.get('notify_on_allocation')}"
                )

    # If reinvoice_to is set, also get responsables for the reinvoice company/department
    reinvoice_to = allocation.get('reinvoice_to', '')  # This is the reinvoice company
    reinvoice_department = allocation.get('reinvoice_department', '')
    if reinvoice_to and reinvoice_department:
        # Pass reinvoice company to filter by both company AND department
        reinvoice_responsables = get_responsables_by_department(reinvoice_department, reinvoice_to)
        logger.debug(f"Found {len(reinvoice_responsables)} responsables for reinvoice company '{reinvoice_to}', department '{reinvoice_department}'")
        for r in reinvoice_responsables:
            if r.get('is_active', True) and r.get('notify_on_allocation', True):
                if r.get('id') not in seen_ids:
                    all_responsables.append(r)
                    seen_ids.add(r.get('id'))

    return all_responsables


def notify_allocation(invoice_data: dict, allocation: dict) -> list[dict]:
    """
    Send notification emails for a single allocation.

    Args:
        invoice_data: Dict with invoice details (invoice_number, supplier, etc.)
        allocation: Dict with allocation details (company, department, etc.)

    Returns:
        List of notification results with responsable info and send status
    """
    if not is_smtp_configured():
        logger.warning("SMTP not configured, skipping notifications")
        return []

    if not is_notifications_enabled():
        logger.info("Allocation notifications are disabled globally")
        return []

    results = []
    responsables = find_responsables_for_allocation(allocation)

    invoice_id = invoice_data.get('id')
    invoice_value = float(invoice_data.get('invoice_value', 0) or 0)

    # Look up department CC email
    company = allocation.get('company', '')
    department = allocation.get('department', '')
    department_cc = get_department_cc_email(company, department) if company and department else None

    # Calculate allocation_percent and allocation_value if not provided
    # Frontend sends 'allocation' as decimal (0.5 = 50%), template expects 'allocation_percent' (50)
    allocation_decimal = allocation.get('allocation')
    if allocation_decimal is None or allocation_decimal == 0:
        # Try to get from allocation_percent if available
        pct = allocation.get('allocation_percent', 0)
        allocation_decimal = float(pct) / 100 if pct else 0
    else:
        allocation_decimal = float(allocation_decimal)

    # Set allocation_percent (e.g., 50 for 50%)
    if not allocation.get('allocation_percent'):
        allocation['allocation_percent'] = round(allocation_decimal * 100, 2)

    # Set allocation_value (calculated from invoice_value * decimal)
    if not allocation.get('allocation_value'):
        allocation['allocation_value'] = round(invoice_value * allocation_decimal, 2)

    for responsable in responsables:
        responsable_id = responsable.get('id')
        responsable_name = responsable.get('name', 'User')
        responsable_email = responsable.get('email')

        if not responsable_email:
            continue

        subject = f"O noua bugetare MKT - {invoice_data.get('invoice_number', 'Factura')}"
        html_body = create_allocation_email_html(responsable_name, invoice_data, allocation)
        text_body = create_allocation_email_text(responsable_name, invoice_data, allocation)

        # Log the notification attempt
        log_id = log_notification(
            responsable_id=responsable_id,
            invoice_id=invoice_id,
            notification_type='allocation',
            subject=subject,
            message=text_body,
            status='pending'
        )

        # Send the email with department CC if configured
        success, error_message = send_email(responsable_email, subject, html_body, text_body, department_cc)

        # Update notification status
        if success:
            update_notification_status(log_id, 'sent')
        else:
            update_notification_status(log_id, 'failed', error_message)

        results.append({
            'responsable_id': responsable_id,
            'responsable_name': responsable_name,
            'responsable_email': responsable_email,
            'success': success,
            'error': error_message if not success else None
        })

    return results


def notify_invoice_allocations(invoice_data: dict, allocations: list[dict]) -> list[dict]:
    """
    Send notification emails for all allocations of an invoice.

    Args:
        invoice_data: Dict with invoice details
        allocations: List of allocation dicts

    Returns:
        List of all notification results
    """
    all_results = []

    for allocation in allocations:
        results = notify_allocation(invoice_data, allocation)
        all_results.extend(results)

    return all_results
