"""The Prestator paragraph is shared by the legal test-drive contract and the
monthly Foaie de Parcurs. On the contract it must keep the party designation
(«reprezentată de … denumită în continuare "Prestator", și:» — the Beneficiar
party follows). On the standalone foaie there is no second party, so that
trailing clause dangles and is dropped.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.services.pdf_service import _build_prestator_intro

COMPANY = {
    'company': 'Autoworld INTERNATIONAL S.R.L.',
    'city': 'Cluj-Napoca', 'street': 'Calea Floresti 145',
    'vat': 'RO50186890', 'reg_no': 'J2024002657125',
    'administrator': 'Ioan Mezei',
}


def test_contract_intro_keeps_party_designation():
    txt = _build_prestator_intro(COMPANY, '0264207400')
    assert 'reprezentata de Ioan Mezei, administrator' in txt
    assert txt.endswith('denumita in continuare "Prestator", si:')


def test_standalone_intro_drops_party_designation():
    txt = _build_prestator_intro(COMPANY, '0264207400', standalone=True)
    assert 'denumita in continuare' not in txt
    assert 'reprezentata de' not in txt
    assert 'Prestator' not in txt
    # Still identifies the company + ends as a clean sentence.
    assert txt.startswith('S.C. Autoworld INTERNATIONAL S.R.L.')
    assert txt.rstrip().endswith('.')
