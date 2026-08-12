"""One-time OPS script: convert the 12 already-uploaded staging CarPark cars'
photos from public objects under `carpark/staging/<ident>/NN.jpg` to private
objects under `private/carpark/<vehicle_id>/NN.jpg`, so the media proxy
(`/api/media/<key>`, which only serves the `private/carpark/` prefix) can
serve them, and rewrite `carpark_vehicle_photos.url` to hold the new key.

Run ONCE against staging, AFTER Tasks 1-5 of this feature are deployed there
(spaces_service, the media proxy, and the frontend mediaUrl() helper must all
be live first — otherwise the 12 cars' photos become briefly unreachable
between the ACL flip and the proxy going live).

Usage:
    # Dry run (default): prints the planned old_key -> new_key changes and a
    # count. Makes NO S3 or DB writes.
    STAGING_DATABASE_URL=... DO_SPACES_KEY=... DO_SPACES_SECRET=... \\
        python3 scripts/convert_staging_carpark_photos.py

    # Real run: copies each object to its new private key, deletes the old
    # public object, and updates the DB row, all in one DB transaction.
    DRY_RUN=0 STAGING_DATABASE_URL=... DO_SPACES_KEY=... DO_SPACES_SECRET=... \\
        python3 scripts/convert_staging_carpark_photos.py

Idempotent: the target-row query only matches rows whose `url` still starts
with the public `https://jrvimagebank...` URL. Once a row is converted, its
`url` holds a bare `private/carpark/...` key, so a re-run finds nothing left
to do for it (and re-running is otherwise safe: copy+delete on an
already-migrated key would simply not be selected).
"""
import os
from os.path import basename
from urllib.parse import urlparse

import psycopg2

BUCKET = 'jrvimagebank'
REGION = 'fra1'
ENDPOINT_URL = 'https://fra1.digitaloceanspaces.com'

DRY_RUN = os.environ.get('DRY_RUN', '1') != '0'

SELECT_SQL = (
    "SELECT id, vehicle_id, url FROM carpark_vehicle_photos "
    "WHERE url LIKE 'https://jrvimagebank%'"
)


def _make_s3_client():
    import boto3
    return boto3.client(
        's3', region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=os.environ['DO_SPACES_KEY'],
        aws_secret_access_key=os.environ['DO_SPACES_SECRET'])


def _plan_row(pid, vehicle_id, url):
    """Compute (old_key, new_key) for one carpark_vehicle_photos row."""
    old_key = urlparse(url).path.lstrip('/')           # carpark/staging/4631/01.jpg
    filename = basename(old_key)                        # 01.jpg
    new_key = f'private/carpark/{vehicle_id}/{filename}'
    return old_key, new_key


def main():
    staging_db_url = os.environ['STAGING_DATABASE_URL']

    conn = psycopg2.connect(staging_db_url)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(SELECT_SQL)
        rows = cur.fetchall()

        plans = [
            (pid, vehicle_id, url) + _plan_row(pid, vehicle_id, url)
            for pid, vehicle_id, url in rows
        ]

        if DRY_RUN:
            print(f"[DRY RUN] {len(plans)} photo(s) would be converted:")
            for pid, vehicle_id, _url, old_key, new_key in plans:
                print(f"  id={pid} vehicle_id={vehicle_id}: {old_key} -> {new_key}")
            print(f"[DRY RUN] total: {len(plans)} row(s). No S3 or DB writes made. "
                  f"Set DRY_RUN=0 to perform the conversion.")
            return

        if not plans:
            print("Nothing to convert (0 rows matched). Already converted or none uploaded.")
            return

        s3 = _make_s3_client()
        converted = 0
        for pid, vehicle_id, _url, old_key, new_key in plans:
            s3.copy_object(
                Bucket=BUCKET,
                CopySource={'Bucket': BUCKET, 'Key': old_key},
                Key=new_key,
                ACL='private',
                ContentType='image/jpeg',
                MetadataDirective='REPLACE')
            s3.delete_object(Bucket=BUCKET, Key=old_key)
            cur.execute(
                "UPDATE carpark_vehicle_photos SET url=%s WHERE id=%s",
                (new_key, pid))
            converted += 1
            print(f"  id={pid} vehicle_id={vehicle_id}: {old_key} -> {new_key} [OK]")

        conn.commit()
        print(f"converted {converted} photo(s) to private keys")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
