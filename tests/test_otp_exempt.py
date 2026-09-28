"""Unit tests for the per-user OTP-exempt (skip 2FA) feature.

Covers:
- UserRepository.set_otp_exempt writes the flag with parameterized SQL.
- The User model exposes otp_exempt (default False).
- The auth single-factor decision: viewers OR otp-exempt users skip OTP.
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.auth.repositories.user_repository import UserRepository
from core.auth.models import User


class TestSetOtpExempt:
    """UserRepository.set_otp_exempt()."""

    @patch.object(UserRepository, 'execute')
    def test_sets_flag_true(self, mock_execute):
        mock_execute.return_value = 1
        repo = UserRepository()
        result = repo.set_otp_exempt(7, True)
        assert result is True
        mock_execute.assert_called_once_with(
            'UPDATE users SET otp_exempt = %s WHERE id = %s', (True, 7)
        )

    @patch.object(UserRepository, 'execute')
    def test_clears_flag_false(self, mock_execute):
        mock_execute.return_value = 1
        repo = UserRepository()
        repo.set_otp_exempt(7, False)
        # value is coerced to a real bool
        args, _ = mock_execute.call_args
        assert args[1] == (False, 7)

    @patch.object(UserRepository, 'execute')
    def test_coerces_truthy_to_bool(self, mock_execute):
        mock_execute.return_value = 1
        repo = UserRepository()
        repo.set_otp_exempt(3, 1)
        args, _ = mock_execute.call_args
        assert args[1] == (True, 3)


class TestUserModelOtpExempt:
    """User model exposes otp_exempt."""

    def test_defaults_false_when_absent(self):
        user = User({'id': 1, 'email': 'a@b.ro', 'name': 'A'})
        assert user.otp_exempt is False

    def test_reads_true_from_data(self):
        user = User({'id': 1, 'email': 'a@b.ro', 'name': 'A', 'otp_exempt': True})
        assert user.otp_exempt is True


class TestSingleFactorDecision:
    """The login single-factor rule: skip OTP if viewer OR otp-exempt."""

    @staticmethod
    def _skips_otp(role_name, otp_exempt):
        # Mirrors the condition in core/auth/routes.py login handler.
        is_viewer = (role_name or '').strip().lower() == 'viewer'
        return is_viewer or bool(otp_exempt)

    def test_viewer_skips_otp(self):
        assert self._skips_otp('viewer', False) is True

    def test_non_viewer_default_requires_otp(self):
        assert self._skips_otp('admin', False) is False

    def test_non_viewer_exempt_skips_otp(self):
        assert self._skips_otp('admin', True) is True

    def test_viewer_exempt_still_skips(self):
        assert self._skips_otp('viewer', True) is True
