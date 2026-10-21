"""Sale-document token-context builder — pure, no DB, no I/O.

Assembles the token dict that the contract / warranty / proforma renderers
(Tasks 3-5 of the CarPark "Documente vanzare" plan) will fill their templates
from. Every function here takes already-fetched plain dicts (as returned by
`CompanyRepository.get`, `ClientRepository.get_by_id`,
`LeasingCompanyRepository.get`, `vehicle_repository.get_by_id`) and returns a
plain dict — no queries, no network, no escaping (escaping is the
renderer's job, per the design's A5 anti-goal).

Cash vs leasing (design D4): a sale's `sale_type` decides whether the
contract's "Cumparator" (buyer-financier) party is the leasing company or
collapses into the actual buyer:
  - leasing sale (`sale_type` in LEASING_SALE_TYPES): Cumparator = the
    leasing company, Utilizator = the buyer (CRM client or free-text name).
  - cash/direct sale: Cumparator = Utilizator = the buyer.
"""
from typing import Any, Dict, Optional

# `sale_type` values written by the sell flow (frontend SellDialog.tsx) that
# mean "financed via a leasing company" rather than a cash/direct sale.
LEASING_SALE_TYPES = {'PLR', 'CREDIT PLR', 'BT LEASING', 'BRD', 'BCR', 'AW NEXT'}


def _s(value: Any) -> str:
    """Stringify + strip; None/blank becomes ''. Never raises on missing keys."""
    if value is None:
        return ''
    return str(value).strip()


def build_seller(company: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map a `companies` row (CompanyRepository.get, `SELECT *`) to the
    Vanzator (seller) block.

    Mirrors `foi_parcurs/services/pdf_service.py::_company_legal` (strip a
    leading 'RO' from `vat` -> `cui`) — replicated here rather than imported,
    since that function is private to the foi_parcurs module and this
    module's output shape differs (keeps `city`/`county`/`showroom_address`
    as separate tokens instead of foi_parcurs's merged `sediu` string).

    `companies` has no `phone` column today; `.get('phone')` simply comes
    back `None` -> `''`, it never raises.
    """
    company = company or {}
    vat = _s(company.get('vat'))
    cui = vat[2:].strip() if vat[:2].upper() == 'RO' else vat
    return {
        'name': _s(company.get('company')),
        'cui': cui,
        'vat': vat,  # raw registered VAT (e.g. 'RO50188939'), unlike `cui` above.
        'reg_no': _s(company.get('reg_no')),
        'address': _s(company.get('street')),
        'city': _s(company.get('city')),
        'county': _s(company.get('county')),
        'iban': _s(company.get('iban')),
        'bank': _s(company.get('bank')),
        'swift': _s(company.get('swift')),
        'administrator': _s(company.get('administrator')),
        'showroom_address': _s(company.get('showroom_address')),
        'phone': _s(company.get('phone')),
        # `companies` has no dedicated "email" column — `alert_email` is the
        # only company-level email address available; blank when absent.
        'email': _s(company.get('alert_email')),
    }


def build_party_from_client(client: Optional[Dict[str, Any]], fallback_name: Optional[str] = None) -> Dict[str, Any]:
    """Map a `crm_clients` row (ClientRepository.get_by_id, `SELECT *`) to a
    generic "party" block (buyer / utilizator).

    `crm_clients`'s display name column is `display_name` (NOT `name`). When
    there's no CRM client at all (walk-in buyer captured only as free text on
    the vehicle, e.g. `vehicle['buyer_name']`), pass that as `fallback_name`.
    `county` comes from crm_clients' `region` column.
    """
    client = client or {}
    name = client.get('display_name') if client else None
    if not name:
        name = fallback_name
    return {
        'name': name.strip() if isinstance(name, str) else name,
        'cui': _s(client.get('cui')),
        'address': _s(client.get('street')),
        'city': _s(client.get('city')),
        'county': _s(client.get('region')),
        'phone': _s(client.get('phone')),
        'email': _s(client.get('email')),
    }


def _party_from_leasing_company(leasing_company: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map a `carpark_leasing_companies` row (LeasingCompanyRepository.get)
    to the Cumparator party block for a leasing sale.

    Unlike `crm_clients`/`companies`, this table already stores `address`
    directly (no `street` to rename) and carries `reg_no`/`iban`/
    `legal_rep`/`legal_rep_role` — kept here (superset of the generic party
    shape, same precedent as `build_seller` carrying extra fields) since the
    contract renderer needs a signing representative for the Cumparator
    party in a leasing sale.
    """
    lc = leasing_company or {}
    return {
        'name': _s(lc.get('name')),
        'cui': _s(lc.get('cui')),
        'reg_no': _s(lc.get('reg_no')),
        'address': _s(lc.get('address')),
        'city': _s(lc.get('city')),
        'county': _s(lc.get('county')),
        'phone': _s(lc.get('phone')),
        'email': _s(lc.get('email')),
        'iban': _s(lc.get('iban')),
        'legal_rep': _s(lc.get('legal_rep')),
        'legal_rep_role': _s(lc.get('legal_rep_role')),
    }


