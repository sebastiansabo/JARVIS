"""Unit tests for the supplier EuroFib named-preset feature (Procesare).

Covered without a live DB:
- SupplierMasterRepository preset transaction logic: max-5 cap, first-preset-always-active,
  activation deactivating siblings, set_active flip, delete promoting a sibling.
- routes._to_invoice_config_pairs: export honours the per-invoice preset (konto_config_id) and
  falls back to the active preset when a row has none.
- eurofib_export.build_medline_rows: a given preset's konto lands in the right MEDLINE columns,
  so switching presets switches the exported accounts.
"""
import os
import sys
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_B = 'core.base_repository'


def _mock_conn_cursor():
    return MagicMock(), MagicMock()


def _executed_sql(mock_cursor):
    """All SQL strings passed to cursor.execute, lowercased, in call order."""
    return [str(c.args[0]).lower() for c in mock_cursor.execute.call_args_list]


def _insert_call(mock_cursor):
    """The (sql, params) of the first INSERT INTO supplier_konto_config execute call."""
    for c in mock_cursor.execute.call_args_list:
        if 'insert into supplier_konto_config' in str(c.args[0]).lower():
            return c.args
    return None


# ═══════════════════════════════════════════════
# Repository preset transaction logic
# ═══════════════════════════════════════════════
class TestCreatePreset:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_enforces_max_five(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import (
            SupplierMasterRepository, PresetLimitError, MAX_PRESETS_PER_SUPPLIER_COMPANY)
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'n': MAX_PRESETS_PER_SUPPLIER_COMPANY}]

        repo = SupplierMasterRepository()
        with pytest.raises(PresetLimitError):
            repo.create_preset(1, 2, 'Marfă', is_active=False, konto_debit='628701')
        # No INSERT should have been attempted once the cap is hit.
        assert _insert_call(cursor) is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_first_preset_forced_active(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'n': 0}, {'id': 11}]

        repo = SupplierMasterRepository()
        # is_active explicitly False, but as the first preset it must still be created active.
        new_id = repo.create_preset(1, 2, 'Servicii', is_active=False, konto_debit='628701')
        assert new_id == 11
        sql, params = _insert_call(cursor)
        assert params[3] is True  # is_active column value

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_second_preset_inactive_by_default(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'n': 1}, {'id': 12}]

        repo = SupplierMasterRepository()
        repo.create_preset(1, 2, 'Marfă', is_active=False, konto_debit='371000')
        sql, params = _insert_call(cursor)
        assert params[3] is False
        # Not activating → no sibling-deactivation UPDATE.
        assert not any('is_active = false' in s for s in _executed_sql(cursor))

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_active_preset_deactivates_siblings(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'n': 1}, {'id': 13}]

        repo = SupplierMasterRepository()
        repo.create_preset(1, 2, 'Chirie', is_active=True, konto_debit='612000')
        sql, params = _insert_call(cursor)
        assert params[3] is True
        assert any('is_active = false' in s for s in _executed_sql(cursor))


