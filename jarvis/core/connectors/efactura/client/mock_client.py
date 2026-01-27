"""
Mock ANAF Client for Development Testing

Returns realistic mock data for testing without a real certificate.
Enable by setting EFACTURA_MOCK_MODE=true environment variable.
"""

import io
import zipfile
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import random

from core.utils.logging_config import get_logger

logger = get_logger('jarvis.core.connectors.efactura.client.mock')


# Sample invoice data for testing
MOCK_SUPPLIERS = [
    {'cif': '12345678', 'name': 'FURNIZOR TEST SRL'},
    {'cif': '87654321', 'name': 'ACME SERVICES SRL'},
    {'cif': '11223344', 'name': 'TECH SOLUTIONS SA'},
    {'cif': '44332211', 'name': 'OFFICE SUPPLIES SRL'},
    {'cif': '99887766', 'name': 'CONSULTING EXPERT SRL'},
]

MOCK_XML_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
    <cbc:ID>{invoice_number}</cbc:ID>
    <cbc:IssueDate>{issue_date}</cbc:IssueDate>
    <cbc:DueDate>{due_date}</cbc:DueDate>
    <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeID="CIF">{supplier_cif}</cbc:ID>
            </cac:PartyIdentification>
            <cac:PartyName>
                <cbc:Name>{supplier_name}</cbc:Name>
            </cac:PartyName>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeID="CIF">{customer_cif}</cbc:ID>
            </cac:PartyIdentification>
            <cac:PartyName>
                <cbc:Name>{customer_name}</cbc:Name>
            </cac:PartyName>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:LegalMonetaryTotal>
        <cbc:TaxExclusiveAmount currencyID="RON">{net_amount}</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="RON">{gross_amount}</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="RON">{gross_amount}</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>
