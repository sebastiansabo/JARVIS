import os, uuid
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from decimal import Decimal
from database import get_db, get_cursor, release_db
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository
from accounting.facturare.models import InvoiceTypeEnum, InvoiceStateEnum

SUPPLIER_ID = 16   # AUTOWORLD S.R.L. (pre-existing, per test_state_machine_numbering.py)
CUSTOMER_ID = 18

@pytest.fixture
def contract_with_anexa(require_real_db):
    repo = InvoiceStorageRepository()
    ref = f"TEST-ARCH-{uuid.uuid4().hex[:8].upper()}"
    c = repo.create_contract(ref, SUPPLIER_ID, CUSTOMER_ID)
    a = repo.create_anexa(c["id"], 1)
    repo.create_anexa_line(a["id"], 1, "Model X", Decimal("10000"), Decimal("10000"))
    yield repo, c["id"], a["id"]
    conn = get_db(); cur = get_cursor(conn)
    try:
        cur.execute("DELETE FROM facturare_contracts WHERE id = %s", (c["id"],)); conn.commit()
    finally:
        release_db(conn)

def test_arm_and_clear_anexa(contract_with_anexa):
    repo, cid, aid = contract_with_anexa
    assert repo.set_anexa_archive_after(aid, 24) == 1
    row = repo.get_anexa_by_id(aid)
    assert row["archive_after"] is not None and row["archived"] is False
    assert repo.clear_anexa_archive_after(aid) == 1
    assert repo.get_anexa_by_id(aid)["archive_after"] is None

def test_due_anexa_is_archived_with_invoices(contract_with_anexa):
    repo, cid, aid = contract_with_anexa
    repo.create_invoice(aid, InvoiceTypeEnum.INVOICE, InvoiceStateEnum.DRAFT, Decimal("10000"))
    # Arm with a NEGATIVE delay so archive_after is already in the past
    repo.set_anexa_archive_after(aid, -1)
    assert repo.archive_due_anexas() >= 1
    row = repo.get_anexa_by_id(aid)
    assert row["archived"] is True and row["archived_at"] is not None and row["archive_after"] is None
    inv = repo.get_invoices_by_anexa(aid)
    assert all(i["archived"] for i in inv)

def test_due_contract_cascades(contract_with_anexa):
    repo, cid, aid = contract_with_anexa
    repo.set_contract_archive_after(cid, -1)
    assert repo.archive_due_contracts() >= 1
    assert repo.get_contract_by_id(cid)["archived"] is True
    assert repo.get_anexa_by_id(aid)["archived"] is True

def test_list_active_excludes_archived(contract_with_anexa):
    repo, cid, aid = contract_with_anexa
    ids = {a["id"] for a in repo.list_active_anexas()}
    assert aid in ids
    repo.archive_anexa_now(aid)
    ids2 = {a["id"] for a in repo.list_active_anexas()}
    assert aid not in ids2
