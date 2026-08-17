import os, uuid
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from decimal import Decimal
from database import get_db, get_cursor, release_db
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository

SUPPLIER_ID, CUSTOMER_ID = 16, 18

# Uses the dir-scoped require_real_db fixture from tests/accounting/facturare/conftest.py (Task 3 Step 0)
@pytest.fixture
def seeded(require_real_db):
    repo = InvoiceStorageRepository()
    ref = f"TEST-RT-{uuid.uuid4().hex[:8].upper()}"
    c = repo.create_contract(ref, SUPPLIER_ID, CUSTOMER_ID)
    a = repo.create_anexa(c["id"], 1)
    repo.create_anexa_line(a["id"], 1, "M", Decimal("10000"), Decimal("10000"))
    yield repo, c["id"], a["id"]
    conn = get_db(); cur = get_cursor(conn)
    try:
        cur.execute("DELETE FROM facturare_contracts WHERE id = %s", (c["id"],)); conn.commit()
    finally:
        release_db(conn)

def test_contract_archive_now_cascades(seeded):
    repo, cid, aid = seeded
    assert repo.archive_contract_now(cid) >= 1
    assert repo.get_contract_by_id(cid)["archived"] is True
    assert repo.get_anexa_by_id(aid)["archived"] is True
    assert repo.unarchive_contract(cid) >= 1
    assert repo.get_contract_by_id(cid)["archived"] is False
    assert repo.get_anexa_by_id(aid)["archived"] is False

def test_list_anexas_includes_archive_after(seeded):
    repo, cid, aid = seeded
    repo.set_anexa_archive_after(aid, 24)
    a = repo.get_anexa_by_id(aid)
    assert a["archive_after"] is not None