'''


class MockANAFClient:
    """
    Mock ANAF client for development testing.

    Returns realistic mock data without making real API calls.
    """

    def __init__(self, company_cif: str = 'RO225615'):
        """Initialize mock client."""
        self.company_cif = company_cif
        self._generate_mock_messages()
        logger.info("Mock ANAF client initialized", extra={'cif': company_cif})

    def _generate_mock_messages(self):
        """Generate a set of mock messages for testing."""
        self._messages = []
        base_date = datetime.now()

        for i in range(25):  # Generate 25 mock invoices
            days_ago = random.randint(1, 60)
            msg_date = base_date - timedelta(days=days_ago)
            supplier = random.choice(MOCK_SUPPLIERS)

            # Randomly decide if received or sent
            is_received = random.random() > 0.3  # 70% received

            message = {
                'id': f'{100000 + i}',
                'data_creare': msg_date.strftime('%Y%m%d%H%M%S'),
                'cif': self.company_cif,
                'id_solicitare': f'SOL{200000 + i}',
                'detalii': f'Factura {supplier["name"]} - {msg_date.strftime("%Y-%m-%d")}',
                'tip': 'FACTURA PRIMITA' if is_received else 'FACTURA TRIMISA',
                # Extra fields for mock data generation
                '_supplier': supplier,
                '_date': msg_date,
                '_is_received': is_received,
                '_amount': round(random.uniform(100, 10000), 2),
            }
            self._messages.append(message)

        # Sort by date descending
        self._messages.sort(key=lambda x: x['data_creare'], reverse=True)

    def list_messages(
        self,
        company_cif: str,
        days: int = 60,
        page: int = 1,
        filter_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mock list messages with pagination."""
        logger.info(
            "[MOCK] Listing messages",
            extra={'cif': company_cif, 'days': days, 'page': page, 'filter': filter_type}
        )

        # Filter messages
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered = []

        for msg in self._messages:
            msg_date = datetime.strptime(msg['data_creare'], '%Y%m%d%H%M%S')
            if msg_date < cutoff_date:
                continue

            if filter_type == 'P' and not msg['_is_received']:
                continue
            if filter_type == 'T' and msg['_is_received']:
                continue

            # Return clean message without internal fields
            filtered.append({
                'id': msg['id'],
                'data_creare': msg['data_creare'],
                'cif': msg['cif'],
                'id_solicitare': msg['id_solicitare'],
                'detalii': msg['detalii'],
                'tip': msg['tip'],
            })

        # Paginate
        per_page = 10
        total_records = len(filtered)
        total_pages = max(1, (total_records + per_page - 1) // per_page)

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_messages = filtered[start_idx:end_idx]

        has_more = page < total_pages

        return {
            'messages': page_messages,
            'has_more': has_more,
            'next_page': page + 1 if has_more else None,
            'current_page': page,
            'total_pages': total_pages,
            'total_records': total_records,
            'records_per_page': per_page,
            'serial': f'MOCK-{datetime.now().strftime("%Y%m%d")}',
            'title': f'[MOCK] Facturi pentru CIF {company_cif}',
        }

    def list_received_messages(self, company_cif: str, days: int = 60, page: int = 1):
        """Mock list received invoices."""
        return self.list_messages(company_cif, days, page, filter_type='P')

    def list_sent_messages(self, company_cif: str, days: int = 60, page: int = 1):
        """Mock list sent invoices."""
        return self.list_messages(company_cif, days, page, filter_type='T')

    def list_all_messages(self, company_cif: str, days: int = 60):
        """Mock list all messages."""
        return self.list_messages(company_cif, days, page=1, filter_type=None)

    def download_message(self, download_id: str) -> bytes:
        """Mock download invoice ZIP file."""
        logger.info("[MOCK] Downloading invoice", extra={'download_id': download_id})

        # Find the message
        message = None
        for msg in self._messages:
            if msg['id'] == download_id:
                message = msg
                break

        if message is None:
            # Generate random data if not found
            supplier = random.choice(MOCK_SUPPLIERS)
            msg_date = datetime.now() - timedelta(days=random.randint(1, 30))
            amount = round(random.uniform(100, 5000), 2)
        else:
            supplier = message['_supplier']
            msg_date = message['_date']
            amount = message['_amount']

        # Generate mock XML
        net_amount = amount
        vat_amount = round(amount * 0.19, 2)
        gross_amount = round(net_amount + vat_amount, 2)

        invoice_xml = MOCK_XML_TEMPLATE.format(
            invoice_number=f'MOCK-{download_id}',
            issue_date=msg_date.strftime('%Y-%m-%d'),
            due_date=(msg_date + timedelta(days=30)).strftime('%Y-%m-%d'),
            supplier_cif=supplier['cif'],
            supplier_name=supplier['name'],
            customer_cif=self.company_cif,
            customer_name='AUTOWORLD S.R.L.',
            net_amount=f'{net_amount:.2f}',
            gross_amount=f'{gross_amount:.2f}',
        )

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f'{download_id}.xml', invoice_xml.encode('utf-8'))
            zf.writestr(f'{download_id}.xml.p7s', b'MOCK_SIGNATURE_DATA')

        zip_buffer.seek(0)
        return zip_buffer.read()

    def fetch_all_pages(
        self,
        company_cif: str,
        days: int = 60,
        filter_type: Optional[str] = None,
        max_pages: int = 100,
    ) -> list:
        """Fetch all messages across all pages."""
        all_messages = []
        page = 1

        while page <= max_pages:
            result = self.list_messages(company_cif, days, page, filter_type)
            all_messages.extend(result['messages'])

            if not result['has_more']:
                break
            page += 1

        return all_messages

    def xml_to_pdf(
        self,
        xml_content: str,
        standard: str = 'FACT1',
        validate: bool = True,
    ) -> bytes:
        """
        Mock XML to PDF conversion.

        Returns a simple mock PDF file.
        """
        logger.info(
            "[MOCK] Converting XML to PDF",
            extra={'standard': standard, 'validate': validate}
        )

        # Generate a simple mock PDF
        # This is a minimal valid PDF structure
        mock_pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 150 >>
stream
BT
/F1 24 Tf
100 700 Td
(MOCK e-Factura PDF) Tj
0 -30 Td
/F1 12 Tf
(This is a mock PDF for development testing.) Tj
0 -20 Td
(Standard: """ + standard.encode() + b""") Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000468 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
547
%%EOF"""

        return mock_pdf

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Mock rate limit status."""
        return {
            'requests_made': 0,
            'max_per_hour': 150,
            'remaining': 150,
            'window_start': datetime.now().isoformat(),
            'is_near_limit': False,
            'mock_mode': True,
        }

    def close(self):
        """Mock close (no-op)."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
