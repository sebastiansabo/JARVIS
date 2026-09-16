"""The accounting supplier-match queries must resolve a supplier by CUI (the invoice's
e-Factura partner_cif), not only by exact free-text name/alias.

Regression guard for the ATUU PR&MANAGEMENT case: the e-Factura name arrived as
"ATUU PR&MANAGEMENT S.R.L." while the master was stored "ATUU PR&MANAGEMENT SRL", so the
name/alias-only join dropped the invoice from the Procesare worklist even though the CUI
(46590090) matched on both sides.

psycopg2 is mocked globally (see conftest.py), so a live row-level assertion is impossible
here — these tests assert on the generated SQL: each of the three name/alias-matched accounting
queries (worklist / import-ready badge / remap list) must ALSO key on suppliers.cui_normalized
against the invoice's e-Factura partner_cif. The behavioural proof (the row actually appears)
is done separately against the live DB, read-only.
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from unittest.mock import MagicMock

from core.suppliers.repository import SupplierMasterRepository


def _captured_sql(method_name, *args, **kwargs):
    """Run a repo read method with query_all stubbed out; return every SQL string it issued,
    lower-cased and concatenated."""
    repo = SupplierMasterRepository()
    repo.query_all = MagicMock(return_value=[])
    getattr(repo, method_name)(*args, **kwargs)
    assert repo.query_all.call_count >= 1, f"{method_name} issued no query"
    return " ".join(str(c.args[0]).lower() for c in repo.query_all.call_args_list)


def _matches_by_cui(sql):
    """True when the query keys suppliers.cui_normalized against the e-Factura partner_cif."""
    return 'cui_normalized' in sql and 'partner_cif' in sql


def test_worklist_resolves_supplier_by_cui():
    sql = _captured_sql(
        'list_budgeted_invoices', 11, 'Autoworld PREMIUM S.R.L.', '2026-09-01', '2026-09-30')
    assert _matches_by_cui(sql), "worklist must match supplier by CUI, not only name/alias"


def test_import_ready_resolves_supplier_by_cui():
    sql = _captured_sql('import_ready_ids', [1, 2, 3], 11)
    assert _matches_by_cui(sql), "import-ready badge must match supplier by CUI, not only name/alias"


def test_unresolved_excludes_cui_matches():
    sql = _captured_sql('unresolved_invoice_suppliers', 200, 'Autoworld PREMIUM S.R.L.')
    assert _matches_by_cui(sql), "remap list must treat a CUI match as resolved (exclude it)"
