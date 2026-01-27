"""
ANAF e-Factura OAuth2 Service

Handles OAuth2 authentication flow with ANAF's logincert.anaf.ro.
Users authenticate once with their USB token via browser, then use
stored tokens for API calls until they expire.
"""

import os
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import requests

from core.utils.logging_config import get_logger
from ..config import DEFAULT_CONFIG

logger = get_logger('jarvis.core.connectors.efactura.oauth')

# Token validity defaults from ANAF OAuth documentation
ACCESS_TOKEN_VALIDITY_SECONDS = DEFAULT_CONFIG.OAUTH_ACCESS_TOKEN_VALIDITY_SECONDS  # 90 days


# ANAF OAuth2 endpoints
OAUTH_AUTHORIZE_URL = "https://logincert.anaf.ro/anaf-oauth2/v1/authorize"
OAUTH_TOKEN_URL = "https://logincert.anaf.ro/anaf-oauth2/v1/token"
OAUTH_REVOKE_URL = "https://logincert.anaf.ro/anaf-oauth2/v1/revoke"

# OAuth Client credentials (from ANAF registration)
# Set via environment variables for security
OAUTH_CLIENT_ID = os.environ.get('ANAF_OAUTH_CLIENT_ID', '')
OAUTH_CLIENT_SECRET = os.environ.get('ANAF_OAUTH_CLIENT_SECRET', '')

# Default redirect URI (must match ANAF registration)
DEFAULT_REDIRECT_URI = os.environ.get(
    'ANAF_OAUTH_REDIRECT_URI',
    "https://mkt-app-922ou.ondigitalocean.app/efactura/callback"
)


