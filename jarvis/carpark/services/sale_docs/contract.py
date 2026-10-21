"""Contract (CONTRACT DE VANZARE-CUMPARARE) renderer — Task 3 of the CarPark
"Documente vanzare" plan.

`templates/contract.html` reproduces
`docs/superpowers/specs/assets/2026-10-21-sale-docs/contract-vanzare-leasing.txt`
verbatim (legal sections A-L plus Anexa 1 "Specificatie Autoturism" and
Anexa 2 "Proces Verbal Predare Primire", all three bundled in the one source
file) with `{{tokens}}` placed only where that source has a `___` or `[●]`
blank (plus a handful of colon-terminated vehicle-spec fields in Anexa 1 —
`MODEL :`, `SERIE SASIU :`, `AN FABRICATIE :` — which have no underscore/
`[●]` marker in the extracted text but are unambiguously fill-in-the-blank
vehicle fields; see task-3-report.md for the full list of judgment calls).

Token-filling pipeline (`_fill_contract_html`): load the template, flatten
the context dict (Task 2's `build_sale_context` shape) into a single
token -> value dict (`_token_map`), then regex-substitute every
`{{token}}` with `html.escape(str(value))` — ALL values are escaped,
including ones that are "obviously safe" (seller fields), per the design's
anti-goal A5 (no unescaped user/free-text value ever reaches the HTML).
Diacritics are never touched (A1) — this is plain Unicode string handling,
there is no normalization/ASCII-folding step anywhere in this module.

Tokens with no backing context field (e.g. the sales-consultant name blank
in the Vanzator paragraph, the "nr." half of "str. [●] nr. [●]", the engine
serial number) resolve to '' via `.get(key, '')` in the substitution — left
visually blank in the rendered document rather than leaking a literal
`{{...}}` placeholder. Nothing is mandatory there; `validate_contract_context`
below enforces only the fields the business actually requires.
"""
import html
import re
from pathlib import Path

from carpark.services.sale_docs.html_pdf import html_to_pdf_bytes

TEMPLATE_PATH = Path(__file__).parent / 'templates' / 'contract.html'

_TOKEN_RE = re.compile(r'\{\{(\w+)\}\}')


def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding='utf-8')


def _format_price(price) -> str:
    """Render a numeric price as a plain string — '45000' for a whole
    number, '45000.50' otherwise. No thousands grouping: the source legal
    text has no locale-specific formatting convention to match, and
    inventing one (comma vs. dot grouping) would be guessing at a detail
    the brief doesn't specify.
    """
    if price is None or price == '':
        return ''
    try:
        f = float(price)
    except (TypeError, ValueError):
        return str(price)
    if f == int(f):
        return str(int(f))
    return f'{f:.2f}'


def _join_spec(*parts) -> str:
    """'Audi / A4 / 2.0 TDI S-Line' — skips missing parts rather than
    emitting a lone ' / ' for a blank brand/model/variant."""
    return ' / '.join(str(p) for p in parts if p not in (None, ''))


