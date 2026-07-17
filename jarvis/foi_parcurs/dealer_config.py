"""Per company+brand dealer contact + Google review config for the test-drive
email. Keyed by (company, brand); falls back to env vars for unconfigured combos
so nothing is hardcoded in the email logic itself."""
import os


def _norm(s: str) -> str:
    return (s or '').strip().lower()


# Extend as brands/locations are onboarded. Values here take precedence over env.
_DEALERS = {
    ('autoworld plus s.r.l.', 'mg motor'): {
        'review_url': 'https://g.page/r/CQxsCUMofMlJEBM/review',
        'address': 'Calea Clujului 4B-4C, Com. Apahida, 407035, jud. Cluj',
        'phone': '0264-207 400 / 0264-502 600',
    },
}


def get_dealer_config(company: str, brand: str) -> dict:
    """Review URL + dealer address/phone for a (company, brand). Falls back to the
    GOOGLE_REVIEW_URL / DEALER_ADDRESS / DEALER_PHONE env vars when the combo isn't
    configured above."""
    e = _DEALERS.get((_norm(company), _norm(brand)), {})
    return {
        'review_url': e.get('review_url') or os.environ.get('GOOGLE_REVIEW_URL', ''),
        'address': e.get('address') or os.environ.get('DEALER_ADDRESS', ''),
        'phone': e.get('phone') or os.environ.get('DEALER_PHONE', ''),
    }
