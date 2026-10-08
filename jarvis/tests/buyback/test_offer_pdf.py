"""Tests for the buyback offer-email vehicle-sheet PDF."""
from buyback.services.offer_pdf import build_vehicle_sheet_pdf


def test_vehicle_sheet_pdf_is_valid_and_nonempty():
    rec = {'record_code': 'BB-1', 'brand': 'BMW', 'model': 'X5', 'vin': 'WBA00000000000001',
           'mileage_km': 85000, 'fuel_type': 'diesel', 'has_damage': True,
           'damage_details': 'zgârietură ușă dreapta'}
    data = build_vehicle_sheet_pdf(rec)
    assert isinstance(data, (bytes, bytearray))
    assert bytes(data[:4]) == b'%PDF'
    assert len(data) > 500


def test_vehicle_sheet_pdf_handles_missing_fields():
    data = build_vehicle_sheet_pdf({'record_code': 'BB-2', 'brand': 'Audi', 'model': 'A4'})
    assert bytes(data[:4]) == b'%PDF'