@dataclass
class OAuthTokens:
    """OAuth2 token data."""
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: datetime
    scope: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if access token is expired."""
        return datetime.utcnow() >= self.expires_at

    def expires_in_seconds(self) -> int:
        """Get seconds until expiration."""
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_type': self.token_type,
            'expires_at': self.expires_at.isoformat(),
            'scope': self.scope,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OAuthTokens':
        """Create from dictionary."""
        expires_at = data.get('expires_at')
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))

        return cls(
            access_token=data['access_token'],
            refresh_token=data['refresh_token'],
            token_type=data.get('token_type', 'Bearer'),
            expires_at=expires_at,
            scope=data.get('scope'),
        )


class ANAFOAuthService:
    """
    Service for ANAF OAuth2 authentication.

    Flow:
    1. Generate authorization URL with PKCE
    2. User authenticates with USB token in browser
    3. ANAF redirects back with authorization code
    4. Exchange code for access + refresh tokens
    5. Store tokens for future API calls
    6. Auto-refresh when access token expires
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        """
        Initialize OAuth service.

        Args:
            client_id: ANAF OAuth client ID (from registration)
            client_secret: ANAF OAuth client secret (from registration)
            redirect_uri: OAuth callback URL (defaults to env var)
        """
        self.client_id = client_id or OAUTH_CLIENT_ID
        self.client_secret = client_secret or OAUTH_CLIENT_SECRET
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
        self._pending_auth: Dict[str, Dict] = {}  # state -> {code_verifier, cif}

        if not self.client_id or not self.client_secret:
            logger.warning(
                "ANAF OAuth credentials not configured. "
                "Set ANAF_OAUTH_CLIENT_ID and ANAF_OAUTH_CLIENT_SECRET environment variables."
            )

    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate random code verifier (43-128 characters)
        code_verifier = secrets.token_urlsafe(64)

        # Create code challenge (SHA256 hash, base64url encoded)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()

        return code_verifier, code_challenge

    def get_authorization_url(
        self,
        company_cif: str,
        scope: str = "efactura",
    ) -> Tuple[str, str]:
        """
        Generate ANAF authorization URL.

        Args:
            company_cif: Company CIF (without RO prefix) - stored for reference
            scope: OAuth scope (default: efactura)

        Returns:
            Tuple of (authorization_url, state)

        Raises:
            ValueError: If OAuth credentials not configured
        """
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "ANAF OAuth credentials not configured. "
                "Set ANAF_OAUTH_CLIENT_ID and ANAF_OAUTH_CLIENT_SECRET environment variables."
            )

        # Generate state and PKCE
        state = secrets.token_urlsafe(32)
        code_verifier, code_challenge = self.generate_pkce_pair()

        # Store pending auth data
        self._pending_auth[state] = {
            'code_verifier': code_verifier,
            'cif': company_cif,
            'created_at': datetime.utcnow().isoformat(),
        }

        # Build authorization URL
        # Use registered client_id, not CIF
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': scope,
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'token_content_type': 'jwt',
        }

        # Build URL with query params
        query = '&'.join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{OAUTH_AUTHORIZE_URL}?{query}"

        logger.info(
            "Generated authorization URL",
            extra={
                'cif': company_cif,
                'client_id': self.client_id[:8] + '...',
                'redirect_uri': self.redirect_uri,
                'state': state[:8] + '...',
            }
        )

        return auth_url, state

    def exchange_code_for_tokens(
        self,
        code: str,
        state: str,
    ) -> OAuthTokens:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from ANAF callback
            state: State parameter from callback

        Returns:
            OAuthTokens object

        Raises:
            ValueError: If state is invalid or exchange fails
        """
        # Validate state and get pending auth data
        if state not in self._pending_auth:
            raise ValueError("Invalid or expired state parameter")

        pending = self._pending_auth.pop(state)
        code_verifier = pending['code_verifier']
        company_cif = pending['cif']

        logger.info(
            "Exchanging authorization code for tokens",
            extra={'cif': company_cif, 'state': state[:8] + '...'}
        )

        # Exchange code for tokens
        try:
            response = requests.post(
                OAUTH_TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': self.redirect_uri,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code_verifier': code_verifier,
                    'token_content_type': 'jwt',
                },
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(
                    "Token exchange failed",
                    extra={
                        'status_code': response.status_code,
                        'response': response.text[:200],
                    }
                )
                raise ValueError(f"Token exchange failed: {response.status_code}")

            data = response.json()

            # Calculate expiration time
            # Per ANAF OAuth docs: Access Token JWT validity = 90 days (7,776,000 seconds)
            expires_in = data.get('expires_in', ACCESS_TOKEN_VALIDITY_SECONDS)  # Default 90 days per ANAF docs
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            tokens = OAuthTokens(
                access_token=data['access_token'],
                refresh_token=data['refresh_token'],
                token_type=data.get('token_type', 'Bearer'),
                expires_at=expires_at,
                scope=data.get('scope'),
            )

            logger.info(
                "Token exchange successful",
                extra={
                    'cif': company_cif,
                    'expires_in': expires_in,
                    'expires_in_days': expires_in // 86400,
                }
            )

            return tokens

        except requests.RequestException as e:
            logger.error(
                "Token exchange request failed",
                extra={'error': str(e)}
            )
            raise ValueError(f"Token exchange request failed: {e}")

    def refresh_access_token(
        self,
        refresh_token: str,
        company_cif: str,
    ) -> OAuthTokens:
        """
        Refresh expired access token.

        Args:
            refresh_token: Refresh token from previous auth
            company_cif: Company CIF (for logging)

        Returns:
            New OAuthTokens object

        Raises:
            ValueError: If refresh fails
        """
        logger.info(
            "Refreshing access token",
            extra={'cif': company_cif}
        )

        try:
            response = requests.post(
                OAUTH_TOKEN_URL,
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'token_content_type': 'jwt',
                },
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(
                    "Token refresh failed",
                    extra={
                        'status_code': response.status_code,
                        'response': response.text[:200],
                    }
                )
                raise ValueError(f"Token refresh failed: {response.status_code}")

            data = response.json()

            # Calculate expiration time
            # Per ANAF OAuth docs: Access Token JWT validity = 90 days (7,776,000 seconds)
            expires_in = data.get('expires_in', ACCESS_TOKEN_VALIDITY_SECONDS)  # Default 90 days per ANAF docs
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # Use new refresh token if provided, otherwise keep the old one
            new_refresh_token = data.get('refresh_token', refresh_token)

            tokens = OAuthTokens(
                access_token=data['access_token'],
                refresh_token=new_refresh_token,
                token_type=data.get('token_type', 'Bearer'),
                expires_at=expires_at,
                scope=data.get('scope'),
            )

            logger.info(
                "Token refresh successful",
                extra={
                    'cif': company_cif,
                    'expires_in': expires_in,
                    'expires_in_days': expires_in // 86400,
                }
            )

            return tokens

        except requests.RequestException as e:
            logger.error(
                "Token refresh request failed",
                extra={'error': str(e)}
            )
            raise ValueError(f"Token refresh request failed: {e}")

    def revoke_token(
        self,
        token: str,
        token_type: str = 'refresh_token',
    ) -> bool:
        """
        Revoke an OAuth token.

        Args:
            token: Token to revoke
            token_type: 'access_token' or 'refresh_token'

        Returns:
            True if revocation successful
        """
        logger.info("Revoking OAuth token")

        try:
            response = requests.post(
                OAUTH_REVOKE_URL,
                data={
                    'token': token,
                    'token_type_hint': token_type,
                },
                timeout=30,
            )

            # Revocation should return 200 even if token is already invalid
            success = response.status_code == 200

            if success:
                logger.info("Token revoked successfully")
            else:
                logger.warning(
                    "Token revocation may have failed",
                    extra={'status_code': response.status_code}
                )

            return success

        except requests.RequestException as e:
            logger.error(
                "Token revocation request failed",
                extra={'error': str(e)}
            )
            return False

    def get_pending_auth(self, state: str) -> Optional[Dict]:
        """Get pending auth data for a state."""
        return self._pending_auth.get(state)

    def store_pending_auth(self, state: str, data: Dict):
        """Store pending auth data (for session persistence)."""
        self._pending_auth[state] = data

    def cleanup_expired_pending(self, max_age_minutes: int = 10):
        """Remove expired pending auth requests."""
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        expired_states = [
            state for state, data in self._pending_auth.items()
            if datetime.fromisoformat(data['created_at']) < cutoff
        ]

        for state in expired_states:
            del self._pending_auth[state]

        if expired_states:
            logger.debug(f"Cleaned up {len(expired_states)} expired pending auth requests")


# Global service instance
_oauth_service: Optional[ANAFOAuthService] = None


def get_oauth_service() -> ANAFOAuthService:
    """Get or create the global OAuth service instance."""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = ANAFOAuthService()
    return _oauth_service
