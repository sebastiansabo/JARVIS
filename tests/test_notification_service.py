"""Unit tests for Notification Service module.

Tests for:
- notification_service.py: Email sending, SMTP configuration, allocation notifications
"""
import sys
import os

# Set dummy DATABASE_URL before importing modules that require it
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.services.notification_service import (
    get_smtp_config,
    is_smtp_configured,
    send_email,
    send_test_email,
    format_currency,
    create_allocation_email_html,
    create_allocation_email_text,
    find_responsables_for_allocation,
    notify_allocation,
    notify_invoice_allocations
)


# ============== SMTP CONFIGURATION TESTS ==============

class TestGetSmtpConfig:
    """Tests for get_smtp_config() function."""

    @patch('core.services.notification_service.get_notification_settings')
    def test_returns_config_dict(self, mock_settings):
        mock_settings.return_value = {
            'smtp_host': 'smtp.example.com',
            'smtp_port': '587',
            'smtp_tls': 'true',
            'smtp_username': 'user@example.com',
            'smtp_password': 'password123',
            'from_email': 'noreply@example.com',
            'from_name': 'Test System',
            'global_cc': 'cc@example.com'
        }

        config = get_smtp_config()

        assert config['host'] == 'smtp.example.com'
        assert config['port'] == 587
        assert config['use_tls'] is True
        assert config['username'] == 'user@example.com'
        assert config['password'] == 'password123'
        assert config['from_email'] == 'noreply@example.com'
        assert config['from_name'] == 'Test System'
        assert config['global_cc'] == 'cc@example.com'

    @patch('core.services.notification_service.get_notification_settings')
    def test_default_port(self, mock_settings):
        """Should default to port 587 if not specified"""
        mock_settings.return_value = {
            'smtp_port': None
        }

        config = get_smtp_config()

        assert config['port'] == 587

    @patch('core.services.notification_service.get_notification_settings')
    def test_tls_defaults_to_true(self, mock_settings):
        """Should default TLS to true when key is missing"""
        # Don't include smtp_tls key - let it use default
        mock_settings.return_value = {
            'smtp_host': 'smtp.example.com'
        }

        config = get_smtp_config()

        # When smtp_tls key is missing, settings.get('smtp_tls', 'true') returns 'true'
        assert config['use_tls'] is True

    @patch('core.services.notification_service.get_notification_settings')
    def test_handles_empty_settings(self, mock_settings):
        mock_settings.return_value = {}

        config = get_smtp_config()

        assert config['host'] == ''
        assert config['from_email'] == ''


class TestIsSmtpConfigured:
    """Tests for is_smtp_configured() function."""

    @patch('core.services.notification_service.get_smtp_config')
    def test_returns_true_when_configured(self, mock_config):
        mock_config.return_value = {
            'host': 'smtp.example.com',
            'from_email': 'noreply@example.com'
        }

        assert is_smtp_configured() is True

    @patch('core.services.notification_service.get_smtp_config')
    def test_returns_false_without_host(self, mock_config):
        mock_config.return_value = {
            'host': '',
            'from_email': 'noreply@example.com'
        }

        assert is_smtp_configured() is False

    @patch('core.services.notification_service.get_smtp_config')
    def test_returns_false_without_from_email(self, mock_config):
        mock_config.return_value = {
            'host': 'smtp.example.com',
            'from_email': ''
        }

        assert is_smtp_configured() is False


# ============== SEND EMAIL TESTS ==============

