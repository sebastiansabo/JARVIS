"""Tests for carpark.services.sale_docs.contract and .html_pdf.

Task 3 of the CarPark "Documente vanzare" plan: the contract.html template
reproduces docs/superpowers/specs/assets/2026-10-21-sale-docs/
contract-vanzare-leasing.txt verbatim (legal sections A-L + Anexa 1/2), with
`{{tokens}}` only where the source has `___`/`[●]` blanks.

Most tests assert on the FILLED HTML STRING that `_fill_contract_html`
builds (pure string substitution, no browser) — the one exception is
`test_html_to_pdf_bytes_smoke`, which drives the real Playwright/Chromium
path and is skipped when Chromium isn't installed in the test environment.
"""
import pytest

from carpark.services.sale_docs.contract import (
    _fill_contract_html,
    render_contract_pdf,
    validate_contract_context,
)
from carpark.services.sale_docs.html_pdf import html_to_pdf_bytes


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
    except Exception:
        return False
    return True


CHROMIUM_AVAILABLE = _chromium_available()


def _party(**overrides):
    base = {
        'name': 'Ion Popescu',
        'cui': 'RO99887766',
        'address': 'Str. Lalelelor 1',
        'city': 'Cluj-Napoca',
        'county': 'Cluj',
        'phone': '0722111222',
        'email': 'ion@example.com',
    }
    base.update(overrides)
    return base


def _leasing_party(**overrides):
    base = {
        'name': 'BRD Leasing IFN SA',
        'cui': 'RO11223344',
        'reg_no': 'J40/1/2001',
        'address': 'Bd. Ion Mihalache 1-7',
        'city': 'Bucuresti',
        'county': 'Sector 1',
        'phone': '0211234567',
        'email': 'office@brdleasing.ro',
        'iban': 'RO11BRDE1234567890',
        'legal_rep': 'Maria Ionescu',
        'legal_rep_role': 'Director',
    }
    base.update(overrides)
    return base


def _seller(**overrides):
    base = {
        'name': 'Autoworld Premium SRL',
        'cui': '50188939',
        'vat': 'RO50188939',
        'reg_no': 'J2024002670120',
        'address': 'Calea Floresti 145',
        'city': 'Cluj-Napoca',
        'county': 'Cluj',
        'iban': 'RO24BACX0000002700266000',
        'bank': 'Unicredit',
        'swift': 'BACXROBU',
        'administrator': 'Mezei Ioan',
        'showroom_address': 'Calea Turzii 249',
        'phone': '0264-502600',
        'email': 'aap@autoworld.ro',
    }
    base.update(overrides)
    return base


def _context(**overrides):
    base = {
        'seller': _seller(),
        'cumparator': _party(),
        'utilizator': _party(),
        'is_leasing': False,
        'brand': 'Audi',
        'model': 'A4',
        'variant': '2.0 TDI S-Line',
        'vin': 'WAUZZZ8K9DA012345',
        'registration_number': None,
        'mileage_km': 45000,
        'year': 2021,
        'color': 'Negru',
        'price': 24990,
        'currency': 'EUR',
        'fuel': 'Diesel',
        'consultant_name': None,
        'contract_number': 'CT-2026-001',
        'contract_date': '2026-10-21',
        'proforma_number': None,
        'proforma_date': None,
        'delivery_term_days': 5,
        'delivery_place': None,
        'delivery_date': None,
        'autonomy': None,
    }
    base.update(overrides)
    return base


def test_contract_fills_tokens():
    context = _context()
    html_out = _fill_contract_html(context)

    assert 'WAUZZZ8K9DA012345' in html_out  # VIN
    assert 'Ion Popescu' in html_out  # buyer name (utilizator == cumparator, cash sale)
    assert '24990' in html_out  # price


def test_contract_keeps_diacritics():
    context = _context(
        utilizator=_party(name='Ion Măriuță', city='Cluj-Napoca', county='Argeș'),
        cumparator=_party(name='Ion Măriuță', city='Cluj-Napoca', county='Argeș'),
    )
    html_out = _fill_contract_html(context)

    assert 'Ion Măriuță' in html_out
    assert 'ă' in html_out
    assert 'ț' in html_out
    assert 'Argeș' in html_out
    assert 'ș' in html_out
    # No ASCII-fold: the folded forms must NOT be substituted for the real ones.
    assert 'Ion Mariuta' not in html_out


def test_contract_escapes_user_field():
    context = _context(
        utilizator=_party(name='<script>x</script>'),
        cumparator=_party(name='<script>x</script>'),
    )
    html_out = _fill_contract_html(context)

    assert '<script>x</script>' not in html_out
    assert '&lt;script&gt;x&lt;/script&gt;' in html_out


