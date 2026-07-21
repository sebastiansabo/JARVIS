"""Unit tests for the e-Factura module.

Tests:
- InvoiceRepository: CRUD, dedup, list, unallocated, hidden, bin, bulk ops
- CompanyConnectionRepository: CRUD, sync cursor, status
- SyncRepository: runs, errors, stats
- SupplierMappingRepository: CRUD, lookup, bulk
- SupplierTypeRepository: CRUD
- Models: data validation, computed properties
- Config: enums, ANAFConfig, ConnectorConfig
"""

import sys
import os
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_B = 'core.base_repository'


def _mock_db():
    conn = MagicMock()
    cursor = MagicMock()
    return conn, cursor


# ═══════════════════════════════════════════════
# Models & Config Tests (no DB needed)
# ═══════════════════════════════════════════════

class TestModels:

    def test_invoice_full_number_with_series(self):
        from core.connectors.efactura.models import Invoice
        from core.connectors.efactura.config import InvoiceDirection
        inv = Invoice(invoice_series='ABC', invoice_number='123')
        assert inv.full_invoice_number == 'ABC-123'

    def test_invoice_full_number_without_series(self):
        from core.connectors.efactura.models import Invoice
        inv = Invoice(invoice_number='456')
        assert inv.full_invoice_number == '456'

    def test_invoice_defaults(self):
        from core.connectors.efactura.models import Invoice
        from core.connectors.efactura.config import InvoiceDirection, EFacturaStatus
        inv = Invoice()
        assert inv.direction == InvoiceDirection.RECEIVED
        assert inv.status == EFacturaStatus.PROCESSED
        assert inv.total_amount == Decimal('0.00')
        assert inv.currency == 'RON'

    def test_company_connection_cert_not_expiring(self):
        from core.connectors.efactura.models import CompanyConnection
        from datetime import timedelta
        conn = CompanyConnection(
            cert_expires_at=datetime.now() + timedelta(days=60)
        )
        assert conn.is_cert_expiring_soon(days=30) is False

    def test_company_connection_cert_expiring_soon(self):
        from core.connectors.efactura.models import CompanyConnection
        from datetime import timedelta
        conn = CompanyConnection(
            cert_expires_at=datetime.now() + timedelta(days=10)
        )
        assert conn.is_cert_expiring_soon(days=30) is True

    def test_company_connection_no_cert(self):
        from core.connectors.efactura.models import CompanyConnection
        conn = CompanyConnection()
        assert conn.is_cert_expiring_soon() is False

    def test_sync_run_defaults(self):
        from core.connectors.efactura.models import SyncRun
        run = SyncRun(run_id='abc', company_cif='12345')
        assert run.messages_checked == 0
        assert run.invoices_created == 0
        assert run.success is False

    def test_sync_error_defaults(self):
        from core.connectors.efactura.models import SyncError
        err = SyncError(run_id='abc', error_type='NETWORK', error_message='timeout')
        assert err.is_retryable is False
        assert err.message_id is None

    def test_anaf_message_from_response(self):
        from core.connectors.efactura.models import ANAFMessage
        data = {
            'id': '999',
            'cif': '12345678',
            'id_solicitare': 'SOL-1',
            'tip': 'FACTURA',
            'data_creare': '202401151030',
            'stare': 'ok',
        }
        msg = ANAFMessage.from_anaf_response(data)
        assert msg.id == '999'
        assert msg.cif == '12345678'
        assert msg.upload_id == 'SOL-1'
        assert msg.message_type == 'FACTURA'
        assert msg.creation_date is not None
        assert msg.creation_date.year == 2024

    def test_anaf_message_bad_date(self):
        from core.connectors.efactura.models import ANAFMessage
        msg = ANAFMessage.from_anaf_response({'data_creare': 'not-a-date'})
        assert msg.creation_date is None

    def test_parsed_invoice_defaults(self):
        from core.connectors.efactura.models import ParsedInvoice
        parsed = ParsedInvoice()
        assert parsed.total_amount == Decimal('0.00')
        assert parsed.line_items == []
        assert parsed.vat_breakdown == []