class TestSendEmail:
    """Tests for send_email() function."""

    @patch('core.services.notification_service.get_smtp_config')
    def test_returns_error_without_host(self, mock_config):
        mock_config.return_value = {'host': '', 'from_email': 'test@example.com'}

        success, error = send_email('to@example.com', 'Subject', '<p>Body</p>')

        assert success is False
        assert 'SMTP host not configured' in error

    @patch('core.services.notification_service.get_smtp_config')
    def test_returns_error_without_from_email(self, mock_config):
        mock_config.return_value = {'host': 'smtp.example.com', 'from_email': ''}

        success, error = send_email('to@example.com', 'Subject', '<p>Body</p>')

        assert success is False
        assert 'From email not configured' in error

    @patch('core.services.notification_service.smtplib.SMTP')
    @patch('core.services.notification_service.get_smtp_config')
    def test_sends_email_with_tls(self, mock_config, mock_smtp):
        mock_config.return_value = {
            'host': 'smtp.example.com',
            'port': 587,
            'use_tls': True,
            'username': 'user',
            'password': 'pass',
            'from_email': 'from@example.com',
            'from_name': 'Test',
            'global_cc': ''
        }

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        success, error = send_email('to@example.com', 'Test Subject', '<p>HTML</p>', 'Plain text')

        assert success is True
        assert error == ''
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with('user', 'pass')

    @patch('core.services.notification_service.smtplib.SMTP')
    @patch('core.services.notification_service.get_smtp_config')
    def test_includes_global_cc(self, mock_config, mock_smtp):
        mock_config.return_value = {
            'host': 'smtp.example.com',
            'port': 587,
            'use_tls': False,
            'username': '',
            'password': '',
            'from_email': 'from@example.com',
            'from_name': '',
            'global_cc': 'cc@example.com'
        }

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        send_email('to@example.com', 'Subject', '<p>Body</p>')

        # Check that CC was included in recipients
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]  # Second positional arg is recipients list
        assert 'cc@example.com' in recipients

    @patch('core.services.notification_service.smtplib.SMTP')
    @patch('core.services.notification_service.get_smtp_config')
    def test_includes_department_cc(self, mock_config, mock_smtp):
        mock_config.return_value = {
            'host': 'smtp.example.com',
            'port': 587,
            'use_tls': False,
            'username': '',
            'password': '',
            'from_email': 'from@example.com',
            'from_name': '',
            'global_cc': ''
        }

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        send_email('to@example.com', 'Subject', '<p>Body</p>', department_cc='dept@example.com')

        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        assert 'dept@example.com' in recipients

    @patch('core.services.notification_service.smtplib.SMTP')
    @patch('core.services.notification_service.get_smtp_config')
    def test_handles_smtp_auth_error(self, mock_config, mock_smtp):
        import smtplib
        mock_config.return_value = {
            'host': 'smtp.example.com',
            'port': 587,
            'use_tls': True,
            'username': 'user',
            'password': 'wrong',
            'from_email': 'from@example.com',
            'from_name': '',
            'global_cc': ''
        }

        mock_smtp.side_effect = smtplib.SMTPAuthenticationError(535, b'Authentication failed')

        success, error = send_email('to@example.com', 'Subject', '<p>Body</p>')

        assert success is False
        assert 'authentication failed' in error.lower()


# ============== FORMAT CURRENCY TESTS ==============

class TestFormatCurrency:
    """Tests for format_currency() function."""

    def test_formats_ron(self):
        result = format_currency(1234.56, 'RON')
        assert result == '1,234.56 RON'

    def test_formats_eur(self):
        result = format_currency(100.00, 'EUR')
        assert result == '100.00 EUR'

    def test_default_currency_ron(self):
        result = format_currency(500.00)
        assert 'RON' in result

    def test_handles_large_numbers(self):
        result = format_currency(1234567.89, 'RON')
        assert '1,234,567.89' in result


# ============== EMAIL TEMPLATE TESTS ==============

class TestCreateAllocationEmailHtml:
    """Tests for create_allocation_email_html() function."""

    def test_includes_responsable_name(self):
        html = create_allocation_email_html(
            'John Doe',
            {'invoice_number': 'INV-001', 'supplier': 'Test', 'invoice_date': '2025-12-15',
             'invoice_value': 100, 'currency': 'RON'},
            {'company': 'TestCo', 'department': 'Marketing', 'allocation_percent': 50,
             'allocation_value': 50}
        )

        assert 'John Doe' in html

    def test_includes_invoice_number(self):
        html = create_allocation_email_html(
            'User',
            {'invoice_number': 'INV-2025-001', 'supplier': 'Supplier', 'invoice_date': '2025-12-15',
             'invoice_value': 100, 'currency': 'RON'},
            {'company': 'Co', 'department': 'Dept', 'allocation_percent': 100, 'allocation_value': 100}
        )

        assert 'INV-2025-001' in html

    def test_includes_allocation_percent(self):
        html = create_allocation_email_html(
            'User',
            {'invoice_number': 'INV-001', 'supplier': 'S', 'invoice_date': 'd', 'invoice_value': 100, 'currency': 'RON'},
            {'company': 'Co', 'department': 'Dept', 'allocation_percent': 75, 'allocation_value': 75}
        )

        assert '75%' in html

    def test_includes_reinvoice_section(self):
        html = create_allocation_email_html(
            'User',
            {'invoice_number': 'INV-001', 'supplier': 'S', 'invoice_date': 'd', 'invoice_value': 100, 'currency': 'RON'},
            {'company': 'Co', 'department': 'Dept', 'allocation_percent': 100, 'allocation_value': 100,
             'reinvoice_to': 'Other Company', 'reinvoice_department': 'Other Dept'}
        )

        assert 'Other Company' in html
        assert 'Refacturare' in html

    def test_brand_shown_when_present(self):
        html = create_allocation_email_html(
            'User',
            {'invoice_number': 'INV-001', 'supplier': 'S', 'invoice_date': 'd', 'invoice_value': 100, 'currency': 'RON'},
            {'company': 'Co', 'brand': 'BrandX', 'department': 'Dept', 'allocation_percent': 100, 'allocation_value': 100}
        )

        assert 'BrandX' in html


