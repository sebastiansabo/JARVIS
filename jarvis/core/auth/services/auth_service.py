"""Auth Service - Business logic for authentication operations.

This module contains all business logic related to authentication.
Routes should call these methods instead of accessing the database directly.
"""
from typing import Optional, Dict, Any, List
from werkzeug.security import check_password_hash
from dataclasses import dataclass

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

        if len(new_password) < 6:
            return AuthResult(success=False, error='New password must be at least 6 characters')

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