class TestConfig:

    def test_invoice_direction_values(self):
        from core.connectors.efactura.config import InvoiceDirection
        assert InvoiceDirection.RECEIVED.value == 'received'
        assert InvoiceDirection.SENT.value == 'sent'

    def test_efactura_status_values(self):
        from core.connectors.efactura.config import EFacturaStatus
        assert EFacturaStatus.PROCESSED.value == 'processed'
        assert EFacturaStatus.VALID.value == 'valid'
        assert EFacturaStatus.ERROR.value == 'error'

    def test_artifact_type_values(self):
        from core.connectors.efactura.config import ArtifactType
        assert ArtifactType.ZIP.value == 'zip'
        assert ArtifactType.XML.value == 'xml'
        assert ArtifactType.PDF.value == 'pdf'

    def test_anaf_config_base_url_production(self):
        from core.connectors.efactura.config import ANAFConfig, Environment
        cfg = ANAFConfig()
        assert 'prod' in cfg.get_base_url(Environment.PRODUCTION)

    def test_anaf_config_base_url_test(self):
        from core.connectors.efactura.config import ANAFConfig, Environment
        cfg = ANAFConfig()
        assert 'test' in cfg.get_base_url(Environment.TEST)

    def test_connector_config_from_env(self):
        from core.connectors.efactura.config import ConnectorConfig, Environment
        with patch.dict(os.environ, {
            'EFACTURA_ENVIRONMENT': 'test',
            'EFACTURA_ENABLE_SENT': 'false',
        }):
            cfg = ConnectorConfig.from_env()
            assert cfg.environment == Environment.TEST
            assert cfg.enable_sent_invoices is False

    def test_connector_config_defaults(self):
        from core.connectors.efactura.config import ConnectorConfig, Environment
        cfg = ConnectorConfig()
        assert cfg.environment == Environment.TEST
        assert cfg.enable_auto_sync is True
        assert cfg.enable_notifications is False

    def test_ui_config_structure(self):
        from core.connectors.efactura.config import UI_CONFIG
        assert UI_CONFIG['name'] == 'RO e-Factura'
        assert len(UI_CONFIG['fields']) >= 5
        field_keys = {f['key'] for f in UI_CONFIG['fields']}
        assert 'environment' in field_keys
        assert 'company_cif' in field_keys


# ═══════════════════════════════════════════════
# CompanyConnectionRepository Tests
# ═══════════════════════════════════════════════

class TestCompanyConnectionRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 1, 'created_at': datetime.now(), 'updated_at': datetime.now()
        }

        from core.connectors.efactura.repositories.company_repo import CompanyConnectionRepository
        from core.connectors.efactura.models import CompanyConnection
        repo = CompanyConnectionRepository()
        connection = CompanyConnection(cif='12345678', display_name='Test SRL')
        result = repo.create(connection)
        assert result.id == 1
        mock_conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_by_cif(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 1, 'cif': '12345678', 'display_name': 'Test SRL',
            'environment': 'test', 'status': 'active', 'status_message': None,
            'config': {}, 'cert_fingerprint': None, 'cert_expires_at': None,
            'last_sync_at': None, 'last_received_cursor': None, 'last_sent_cursor': None,
            'created_at': datetime.now(), 'updated_at': datetime.now(),
        }

        from core.connectors.efactura.repositories.company_repo import CompanyConnectionRepository
        repo = CompanyConnectionRepository()
        result = repo.get_by_cif('12345678')
        assert result is not None
        assert result.cif == '12345678'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_by_cif_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        from core.connectors.efactura.repositories.company_repo import CompanyConnectionRepository
        repo = CompanyConnectionRepository()
        result = repo.get_by_cif('99999999')
        assert result is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all_active(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'cif': '111', 'display_name': 'A SRL', 'environment': 'test',
             'status': 'active', 'status_message': None, 'config': {},
             'cert_fingerprint': None, 'cert_expires_at': None,
             'last_sync_at': None, 'last_received_cursor': None, 'last_sent_cursor': None,
             'created_at': datetime.now(), 'updated_at': datetime.now()},
            {'id': 2, 'cif': '222', 'display_name': 'B SRL', 'environment': 'test',
             'status': 'active', 'status_message': None, 'config': {},
             'cert_fingerprint': None, 'cert_expires_at': None,
             'last_sync_at': None, 'last_received_cursor': None, 'last_sent_cursor': None,
             'created_at': datetime.now(), 'updated_at': datetime.now()},
        ]

        from core.connectors.efactura.repositories.company_repo import CompanyConnectionRepository
        repo = CompanyConnectionRepository()
        result = repo.get_all_active()
        assert len(result) == 2
        assert result[0].display_name == 'A SRL'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.connectors.efactura.repositories.company_repo import CompanyConnectionRepository
        repo = CompanyConnectionRepository()
        result = repo.delete('12345678')
        assert result is True


