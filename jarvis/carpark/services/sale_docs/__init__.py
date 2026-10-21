"""Sale-documents facade — Task 6 of the CarPark "Documente vanzare" plan.

Wires Tasks 1-5 together behind a single, request-agnostic entry point:
fetch the DB entities (vehicle, seller company, buyer CRM client, leasing
company), build the Task 2 context, dispatch on `doc_type` to the Task 3/4/5
renderer, and return the resulting PDF bytes + a filename.

Deliberately has no Flask/current_user dependency — the caller (the route
module) resolves anything request-scoped (the sales-consultant name) and
passes it in via `form['consultant_name']` before calling `generate()`.
"""
from typing import Any, Dict, Optional, Tuple

from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.leasing_company_repository import LeasingCompanyRepository
from carpark.services.sale_docs.context import build_sale_context
from core.organization.repositories.company_repository import CompanyRepository
from crm.repositories.client_repository import ClientRepository


def generate(vehicle_id: int, doc_type: str, form: Optional[Dict[str, Any]]) -> Tuple[bytes, str]:
    """Fetch the vehicle/company/buyer/leasing-company rows, build the Task 2
    context, render the requested document type, and return (pdf_bytes,
    filename).

    Raises `ValueError` for: unknown vehicle (defensive — the route already
    gates ownership before calling this), no price on the vehicle (raised by
    `build_sale_context`), missing/invalid doc-type-specific required fields
    (contract/proforma/warranty validation errors — `validate_contract_context`,
    `validate_proforma_context`, `validate_warranty_context`, each called
    here before rendering, per spec A4 — or a missing proforma_number), or
    an unknown `doc_type`. Callers map `ValueError` to HTTP 400.
    """
    form = form or {}

    vehicle = VehicleRepository().get_by_id(vehicle_id)
    if vehicle is None:
        raise ValueError(f'vehicle {vehicle_id} not found')

    company = CompanyRepository().get(vehicle['company_id'])

    buyer_client = None
    if vehicle.get('buyer_client_id'):
        buyer_client = ClientRepository().get_by_id(vehicle['buyer_client_id'])

    leasing_company = None
    if form.get('leasing_company_id'):
        leasing_company = LeasingCompanyRepository().get(form.get('leasing_company_id'))

    context = build_sale_context(vehicle, company, buyer_client, leasing_company, form)

    if doc_type == 'contract':
        from carpark.services.sale_docs.contract import render_contract_pdf, validate_contract_context
        errors = validate_contract_context(context)
        if errors:
            raise ValueError('; '.join(errors))
        pdf = render_contract_pdf(context)
        filename = f"contract_vanzare_{context.get('vin') or vehicle_id}.pdf"
    elif doc_type == 'proforma':
        from carpark.services.sale_docs.proforma import render_proforma_pdf, validate_proforma_context
        errors = validate_proforma_context(context)
        if errors:
            raise ValueError('; '.join(errors))
        proforma_number = form.get('proforma_number')
        try:
            proforma_number = int(proforma_number)
        except (TypeError, ValueError):
            raise ValueError('proforma_number is required') from None
        pdf = render_proforma_pdf(context, proforma_number)
        filename = f'proforma_{proforma_number}.pdf'
    elif doc_type == 'garantie':
        from carpark.services.sale_docs.warranty import render_warranty_pdf, validate_warranty_context
        errors = validate_warranty_context(context)
        if errors:
            raise ValueError('; '.join(errors))
        pdf = render_warranty_pdf(context)
        filename = f"certificat_garantie_{context.get('vin') or vehicle_id}.pdf"
    else:
        raise ValueError(f'unknown doc_type: {doc_type}')

    return pdf, filename