def build_sale_context(
    vehicle: Dict[str, Any],
    company: Optional[Dict[str, Any]],
    buyer_client: Optional[Dict[str, Any]],
    leasing_company: Optional[Dict[str, Any]],
    form: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the full token context for the sale-document renderers.

    Resolves cash vs leasing (design D4) from `vehicle['sale_type']`:
      - in `LEASING_SALE_TYPES` -> `cumparator` = the leasing company party,
        `utilizator` = the buyer party, `is_leasing` = True.
      - otherwise -> `cumparator` = `utilizator` = the buyer party,
        `is_leasing` = False.

    Price = `form['price']` (the dialog's editable override, design D7) ->
    `vehicle['sale_price']` -> `vehicle['current_price']`; raises
    `ValueError` if none of the three is set (a sale document cannot be
    generated without a price) — never silently emits a blank price
    (design A4). Currency likewise prefers `form['currency']` over the
    vehicle's `price_currency`.

    `form` tokens (consultant_name, contract_number, contract_date,
    proforma_number, proforma_date, delivery_term_days, delivery_place,
    delivery_date, autonomy) are passed through verbatim/unescaped:
    escaping is the renderer's job, not this pure context-assembly module.
    `consultant_name` is the salesperson (design D3) — the route resolves
    `salesperson_user_id` -> name upstream and passes it via `form`.
    """
    vehicle = vehicle or {}
    form = form or {}

    price = form.get('price') or vehicle.get('sale_price') or vehicle.get('current_price')
    if price is None:
        raise ValueError('cannot build sale context: no price in form, sale_price or current_price')

    sale_type = _s(vehicle.get('sale_type'))
    is_leasing = sale_type in LEASING_SALE_TYPES

    buyer_party = build_party_from_client(buyer_client, fallback_name=vehicle.get('buyer_name'))

    if is_leasing:
        cumparator = _party_from_leasing_company(leasing_company)
        utilizator = buyer_party
    else:
        cumparator = buyer_party
        utilizator = buyer_party

    return {
        'seller': build_seller(company),
        'cumparator': cumparator,
        'utilizator': utilizator,
        'is_leasing': is_leasing,
        # Vehicle tokens
        'brand': vehicle.get('brand'),
        'model': vehicle.get('model'),
        'variant': vehicle.get('variant'),
        'vin': vehicle.get('vin'),
        'registration_number': vehicle.get('registration_number'),
        'mileage_km': vehicle.get('mileage_km'),
        'year': vehicle.get('year_of_manufacture'),
        'color': vehicle.get('color_exterior'),
        'price': price,
        'currency': form.get('currency') or vehicle.get('price_currency'),
        'fuel': vehicle.get('fuel_type'),
        # Form tokens, passed through as-is
        'consultant_name': form.get('consultant_name'),
        'contract_number': form.get('contract_number'),
        'contract_date': form.get('contract_date'),
        'proforma_number': form.get('proforma_number'),
        'proforma_date': form.get('proforma_date'),
        'delivery_term_days': form.get('delivery_term_days'),
        'delivery_place': form.get('delivery_place'),
        'delivery_date': form.get('delivery_date'),
        'autonomy': form.get('autonomy'),
    }
