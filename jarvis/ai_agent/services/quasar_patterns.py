"""
Critical-value detection patterns — single source of truth.

Used by (1) the snippet-loss report (scripts/quasar_snippet_report.py) and
(2) RAGService._create_snippet, which re-attaches high-criticality values that
fall past the 300-char cutoff. Deliberately dependency-free: it needs only `re`,
so the "most certain number" (snippet loss) and the fix run without installing
quasar / sentence-transformers / torch.

The DEFAULT list mirrors quasar.core._CRITICAL_PATTERNS (v0.1.0). The ROMANIAN
list was verified against real repo invoices on 2026-07-14 (see the pattern
checkpoint): cui allows an optional space ("RO 24936674"); invoice_series
excludes RO<digits>/RON/TVA/LEI/TOTAL to avoid CUI + label false-positives.
vat_rate and anaf_order were dropped — they matched zero real invoices and only
inflate the critical count.
"""
from __future__ import annotations
import re

# quasar.core._CRITICAL_PATTERNS @ v0.1.0 (vendored so this module has no deps)
DEFAULT_PATTERNS = [
    (r'[€$£¥]\s?\d[\d,.]*', "currency"),
    (r'\b\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?\b', "large_number"),
    (r'\b[A-HJ-NPR-Z0-9]{17}\b', "vin"),
    (r'\bRO\d{2}[A-Z0-9]{16,}\b', "iban"),
    (r'\b[A-Z]{2}\d{2}[A-Z0-9]{10,}\b', "account"),
    (r'\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b', "date"),
    (r'\b(?:Order|Article|Regulation|Section|Clause|Directive)\s+[\w/.\-]+', "legal_ref"),
    (r'\b[A-Z0-9]{6,}\-[A-Z0-9]{3,}\b', "code"),
    (r'\b\d{6,}\b', "long_id"),
]

# Romanian additions — verified against real invoices (refined 3).
ROMANIAN_PATTERNS = [
    (r"\bRO\s?\d{2,10}\b", "cui"),                                        # fiscal code, incl. "RO 24936674"
    (r"\bJ\d{2}/\d+/\d{4}\b", "reg_com"),                                 # trade register J12/2102/2024
    (r"\b(?!RO\s?\d)(?!RON|TVA|LEI|TOTAL)[A-Z]{2,4}\s?\d{4,}\b", "invoice_series"),
]

ALL_PATTERNS = DEFAULT_PATTERNS + ROMANIAN_PATTERNS
_COMPILED = [(re.compile(p), kind) for p, kind in ALL_PATTERNS]


def find_critical(text: str) -> list[str]:
    """All critical spans in `text` (verbatim), using default + Romanian patterns.

    Mirrors quasar.core.find_critical semantics (order-preserving, may repeat);
    callers dedupe with set() when they need distinct values.
    """
    hits: list[str] = []
    for rx, _kind in _COMPILED:
        hits.extend(m.group(0) for m in rx.finditer(text))
    return hits


def find_critical_kinds(text: str) -> list[tuple[str, str]]:
    """Like find_critical but returns (value, kind) — for readable reports."""
    hits: list[tuple[str, str]] = []
    for rx, kind in _COMPILED:
        hits.extend((m.group(0), kind) for m in rx.finditer(text))
    return hits


# Kinds worth force-preserving in a truncated snippet. Deliberately EXCLUDES the
# generic long_id/large_number/date/currency kinds — those are numerous and low
# value (e.g. 25k car-dossier internal ids), and preserving them would bloat
# snippets. See scripts/quasar_snippet_report.py for the per-source-type finding.
HIGH_CRITICAL_KINDS = {"iban", "account", "vin", "cui", "reg_com"}


def dropped_critical_values(full_content: str, visible: str,
                            kinds: set = HIGH_CRITICAL_KINDS) -> list[str]:
    """High-criticality values present in `full_content` but missing from `visible`.

    Order-preserving, de-duplicated. Used to append IBANs/VINs/VATs that fall
    past a snippet cutoff back into the snippet so the LLM still sees them.
    """
    out: list[str] = []
    seen: set = set()
    for value, kind in find_critical_kinds(full_content):
        if kind in kinds and value not in visible and value not in seen:
            seen.add(value)
            out.append(value)
    return out