def test_anexa2_handover_uses_delivery_date_not_contract_date():
    # Distinct values so we can tell which token fills the Anexa 2
    # "Incheiat la data de ..." (predare-primire) slot.
    context = _context(contract_date='2026-10-21', delivery_date='2026-11-05')
    html_out = _fill_contract_html(context)

    assert 'Incheiat la data de 2026-11-05' in html_out  # handover date
    assert 'Incheiat la data de 2026-10-21' not in html_out  # NOT the signing date
    # The signing date still fills the signing line elsewhere.
    assert 'semnat astazi, 2026-10-21' in html_out


def test_cash_sale_cumparator_rep_falls_back_to_buyer_name():
    # Cash sale: cumparator == utilizator == the individual buyer, who has
    # no distinct legal_rep. The Cumparator paragraph/signature must show
    # the buyer's own name, not a blank "reprezentata legal de , ...".
    buyer = _party(name='Ion Popescu')
    context = _context(is_leasing=False, cumparator=buyer, utilizator=buyer)
    html_out = _fill_contract_html(context)

    assert 'reprezentata legal de Ion Popescu' in html_out
    assert 'reprezentata legal de , in calitate de' not in html_out


def test_leasing_cumparator_rep_prefers_legal_rep():
    # When a real leasing-company legal rep exists, it wins over the name fallback.
    context = _context(is_leasing=True, cumparator=_leasing_party(name='BRD Leasing IFN SA', legal_rep='Maria Ionescu'))
    html_out = _fill_contract_html(context)

    assert 'reprezentata legal de Maria Ionescu' in html_out


def test_consultant_name_fills_when_provided():
    context = _context(consultant_name='Andrei Vasilescu')
    html_out = _fill_contract_html(context)

    # Appears in all three "prin ... in calitatate de consultant vanzari" slots.
    assert html_out.count('prin Andrei Vasilescu in calitatate de consultant vanzari') == 3


def test_registration_number_fills():
    context = _context(registration_number='CJ 01 ABC')
    html_out = _fill_contract_html(context)

    assert 'Nr inmatriculare CJ 01 ABC ,' in html_out


def test_validate_flags_missing_contract_number():
    context = _context(contract_number=None)
    errors = validate_contract_context(context)

    assert any('contract' in e.lower() or 'numărul' in e.lower() or 'numarul' in e.lower() for e in errors)


def test_validate_leasing_requires_leasing_company():
    context = _context(is_leasing=True, cumparator=_party(name=None))
    errors = validate_contract_context(context)

    assert any('leasing' in e.lower() for e in errors)

    # Supplying the leasing company clears that specific error.
    context_ok = _context(is_leasing=True, cumparator=_leasing_party())
    errors_ok = validate_contract_context(context_ok)
    assert not any('leasing' in e.lower() for e in errors_ok)


def test_validate_passes_for_complete_cash_context():
    context = _context()
    assert validate_contract_context(context) == []


def test_contract_seller_is_data_driven():
    # Critical #1 (spec G2/A2): the contract's Vanzator party-identity +
    # payment account must come from context['seller'], not be hardcoded to
    # Autoworld Premium's details — mirrors warranty.py/proforma.py, which
    # already derive the seller this way.
    other_seller = _seller(
        name='MG MOTOR CLUJ SRL',
        vat='RO12345678',
        reg_no='J12/999/2020',
        iban='RO99MGMG0000000000000001',
        bank='Banca Transilvania',
    )
    context = _context(seller=other_seller)
    html_out = _fill_contract_html(context)

    assert 'MG MOTOR CLUJ SRL' in html_out
    assert 'RO99MGMG0000000000000001' in html_out
    # No leak of the old hardcoded Autoworld Premium seller identity (the
    # Vanzator paragraphs/signature cells) or its IBAN. NOTE: the untouched
    # GDPR clause (section K, left verbatim per the brief) legitimately
    # still contains the literal "AUTOWORLD PREMIUM" substring on its own —
    # so this checks the specific signature-row/IBAN strings that used to
    # be hardcoded in the now-tokenized party-identity sections, not every
    # occurrence of the company name in the document.
    assert 'SC AUTOWORLD PREMIUM SRL' not in html_out
    assert 'RO24BACX0000002700266000' not in html_out


def test_contract_price_uses_context_currency():
    # Important #2: the price-amount labels must show the context's
    # currency, not a hardcoded 'Euro'/'EUR' — a RON-priced sale must not
    # render "<price> Euro".
    context = _context(price=120000, currency='RON')
    html_out = _fill_contract_html(context)

    assert '120000 RON' in html_out
    assert '120000 Euro' not in html_out


@pytest.mark.skipif(not CHROMIUM_AVAILABLE, reason='Playwright Chromium not available in this environment')
def test_html_to_pdf_bytes_smoke():
    pdf_bytes = html_to_pdf_bytes('<p>ăîșțâ</p>')
    assert pdf_bytes.startswith(b'%PDF')


@pytest.mark.skipif(not CHROMIUM_AVAILABLE, reason='Playwright Chromium not available in this environment')
def test_render_contract_pdf_smoke():
    context = _context()
    pdf_bytes = render_contract_pdf(context)
    assert pdf_bytes.startswith(b'%PDF')
