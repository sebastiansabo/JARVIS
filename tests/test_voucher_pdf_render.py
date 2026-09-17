"""Smoke tests for voucher PDF rendering.

Exercises the two paths touched by the notes + percentage-label change:
- a percentage voucher (Type prints as "Discount") with a long note that wraps
- a value voucher with no note (Notes block is skipped)
The DB-backed helpers (company/signature lookup) swallow errors and return
empty, so these run without a database.
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.vouchers.pdf_generator import generate_voucher_pdf


def _base_voucher(**overrides):
    voucher = dict(
        voucher_code='VCH-0001',
        company_id=0,
        client_name='ACME SRL',
        contract_number='C-123',
        car_vin='WVWZZZ1JZXW000001',
        validity_months=36,
        voucher_type='value',
        value_lei=100,
        status='active',
        issued_at='2026-09-17',
        expires_at='2029-09-17',
    )
    voucher.update(overrides)
    return voucher


def test_percentage_voucher_with_long_notes_renders():
    voucher = _base_voucher(
        voucher_type='accessory_percentage',
        value_lei=None,
        discount_percentage=15,
        notes='Valabil doar la prezentarea buletinului ' * 6,
    )
    pdf = generate_voucher_pdf(voucher)
    assert pdf[:4] == b'%PDF'
    assert len(pdf) > 1000


def test_value_voucher_without_notes_renders():
    pdf = generate_voucher_pdf(_base_voucher(notes=None))
    assert pdf[:4] == b'%PDF'
    assert len(pdf) > 1000
