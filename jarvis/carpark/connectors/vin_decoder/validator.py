"""ISO 3779 VIN (Vehicle Identification Number) validation.

Validates:
- 17-character length
- Allowed characters (A-Z, 0-9 excluding I, O, Q)
- Check digit at position 9
- Extracts WMI, VDS, VIS sections
"""
import re

# Characters allowed in a VIN (ISO 3779) — I, O, Q are excluded
_VALID_CHARS = set('ABCDEFGHJKLMNPRSTUVWXYZ0123456789')
_VIN_PATTERN = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')

# Transliteration values for check digit calculation
_TRANSLITERATION = {
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
    'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
    '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
}

# Position weights for check digit calculation (positions 1-17)
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def _calculate_check_digit(vin: str) -> str:
    """Calculate the ISO 3779 check digit for a VIN.

    Returns the expected check digit character ('0'-'9' or 'X').
    """
    total = 0
    for i, char in enumerate(vin):
        value = _TRANSLITERATION.get(char, 0)
        total += value * _WEIGHTS[i]
    remainder = total % 11
    return 'X' if remainder == 10 else str(remainder)


def validate_vin(vin: str) -> dict:
    """Validate a VIN and return structured result.

    Args:
        vin: The VIN string to validate.

    Returns:
        dict with keys: valid, vin, wmi, vds, vis, check_digit_valid, errors
    """
    errors = []

    if not vin or not isinstance(vin, str):
        return {
            'valid': False,
            'vin': str(vin) if vin else '',
            'wmi': '',
            'vds': '',
            'vis': '',
            'check_digit_valid': False,
            'errors': ['VIN is required'],
        }

    # Normalize: strip whitespace, uppercase
    clean = vin.strip().upper()

    # Length check
    if len(clean) != 17:
        errors.append(f'VIN must be 17 characters (got {len(clean)})')

    # Character check
    invalid_chars = set(clean) - _VALID_CHARS
    if invalid_chars:
        errors.append(
            f"Invalid characters: {', '.join(sorted(invalid_chars))}. "
            f"I, O, Q are not allowed in VINs."
        )

    # If basic checks fail, return early
    if errors:
        return {
            'valid': False,
            'vin': clean,
            'wmi': clean[:3] if len(clean) >= 3 else '',
            'vds': clean[3:9] if len(clean) >= 9 else '',
            'vis': clean[9:] if len(clean) >= 10 else '',
            'check_digit_valid': False,
            'errors': errors,
        }

    # Extract sections
    wmi = clean[:3]    # World Manufacturer Identifier (positions 1-3)
    vds = clean[3:9]   # Vehicle Descriptor Section (positions 4-9, includes check digit)
    vis = clean[9:]    # Vehicle Identifier Section (positions 10-17)

    # Check digit validation (position 9, index 8)
    expected = _calculate_check_digit(clean)
    actual = clean[8]
    check_digit_valid = expected == actual

    if not check_digit_valid:
        errors.append(
            f'Check digit mismatch: position 9 is {actual}, expected {expected}'
        )

    return {
        'valid': len(errors) == 0,
        'vin': clean,
        'wmi': wmi,
        'vds': vds,
        'vis': vis,
        'check_digit_valid': check_digit_valid,
        'errors': errors,
    }
