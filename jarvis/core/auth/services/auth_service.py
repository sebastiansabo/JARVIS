"""Auth Service - Business logic for authentication operations.

This module contains all business logic related to authentication.
Routes should call these methods instead of accessing the database directly.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from werkzeug.security import check_password_hash
from dataclasses import dataclass
import hmac
import hashlib
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from core.utils.logging_config import get_logger

logger = get_logger('jarvis.auth')

from ..repositories.user_repository import UserRepository
from ..repositories.event_repository import EventRepository


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    user_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AuthService:
    """Service for authentication-related business logic."""

    def __init__(self):
        self.user_repo = UserRepository()
        self.event_repo = EventRepository()

    def authenticate(self, email: str, password: str) -> AuthResult:
        """Authenticate a user by email and password.

        Args:
            email: The user's email address
            password: The user's password

        Returns:
            AuthResult with success status and user data if successful
        """
        if not email or not password:
            return AuthResult(success=False, error='Email and password are required')

        user = self.user_repo.get_by_email(email)

        if not user:
            return AuthResult(success=False, error='Invalid email or password')

        if not user.get('is_active', False):
            return AuthResult(success=False, error='Account is inactive')

        if not user.get('password_hash'):
            return AuthResult(success=False, error='Password not set')

        if not check_password_hash(user['password_hash'], password):
            return AuthResult(success=False, error='Invalid email or password')

        return AuthResult(success=True, user_data=user)

    def change_password(
        self,
        user_id: int,
        user_email: str,
        current_password: str,
        new_password: str
    ) -> AuthResult:
        """Change a user's password.

        Args:
            user_id: The user's ID
            user_email: The user's email (for verification)
            current_password: The current password
            new_password: The new password

        Returns:
            AuthResult with success status
        """
        if not current_password or not new_password:
            return AuthResult(success=False, error='Both current and new password required')

        if len(new_password) < 10:
            return AuthResult(success=False, error='New password must be at least 10 characters')

        # Verify current password
        auth_result = self.authenticate(user_email, current_password)
        if not auth_result.success:
            return AuthResult(success=False, error='Current password is incorrect')

        # Set new password
        if self.user_repo.update_password(user_id, new_password):
            return AuthResult(success=True)
        else:
            return AuthResult(success=False, error='Failed to update password')

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user by their ID.

        Args:
            user_id: The user's ID

        Returns:
            User dict or None if not found
        """
        return self.user_repo.get_by_id(user_id)

    def update_last_login(self, user_id: int) -> bool:
        """Update the last login timestamp for a user.

        Args:
            user_id: The user's ID

        Returns:
            True if successful
        """
        return self.user_repo.update_last_login(user_id)

    def update_last_seen(self, user_id: int) -> bool:
        """Update the last seen timestamp for a user (heartbeat).

        Args:
            user_id: The user's ID

        Returns:
            True if successful
        """
        return self.user_repo.update_last_seen(user_id)

    def get_online_users(self, minutes: int = 5) -> Dict[str, Any]:
        """Get count and list of currently online users.

        Args:
            minutes: Number of minutes to consider a user "online"

        Returns:
            Dict with 'count' and 'users' list
        """
        users = self.user_repo.get_online_users(minutes)
        return {
            'count': len(users),
            'users': users
        }

    def log_event(
        self,
        event_type: str,
        description: str = None,
        user_id: int = None,
        user_email: str = None,
        entity_type: str = None,
        entity_id: int = None,
        ip_address: str = None,
        user_agent: str = None,
        details: Dict[str, Any] = None
    ) -> int:
        """Log a user event for audit purposes.

        Args:
            event_type: Type of event (login, logout, etc.)
            description: Human-readable description
            user_id: ID of the user
            user_email: Email of the user
            entity_type: Type of entity affected
            entity_id: ID of the entity
            ip_address: Request IP address
            user_agent: Request user agent
            details: Additional details as dict

        Returns:
            The event ID
        """
        return self.event_repo.log_event(
            event_type=event_type,
            event_description=description,
            user_id=user_id,
            user_email=user_email,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )

    # --- Password Reset Methods ---

    def request_password_reset(self, email: str, base_url: str) -> AuthResult:
        """Request a password reset for a user.

        Always returns success to prevent email enumeration.

        Args:
            email: The user's email address
            base_url: The base URL for building the reset link

        Returns:
            AuthResult (always success=True to prevent enumeration)
        """
        if not email:
            return AuthResult(success=True)

        user = self.user_repo.get_by_email(email)

        if not user or not user.get('is_active', False):
            # Don't reveal whether the email exists
            return AuthResult(success=True)

        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        if not self.user_repo.create_reset_token(user['id'], token, expires_at):
            logger.error(f"Failed to create reset token for user {user['id']}")
            return AuthResult(success=True)

        # Send reset email
        reset_url = f"{base_url.rstrip('/')}/reset-password/{token}"
        self._send_reset_email(user['name'], user['email'], reset_url)

        return AuthResult(success=True)

    def reset_password(self, token: str, new_password: str) -> AuthResult:
        """Reset a user's password using a valid token.

        Args:
            token: The reset token
            new_password: The new password

        Returns:
            AuthResult with success status
        """
        if not token or not new_password:
            return AuthResult(success=False, error='Token and password are required')

        if len(new_password) < 6:
            return AuthResult(success=False, error='Password must be at least 6 characters')

        token_data = self.user_repo.get_reset_token(token)
        if not token_data:
            return AuthResult(success=False, error='Invalid or expired reset link')

        # Update password
        if not self.user_repo.update_password(token_data['user_id'], new_password):
            return AuthResult(success=False, error='Failed to update password')

        # Mark token as used
        self.user_repo.mark_token_used(token)

        logger.info(f"Password reset completed for user {token_data['email']}")
        return AuthResult(success=True)

    def validate_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Check if a reset token is valid.

        Args:
            token: The reset token

        Returns:
            Token data dict if valid, None otherwise
        """
        return self.user_repo.get_reset_token(token)

    def _send_reset_email(self, name: str, email: str, reset_url: str):
        """Send a password reset email."""
        from core.services.notification_service import send_email, is_smtp_configured

        if not is_smtp_configured():
            logger.warning("SMTP not configured - cannot send password reset email")
            return

        subject = "J.A.R.V.I.S. - Password Reset"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #333; font-size: 24px; margin: 0;">J.A.R.V.I.S.</h1>
                <p style="color: #666; margin: 5px 0 0;">Password Reset</p>
            </div>
            <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; margin-bottom: 20px;">
                <p style="margin: 0 0 15px; color: #333;">Hi {name},</p>
                <p style="margin: 0 0 15px; color: #333;">We received a request to reset your password. Click the button below to set a new password:</p>
                <div style="text-align: center; margin: 25px 0;">
                    <a href="{reset_url}" style="background: #0d6efd; color: #fff; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 500; display: inline-block;">Reset Password</a>
                </div>
                <p style="margin: 0 0 10px; color: #666; font-size: 14px;">This link expires in <strong>1 hour</strong>.</p>
                <p style="margin: 0; color: #666; font-size: 14px;">If you didn't request this, you can safely ignore this email.</p>
            </div>
            <div style="text-align: center; color: #999; font-size: 12px;">
                <p style="margin: 0;">If the button doesn't work, copy this link:<br>
                <a href="{reset_url}" style="color: #0d6efd; word-break: break-all;">{reset_url}</a></p>
            </div>
        </div>
        """

        text_body = f"""J.A.R.V.I.S. - Password Reset

Hi {name},

We received a request to reset your password. Visit the link below to set a new password:

{reset_url}

This link expires in 1 hour.

If you didn't request this, you can safely ignore this email.
"""

        success, error = send_email(email, subject, html_body, text_body, skip_global_cc=True)
        if not success:
            logger.error(f"Failed to send reset email to {email}: {error}")
        else:
            logger.info(f"Password reset email sent to {email}")

    # --- OTP Two-Factor Authentication Methods ---

    OTP_EXPIRY_MINUTES = 5
    OTP_MAX_ATTEMPTS = 5
    OTP_MAX_SENDS = 3
    TRUSTED_DEVICE_MAX_AGE = 30 * 24 * 3600  # 30 days in seconds
    TRUSTED_COOKIE_NAME = 'jarvis_trusted_device'

    def _generate_otp_code(self) -> str:
        """Generate a cryptographically random 6-digit OTP code."""
        return f'{secrets.randbelow(1000000):06d}'

    def _hash_otp(self, code: str, secret_key: str) -> str:
        """HMAC-hash an OTP code so only the hash is stored in DB."""
        return hmac.new(secret_key.encode(), code.encode(), 'sha256').hexdigest()

    def _compare_otp(self, submitted_hash: str, stored_hash: str) -> bool:
        """Compare OTP hashes using timing-safe comparison."""
        return hmac.compare_digest(submitted_hash, stored_hash)

    def _compute_device_hash(self, user_agent: str, ip_address: str) -> str:
        """Compute a device fingerprint hash from User-Agent and IP /24 prefix."""
        ip_parts = ip_address.split('.')
        ip_prefix = '.'.join(ip_parts[:3]) if len(ip_parts) == 4 else ip_address
        raw = f'{user_agent}|{ip_prefix}'
        return hashlib.sha256(raw.encode()).hexdigest()

    def generate_and_send_otp(self, user_id: int, user_email: str, user_name: str, secret_key: str) -> tuple:
        """Generate OTP, store hash in DB, send plaintext via email.

        Returns:
            (otp_id, success, error_message)
        """
        code = self._generate_otp_code()
        code_hash = self._hash_otp(code, secret_key)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        otp_id = self.user_repo.create_otp(user_id, code_hash, expires_at)
        if not otp_id:
            logger.error(f"Failed to create OTP for user {user_id}")
            return None, False, "Failed to generate verification code"

        success, error = self._send_otp_email(user_name, user_email, code)
        return otp_id, success, error

    def resend_otp(self, otp_id: int, user_email: str, user_name: str, secret_key: str) -> tuple:
        """Regenerate code for existing OTP row and resend email.

        Returns:
            (success, error_message, blocked)
            blocked: True if max sends reached
        """
        otp = self.user_repo.get_otp(otp_id)
        if not otp or otp['used_at']:
            return False, "Invalid verification session", True

        if otp['send_count'] >= self.OTP_MAX_SENDS:
            return False, "Maximum resend attempts reached. Please log in again.", True

        new_code = self._generate_otp_code()
        new_code_hash = self._hash_otp(new_code, secret_key)
        new_expires = datetime.now(timezone.utc) + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        if not self.user_repo.update_otp_for_resend(otp_id, new_code_hash, new_expires):
            return False, "Failed to regenerate code", False

        success, error = self._send_otp_email(user_name, user_email, new_code)
        if not success:
            updated_otp = self.user_repo.get_otp(otp_id)
            if updated_otp and updated_otp['send_count'] >= self.OTP_MAX_SENDS:
                return False, "Unable to send verification code. Please try again later.", True
        return success, error, False

    def verify_otp(self, otp_id: int, submitted_code: str, secret_key: str) -> tuple:
        """Verify a submitted OTP code.

        Returns:
            (success, error_message)
        """
        otp = self.user_repo.get_otp(otp_id)
        if not otp or otp['used_at']:
            return False, "Invalid verification session. Please log in again."

        now = datetime.now(timezone.utc)
        expires_at = otp['expires_at']
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            return False, "Code expired. Please request a new one."

        if otp['attempts'] >= self.OTP_MAX_ATTEMPTS:
            return False, "Too many wrong attempts. Please request a new code."

        submitted_hash = self._hash_otp(submitted_code.strip(), secret_key)
        if not self._compare_otp(submitted_hash, otp['code']):
            self.user_repo.increment_otp_attempts(otp_id)
            remaining = self.OTP_MAX_ATTEMPTS - otp['attempts'] - 1
            if remaining <= 0:
                return False, "Too many wrong attempts. Please request a new code."
            return False, f"Invalid code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."

        self.user_repo.mark_otp_used(otp_id)
        return True, ""

    def create_trusted_device_cookie(self, user_id: int, user_agent: str, ip_address: str, secret_key: str) -> str:
        """Create a signed trusted device cookie value."""
        s = URLSafeTimedSerializer(secret_key)
        device_hash = self._compute_device_hash(user_agent, ip_address)
        return s.dumps({'uid': user_id, 'dh': device_hash})

    def validate_trusted_device_cookie(self, cookie_value: str, user_id: int, user_agent: str, ip_address: str, secret_key: str) -> bool:
        """Validate a trusted device cookie."""
        if not cookie_value:
            return False
        s = URLSafeTimedSerializer(secret_key)
        try:
            data = s.loads(cookie_value, max_age=self.TRUSTED_DEVICE_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False

        if data.get('uid') != user_id:
            return False

        expected_hash = self._compute_device_hash(user_agent, ip_address)
        return hmac.compare_digest(data.get('dh', ''), expected_hash)

    def _send_otp_email(self, name: str, email: str, code: str) -> tuple:
        """Send OTP verification email. Returns (success, error_message)."""
        from core.services.notification_service import send_email, is_smtp_configured

        if not is_smtp_configured():
            logger.warning("SMTP not configured - cannot send OTP email")
            return False, "Email service not configured"

        subject = "J.A.R.V.I.S. \u2014 Your login verification code"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #333; font-size: 24px; margin: 0;">J.A.R.V.I.S.</h1>
                <p style="color: #666; margin: 5px 0 0;">Login Verification</p>
            </div>
            <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; margin-bottom: 20px;">
                <p style="margin: 0 0 15px; color: #333;">Hi {name},</p>
                <p style="margin: 0 0 20px; color: #333;">Your verification code is:</p>
                <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #333; background: #fff; padding: 20px; text-align: center; border-radius: 8px; border: 2px solid #e9ecef; margin: 0 0 20px;">
                    {code}
                </div>
                <p style="margin: 0 0 10px; color: #666; font-size: 14px;">This code expires in <strong>5 minutes</strong>.</p>
                <p style="margin: 0; color: #666; font-size: 14px;">If you did not attempt to log in, please ignore this email and consider changing your password.</p>
            </div>
            <div style="text-align: center; color: #999; font-size: 12px;">
                <p style="margin: 0;">This is an automated message from J.A.R.V.I.S.</p>
            </div>
        </div>
        """

        text_body = f"""J.A.R.V.I.S. \u2014 Login Verification

Hi {name},

Your verification code is: {code}

This code expires in 5 minutes.

If you did not attempt to log in, please ignore this email and consider changing your password.
"""

        success, error = send_email(email, subject, html_body, text_body, skip_global_cc=True)
        if not success:
            logger.error(f"Failed to send OTP email to {email}: {error}")
        else:
            logger.info(f"OTP email sent to {email}")
        return success, error
