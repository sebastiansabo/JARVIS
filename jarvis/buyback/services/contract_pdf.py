"""Diacritics-safe reportlab primitives for the BuyBack contract PDF renderer.

Every other reportlab PDF in this repo (see offer_pdf.py::_ascii) strips
Romanian diacritics (ă â î ș ț) to ASCII because reportlab's base-14 fonts
(Helvetica/Times) have no glyphs for them. A legal purchase contract must
render the real characters, so this module registers a bundled Unicode
TrueType font (DejaVu Sans) and exposes a text-escaping helper that keeps
diacritics intact instead of folding them.

This module is intentionally primitives-only: `_register_fonts()`, `_ptext()`
and the FONT_REGULAR/FONT_BOLD constants. The contract-context builder and the
actual PDF renderer are added in later tasks of the P3b contract-renderer
feature, on top of these primitives.
"""
import html
import logging
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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