# ═══════════════════════════════════════════════
# SyncRepository Tests
# ═══════════════════════════════════════════════

class TestSyncRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_run(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 1}

        from core.connectors.efactura.repositories.sync_repo import SyncRepository
        repo = SyncRepository()
        run = repo.create_run('12345678', direction='received')
        assert run.id == 1
        assert run.company_cif == '12345678'
        assert run.direction == 'received'
        assert run.run_id  # UUID was generated
        mock_conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_record_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 5, 'created_at': datetime.now()}

        from core.connectors.efactura.repositories.sync_repo import SyncRepository
        repo = SyncRepository()
        error = repo.record_error(
            run_id='abc-123',
            error_type='NETWORK',
            error_message='Connection timeout',
            message_id='MSG-1',
            is_retryable=True,
        )
        assert error.id == 5
        assert error.error_type == 'NETWORK'
        assert error.is_retryable is True
        mock_conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_record_error_truncates_message(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 6, 'created_at': datetime.now()}

        from core.connectors.efactura.repositories.sync_repo import SyncRepository
        repo = SyncRepository()
        long_message = 'x' * 1000
        error = repo.record_error(
            run_id='abc', error_type='API', error_message=long_message
        )
        assert len(error.error_message) <= 500

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_run_by_id(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 1, 'run_id': 'abc-123', 'company_cif': '12345678',
            'started_at': datetime.now(), 'finished_at': None,
            'success': False, 'direction': 'received',
            'messages_checked': 10, 'invoices_fetched': 5,
            'invoices_created': 3, 'invoices_updated': 1,
            'invoices_skipped': 1, 'errors_count': 0,
            'cursor_before': None, 'cursor_after': 'cur-1',
            'error_summary': None,
        }

        from core.connectors.efactura.repositories.sync_repo import SyncRepository
        repo = SyncRepository()
        run = repo.get_run_by_id('abc-123')
        assert run is not None
        assert run.company_cif == '12345678'
        assert run.messages_checked == 10

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_run_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        from core.connectors.efactura.repositories.sync_repo import SyncRepository
        repo = SyncRepository()
        run = repo.get_run_by_id('nonexistent')
        assert run is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_recent_runs(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'run_id': 'r1', 'company_cif': '111',
             'started_at': datetime.now(), 'finished_at': datetime.now(),
             'success': True, 'direction': 'both',
             'messages_checked': 5, 'invoices_fetched': 2,
             'invoices_created': 2, 'invoices_updated': 0,
             'invoices_skipped': 0, 'errors_count': 0,
             'cursor_before': None, 'cursor_after': None,
             'error_summary': None},
        ]

        from core.connectors.efactura.repositories.sync_repo import SyncRepository
        repo = SyncRepository()
        runs = repo.get_recent_runs(company_cif='111', limit=10)
        assert len(runs) == 1
        assert runs[0].success is True


# ═══════════════════════════════════════════════
# InvoiceRepository Tests
# ═══════════════════════════════════════════════

class TestInvoiceRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_by_id(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 10, 'cif_owner': '12345678', 'company_id': 1,
            'direction': 'received', 'partner_cif': '87654321',
            'partner_name': 'Furnizor SRL', 'invoice_number': 'INV-001',
            'invoice_series': 'A', 'issue_date': date(2024, 1, 15),
            'due_date': date(2024, 2, 15), 'total_amount': Decimal('1190.00'),
            'total_vat': Decimal('190.00'), 'total_without_vat': Decimal('1000.00'),
            'currency': 'RON', 'status': 'processed',
            'created_at': datetime.now(), 'updated_at': datetime.now(),
        }

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        inv = repo.get_by_id(10)
        assert inv is not None
        assert inv.partner_name == 'Furnizor SRL'
        assert inv.total_amount == Decimal('1190.00')

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_by_id_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        inv = repo.get_by_id(999)
        assert inv is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_exists_by_message_id_true(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'?column?': 1}

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        from core.connectors.efactura.config import InvoiceDirection
        repo = InvoiceRepository()
        result = repo.exists_by_message_id('12345', InvoiceDirection.RECEIVED, 'MSG-1')
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_exists_by_message_id_false(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        from core.connectors.efactura.config import InvoiceDirection
        repo = InvoiceRepository()
        result = repo.exists_by_message_id('12345', InvoiceDirection.RECEIVED, 'MSG-X')
        assert result is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_ignore_invoice(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.ignore_invoice(10, ignored=True)
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_is_allocated_true(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'jarvis_invoice_id': 42}

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.is_allocated(10)
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_is_allocated_false(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'jarvis_invoice_id': None}

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.is_allocated(10)
        assert result is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_invoice(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.delete_invoice(10)
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_restore_from_bin(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.restore_from_bin(10)
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_count_unallocated(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'total': 15}

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.count_unallocated('12345678')
        assert result == 15

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_count_hidden(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'total': 7}

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.count_hidden()
        assert result == 7

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_count_deleted(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'total': 3}

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.count_deleted()
        assert result == 3

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_external_ref(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 1, 'invoice_id': 10, 'external_system': 'anaf',
            'message_id': 'MSG-1', 'upload_id': None, 'download_id': 'DL-1',
            'xml_hash': 'abc123', 'signature_hash': None,
            'raw_response_hash': None, 'created_at': datetime.now(),
        }

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        ref = repo.get_external_ref(10)
        assert ref is not None
        assert ref.message_id == 'MSG-1'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_artifacts(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'invoice_id': 10, 'artifact_type': 'zip',
             'storage_uri': '/path/to/file.zip', 'original_filename': 'invoice.zip',
             'mime_type': 'application/zip', 'checksum': 'abc', 'size_bytes': 1024,
             'created_at': datetime.now()},
            {'id': 2, 'invoice_id': 10, 'artifact_type': 'xml',
             'storage_uri': '/path/to/file.xml', 'original_filename': 'invoice.xml',
             'mime_type': 'application/xml', 'checksum': 'def', 'size_bytes': 512,
             'created_at': datetime.now()},
        ]

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        artifacts = repo.get_artifacts(10)
        assert len(artifacts) == 2

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_overrides(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.update_overrides(
            invoice_id=10,
            type_override='Service',
            department_override='Marketing',
        )
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_bulk_delete(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 3

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.bulk_delete([1, 2, 3])
        assert result == 3

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_bulk_restore_from_bin(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 2

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.bulk_restore_from_bin([5, 6])
        assert result == 2

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_bulk_hide(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 4

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository as InvoiceRepository
        repo = InvoiceRepository()
        result = repo.bulk_hide([1, 2, 3, 4])
        assert result == 4


# ═══════════════════════════════════════════════
# SupplierTypeRepository Tests
# ═══════════════════════════════════════════════

class TestSupplierTypeRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Service', 'description': None,
             'hide_in_filter': True, 'is_active': True,
             'created_at': datetime.now(), 'updated_at': datetime.now()},
            {'id': 2, 'name': 'Merchandise', 'description': None,
             'hide_in_filter': True, 'is_active': True,
             'created_at': datetime.now(), 'updated_at': datetime.now()},
        ]

        from core.connectors.efactura.repositories.supplier_type_repository import SupplierTypeRepository
        repo = SupplierTypeRepository()
        types = repo.get_all(active_only=True)
        assert len(types) == 2
        assert types[0]['name'] == 'Service'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 3}

        from core.connectors.efactura.repositories.supplier_type_repository import SupplierTypeRepository
        repo = SupplierTypeRepository()
        type_id = repo.create(name='Equipment', description='Office equipment')
        assert type_id == 3
        mock_conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_soft(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.connectors.efactura.repositories.supplier_type_repository import SupplierTypeRepository
        repo = SupplierTypeRepository()
        result = repo.delete(1)
        assert result is True


class TestUnallocatedLifecycle:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_soft_delete_old_unallocated(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 7

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        count = repo.soft_delete_old_unallocated(days=10)

        assert count == 7
        sql = mock_cursor.execute.call_args[0][0]
        assert 'UPDATE efactura_invoices' in sql
        assert 'SET deleted_at = NOW()' in sql
        assert 'jarvis_invoice_id IS NULL' in sql
        assert 'ignored = FALSE' in sql
        assert 'deleted_at IS NULL' in sql
        assert 'created_at <' in sql
        mock_conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_purge_binned_old(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 3

        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        count = repo.purge_binned_old(days=10)

        assert count == 3
        sql = mock_cursor.execute.call_args[0][0]
        assert 'DELETE FROM efactura_invoices' in sql
        assert 'jarvis_invoice_id IS NULL' in sql
        assert 'deleted_at IS NOT NULL' in sql
        assert 'deleted_at <' in sql
        mock_conn.commit.assert_called()
