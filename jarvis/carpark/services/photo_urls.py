"""Resolve stored CarPark photo references into URLs an external marketplace
can fetch server-side.

carpark_vehicle_photos.url holds a *private* Spaces object key
(``private/carpark/{vehicle_id}/{uuid}.jpg`` — see carpark/routes/photos.py,
connectors/autofox/service.py, connectors/carbackground/service.py), not a
public URL. Shopify, Autovit, etc. cannot authenticate to Spaces, so a raw key
must be presigned into a time-limited GET URL before it is handed to them.
Legacy rows may still hold a public http(s) URL or a data: URI; those are
passed through untouched.

Shared by every push connector so the fix lives in one place.
"""
from typing import Iterable, List

from core.services import spaces_service

# Long enough for a marketplace to fetch the images asynchronously after the
# advert/product is created (Shopify and Autovit both pull images server-side
# some time after the API call returns).
DEFAULT_PRESIGN_TTL = 24 * 3600


def public_photo_url(ref: str, expires: int = DEFAULT_PRESIGN_TTL) -> str:
    """One stored photo reference -> fetchable URL (or the input, if it already is one)."""
    if not ref or ref.startswith(('http://', 'https://', 'data:')):
        return ref
    return spaces_service.presigned_url(ref, expires=expires)


def public_photo_urls(refs: Iterable[str], expires: int = DEFAULT_PRESIGN_TTL) -> List[str]:
    """Vectorised public_photo_url; drops empties, preserves order."""
    return [u for u in (public_photo_url(r, expires) for r in refs if r) if u]
