"""
Mock ANAF API Responses

Test fixtures for mocking ANAF e-Factura API responses.
"""

import io
import zipfile
from datetime import datetime


# Sample list of received messages
MOCK_LIST_RECEIVED_RESPONSE = {
    'mesaje': [
        {
            'id': '3066421557',
            'cif': '12345678',
            'id_solicitare': '5033917117',
            'tip': 'FACTURA',
            'data_creare': '202501261030',
            'stare': 'valid',
        },
        {
            'id': '3066421558',
            'cif': '12345678',
            'id_solicitare': '5033917118',
            'tip': 'FACTURA',
            'data_creare': '202501251430',
            'stare': 'valid',
        },
    ],
    'numar_total': 2,
    'numar_total_pagini': 1,
    'pagina_curenta': 1,
}

# Sample list of sent messages
MOCK_LIST_SENT_RESPONSE = {
    'mesaje': [
        {
            'id': '4077532668',
            'cif': '12345678',
            'id_solicitare': '6044028228',
            'tip': 'FACTURA',
            'data_creare': '202501260900',
            'stare': 'valid',
        },
    ],
    'numar_total': 1,
    'numar_total_pagini': 1,
    'pagina_curenta': 1,
}

# Sample message status response
MOCK_MESSAGE_STATUS_RESPONSE = {
    'stare': 'valid',
    'stare_mesaj': 'Factura validata cu succes',
    'id_descarcare': '3066421557',
    'erori': [],
}

# Rate limit exceeded response
MOCK_RATE_LIMIT_RESPONSE = {
    'error': 'Too Many Requests',
    'message': 'Rate limit exceeded. Please wait.',
}

# Sample UBL 2.1 Invoice XML
SAMPLE_UBL_INVOICE_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>INV-2025-001</cbc:ID>
    <cbc:IssueDate>2025-01-26</cbc:IssueDate>
    <cbc:DueDate>2025-02-26</cbc:DueDate>
    <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
    <cbc:Note>Test invoice for unit testing</cbc:Note>

    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyLegalEntity>
                <cbc:RegistrationName>ACME SRL</cbc:RegistrationName>
                <cbc:CompanyID>J40/1234/2020</cbc:CompanyID>
            </cac:PartyLegalEntity>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>RO87654321</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PostalAddress>
                <cbc:StreetName>Str. Exemplu nr. 10</cbc:StreetName>
                <cbc:CityName>Bucuresti</cbc:CityName>
                <cac:Country>
                    <cbc:IdentificationCode>RO</cbc:IdentificationCode>
                </cac:Country>
            </cac:PostalAddress>
        </cac:Party>
    </cac:AccountingSupplierParty>

    <cac:AccountingCustomerParty>
        <cac:Party>
            <cac:PartyLegalEntity>
                <cbc:RegistrationName>TEST COMPANY SRL</cbc:RegistrationName>
            </cac:PartyLegalEntity>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>RO12345678</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>

    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="RON">190.00</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="RON">1000.00</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="RON">190.00</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>19</cbc:Percent>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>

    <cac:LegalMonetaryTotal>
        <cbc:TaxExclusiveAmount currencyID="RON">1000.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="RON">1190.00</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="RON">1190.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>

    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="BUC">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="RON">1000.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Test Product</cbc:Name>
            <cbc:Description>A product for testing</cbc:Description>
            <cac:ClassifiedTaxCategory>
                <cbc:Percent>19</cbc:Percent>
            </cac:ClassifiedTaxCategory>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="RON">100.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
</Invoice>
'''

# Sample signature XML (simplified)
SAMPLE_SIGNATURE_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
        <CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
        <SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
    </SignedInfo>
    <SignatureValue>ABC123...</SignatureValue>
</Signature>
'''


def create_mock_zip_content(
    invoice_xml: bytes = SAMPLE_UBL_INVOICE_XML,
    include_signature: bool = True,
    filename: str = 'invoice.xml',
) -> bytes:
    """
    Create a mock ZIP file containing invoice XML and optional signature.

    Args:
        invoice_xml: Invoice XML content
        include_signature: Whether to include signature file
        filename: Name of the invoice XML file

    Returns:
        ZIP file content as bytes
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, invoice_xml)
        if include_signature:
            zf.writestr('semnatura.xml', SAMPLE_SIGNATURE_XML)

    buffer.seek(0)
    return buffer.read()


# Error response examples
MOCK_AUTH_ERROR_RESPONSE = {
    'error': 'Unauthorized',
    'message': 'Invalid or expired certificate',
}

MOCK_VALIDATION_ERROR_RESPONSE = {
    'stare': 'nok',
    'erori': [
        {
            'cod': 'E001',
            'mesaj': 'CIF invalid',
        },
    ],
}

# Pagination example with multiple pages
MOCK_PAGINATED_RESPONSE_PAGE1 = {
    'mesaje': [
        {'id': f'msg_{i}', 'cif': '12345678', 'tip': 'FACTURA'}
        for i in range(100)
    ],
    'numar_total': 250,
    'numar_total_pagini': 3,
    'pagina_curenta': 1,
}

MOCK_PAGINATED_RESPONSE_PAGE2 = {
    'mesaje': [
        {'id': f'msg_{i}', 'cif': '12345678', 'tip': 'FACTURA'}
        for i in range(100, 200)
    ],
    'numar_total': 250,
    'numar_total_pagini': 3,
    'pagina_curenta': 2,
}

MOCK_PAGINATED_RESPONSE_PAGE3 = {
    'mesaje': [
        {'id': f'msg_{i}', 'cif': '12345678', 'tip': 'FACTURA'}
        for i in range(200, 250)
    ],
    'numar_total': 250,
    'numar_total_pagini': 3,
    'pagina_curenta': 3,
}
