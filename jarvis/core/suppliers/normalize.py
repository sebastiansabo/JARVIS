"""Canonical identity normalization for the supplier master."""
import re


def normalize_cui(value: str | None) -> str | None:
    """Digits-only canonical CUI. 'RO9997007' -> '9997007'. Empty -> None."""
    if not value:
        return None
    digits = re.sub(r'\D', '', value)
    return digits or None


def normalize_nr_reg(value: str | None) -> str | None:
    """Uppercase, whitespace-stripped Nr. Reg. Com (keeps separators). Empty -> None."""
    if not value:
        return None
    s = re.sub(r'\s+', '', value).upper()
    return s or None