class TestCreateAllocationEmailText:
    """Tests for create_allocation_email_text() function."""

    def test_includes_invoice_details(self):
        text = create_allocation_email_text(
            'User',
            {'invoice_number': 'INV-001', 'supplier': 'Test Supplier', 'invoice_date': '2025-12-15',
             'invoice_value': 1000, 'currency': 'RON'},
            {'company': 'Co', 'department': 'Dept', 'allocation_percent': 50, 'allocation_value': 500}
        )

        assert 'INV-001' in text
        assert 'Test Supplier' in text
        assert '2025-12-15' in text

    def test_includes_allocation_details(self):
        text = create_allocation_email_text(
            'User',
            {'invoice_number': 'INV-001', 'supplier': 'S', 'invoice_date': 'd', 'invoice_value': 100, 'currency': 'RON'},
            {'company': 'TestCo', 'department': 'Marketing', 'allocation_percent': 100, 'allocation_value': 100}
        )

        assert 'TestCo' in text
        assert 'Marketing' in text


# ============== FIND RESPONSABLES TESTS ==============

class TestFindResponsablesForAllocation:
    """Tests for find_responsables_for_allocation() function."""

    @patch('core.services.notification_service.get_managers_for_department')
    def test_finds_department_responsables(self, mock_get):
        mock_get.return_value = [
            {'id': 1, 'name': 'John', 'is_active': True, 'notify_on_allocation': True}
        ]

        allocation = {'department': 'Marketing'}
        result = find_responsables_for_allocation(allocation)

        assert len(result) == 1
        assert result[0]['name'] == 'John'

    @patch('core.services.notification_service.get_managers_for_department')
    def test_excludes_inactive_responsables(self, mock_get):
        mock_get.return_value = [
            {'id': 1, 'name': 'Active', 'is_active': True, 'notify_on_allocation': True},
            {'id': 2, 'name': 'Inactive', 'is_active': False, 'notify_on_allocation': True}
        ]

        allocation = {'department': 'Marketing'}
        result = find_responsables_for_allocation(allocation)

        assert len(result) == 1
        assert result[0]['name'] == 'Active'

    @patch('core.services.notification_service._allocation_email_allowed')
    @patch('core.services.notification_service.get_managers_for_department')
    def test_excludes_users_who_disabled_allocation_email(self, mock_get, mock_allowed):
        # Filtering is now by the per-user 'allocation' email preference (migrated
        # from users.notify_on_allocation), not the legacy column.
        mock_get.return_value = [
            {'id': 1, 'name': 'Wants', 'is_active': True},
            {'id': 2, 'name': 'Opted out', 'is_active': True},
        ]
        mock_allowed.return_value = {1}  # user 2 disabled allocation email

        result = find_responsables_for_allocation({'department': 'Marketing'})

        assert [r['id'] for r in result] == [1]
        assert result[0]['name'] == 'Wants'

    @patch('core.services.notification_service.get_managers_for_department')
    def test_includes_reinvoice_department(self, mock_get):
        def side_effect(dept, company=None):
            if dept == 'Marketing':
                return [{'id': 1, 'name': 'Marketing Person', 'is_active': True, 'notify_on_allocation': True}]
            elif dept == 'Sales':
                return [{'id': 2, 'name': 'Sales Person', 'is_active': True, 'notify_on_allocation': True}]
            return []

        mock_get.side_effect = side_effect

        allocation = {
            'department': 'Marketing',
            'reinvoice_to': 'Other Co',
            'reinvoice_department': 'Sales'
        }
        result = find_responsables_for_allocation(allocation)

        assert len(result) == 2

    @patch('core.services.notification_service.get_managers_for_department')
    def test_deduplicates_responsables(self, mock_get):
        """Same person in both departments should only appear once"""
        mock_get.return_value = [
            {'id': 1, 'name': 'Same Person', 'is_active': True, 'notify_on_allocation': True}
        ]

        allocation = {
            'department': 'Marketing',
            'reinvoice_to': 'Co',
            'reinvoice_department': 'Marketing'  # Same department
        }
        result = find_responsables_for_allocation(allocation)

        assert len(result) == 1


