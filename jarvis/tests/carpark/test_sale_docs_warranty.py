"""Tests for carpark.services.sale_docs.warranty.

Task 4 of the CarPark "Documente vanzare" plan: the warranty.html template
reproduces docs/superpowers/specs/assets/2026-10-21-sale-docs/
certificat-garantie.txt verbatim (field block + full warranty-terms legal
text), with `{{tokens}}` only at the 8 named data blanks.

All tests assert on the FILLED HTML STRING that `_fill_warranty_html`
builds (pure string substitution, no browser) — per the brief, no separate
Chromium smoke test is needed here since `html_to_pdf_bytes` is already
smoke-tested in Task 3's test suite.
"""
from carpark.services.sale_docs import warranty as warranty_module
from carpark.services.sale_docs.warranty import _fill_warranty_html, render_warranty_pdf, validate_warranty_context


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


def _seller(**overrides):
    base = {
        'name': 'Autoworld Premium SRL',
        'cui': '50188939',
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
        'delivery_date': '2026-11-05',
        'autonomy': None,
    }
    base.update(overrides)
    return base


def test_warranty_fills_buyer_vin_model():
    context = _context()
    html_out = _fill_warranty_html(context)

    assert 'Ion Popescu' in html_out  # buyer name (utilizator)
    assert 'WAUZZZ8K9DA012345' in html_out  # VIN
    assert 'A4' in html_out  # model


def test_warranty_keeps_diacritics():
    context = _context(
        utilizator=_party(name='Ion Măriuță', city='Cluj-Napoca'),
    )
    html_out = _fill_warranty_html(context)

    assert 'Ion Măriuță' in html_out
    assert 'ă' in html_out
    assert 'ț' in html_out
    # No ASCII-fold: the folded form must NOT be substituted for the real one.
    assert 'Ion Mariuta' not in html_out
    # The legal boilerplate itself is full of diacritics (ș/ț/ă) — spot-check
    # a representative word from the warranty-terms body.
    assert 'garanție' in html_out


def test_warranty_escapes_user_field():
    context = _context(utilizator=_party(name='<script>x</script>'))
    html_out = _fill_warranty_html(context)

    assert '<script>x</script>' not in html_out
    assert '&lt;script&gt;x&lt;/script&gt;' in html_out


def test_warranty_leasing_sale_uses_utilizator_not_leasing_company():
    # In a leasing sale, the warranty's "Cumparator" field must show the
    # actual buyer/driver (utilizator), not the financing leasing company
    # (cumparator) — the person who'd actually file a warranty claim.
    context = _context(
        is_leasing=True,
        cumparator=_party(name='BRD Leasing IFN SA', address='Bd. Ion Mihalache 1-7'),
        utilizator=_party(name='Ion Popescu', address='Str. Lalelelor 1'),
    )
    html_out = _fill_warranty_html(context)

    assert 'Ion Popescu' in html_out
    assert 'BRD Leasing IFN SA' not in html_out


def test_warranty_seller_fields_fill():
    context = _context()
    html_out = _fill_warranty_html(context)

    assert 'Autoworld Premium SRL' in html_out
    assert 'Calea Floresti 145' in html_out


def test_warranty_mileage_and_delivery_date_fill():
    context = _context(mileage_km=45000, delivery_date='2026-11-05')
    html_out = _fill_warranty_html(context)

    assert '45000' in html_out
    assert '2026-11-05' in html_out


def test_render_warranty_pdf_passes_filled_html_and_returns_bytes(monkeypatch):
    # render_warranty_pdf must (a) fill the template and pass the FILLED html
    # (not the raw context) into the shared html_to_pdf_bytes helper, and
    # (b) return exactly what that helper returns. Monkeypatch the helper to a
    # fake that captures its arg and returns a sentinel — this genuinely
    # exercises render_warranty_pdf without needing Chromium, and fails if it
    # calls the wrong helper, passes the wrong arg, or forgets `return`.
    context = _context()
    captured = {}

    def fake_html_to_pdf_bytes(html):
        captured['html'] = html
        return b'%PDF-FAKE'

    monkeypatch.setattr(warranty_module, 'html_to_pdf_bytes', fake_html_to_pdf_bytes)

    result = render_warranty_pdf(context)

    # (a) the html handed to the renderer is the fully-filled template, not raw context.
    assert captured['html'] == _fill_warranty_html(context)
    # (b) render_warranty_pdf returns the helper's bytes verbatim (the `return` is present).
    assert result == b'%PDF-FAKE'


def test_validate_warranty_flags_missing_buyer_and_vin():
    # Important #3 (spec A4): never emit a warranty certificate with no
    # buyer name or no VIN silently missing.
    context = _context(utilizator=_party(name=None))
    errors = validate_warranty_context(context)
    assert any('cump' in e.lower() or 'utiliz' in e.lower() for e in errors)

    context_no_vin = _context(vin=None)
    errors_no_vin = validate_warranty_context(context_no_vin)
    assert any('vin' in e.lower() or 'șasiu' in e.lower() or 'sasiu' in e.lower() for e in errors_no_vin)

    # A complete context has no errors.
    assert validate_warranty_context(_context()) == []
