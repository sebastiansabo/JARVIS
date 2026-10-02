"""The contract PDFs must show the vehicle's plate even when the foaie's own
`registration_number` is blank.

The TD form rarely captures a plate for a showroom car, so the foaie stores a
blank `registration_number`. The real plate still lives on the vehicle record —
denormalized onto the contract as `vehicle_registration_number` by
`get_contract_by_id`'s `fp_vehicles` join, or resolvable via a VIN lookup for
lean export rows that skip the join. Regression guard for the PDF printing '—'
where a real plate exists (mirrors the brand/fuel fallback).
"""
import PyPDF2

from foi_parcurs.services import pdf_service as ps
from test_foi_parcurs_service_context import _fake_service_contract


def _pdf_text(path):
    reader = PyPDF2.PdfReader(path)
    return '\n'.join((page.extract_text() or '') for page in reader.pages)


def test_legal_pdf_uses_vehicle_plate_when_foaie_blank():
    c = _fake_service_contract(
        contract_id='FP-PLATE-LEGAL',
        registration_number='',                     # nothing typed on the TD form
        vehicle_registration_number='CJ 99 PLT',    # real plate, from the fp_vehicles join
    )
    text = _pdf_text(ps.generate_legal_pdf(c))
    assert 'CJ 99 PLT' in text


def test_legal_pdf_prefers_foaie_plate_over_vehicle():
    c = _fake_service_contract(
        contract_id='FP-PLATE-PREF',
        registration_number='CJ 01 FOA',
        vehicle_registration_number='CJ 99 PLT',
    )
    text = _pdf_text(ps.generate_legal_pdf(c))
    assert 'CJ 01 FOA' in text


def test_legal_pdf_falls_back_to_vehicle_repo_by_vin(monkeypatch):
    # Lean export rows carry neither the foaie plate nor the vehicle join —
    # the plate must be resolved from the vehicle repo by VIN.
    from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository
    monkeypatch.setattr(
        FPVehicleRepository, 'get_by_vin',
        lambda self, vin: {'registration_number': 'CJ 77 VIN',
                           'brand': 'Mazda', 'fuel_type': 'Benzina'},
    )
    c = _fake_service_contract(
        contract_id='FP-PLATE-VIN',
        registration_number='',
        vehicle_brand='', vehicle_fuel_type='',     # force the vin-lookup branch
    )
    c.pop('vehicle_registration_number', None)
    text = _pdf_text(ps.generate_legal_pdf(c))
    assert 'CJ 77 VIN' in text


def test_custom_pdf_uses_vehicle_plate_when_foaie_blank():
    c = _fake_service_contract(
        contract_id='FP-PLATE-CUSTOM',
        registration_number='',
        vehicle_registration_number='CJ 42 CUS',
    )
    text = _pdf_text(ps.generate_custom_pdf(c))
    assert 'CJ 42 CUS' in text


def test_service_contract_pdf_uses_vehicle_plate_when_foaie_blank(monkeypatch, tmp_path):
    from foi_parcurs.repositories.document_type_repository import DocumentTypeRepository
    # Body template carries the {registration_number} placeholder (the seeded
    # default service contract does), so this also guards the template-render
    # path, not just the Vehicle KV row. PLACA[...] makes the body occurrence
    # distinct from the KV row's bare plate.
    monkeypatch.setattr(
        DocumentTypeRepository, 'get_template',
        lambda self, company_id, key: {'title': 'Contract Service',
                                       'body_template': 'Corp contract PLACA[{registration_number}].',
                                       'general_conditions': 'Conditii.'},
    )
    monkeypatch.setattr(ps, '_PDF_DIR', str(tmp_path))
    c = _fake_service_contract(
        contract_id='FP-PLATE-SVC',
        document_type='service',
        registration_number='',
        vehicle_registration_number='CJ 55 SVC',
    )
    text = _pdf_text(ps.generate_service_contract_pdf(c))
    assert 'CJ 55 SVC' in text            # Vehicle KV row
    assert 'PLACA[CJ 55 SVC]' in text     # rendered into the body template too
