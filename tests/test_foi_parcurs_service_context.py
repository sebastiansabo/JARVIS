"""Pure-logic units for the Foi de Parcurs Service context."""
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import PyPDF2

from foi_parcurs.document_types import SALES, SERVICE, normalize, pools_match
from foi_parcurs.services.contract_template import render_contract_template, PLACEHOLDERS


class TestDocumentTypes:
    def test_normalize_valid(self):
        assert normalize('service') == SERVICE
        assert normalize('sales') == SALES

    def test_normalize_unknown_defaults_to_sales(self):
        assert normalize('') == SALES
        assert normalize(None) == SALES
        assert normalize('bogus') == SALES

    def test_pools_match(self):
        assert pools_match('service', 'service') is True
        assert pools_match('sales', 'sales') is True

    def test_pools_mismatch(self):
        assert pools_match('service', 'sales') is False
        assert pools_match('sales', 'service') is False

    def test_pools_match_normalizes_blanks(self):
        # a legacy/blank vehicle pool is treated as 'sales'
        assert pools_match('sales', None) is True
        assert pools_match('service', None) is False


class TestContractTemplate:
    def test_substitutes_known_tokens(self):
        out = render_contract_template(
            'Client {client_name}, VIN {vin}, km {km_start}.',
            {'client_name': 'Ion Pop', 'vin': 'WVW123', 'km_start': 45000},
        )
        assert out == 'Client Ion Pop, VIN WVW123, km 45000.'

    def test_unknown_token_renders_literally(self):
        out = render_contract_template('Hi {not_a_token} there', {'client_name': 'X'})
        assert out == 'Hi {not_a_token} there'

    def test_missing_known_token_is_blank(self):
        out = render_contract_template('Ref: {service_order_ref}!', {})
        assert out == 'Ref: !'

    def test_service_order_ref_is_whitelisted(self):
        assert 'service_order_ref' in PLACEHOLDERS

    def test_none_template_is_empty_string(self):
        assert render_contract_template(None, {'vin': 'X'}) == ''


# --- S7: ordered Service contract PDF (pdf_service.generate_service_contract_pdf) ---

def _fake_service_cfg():
    """A `fp_contract_configs` row shaped like ContractConfigRepository.get_active()
    would return, using the real AutoWorld Service face/T&C templates so the
    smoke test renders the actual damage price-list format, not a stand-in."""
    from foi_parcurs.services.service_contract_templates import (
        SERVICE_CONTRACT_FACE, SERVICE_CONTRACT_TERMS,
    )
    return {
        'id': 1,
        'title': 'Contract Inchiriere Auto',
        'body_template': SERVICE_CONTRACT_FACE,
        'general_conditions': SERVICE_CONTRACT_TERMS,
        'is_active': True,
    }


def _fake_service_contract(**overrides):
    base = {
        'contract_id': 'FP-TEST-S7',
        'company_id': 16,
        'company_name': 'AUTOWORLD Plus S.R.L.',
        'company_street': 'Calea Floresti 145',
        'company_city': 'Cluj-Napoca',
        'company_county': 'Cluj',
        'company_reg_no': 'J12/2102/2024',
        'company_vat': 'RO50022994',
        'company_iban': 'RO34 BACX 0000 0026 7930 8000',
        'company_bank': 'Unicredit Cluj-Napoca',
        'company_administrator': 'Ioan Mezei',
        'company_email': 'office@autoworld.ro',
        # set directly (rather than left to the vin->FPVehicleRepository fallback)
        # so the smoke test doesn't need a real vehicle row.
        'vehicle_brand': 'Volkswagen',
        'vehicle_model': 'Golf',
        'vin': 'WVWZZZ1KZAW000001',
        'registration_number': 'CJ 01 TST',
        'client_name': 'Ion Popescu',
        'client_phone': '0740000000',
        'client_email': 'ion.popescu@example.com',
        'client_address': 'Str. Exemplu 1, Cluj-Napoca',
        'client_company': 'Exemplu S.R.L.',
        'client_cui': '12345678',
        'client_ci_serie': 'CJ 123456',
        'km_start': 10000,
        'km_end': 10450,
        'departure_datetime': '2026-08-01T09:00:00',
        'return_datetime': '2026-08-05T18:00:00',
        'advisor_name': 'Andrei Consilier',
        'service_order_ref': 'SVC-2026-001',
        'svc_tariff_eur': 45,
        'svc_rate_basis': 'day',
        'svc_units': 4,
        'svc_total_eur': 180,
        'svc_garantie_eur': 500,
        'svc_fransiza_eur': 300,
        'svc_km_included_day': 200,
        'svc_extra_km_eur': 0.5,
        'general_conditions_accepted_at': '2026-08-01T09:05:00+00:00',
    }
    base.update(overrides)
    return base


