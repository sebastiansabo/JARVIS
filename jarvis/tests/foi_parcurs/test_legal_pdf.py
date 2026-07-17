import os
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from foi_parcurs.services import pdf_service as ps

_INTL = {
    'company': 'Autoworld INTERNATIONAL S.R.L.',
    'street': 'Calea Floresti 145', 'city': 'Cluj-Napoca', 'county': 'Cluj',
    'showroom_address': 'Calea Floresti 145, Cluj-Napoca, 400524',
    'reg_no': 'J2024002657125', 'vat': 'RO 50186890',
    'iban': 'RO88 BACX 0000 0027 0096 8001', 'bank': 'Unicredit Bank',
    'administrator': 'Ioan Mezei',
}


def test_co_replaces_token():
    assert ps._co('anunta {CO} imediat', 'Autoworld ONE S.R.L.') == 'anunta Autoworld ONE S.R.L. imediat'


def test_company_legal_strips_ro_prefix_from_cui():
    legal = ps._company_legal(_INTL)
    assert legal['cui'] == '50186890'
    assert legal['name'] == 'Autoworld INTERNATIONAL S.R.L.'
    assert 'Calea Floresti 145' in legal['sediu']


def test_prestator_intro_contains_identity_and_phone():
    intro = ps._build_prestator_intro(_INTL, '0371536475')
    assert 'Autoworld INTERNATIONAL S.R.L.' in intro
    assert 'CUI 50186890' in intro
    assert 'J2024002657125' in intro
    assert 'RO88 BACX 0000 0027 0096 8001' in intro
    assert '0371536475' in intro
    assert 'Ioan Mezei' in intro
    assert intro.rstrip().endswith('"Prestator", si:')


def test_prestator_intro_omits_missing_phone_label():
    intro = ps._build_prestator_intro(_INTL, '')
    assert 'telefon' not in intro.lower()
