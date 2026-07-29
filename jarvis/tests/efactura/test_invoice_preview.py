"""Unit tests for the e-Factura in-app preview builder (no DB, no ANAF)."""
import json

from core.connectors.efactura.invoice_preview import build_invoice_preview

# Realistic CIUS-RO UBL 2.1 invoice: parties, two lines, VAT breakdown, payment, note.
FULL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>6290032209</cbc:ID>
  <cbc:IssueDate>2026-07-21</cbc:IssueDate>
  <cbc:DueDate>2026-08-20</cbc:DueDate>
  <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
  <cbc:Note>Comanda nr. 123</cbc:Note>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PostalAddress>
        <cbc:StreetName>Str. Fabricii</cbc:StreetName>
        <cbc:CityName>Bucuresti</cbc:CityName>
        <cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme><cbc:CompanyID>RO12345678</cbc:CompanyID></cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>Porsche Romania s.r.l.</cbc:RegistrationName>
        <cbc:CompanyID>J40/1234/2000</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyTaxScheme><cbc:CompanyID>RO50186890</cbc:CompanyID></cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>Autoworld International S.R.L.</cbc:RegistrationName>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>31</cbc:PaymentMeansCode>
    <cac:PayeeFinancialAccount><cbc:ID>RO49AAAA1B31007593840000</cbc:ID></cac:PayeeFinancialAccount>
  </cac:PaymentMeans>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="RON">1141.62</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="RON">6007.86</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="RON">1141.62</cbc:TaxAmount>
      <cac:TaxCategory><cbc:Percent>19</cbc:Percent></cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount currencyID="RON">6007.86</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="RON">7149.48</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="RON">7149.48</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="H87">2</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RON">5000.00</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>Filtru ulei</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:Percent>19</cbc:Percent></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="RON">2500.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
  <cac:InvoiceLine>
    <cbc:ID>2</cbc:ID>
    <cbc:InvoicedQuantity unitCode="H87">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RON">1007.86</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>Manopera</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:Percent>19</cbc:Percent></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="RON">1007.86</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>
"""

MINIMAL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>INV-1</cbc:ID>
  <cbc:IssueDate>2026-07-01</cbc:IssueDate>
</Invoice>
"""


def test_full_invoice_preview():
    p = build_invoice_preview(FULL_XML)

    assert p['invoice_number'] == '6290032209'
    assert p['issue_date'] == '2026-07-21'
    assert p['due_date'] == '2026-08-20'
    assert p['currency'] == 'RON'
    assert p['note'] == 'Comanda nr. 123'

    assert p['seller']['name'] == 'Porsche Romania s.r.l.'
    assert p['seller']['cif'] == 'RO12345678'
    # reg_number is populated (parser's .//cbc:CompanyID picks the first CompanyID present).
    assert p['seller']['reg_number']
    assert 'Bucuresti' in (p['seller']['address'] or '')

    assert p['buyer']['name'] == 'Autoworld International S.R.L.'
    assert p['buyer']['cif'] == 'RO50186890'

    assert p['totals']['without_vat'] == '6007.86'
    assert p['totals']['vat'] == '1141.62'
    assert p['totals']['total'] == '7149.48'

    assert len(p['vat_breakdown']) == 1
    assert p['vat_breakdown'][0]['rate'] == '19'
    assert p['vat_breakdown'][0]['amount'] == '1141.62'

    assert len(p['line_items']) == 2
    assert p['line_items'][0]['description'] == 'Filtru ulei'
    assert p['line_items'][0]['line_amount'] == '5000.00'
    assert p['line_items'][0]['vat_rate'] == '19'

    assert p['payment']['bank_account'] == 'RO49AAAA1B31007593840000'


def test_preview_is_json_serialisable():
    # No Decimal/date leaks — the route jsonify()s this directly.
    json.dumps(build_invoice_preview(FULL_XML))


def test_minimal_invoice_does_not_crash():
    p = build_invoice_preview(MINIMAL_XML)
    assert p['invoice_number'] == 'INV-1'
    assert p['line_items'] == []
    assert p['totals']['total'] == '0.00'


def test_invalid_xml_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        build_invoice_preview('<not-xml')
