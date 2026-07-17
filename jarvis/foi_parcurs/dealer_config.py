"""Per company+brand dealer contact + Google review config for the test-drive
email. Primary source is the `fp_dealer_config` table (editable in the companies
admin, per linked brand); falls back to a small built-in map and then env vars,
so nothing is hardcoded in the email logic itself."""
import os


def _norm(s: str) -> str:
    return (s or '').strip().lower()


# Built-in fallback for combos not yet configured in the DB.
_DEALERS = {
    ('autoworld plus s.r.l.', 'mg motor'): {
        'review_url': 'https://g.page/r/CQxsCUMofMlJEBM/review',
        'address': 'Calea Clujului 4B-4C, Com. Apahida, 407035, jud. Cluj',
        'phone': '0264-207 400 / 0264-502 600',
    },
}


def _db_lookup(company: str, brand: str) -> dict | None:
    """Read the per-(company, brand) config from fp_dealer_config, matched by
    company name + brand name. Returns None on any failure (table missing, no DB)."""
    if not company or not brand:
        return None
    try:
        from core.base_repository import BaseRepository
        return BaseRepository().query_one(
            '''SELECT dc.review_url, dc.address, dc.phone, dc.email
               FROM fp_dealer_config dc
               JOIN companies co ON co.id = dc.company_id
               JOIN brands b ON b.id = dc.brand_id
               WHERE LOWER(co.company) = LOWER(%s) AND LOWER(b.name) = LOWER(%s)''',
            (company.strip(), brand.strip()),
        )
    except Exception:
        return None


def get_dealer_config(company: str, brand: str) -> dict:
    """Review URL + dealer address/phone/email for a (company, brand): DB first,
    then the built-in map, then GOOGLE_REVIEW_URL / DEALER_ADDRESS / DEALER_PHONE /
    DEALER_EMAIL env vars."""
    db = _db_lookup(company, brand) or {}
    fb = _DEALERS.get((_norm(company), _norm(brand)), {})

    def pick(key, env):
        return (db.get(key) or '').strip() or fb.get(key) or os.environ.get(env, '')

    return {
        'review_url': pick('review_url', 'GOOGLE_REVIEW_URL'),
        'address': pick('address', 'DEALER_ADDRESS'),
        'phone': pick('phone', 'DEALER_PHONE'),
        'email': pick('email', 'DEALER_EMAIL'),
    }
