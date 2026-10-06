"""Per-project webhook tokens — generation + hashing.

A webhook token is a long random secret shown to the user exactly ONCE at
creation. Only its SHA-256 hash is persisted (``mkt_project_webhooks.token_hash``),
so a DB leak never exposes a usable token. Validation hashes the inbound
Bearer token and looks the row up by hash.
"""
import hashlib
import secrets

TOKEN_PREFIX = 'whk_'
_PREFIX_DISPLAY_LEN = 12  # shown in the UI to identify a token without revealing it


def hash_token(plaintext: str) -> str:
    """SHA-256 hex digest of a token, whitespace-trimmed (stable for lookup)."""
    return hashlib.sha256(plaintext.strip().encode('utf-8')).hexdigest()


def generate_token() -> tuple[str, str, str]:
    """Mint a new token.

    Returns ``(plaintext, token_hash, token_prefix)``:
    - ``plaintext``   — the secret to show the user once (``whk_...``)
    - ``token_hash``  — SHA-256 hex to persist
    - ``token_prefix``— first few chars, safe to store/display for identification
    """
    plaintext = f'{TOKEN_PREFIX}{secrets.token_urlsafe(32)}'
    return plaintext, hash_token(plaintext), plaintext[:_PREFIX_DISPLAY_LEN]
