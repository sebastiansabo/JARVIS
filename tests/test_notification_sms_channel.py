"""Tests for the SMS notification channel (smsapi.com, opt-in, fail-closed)."""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import database  # noqa: E402, F401

from unittest.mock import patch
from core.notifications.sms_service import normalize_ro_phone, send_sms_to_users


class TestNormalize:
    def test_local_mobile(self):
        assert normalize_ro_phone('0712345678') == '+40712345678'

    def test_spaced_international(self):
        assert normalize_ro_phone('+40 712 345 678') == '+40712345678'

    def test_double_zero_prefix(self):
        assert normalize_ro_phone('0040712345678') == '+40712345678'

    def test_bare_nine_digits(self):
        assert normalize_ro_phone('712345678') == '+40712345678'

    def test_landline_rejected(self):
        assert normalize_ro_phone('0212345678') is None

    def test_garbage_rejected(self):
        assert normalize_ro_phone('12345') is None
        assert normalize_ro_phone('') is None
        assert normalize_ro_phone(None) is None


class TestSend:
    def test_non_mandatory_no_optin_does_not_dispatch(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as R, \
             patch('core.notifications.sms_service._dispatch') as disp:
            R.return_value.preference_filter.return_value = []
            send_sms_to_users([1, 2], 'hi', category='chat')
        disp.assert_not_called()

    def test_mandatory_dispatches_normalized_unique_phones(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as R, \
             patch('core.notifications.sms_service._dispatch') as disp:
            R.return_value.get_contacts.return_value = {
                1: {'phone': '0712345678'}, 2: {'phone': None}, 3: {'phone': '+40712345678'},
            }
            send_sms_to_users([1, 2, 3], 'hi', category='approvals')  # mandatory
        disp.assert_called_once()
        assert disp.call_args.args[0] == ['+40712345678']  # user 2 skipped, dup deduped

    def test_gate_error_is_fail_closed(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as R, \
             patch('core.notifications.sms_service._dispatch') as disp:
            R.return_value.preference_filter.side_effect = RuntimeError('db down')
            send_sms_to_users([1, 2], 'hi', category='chat')
        disp.assert_not_called()  # never blast billed SMS on error

    def test_opted_in_non_mandatory_dispatches(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as R, \
             patch('core.notifications.sms_service._dispatch') as disp:
            R.return_value.preference_filter.return_value = [2]
            R.return_value.get_contacts.return_value = {2: {'phone': '0712345678'}}
            send_sms_to_users([1, 2], 'hi', category='chat')
        disp.assert_called_once()
        assert disp.call_args.args[0] == ['+40712345678']
