"""Warranty certificate (CERTIFICAT DE GARANTIE COMERCIALA) renderer — Task 4
of the CarPark "Documente vanzare" plan.

`templates/warranty.html` reproduces
`docs/superpowers/specs/assets/2026-10-21-sale-docs/certificat-garantie.txt`
verbatim (the short buyer/vehicle field block plus the full warranty-terms
legal text) with `{{tokens}}` placed only at the 8 data blanks named in the
brief: nume cumparator, adresa (cumparator), model, vanzator, adresa
(vanzator), VIN, rulaj la livrare, data livrare. The warranty-period blanks
in the legal text itself (`[…..] luni`, `[.................] km`) and the
maintenance-works blank inside the exclusions list have no corresponding
field anywhere in the Task 2 context — they are reproduced AS-IS (literal
bracket placeholders), not converted to `{{tokens}}`, same "only fill what
has a real data source" judgment contract.py used for its unbacked blanks.

Two Word-field-code extraction artifacts from the source .txt were cleaned
when the template was authored (not reproduced literally, since they were
never actually *visible* text in the original document, just a text-layer
artifact of a Word hyperlink field): `HYPERLINK "mailto:aap@autoworld.ro"`
immediately followed by its own visible-text duplicate `aap@autoworld.ro`
collapses to just `aap@autoworld.ro`; the trailing `PAGE  1` / `PAGE   \\*
MERGEFORMAT2` page-number field codes were dropped (pagination is the
renderer's job, not the source text's). See task-4-report.md for the full
verbatim-verification (word-multiset diff: 0 source words missing from the
template).

Token-filling pipeline (`_fill_warranty_html`) is the same
escape+substitute shape as `contract.py`'s `_fill_contract_html`: load the
template, flatten the context dict (Task 2's `build_sale_context` shape)
into a flat token->value dict (`_token_map`), then regex-substitute every
`{{token}}` with `html.escape(str(value))` — ALL values are escaped per the
design's A5 anti-goal, and diacritics are never touched (A1): this is plain
Unicode string handling, no normalization/ASCII-folding step anywhere here.

Buyer identity (design D4, same as contract.py): the warranty's "Nume
cumparator"/"Adresa" fields map to the Task 2 context's `utilizator` party
(the actual person taking delivery / who would file a warranty claim), NOT
`cumparator` (which is the leasing company in a leasing sale) — in a cash
sale `utilizator == cumparator` anyway, so this only matters for leasing
sales. This mirrors the brief's explicit framing ("utilizator/buyer dict").
"""
import html
import re
from pathlib import Path

from carpark.services.sale_docs.html_pdf import html_to_pdf_bytes

TEMPLATE_PATH = Path(__file__).parent / 'templates' / 'warranty.html'

_TOKEN_RE = re.compile(r'\{\{(\w+)\}\}')


def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding='utf-8')


def _token_map(context: dict) -> dict:
    """Flatten the Task 2 context dict into the flat token-name -> value
    dict the template's `{{token}}` placeholders key into. Missing/unknown
    keys are simply absent — the substitution step in `_fill_warranty_html`
    defaults any absent key to ''.
    """
    context = context or {}
    seller = context.get('seller') or {}
    utilizator = context.get('utilizator') or {}

    return {
        'buyer_name': utilizator.get('name'),
        'buyer_address': utilizator.get('address'),
        'model': context.get('model'),
        'seller_name': seller.get('name'),
        'seller_address': seller.get('address'),
        'vin': context.get('vin'),
        'mileage_km': context.get('mileage_km'),
        'delivery_date': context.get('delivery_date'),
    }


def _fill_warranty_html(context: dict) -> str:
    """Load `warranty.html` and substitute every `{{token}}` with the
    HTML-escaped string value of the matching context field (or '' when the
    token has no backing data). Pure string work — no browser involved, so
    this is what the token/diacritics/escaping tests assert on directly.
    """
    template = _load_template()
    tokens = _token_map(context)

    def _sub(match: 're.Match') -> str:
        value = tokens.get(match.group(1), '')
        if value is None:
            value = ''
        return html.escape(str(value))

    return _TOKEN_RE.sub(_sub, template)


def render_warranty_pdf(context: dict) -> bytes:
    """Fill the warranty template from `context` (Task 2's
    `build_sale_context` output) and render it to PDF bytes via the shared
    `html_to_pdf_bytes` Playwright helper."""
    filled_html = _fill_warranty_html(context)
    return html_to_pdf_bytes(filled_html)


def validate_warranty_context(context: dict) -> list:
    """Return a list of Romanian missing-mandatory-field messages; an empty
    list means `context` has everything required to render a warranty
    certificate.

    Mirrors `contract.py::validate_contract_context` (spec A4 — never emit a
    document with required data silently missing). Mandatory: the buyer's
    name (`context['utilizator']` — see module docstring: the warranty's
    buyer is the actual person taking delivery, not `cumparator`) and the
    vehicle's VIN.
    """
    context = context or {}
    errors = []

    utilizator = context.get('utilizator') or {}
    if not utilizator.get('name'):
        errors.append('Datele cumpărătorului/utilizatorului (nume) sunt obligatorii.')

    if not context.get('vin'):
        errors.append('Seria de șasiu (VIN) este obligatorie.')

    return errors
