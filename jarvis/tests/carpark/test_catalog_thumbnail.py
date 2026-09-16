"""The catalog list serves the small thumbnail of the gallery's FIRST photo.

`primary_photo_url` is consumed ONLY by the CarPark list-view row/card
thumbnail (frontend index.tsx), rendered at ~40-80px. Two properties matter:

1. It ships the small `thumbnail_url` variant (~20 KB) instead of the full
   ~300 KB original, falling back to `url` for legacy photos without a thumb.
2. It tracks GALLERY ORDER — the first photo by `sort_order` (the gallery's
   "1 = cover"), NOT the `is_primary` flag. Drag-reordering the gallery cover
   must change this thumbnail too, so selection mirrors the gallery's own
   `ORDER BY sort_order, id` and excludes soft-deleted photos.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from carpark.repositories.vehicle_repository import CATALOG_SELECT


def test_catalog_primary_photo_uses_thumbnail_of_first_gallery_photo():
    sql = ' '.join(CATALOG_SELECT.split()).lower()
    # Prefer the thumbnail variant over the full original.
    assert 'coalesce(p.thumbnail_url, p.url)' in sql
    # Selection follows gallery order (first by sort_order), not is_primary,
    # so it changes when the gallery is reordered.
    assert 'order by p.sort_order, p.id limit 1) as primary_photo_url' in sql
    assert 'is_primary' not in sql  # cover is order-driven, never the flag
    # Soft-deleted photos never surface as the cover.
    assert 'where p.vehicle_id = v.id and p.deleted_at is null order by' in sql


def test_catalog_photo_count_excludes_soft_deleted():
    sql = ' '.join(CATALOG_SELECT.split()).lower()
    assert 'count(*) from carpark_vehicle_photos p where p.vehicle_id = v.id and p.deleted_at is null) as photo_count' in sql