def _token_map(context: dict) -> dict:
    """Flatten the Task 2 context dict (seller/cumparator/utilizator party
    dicts + top-level vehicle/form tokens) into the single flat
    token-name -> value dict the template's `{{token}}` placeholders key
    into. Missing/unknown keys are simply absent here — the substitution
    step in `_fill_contract_html` defaults any absent key to ''.
    """
    context = context or {}
    seller = context.get('seller') or {}
    cumparator = context.get('cumparator') or {}
    utilizator = context.get('utilizator') or {}

    brand = context.get('brand')
    model = context.get('model')
    variant = context.get('variant')

    return {
        'contract_number': context.get('contract_number'),
        'contract_date': context.get('contract_date'),
        # Anexa 2 "Incheiat la data de ..." is the handover (predare-primire)
        # date, which routinely differs from the signing date — use the
        # dedicated delivery_date token, not contract_date.
        'delivery_date': context.get('delivery_date'),
        'delivery_term_days': context.get('delivery_term_days'),
        'autonomy': context.get('autonomy'),
        'brand': brand,
        'model': model,
        'variant': variant,
        'vin': context.get('vin'),
        'year': context.get('year'),
        'color': context.get('color'),
        'mileage_km': context.get('mileage_km'),
        'price': _format_price(context.get('price')),
        'vehicle_full_spec': _join_spec(brand, model, variant),
        'quantity': '1',  # the source text itself says "unul (bucata)" — always one vehicle.
        'currency': context.get('currency'),

        # Vanzator (seller) — data-driven from context['seller']
        # (context.py's build_seller), same convention warranty.py/
        # proforma.py already use (spec G2/A2) — NOT fixed boilerplate. The
        # one blank with no `seller` counterpart is the sales-consultant
        # name (design D3), threaded through the Task 2 context from the
        # form (salesperson resolved upstream).
        'consultant_name': context.get('consultant_name'),
        'seller_name': seller.get('name'),
        'seller_address': seller.get('address'),
        'seller_city': seller.get('city'),
        'seller_county': seller.get('county'),
        'seller_reg_no': seller.get('reg_no'),
        'seller_vat': seller.get('vat'),
        'seller_phone': seller.get('phone'),
        'seller_email': seller.get('email'),
        'seller_showroom_address': seller.get('showroom_address'),
        'seller_iban': seller.get('iban'),
        'seller_bank': seller.get('bank'),
        'seller_rep_name': seller.get('administrator'),

        # Cumparator party block (leasing company when is_leasing, else the
        # same buyer as Utilizator — see context.py's build_sale_context).
        'cumparator_name': cumparator.get('name'),
        'cumparator_city': cumparator.get('city'),
        'cumparator_county': cumparator.get('county'),
        'cumparator_address': cumparator.get('address'),
        'cumparator_nr': '',  # "str. [●] nr. [●]" — number has no separate field; address already carries it.
        'cumparator_reg_no': cumparator.get('reg_no'),
        'cumparator_cui': cumparator.get('cui'),
        'cumparator_tel': cumparator.get('phone'),
        'cumparator_fax': '',  # no fax field anywhere in the context.
        # Fall back to the Cumparator's own name when there's no distinct
        # legal rep — in a cash sale Cumparator == Utilizator == the
        # individual buyer, who signs as their own representative (same
        # fallback as utilizator_rep below). A leasing-company Cumparator
        # carries a real legal_rep, so that wins when present.
        'cumparator_rep': cumparator.get('legal_rep') or cumparator.get('name'),
        'cumparator_rep_role': cumparator.get('legal_rep_role'),
        'cumparator_rep_signature': cumparator.get('legal_rep') or cumparator.get('name'),

        # Utilizator party block (the actual buyer/driver).
        'utilizator_name': utilizator.get('name'),
        'utilizator_city': utilizator.get('city'),
        'utilizator_county': utilizator.get('county'),
        'utilizator_address': utilizator.get('address'),
        'utilizator_nr': '',
        'utilizator_reg_no': '',  # build_party_from_client has no reg_no field.
        'utilizator_cui': utilizator.get('cui'),
        'utilizator_tel': utilizator.get('phone'),
        'utilizator_fax': '',
        'utilizator_rep': utilizator.get('name'),  # an individual buyer signs as their own representative.
        'utilizator_rep_role': '',
        'utilizator_rep_signature': utilizator.get('name'),

        # Anexa 2 registration number — real carpark_vehicles column,
        # threaded through the Task 2 context.
        'registration_number': context.get('registration_number'),
        # Anexa 1/2 fields with no Task-2-context counterpart.
        'engine_serial': '',
        'upholstery': '',
        'exchange_rate_source': '',
    }


def _fill_contract_html(context: dict) -> str:
    """Load `contract.html` and substitute every `{{token}}` with the
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


def render_contract_pdf(context: dict) -> bytes:
    """Fill the contract template from `context` (Task 2's
    `build_sale_context` output) and render it to PDF bytes via the shared
    `html_to_pdf_bytes` Playwright helper."""
    filled_html = _fill_contract_html(context)
    return html_to_pdf_bytes(filled_html)


def validate_contract_context(context: dict) -> list:
    """Return a list of Romanian missing-mandatory-field messages; an empty
    list means `context` has everything required to render a contract.

    Mandatory: contract_number, price, the buyer party's name (Utilizator —
    the actual person/company taking delivery), and — only for a leasing
    sale (`context['is_leasing']`) — the leasing company's name
    (Cumparator). A cash sale's Cumparator is the same party as Utilizator
    (per context.py's build_sale_context), so no separate check is needed
    for it there.
    """
    context = context or {}
    errors = []

    if not context.get('contract_number'):
        errors.append('Numărul contractului este obligatoriu.')

    if not context.get('price'):
        errors.append('Prețul contractului este obligatoriu.')

    utilizator = context.get('utilizator') or {}
    if not utilizator.get('name'):
        errors.append('Datele cumpărătorului/utilizatorului (nume) sunt obligatorii.')

    if context.get('is_leasing'):
        cumparator = context.get('cumparator') or {}
        if not cumparator.get('name'):
            errors.append('Denumirea societății de leasing (Cumpărător) este obligatorie pentru o vânzare în leasing.')

    return errors
