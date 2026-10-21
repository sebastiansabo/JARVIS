"""Diacritics-safe reportlab primitives for the BuyBack contract PDF renderer.

Every other reportlab PDF in this repo (see offer_pdf.py::_ascii) strips
Romanian diacritics (ă â î ș ț) to ASCII because reportlab's base-14 fonts
(Helvetica/Times) have no glyphs for them. A legal purchase contract must
render the real characters, so this module registers a bundled Unicode
TrueType font (DejaVu Sans) and exposes a text-escaping helper that keeps
diacritics intact instead of folding them.

Also hosts `build_contract_context()` (Task 3): a pure record/company/offer/
consignment -> {token: value} dict builder for `contract_template
.render_contract_template()`. The actual PDF renderer (Task 4) is added on
top of these, in a later task of the P3b contract-renderer feature.
"""
import html
import logging
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from buyback.services.contract_template import PLACEHOLDERS

logger = logging.getLogger('jarvis.buyback.contract_pdf')

FONT_REGULAR = 'DejaVuSans'
FONT_BOLD = 'DejaVuSans-Bold'

# Candidate (regular, bold) TTF path pairs, tried in order. The bundled repo
# copy comes first so rendering has no system dependency on mac dev or in the
# DO container; the system DejaVu paths (mirroring
# jarvis/accounting/bilant/pdf_handler.py) are a fallback for environments
# that ship the font at the OS level; reportlab's own bundled Vera.ttf is the
# last resort so a render never hard-fails even if both diacritic fonts are
# somehow missing (Vera has no Romanian glyphs, but it is a real embeddable
# Unicode-capable TTF, registered under the DejaVu names so callers are
# unaffected).
_BUNDLED_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')
_REPORTLAB_FONTS_DIR = os.path.join(os.path.dirname(pdfmetrics.__file__), '..', 'fonts')

_FONT_CANDIDATES = [
    (
        os.path.join(_BUNDLED_DIR, 'DejaVuSans.ttf'),
        os.path.join(_BUNDLED_DIR, 'DejaVuSans-Bold.ttf'),
    ),
    (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ),
    (
        os.path.join(_REPORTLAB_FONTS_DIR, 'Vera.ttf'),
        os.path.join(_REPORTLAB_FONTS_DIR, 'VeraBd.ttf'),
    ),
]

_fonts_registered = False
_registered_names = (FONT_REGULAR, FONT_BOLD)


def _register_fonts():
    """Register the Unicode TTF pair reportlab will render contract text
    with, trying the bundled repo font, then system DejaVu, then reportlab's
    bundled Vera.ttf as a last resort. Idempotent — safe to call on every
    render. Always registers under the DejaVuSans/DejaVuSans-Bold names
    (even for the Vera fallback) so callers never need to branch on which
    font actually ended up loaded.

    Returns the (regular, bold) font names actually registered.
    """
    global _fonts_registered, _registered_names
    if _fonts_registered:
        return _registered_names

    for regular_path, bold_path in _FONT_CANDIDATES:
        if not (os.path.exists(regular_path) and os.path.exists(bold_path)):
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular_path))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, bold_path))
        except Exception:
            logger.warning('contract_pdf: failed to register font pair %s / %s', regular_path, bold_path, exc_info=True)
            continue
        logger.debug('contract_pdf: registered fonts from %s / %s', regular_path, bold_path)
        _fonts_registered = True
        _registered_names = (FONT_REGULAR, FONT_BOLD)
        return _registered_names

    logger.warning('contract_pdf: no Unicode TTF found in any candidate path, diacritics will not render')
    return _registered_names


def _ptext(value) -> str:
    """HTML-escaped text safe to put inside a reportlab Paragraph.

    Escaping is REQUIRED for user-controlled fields: reportlab parses a mini
    markup, so a bare '<'/'&' crashes the parser and an <img src=...> tag
    would trigger a fetch (SSRF). Unlike offer_pdf.py::_ptext, this does NOT
    ASCII-fold diacritics — the registered DejaVu font can render them, and a
    legal contract must show real Romanian characters.
    """
    text = '' if value is None else str(value)
    return html.escape(text)


# ═══════════════════════════════════════════════════════════════════════
# Context builder — record/company/offer/consignment -> {token: value} dict
# ═══════════════════════════════════════════════════════════════════════
#
# Pure function, no DB/IO: callers (the route/service layer, Task 4+) load
# the record/company/offer/consignment dicts first. Every key in
# contract_template.PLACEHOLDERS is guaranteed present in the returned dict
# (defaulted to '') so render_contract_template() never sees a missing key
# and a sparse record/company can never crash contract generation.

# Short Romanian TVA note shown in the price clause, keyed by the
# buyback_records.vat_status value (see buyback/routes/lookups.py
# _STATIC_VAT_STATUSES: 'with_vat' / 'no_vat'). Any other/missing value
# renders empty rather than guessing.
_VAT_NOTES = {
    'with_vat': 'TVA inclus',
    'no_vat': 'neplatitor de TVA',
}