class TestSetActive:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_flips_active(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'supplier_id': 1, 'company_id': 2}]

        repo = SupplierMasterRepository()
        assert repo.set_active(13) == 1
        sqls = _executed_sql(cursor)
        assert any('is_active = false' in s for s in sqls)
        assert any('is_active = true' in s and 'where id = %s' in s for s in sqls)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_missing_preset_returns_zero(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [None]

        repo = SupplierMasterRepository()
        assert repo.set_active(999) == 0
        # Only the lookup ran — no UPDATEs.
        assert not any('update' in s for s in _executed_sql(cursor))


class TestDeletePreset:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_active_promotes_sibling(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'supplier_id': 1, 'company_id': 2, 'is_active': True}]

        repo = SupplierMasterRepository()
        assert repo.delete_preset(13) == 1
        sqls = _executed_sql(cursor)
        assert any(s.startswith('delete from supplier_konto_config') for s in sqls)
        assert any('is_active = true' in s for s in sqls)  # promotion

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_inactive_no_promotion(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.side_effect = [{'supplier_id': 1, 'company_id': 2, 'is_active': False}]

        repo = SupplierMasterRepository()
        assert repo.delete_preset(14) == 1
        sqls = _executed_sql(cursor)
        assert any(s.startswith('delete from supplier_konto_config') for s in sqls)
        assert not any('is_active = true' in s for s in sqls)


# ═══════════════════════════════════════════════
# Export wiring: per-invoice override → chosen preset
# ═══════════════════════════════════════════════
class _FakeRepo:
    """Stand-in for SupplierMasterRepository capturing which resolver each invoice used."""
    def __init__(self):
        self.by_id_calls = []
        self.effective_calls = []

    def get_konto_by_id(self, preset_id):
        self.by_id_calls.append(preset_id)
        return {'konto': {'konto_debit': f'BYID-{preset_id}'}, 'konto_config_id': preset_id, 'name': 'X'}

    def get_effective_konto(self, supplier_id, company_id):
        self.effective_calls.append((supplier_id, company_id))
        return {'konto': {'konto_debit': 'ACTIVE'}, 'has_company_config': True,
                'konto_config_id': 99, 'name': 'Implicit'}


class TestExportPairWiring:

    def _row(self, **over):
        row = {'id': 1, 'supplier': 'A24', 'supplier_id': 5, 'invoice_number': 'F1',
               'invoice_date': '2026-08-31', 'net_value': 100, 'invoice_value': 119,
               'subtract_vat': True, 'due_date': '2026-09-30'}
        row.update(over)
        return row

    def test_uses_override_preset_when_present(self):
        from core.suppliers import routes
        fake = _FakeRepo()
        with patch.object(routes, '_repo', fake):
            pairs = routes._to_invoice_config_pairs([self._row(konto_config_id=7)], company_id=2, skipped=[])
        assert len(pairs) == 1
        _invoice, konto = pairs[0]
        assert konto['konto_debit'] == 'BYID-7'
        assert fake.by_id_calls == [7]
        assert fake.effective_calls == []

    def test_falls_back_to_active_without_preset(self):
        from core.suppliers import routes
        fake = _FakeRepo()
        with patch.object(routes, '_repo', fake):
            pairs = routes._to_invoice_config_pairs([self._row(konto_config_id=None)], company_id=2, skipped=[])
        _invoice, konto = pairs[0]
        assert konto['konto_debit'] == 'ACTIVE'
        assert fake.effective_calls == [(5, 2)]
        assert fake.by_id_calls == []


# ═══════════════════════════════════════════════
# Pure export: the chosen preset's accounts drive the rows
# ═══════════════════════════════════════════════
class TestImportStatusMarking:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_mark_imported_sets_importat_from_bugetata(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        repo = SupplierMasterRepository()
        repo.mark_invoices_imported([1, 2, 3])
        sql = str(cursor.execute.call_args_list[-1].args[0]).lower()
        assert "status = 'importat'" in sql
        assert "lower(status) = 'bugetata'" in sql

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_unmark_reverts_importat_to_bugetata(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        repo = SupplierMasterRepository()
        repo.unmark_imported_invoices([1])
        sql = str(cursor.execute.call_args_list[-1].args[0]).lower()
        assert "status = 'bugetata'" in sql
        assert "lower(status) = 'importat'" in sql

    def test_mark_imported_empty_is_noop(self):
        from core.suppliers.repository import SupplierMasterRepository
        assert SupplierMasterRepository().mark_invoices_imported([]) == 0

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_import_ready_ids_returns_query_ids(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchall.return_value = [{'id': 5}, {'id': 9}]
        repo = SupplierMasterRepository()
        assert repo.import_ready_ids([5, 7, 9], company_id=2) == [5, 9]
        sql = str(cursor.execute.call_args_list[-1].args[0]).lower()
        assert "lower(i.status) = 'bugetata'" in sql
        assert 'kc.is_active' in sql

    def test_import_ready_ids_empty_is_noop(self):
        from core.suppliers.repository import SupplierMasterRepository
        assert SupplierMasterRepository().import_ready_ids([]) == []


class TestSchemasForInvoiceHelpers:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_invoice_override_returns_id(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = {'konto_config_id': 42}
        assert SupplierMasterRepository().get_invoice_override(7) == 42

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_invoice_override_none_when_absent(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = None
        assert SupplierMasterRepository().get_invoice_override(7) is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_invoice_supplier_name(self, mock_get_db, mock_get_cursor, mock_release):
        from core.suppliers.repository import SupplierMasterRepository
        conn, cursor = _mock_conn_cursor()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = {'supplier': 'A24 ROAD PATROL SRL'}
        assert SupplierMasterRepository().invoice_supplier_name(7) == 'A24 ROAD PATROL SRL'


class TestBuildMedlineRowsUsesConfig:

    def _invoice(self):
        return {'supplier': 'A24', 'invoice_number': '2195', 'invoice_date': '2026-08-31',
                'due_date': '2026-09-30', 'net_amount': 100, 'vat_amount': 19, 'gross_amount': 119}

    def test_different_presets_yield_different_accounts(self):
        from core.suppliers.eurofib_export import build_medline_rows, _COL_INDEX
        cfg_a = {'konto_debit': '628701', 'konto_credit': '40102793', 'klient': '140',
                 'steuercode': '621', 'belegart': 'JC'}
        cfg_b = {'konto_debit': '371000', 'konto_credit': '40100001', 'klient': '140',
                 'steuercode': '622', 'belegart': 'JC'}
        credit_a, debit_a = build_medline_rows(self._invoice(), cfg_a)
        credit_b, debit_b = build_medline_rows(self._invoice(), cfg_b)
        assert debit_a[_COL_INDEX['konto']] == '628701'
        assert credit_a[_COL_INDEX['konto']] == '40102793'
        assert debit_b[_COL_INDEX['konto']] == '371000'
        assert credit_b[_COL_INDEX['konto']] == '40100001'
        # amounts identical, only the accounts differ with the preset
        assert debit_a[_COL_INDEX['betrag']] == debit_b[_COL_INDEX['betrag']] == '100.00'
