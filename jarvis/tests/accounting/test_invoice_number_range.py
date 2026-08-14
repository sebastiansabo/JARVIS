"""Regression tests for the Facturare invoice_number range.

Suppliers now issue 8-digit invoice numbers (e.g. 92005610). The original
schemas capped invoice_number at 9,999,999 (7 digits), which rejected them
with a Pydantic ``less_than_equal`` error. These tests pin the widened
9-digit bound (<= 999,999,999) across every lifecycle request model.

Pure schema validation — no database required.
"""
import os
import sys

import pytest
from pydantic import ValidationError

# Ensure the jarvis package root is on sys.path.
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

from accounting.facturare.schemas import (  # noqa: E402
    ProformaCreateRequest,
    InvoiceCreateRequest,
    StornoCreateRequest,
    FinalCreateRequest,
)

# (model, extra required kwargs) for each lifecycle request that carries invoice_number.
CASES = [
    (ProformaCreateRequest, {"anexa_id": 1, "amount_eur": 1}),
    (InvoiceCreateRequest, {"anexa_id": 1, "sequence_number": 1}),
    (StornoCreateRequest, {"anexa_id": 1}),
    (FinalCreateRequest, {"anexa_id": 1}),
]


@pytest.mark.parametrize("model, base", CASES)
def test_accepts_eight_digit_invoice_number(model, base):
    # The exact number from the reported bug report.
    obj = model(invoice_number=92005610, **base)
    assert obj.invoice_number == 92005610


@pytest.mark.parametrize("model, base", CASES)
def test_accepts_nine_digit_upper_bound(model, base):
    obj = model(invoice_number=999999999, **base)
    assert obj.invoice_number == 999999999


@pytest.mark.parametrize("model, base", CASES)
def test_rejects_above_upper_bound(model, base):
    with pytest.raises(ValidationError):
        model(invoice_number=1000000000, **base)


@pytest.mark.parametrize("model, base", CASES)
def test_rejects_below_lower_bound(model, base):
    with pytest.raises(ValidationError):
        model(invoice_number=0, **base)