# ============== NOTIFY ALLOCATION TESTS ==============

class TestNotifyAllocation:
    """Tests for notify_allocation() function."""

    @patch('core.services.notification_service.is_smtp_configured')
    def test_skips_if_smtp_not_configured(self, mock_configured):
        mock_configured.return_value = False

        result = notify_allocation({}, {})

        assert result == []

    @patch('core.services.notification_service.send_email')
    @patch('core.services.notification_service.log_notification')
    @patch('core.services.notification_service.update_notification_status')
    @patch('core.services.notification_service.get_department_cc_email')
    @patch('core.services.notification_service.find_responsables_for_allocation')
    @patch('core.services.notification_service.is_smtp_configured')
    def test_sends_to_each_responsable(self, mock_configured, mock_find, mock_cc, mock_update, mock_log, mock_send):
        mock_configured.return_value = True
        mock_find.return_value = [
            {'id': 1, 'name': 'User 1', 'email': 'user1@example.com'},
            {'id': 2, 'name': 'User 2', 'email': 'user2@example.com'}
        ]
        mock_cc.return_value = None
        mock_log.return_value = 1
        mock_send.return_value = (True, '')

        invoice_data = {'id': 1, 'invoice_number': 'INV-001', 'invoice_value': 100}
        allocation = {'company': 'Co', 'department': 'Dept', 'allocation_percent': 100}

        result = notify_allocation(invoice_data, allocation)

        assert len(result) == 2
        assert mock_send.call_count == 2

    @patch('core.services.notification_service.send_email')
    @patch('core.services.notification_service.log_notification')
    @patch('core.services.notification_service.update_notification_status')
    @patch('core.services.notification_service.get_department_cc_email')
    @patch('core.services.notification_service.find_responsables_for_allocation')
    @patch('core.services.notification_service.is_smtp_configured')
    def test_skips_responsable_without_email(self, mock_configured, mock_find, mock_cc, mock_update, mock_log, mock_send):
        mock_configured.return_value = True
        mock_find.return_value = [
            {'id': 1, 'name': 'No Email', 'email': None},
            {'id': 2, 'name': 'Has Email', 'email': 'user@example.com'}
        ]
        mock_cc.return_value = None
        mock_log.return_value = 1
        mock_send.return_value = (True, '')

        result = notify_allocation({'id': 1, 'invoice_number': 'INV', 'invoice_value': 100},
                                  {'company': 'Co', 'department': 'D', 'allocation_percent': 100})

        assert mock_send.call_count == 1


# ============== NOTIFY INVOICE ALLOCATIONS TESTS ==============

class TestNotifyInvoiceAllocations:
    """Tests for notify_invoice_allocations() function."""

    @patch('core.services.notification_service.notify_allocation')
    def test_calls_notify_for_each_allocation(self, mock_notify):
        mock_notify.return_value = [{'success': True}]

        invoice_data = {'id': 1, 'invoice_number': 'INV-001'}
        allocations = [
            {'company': 'Co1', 'department': 'D1'},
            {'company': 'Co2', 'department': 'D2'}
        ]

        result = notify_invoice_allocations(invoice_data, allocations)

        assert mock_notify.call_count == 2
        assert len(result) == 2

    @patch('core.services.notification_service.notify_allocation')
    def test_empty_allocations(self, mock_notify):
        result = notify_invoice_allocations({}, [])

        assert result == []
        mock_notify.assert_not_called()


# ============== TEST EMAIL TESTS ==============

class TestSendTestEmail:
    """Tests for send_test_email() function."""

    @patch('core.services.notification_service.send_email')
    def test_sends_test_email(self, mock_send):
        mock_send.return_value = (True, '')

        success, error = send_test_email('test@example.com')

        assert success is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert 'Test Email' in call_args[0][1]  # Subject
        assert 'test@example.com' == call_args[0][0]  # To address


# Run with: pytest tests/test_notification_service.py -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