# consignment_terms JSONB keys that map 1:1 onto a same-named PLACEHOLDERS
# token — copied verbatim when present (see test_consignment_terms_tokens).
_CONSIGNMENT_DIRECT_FIELDS = ('owner_price', 'promo_price', 'commission', 'monthly_fee')

# 'min_price' has no single canonical source key across the consignment
# flows seen in this codebase: buyback/routes/custody.py::
# validate_custody_agreement stores it as 'min_sale_price' on the real
# custody-agreement JSONB; the brief's own token-naming convention points at
# 'floor'; a future caller may just pass 'min_price' directly. Tried in this
# order, first match wins.
_MIN_PRICE_KEYS = ('floor', 'min_sale_price', 'min_price')


def _s(value) -> str:
    """None -> '', everything else -> str(value). Never raises."""
    return '' if value is None else str(value)


def _company_address(company: dict) -> str:
    """Non-empty of street/city/county/postal_code joined ', '; falls back
    to showroom_address when none of those four are set."""
    parts = (company.get('street'), company.get('city'), company.get('county'), company.get('postal_code'))
    composed = ', '.join(p for p in parts if p)
    return composed if composed else _s(company.get('showroom_address'))


def _seller_ci(record: dict) -> str:
    """'seria {serie} nr. {number}' only when BOTH halves are present."""
    serie = record.get('seller_ci_serie')
    number = record.get('seller_ci_number')
    if serie and number:
        return f'seria {serie} nr. {number}'
    return ''


def _price_eur(offer: dict) -> str:
    """offer['amount_eur'] (a Decimal) as a plain thousands-grouped string
    when an accepted offer is supplied, else ''. price_ron/price_words are
    deferred for P3b (BNR-at-signing + RO number-to-words)."""
    amount = offer.get('amount_eur')
    if amount is None:
        return ''
    return '{:,.0f}'.format(amount)


def build_contract_context(record, company, *, offer=None, consignment=None,
                            contract_number='', contract_date='') -> dict:
    """Build the {token: value} dict consumed by
    contract_template.render_contract_template() for one contract PDF.

    `record` is a buyback_records row (serialized), `company` a companies
    row (CompanyRepository().get), `offer` the accepted-offer row (if any),
    `consignment` the consignment agreement carrying `consignment_terms`
    JSONB (if any). All four, plus every field read off them, are optional —
    a sparse/empty record or company must render all-empty tokens, not
    raise.
    """
    record = record or {}
    company = company or {}
    offer = offer or {}
    consignment = consignment or {}
    terms = consignment.get('consignment_terms') or {}

    ctx = {token: '' for token in PLACEHOLDERS}

    ctx['contract_number'] = _s(contract_number)
    ctx['contract_date'] = _s(contract_date)

    ctx['company_name'] = _s(company.get('company'))
    ctx['company_vat'] = _s(company.get('vat'))
    ctx['company_reg_no'] = _s(company.get('reg_no'))
    ctx['company_iban'] = _s(company.get('iban'))
    ctx['company_bank'] = _s(company.get('bank'))
    ctx['company_administrator'] = _s(company.get('administrator'))
    ctx['company_address'] = _company_address(company)

    ctx['advisor_name'] = _s(record.get('advisor_name'))

    ctx['seller_name'] = _s(record.get('seller_name'))
    ctx['seller_cui'] = _s(record.get('seller_cui'))
    ctx['seller_cnp'] = _s(record.get('seller_cnp'))
    ctx['seller_address'] = _s(record.get('seller_address'))
    ctx['seller_reg_no'] = _s(record.get('seller_reg_no'))
    ctx['seller_legal_rep'] = _s(record.get('seller_legal_rep'))
    ctx['seller_ci'] = _seller_ci(record)

    ctx['brand'] = _s(record.get('brand'))
    ctx['model'] = _s(record.get('model'))
    ctx['vin'] = _s(record.get('vin'))
    mileage = record.get('mileage_km')
    ctx['mileage'] = mileage if mileage is not None else ''
    engine_capacity = record.get('engine_capacity_cm3')
    ctx['engine_capacity'] = engine_capacity if engine_capacity is not None else ''
    ctx['first_registration'] = _s(record.get('first_registration_date'))
    ctx['manufacture_date'] = _s(record.get('manufacture_date'))

    # engine_no / power_cp / civ_no: no source column on buyback_records.
    # Left at their '' default above — documented gap, not a bug (brief
    # Task 3, "no source column exists").

    ctx['price_eur'] = _price_eur(offer)
    # price_ron / price_words: deferred for P3b — BNR-at-signing conversion
    # and RO number-to-words are not implemented yet; left '' (clause text
    # already states "la cursul BNR+1% la data semnarii"). Flagged in the
    # handoff for user confirmation of legal need.

    ctx['vat_note'] = _VAT_NOTES.get(record.get('vat_status'), '')

    for field in _CONSIGNMENT_DIRECT_FIELDS:
        value = terms.get(field)
        if value is not None:
            ctx[field] = value

    for key in _MIN_PRICE_KEYS:
        value = terms.get(key)
        if value is not None:
            ctx['min_price'] = value
            break

    return ctx
