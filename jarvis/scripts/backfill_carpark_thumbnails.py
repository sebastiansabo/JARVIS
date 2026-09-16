"""Backfill CarPark photo thumbnails for rows that predate thumbnail generation.

The upload route now stores a small `_thumb.jpg` variant alongside every image
and records its key in `carpark_vehicle_photos.thumbnail_url`, so the catalog
list can serve ~20 KB instead of the full ~300 KB original. Existing rows have
`thumbnail_url IS NULL` and still make the list download full-size images —
this script generates their missing thumbnails.

SELF-CONTAINED BY DESIGN: connects to Postgres with raw psycopg2 and to Spaces
with raw boto3, reading env vars directly. It deliberately does NOT import
`database` (which runs init_db() / full schema migration at import time) or
anything under the app package. Safe to point at prod without triggering a
migration.

Idempotent: only touches rows where thumbnail_url IS NULL. Re-running skips
rows already backfilled. Dry-run by default; pass --commit to write.

Env required:
    DATABASE_URL, DO_SPACES_KEY, DO_SPACES_SECRET, DO_SPACES_BUCKET, DO_SPACES_REGION

Usage (from the jarvis/ dir):
    python scripts/backfill_carpark_thumbnails.py            # dry run, all rows
    python scripts/backfill_carpark_thumbnails.py --commit   # apply
    python scripts/backfill_carpark_thumbnails.py --commit --vehicle 18
    python scripts/backfill_carpark_thumbnails.py --commit --limit 100
"""
import argparse
import base64
import io
import os
import sys
import uuid

import psycopg2
import psycopg2.extras
from PIL import Image, ImageOps, UnidentifiedImageError

# Must match jarvis/carpark/routes/photos.py's thumbnail parameters.
THUMB_MAX_PX = 400
THUMB_QUALITY = 70
MAX_PHOTO_PIXELS = 50_000_000  # decompression-bomb guard (~50 MP source)


def _spaces_cfg():
    return {
        'key': os.environ.get('DO_SPACES_KEY'),
        'secret': os.environ.get('DO_SPACES_SECRET'),
        'bucket': os.environ.get('DO_SPACES_BUCKET'),
        'region': os.environ.get('DO_SPACES_REGION'),
    }


def _spaces_client(cfg):
    import boto3
    return boto3.client(
        's3', region_name=cfg['region'],
        endpoint_url=f"https://{cfg['region']}.digitaloceanspaces.com",
        aws_access_key_id=cfg['key'], aws_secret_access_key=cfg['secret'])


def _compress_thumb(raw: bytes) -> bytes:
    """Re-encode arbitrary image bytes as a size-capped, EXIF-corrected JPEG
    thumbnail. Mirrors photos.py::_compress_jpeg(max_px, q)."""
    im = Image.open(io.BytesIO(raw))
    w, h = im.size
    if w * h > MAX_PHOTO_PIXELS:
        raise ValueError('Image dimensions too large')
    im = ImageOps.exif_transpose(im).convert('RGB')
    im.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, 'JPEG', quality=THUMB_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def _source_bytes(client, bucket, url):
    """Return the original image bytes for a photo `url`, or None if it can't
    be sourced (external http URL). Handles both Spaces keys and legacy
    base64 data-URLs."""
    if url.startswith('data:'):
        _, _, payload = url.partition(',')
        return base64.b64decode(payload)
    if url.startswith(('http://', 'https://')):
        return None  # externally hosted — nothing to backfill from Spaces
    obj = client.get_object(Bucket=bucket, Key=url)
    return obj['Body'].read()


def _thumb_key(vehicle_id, url):
    """Key for the thumbnail: pair it with the original's uuid stem when the
    original is a Spaces key; otherwise mint a fresh uuid under the vehicle."""
    if url.startswith('private/carpark/') and url.endswith('.jpg'):
        return url[:-len('.jpg')] + '_thumb.jpg'
    return f'private/carpark/{vehicle_id}/{uuid.uuid4().hex}_thumb.jpg'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit', action='store_true',
                    help='Actually upload thumbnails and update rows (default: dry run)')
    ap.add_argument('--vehicle', type=int, default=None,
                    help='Limit to a single vehicle_id')
    ap.add_argument('--limit', type=int, default=None,
                    help='Process at most N rows')
    args = ap.parse_args()

    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        sys.exit('DATABASE_URL not set')
    cfg = _spaces_cfg()
    if not all(cfg.values()):
        sys.exit('DO_SPACES_* env vars not fully set')

    client = _spaces_client(cfg)
    bucket = cfg['bucket']

    sql = """
        SELECT id, vehicle_id, url
          FROM carpark_vehicle_photos
         WHERE thumbnail_url IS NULL
    """
    params = []
    if args.vehicle is not None:
        sql += ' AND vehicle_id = %s'
        params.append(args.vehicle)
    sql += ' ORDER BY id'
    if args.limit is not None:
        sql += ' LIMIT %s'
        params.append(args.limit)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    done = skipped = failed = 0
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        print(f'{len(rows)} photo(s) without a thumbnail'
              f"{' (DRY RUN)' if not args.commit else ''}")

        for row in rows:
            pid, vid, url = row['id'], row['vehicle_id'], row['url']
            try:
                raw = _source_bytes(client, bucket, url)
                if raw is None:
                    skipped += 1
                    print(f'  skip  photo {pid} (external url)')
                    continue
                thumb = _compress_thumb(raw)
                tkey = _thumb_key(vid, url)
                if args.commit:
                    client.put_object(
                        Bucket=bucket, Key=tkey, Body=thumb,
                        ACL='private', ContentType='image/jpeg',
                        CacheControl='private, max-age=31536000, immutable')
                    with conn.cursor() as ucur:
                        ucur.execute(
                            'UPDATE carpark_vehicle_photos SET thumbnail_url = %s WHERE id = %s',
                            (tkey, pid))
                    conn.commit()
                done += 1
                print(f'  ok    photo {pid} veh {vid} -> {tkey} ({len(thumb)} B)')
            except (UnidentifiedImageError, OSError, ValueError) as e:
                conn.rollback()
                failed += 1
                print(f'  FAIL  photo {pid}: {e}')
            except Exception as e:  # noqa: BLE001 — best-effort per-row, keep going
                conn.rollback()
                failed += 1
                print(f'  FAIL  photo {pid}: {e!r}')
    finally:
        conn.close()

    verb = 'generated' if args.commit else 'would generate'
    print(f'\nDone: {verb} {done}, skipped {skipped}, failed {failed}.')
    if not args.commit and done:
        print('Re-run with --commit to apply.')


if __name__ == '__main__':
    main()
