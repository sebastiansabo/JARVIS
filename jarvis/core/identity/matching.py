"""Shared matching helpers for unified employee mapping.

Pure functions and dataclasses reused by the unified mapping service to keep
Sincron and BioStar auto-map logic consistent.
"""

from dataclasses import dataclass
from typing import Optional


# Confidence constants (0-100)
CONF_CNP = 100
CONF_EMAIL = 100
CONF_MANUAL = 100
CONF_CROSS_VERIFIED = 95
CONF_NAME_EXACT = 90
CONF_NAME_FIRST_LAST = 85
CONF_NAME_LAST_FIRST = 80


@dataclass
class MatchResult:
    """Outcome of a single match attempt."""
    user_id: int
    method: str          # 'cnp' | 'auto_email' | 'auto_name' | 'manual' | 'cross_verified'
    confidence: int      # 0-100
    source: str          # 'sincron' | 'biostar'


def normalize_cnp(cnp: Optional[str]) -> Optional[str]:
    """Trim, strip placeholder 'x' filler, lowercase. Returns None if empty."""
    if not cnp:
        return None
    value = cnp.strip().lower()
    stripped = value.replace('x', '')
    if not stripped:
        return None
    return value


def normalize_name(name: Optional[str]) -> str:
    """Trim + lowercase. Returns '' for falsy input."""
    if not name:
        return ''
    return ' '.join(name.strip().lower().split())


def normalize_email(email: Optional[str]) -> str:
    """Trim + lowercase."""
    if not email:
        return ''
    return email.strip().lower()


def build_candidate_names(nume: Optional[str], prenume: Optional[str]) -> list[str]:
    """Return both name orderings (nume+prenume, prenume+nume) as normalized strings."""
    first = normalize_name(f"{nume or ''} {prenume or ''}")
    second = normalize_name(f"{prenume or ''} {nume or ''}")
    out = []
    if first:
        out.append(first)
    if second and second != first:
        out.append(second)
    return out
