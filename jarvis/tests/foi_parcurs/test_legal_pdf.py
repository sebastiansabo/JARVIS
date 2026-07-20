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


def test_company_legal_splits_multiline_showroom():
    c = dict(_INTL, showroom_address='Str. Oradiei 1-3-5-7, Cluj-Napoca, 400220\nCalea Turzii 249, Cluj-Napoca, 400495')
    legal = ps._company_legal(c)
    assert legal['puncte'] == 'Str. Oradiei 1-3-5-7, Cluj-Napoca, 400220; Calea Turzii 249, Cluj-Napoca, 400495'


def test_prestator_intro_omits_missing_administrator():
    c = dict(_INTL, administrator='')
    intro = ps._build_prestator_intro(c, '0371536475')
    assert 'reprezentata de' not in intro


def test_dealer_constants_use_token_not_hardcoded_name():
    # Every dealer body mention must be tokenized; third-party entities stay.
    dealer_blocks = ps._TC_OBLIGATIONS + ps._TC_PARAGRAPHS
    joined = ' '.join(dealer_blocks)
    assert 'AUTOWORLD Plus' not in joined
    assert 'AUTOWORLD INTERNATIONAL S.R.L.' not in joined
    assert '{CO}' in joined


def test_terms_flowables_accepts_company_name():
    # Should not raise and should return a non-empty list of flowables.
    fl = ps._terms_flowables('Autoworld ONE S.R.L.')
    assert isinstance(fl, list) and len(fl) > 0


def test_terms_flowables_renders_company_gdpr_and_no_notice_page():
    fl = ps._terms_flowables('Autoworld ONE S.R.L.', '## Prelucrare\n\nText GDPR firma.')
    joined = ' '.join(getattr(p, 'text', '') for p in fl)
    assert 'NOTA DE INFORMARE' not in joined            # notice page removed
    assert 'PRELUCRAREA DATELOR CU CARACTER PERSONAL' in joined
    assert 'Text GDPR firma.' in joined                 # company text rendered
    assert 'CONDITII GENERALE TEST DRIVE' in joined     # T&C kept


def test_terms_flowables_omits_gdpr_section_when_empty():
    fl = ps._terms_flowables('Autoworld ONE S.R.L.', '')
    joined = ' '.join(getattr(p, 'text', '') for p in fl)
    assert 'PRELUCRAREA DATELOR CU CARACTER PERSONAL' not in joined
    assert 'NOTA DE INFORMARE' not in joined
    assert 'CONDITII GENERALE TEST DRIVE' in joined     # T&C still there


def test_parse_conditions_blocks():
    text = "## Termeni\n\nRand unu.\nRand doi.\n\n- alfa\n- beta\n\nUltim paragraf."
    blocks = ps._parse_conditions(text)
    assert blocks[0] == ('heading', 'Termeni')
    assert blocks[1] == ('paragraph', 'Rand unu. Rand doi.')
    assert blocks[2] == ('bullets', ['alfa', 'beta'])
    assert blocks[3] == ('paragraph', 'Ultim paragraf.')


def test_parse_conditions_empty():
    assert ps._parse_conditions('') == []
    assert ps._parse_conditions('   \n  ') == []


def test_general_conditions_flowables_empty_when_no_text():
    assert ps._general_conditions_flowables('', None) == []


def test_general_conditions_flowables_present():
    fl = ps._general_conditions_flowables('## T\n\ntext', '2026-07-20T09:00:00+00:00')
    assert fl  # non-empty list of flowables