def _pdf_text(path):
    reader = PyPDF2.PdfReader(path)
    return '\n'.join(page.extract_text() or '' for page in reader.pages)


def _flowables_text(flowables):
    """Plain text of a list of ReportLab flowables (Table cells + Paragraphs),
    for asserting on `_damage_table` output without building a full PDF."""
    from reportlab.platypus import Table
    out = []
    for fl in flowables:
        if isinstance(fl, Table):
            for row in fl._cellvalues:
                for cell in row:
                    if hasattr(cell, 'getPlainText'):
                        out.append(cell.getPlainText())
        elif hasattr(fl, 'getPlainText'):
            out.append(fl.getPlainText())
    return '\n'.join(out)


class TestServiceContractPdf:
    """S7 — the Service contract PDF renders in the ordered, structured
    layout: Title -> Partile -> Autovehicul&perioada/Kilometraj -> Tarif si
    garantie -> Conditii generale (T&C + damage price table + GDPR) ->
    Semnaturi."""

    def test_ordered_pdf_has_tariff_table_damage_table_and_sections(self, monkeypatch, tmp_path):
        from foi_parcurs.repositories.contract_config_repository import ContractConfigRepository
        from foi_parcurs.services import pdf_service as ps

        cfg = _fake_service_cfg()
        monkeypatch.setattr(
            ContractConfigRepository, 'get_active',
            lambda self, company_id, brand_name, document_type='service': cfg,
        )
        monkeypatch.setattr(ps, '_PDF_DIR', str(tmp_path))

        contract = _fake_service_contract()
        out_path = ps.generate_service_contract_pdf(contract)

        assert os.path.exists(out_path)
        text = _pdf_text(out_path)

        # A damage-price label from SERVICE_CONTRACT_TERMS survives the
        # marker split and renders as a real table row (diacritics are
        # stripped by pdf_service's `_ascii`, "cheie" has none).
        assert 'Pierdere cheie' in text
        assert 'Elemente vitrate' in text          # category-header row
        assert 'Anvelopa' in text                  # another priced row further down

        # Tarif si garantie summary table (svc_* snapshot off the contract row)
        assert 'Tarif si garantie' in text
        assert '45 EUR / zi' in text                # svc_tariff_eur + rate basis
        assert 'Total\n180 EUR' in text              # svc_total_eur
        assert 'Garantie\n500 EUR' in text           # svc_garantie_eur
        assert 'Fransiza\n300 EUR' in text           # svc_fransiza_eur
        assert 'Km inclusi/zi\n200' in text          # svc_km_included_day
        assert '0.5 EUR/km' in text                 # svc_extra_km_eur

        # Section headers, in order.
        headings = ['Partile', 'Date Companie si Vehicul', 'Date Client', 'Consilier',
                    'Perioada', 'Kilometraj', 'Tarif si garantie', 'Conditii generale',
                    'Valoarea facturabila a daunelor', 'Protectia datelor',
                    'Semnaturi']
        positions = [text.find(h) for h in headings]
        assert all(p != -1 for p in positions), dict(zip(headings, positions))
        assert positions == sorted(positions), dict(zip(headings, positions))

        # GDPR/consent tail actually made it into the doc (not silently dropped).
        assert 'AUTOWORLD SRL' in text
        assert 'protectiadatelor@autoworld.ro' in text

    def test_falls_back_to_legal_pdf_when_no_active_config(self, monkeypatch):
        from foi_parcurs.repositories.contract_config_repository import ContractConfigRepository
        from foi_parcurs.services import pdf_service as ps

        monkeypatch.setattr(
            ContractConfigRepository, 'get_active',
            lambda self, company_id, brand_name, document_type='service': None,
        )
        calls = {}

        def fake_legal_pdf(contract):
            calls['contract'] = contract
            return '/tmp/fallback-legal.pdf'

        monkeypatch.setattr(ps, 'generate_legal_pdf', fake_legal_pdf)

        contract = _fake_service_contract()
        result = ps.generate_service_contract_pdf(contract)

        assert result == '/tmp/fallback-legal.pdf'
        assert calls.get('contract') is contract

    def test_split_general_conditions_finds_marker(self):
        from foi_parcurs.services import pdf_service as ps
        from foi_parcurs.services.service_contract_templates import SERVICE_CONTRACT_TERMS

        before, damage_block, after = ps._split_general_conditions(SERVICE_CONTRACT_TERMS)
        assert 'DISPOZIȚII FINALE' in before
        assert 'Pierdere cheie' in damage_block
        assert '|' not in after
        assert 'AUTOWORLD SRL' in after

    def test_split_general_conditions_no_marker_returns_whole_text_as_before(self):
        from foi_parcurs.services import pdf_service as ps

        before, damage_block, after = ps._split_general_conditions('plain T&C, no damage table')
        assert before == 'plain T&C, no damage table'
        assert damage_block == ''
        assert after == ''

    def test_damage_table_returns_flowables_for_priced_lines(self):
        from foi_parcurs.services import pdf_service as ps

        block = 'Pierdere cheie masina | 250 Eur-400 Eur\nElemente vitrate\nParbriz | 160 Eur-600 Eur\n*Preturile includ TVA'
        fl = ps._damage_table(block)
        assert fl  # non-empty: at least the Table (+ note Paragraph)

    def test_damage_table_empty_only_for_truly_empty_or_boilerplate(self):
        from foi_parcurs.services import pdf_service as ps

        # Genuinely nothing to render.
        assert ps._damage_table('') == []
        # The two known boilerplate caption lines carry no data of their own
        # (the caller renders the heading + 'Cost' column header) -> [].
        assert ps._damage_table('VALOAREA  FACTURABILA  A DAUNELOR\nCost Dauna Neasigurata*') == []

    def test_damage_table_preserves_custom_category_header(self):
        # A dealer's admin-editable general_conditions may add a custom
        # category header whose text contains 'daune' (e.g. 'Daune caroserie').
        # It must NOT be swallowed by the boilerplate-caption skip.
        from foi_parcurs.services import pdf_service as ps

        fl = ps._damage_table('Daune caroserie\nZgarietura noua | 90 Eur\n*Preturile includ TVA')
        assert 'Daune caroserie' in _flowables_text(fl)      # header survives
        assert 'Zgarietura noua' in _flowables_text(fl)       # priced row too
        assert 'Preturile includ TVA' in _flowables_text(fl)  # note too

    def test_damage_table_renders_disclaimer_only_segment(self):
        # A marker-delimited segment with only a '*' disclaimer note and no
        # priced rows must still surface the note (not vanish).
        from foi_parcurs.services import pdf_service as ps

        fl = ps._damage_table('*Preturile afisate includ TVA')
        assert fl  # not dropped
        assert 'Preturile afisate includ TVA' in _flowables_text(fl)

    def test_damage_table_renders_header_plus_note_without_prices(self):
        from foi_parcurs.services import pdf_service as ps

        fl = ps._damage_table('Daune caroserie\n*nota disclaimer')
        text = _flowables_text(fl)
        assert 'Daune caroserie' in text
        assert 'nota disclaimer' in text

    def test_custom_damage_category_header_survives_in_pdf(self, monkeypatch, tmp_path):
        # End-to-end: a custom 'Daune caroserie' header inside the damage
        # segment reaches the rendered PDF text, and the disclaimer note is
        # not lost either.
        from foi_parcurs.repositories.contract_config_repository import ContractConfigRepository
        from foi_parcurs.services import pdf_service as ps

        custom_terms = (
            '1. Termeni custom.\n'
            '\n'
            '=== VALOAREA FACTURABILĂ A DAUNELOR ===\n'
            'VALOAREA FACTURABILA A DAUNELOR\n'
            'Cost Dauna Neasigurata*\n'
            '\n'
            'Daune caroserie\n'
            'Zgarietura noua | 90 Eur\n'
            'Interior\n'
            'Scaun fata | 240 Eur\n'
            '*Preturile afisate includ TVA custom.\n'
            '\n'
            'Text GDPR custom aici.\n'
        )
        cfg = _fake_service_cfg()
        cfg['general_conditions'] = custom_terms
        monkeypatch.setattr(
            ContractConfigRepository, 'get_active',
            lambda self, company_id, brand_name, document_type='service': cfg,
        )
        monkeypatch.setattr(ps, '_PDF_DIR', str(tmp_path))

        out_path = ps.generate_service_contract_pdf(_fake_service_contract(contract_id='FP-TEST-S7-CUSTOM'))
        text = _pdf_text(out_path)

        assert 'Daune caroserie' in text                # custom header preserved
        assert 'Zgarietura noua' in text                # priced row
        assert 'Interior' in text                       # second custom header
        assert 'Preturile afisate includ TVA custom' in text   # disclaimer note kept
        assert 'Text GDPR custom aici' in text          # GDPR tail after the table
