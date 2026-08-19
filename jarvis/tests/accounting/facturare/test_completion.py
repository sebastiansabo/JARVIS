import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from decimal import Decimal
from accounting.facturare.services.completion import is_anexa_complete, is_contract_complete


class FakeRepo:
    """In-memory stand-in for InvoiceStorageRepository (no DB)."""
    def __init__(self, lines, invoices, anexas_by_contract=None):
        self._lines = lines
        self._invoices = invoices
        self._anexas_by_contract = anexas_by_contract or {}
    def get_lines_by_anexa(self, anexa_id):
        return self._lines
    def get_invoices_by_anexa(self, anexa_id):
        return self._invoices
    def list_anexas_by_contract(self, contract_id):
        return self._anexas_by_contract.get(contract_id, [])


def _lines(*prices):
    return [{'id': i + 1, 'selling_price_eur': Decimal(str(p))} for i, p in enumerate(prices)]

def _inv(itype, amount, seq=1, line_ids=None):
    return {'invoice_type': itype, 'sequence_number': seq,
            'total_amount_eur': Decimal(str(amount)), 'line_ids': line_ids}


def test_empty_anexa_is_not_complete():
    assert is_anexa_complete(FakeRepo([], []), 1) is False

def test_proforma_only_is_not_complete():
    repo = FakeRepo(_lines(10000), [_inv('PROFORMA', 10000)])
    assert is_anexa_complete(repo, 1) is False

def test_unpaired_proforma_blocks_completion():
    # Proforma seq 2 has no matching invoice seq 2
    repo = FakeRepo(_lines(10000, 10000), [
        _inv('INVOICE', 10000, seq=1, line_ids=[1]),
        _inv('PROFORMA', 10000, seq=2, line_ids=[2]),
        _inv('INVOICE', 10000, seq=1, line_ids=[1]),
    ])
    assert is_anexa_complete(repo, 1) is False

def test_unpaired_proforma_blocks_even_when_lines_fully_invoiced():
    # Line fully covered by INVOICE seq 1 (net check passes on its own),
    # but a stray PROFORMA seq 2 has no matching INVOICE seq 2 -> the
    # unpaired-proforma gate must still block completion.
    repo = FakeRepo(_lines(10000), [
        _inv('INVOICE', 10000, seq=1, line_ids=[1]),
        _inv('PROFORMA', 5000, seq=2, line_ids=[1]),
    ])
    assert is_anexa_complete(repo, 1) is False

def test_advance_only_without_final_is_not_complete():
    # A full-value advance invoice (factura de avans, invoice_type INVOICE)
    # reaches the selling price on its own, but revenue is booked only at
    # final invoicing. With no FINAL the anexa must NOT be archive-complete.
    repo = FakeRepo(_lines(10000, 10000), [
        _inv('PROFORMA', 20000, seq=1), _inv('INVOICE', 20000, seq=1),
    ])
    assert is_anexa_complete(repo, 1) is False

def test_final_invoice_for_every_car_completes_anexa():
    # avans -> storno -> final for the whole anexa settles it.
    repo = FakeRepo(_lines(10000, 10000), [
        _inv('PROFORMA', 20000, seq=1), _inv('INVOICE', 20000, seq=1),
        _inv('STORNO', -20000, seq=1), _inv('FINAL', 20000, seq=1),
    ])
    assert is_anexa_complete(repo, 1) is True

def test_final_for_one_car_of_two_is_not_complete():
    # Car 1 finally invoiced, car 2 has only a full advance -> the anexa is
    # not complete until *every* car is finally invoiced.
    repo = FakeRepo(_lines(10000, 10000), [
        _inv('INVOICE', 10000, seq=1, line_ids=[1]),
        _inv('STORNO', -10000, seq=1, line_ids=[1]),
        _inv('FINAL', 10000, seq=1, line_ids=[1]),
        _inv('INVOICE', 10000, seq=1, line_ids=[2]),
    ])
    assert is_anexa_complete(repo, 1) is False

def test_partial_invoice_is_not_complete():
    # One 20000 invoice covering both 10000 lines = 100%; here only one line invoiced
    repo = FakeRepo(_lines(10000, 10000), [
        _inv('INVOICE', 10000, seq=1, line_ids=[1]),
    ])
    assert is_anexa_complete(repo, 1) is False

def test_storno_reopens_then_final_recloses():
    lines = _lines(10000)
    reopened = FakeRepo(lines, [
        _inv('INVOICE', 10000, seq=1), _inv('STORNO', -10000, seq=1),
    ])
    assert is_anexa_complete(reopened, 1) is False
    reclosed = FakeRepo(lines, [
        _inv('INVOICE', 10000, seq=1), _inv('STORNO', -10000, seq=1),
        _inv('FINAL', 10000, seq=1),
    ])
    assert is_anexa_complete(reclosed, 1) is True

def _finalized(total):
    """Invoices that fully settle a car of `total`: avans -> storno -> final."""
    return [_inv('INVOICE', total, seq=1), _inv('STORNO', -total, seq=1),
            _inv('FINAL', total, seq=1)]

def test_contract_complete_requires_all_anexas():
    # Build a contract repo delegating per-anexa. Each anexa must be finally
    # invoiced (FINAL) to count as complete.
    class ContractRepo(FakeRepo):
        def __init__(self):
            super().__init__([], [], {77: [{'id': 1}, {'id': 2}]})
            self.per = {1: _finalized(10000), 2: []}
            self.per_lines = {1: _lines(10000), 2: _lines(5000)}
        def get_lines_by_anexa(self, aid): return self.per_lines[aid]
        def get_invoices_by_anexa(self, aid): return self.per[aid]
    repo = ContractRepo()
    assert is_contract_complete(repo, 77) is False   # anexa 2 not finally invoiced
    repo.per[2] = _finalized(5000)
    assert is_contract_complete(repo, 77) is True

def test_contract_with_no_anexas_is_not_complete():
    assert is_contract_complete(FakeRepo([], [], {5: []}), 5) is False
