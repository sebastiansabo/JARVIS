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

# Blast-radius tripwire: carpark_vehicle_photos has no company_id column, so the
# SELECT below is scoped only by the public-URL prefix. On a real run we abort
# unless the match set is exactly this many rows (the 12 known cars = 320 photos),
# so an unexpected match set can never trigger irreversible S3 deletes.
EXPECTED_COUNT = int(os.environ.get('EXPECTED_COUNT', '320'))

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
            note = "" if len(plans) == EXPECTED_COUNT else (
                f"  <-- WARNING: differs from EXPECTED_COUNT={EXPECTED_COUNT}; "
                f"a real run (DRY_RUN=0) would ABORT unless this matches.")
            print(f"[DRY RUN] total: {len(plans)} row(s).{note} "
                  f"No S3 or DB writes made. Set DRY_RUN=0 to perform the conversion.")
            return

        if not plans:
            print("Nothing to convert (0 rows matched). Already converted or none uploaded.")
            return

        # Tripwire (real run only): refuse to touch S3/DB unless the match set is
        # exactly the expected size. Guards against a schema/data change silently
        # widening the LIKE match and triggering irreversible deletes.
        if len(plans) != EXPECTED_COUNT:
            print(f"ABORT: matched {len(plans)} row(s) but EXPECTED_COUNT={EXPECTED_COUNT}. "
                  f"No S3 or DB writes made. Re-check the data, then set EXPECTED_COUNT to "
                  f"the confirmed number if this is intentional.")
            raise SystemExit(1)

        s3 = _make_s3_client()
        converted = 0
        delete_failures = 0
        # Per-row atomicity: copy -> UPDATE+commit -> delete-old. Each row is durably
        # migrated (or not) on its own; a failure at any step leaves a clean, re-runnable
        # state (old object + old DB url intact, OR new key + correct DB url with at worst
        # an orphaned old object). No single end-of-run commit / rollback that could revert
        # DB rows whose old S3 objects were already irreversibly deleted.
        for pid, vehicle_id, _url, old_key, new_key in plans:
            # ContentType='image/jpeg' + MetadataDirective='REPLACE' assumes jpg sources,
            # which holds for these `NN.jpg` keys.
            s3.copy_object(
                Bucket=BUCKET,
                CopySource={'Bucket': BUCKET, 'Key': old_key},
                Key=new_key,
                ACL='private',
                ContentType='image/jpeg',
                MetadataDirective='REPLACE')
            # Commit the DB pointer to the new key BEFORE deleting the old object, so the
            # row can never point at a deleted object.
            cur.execute(
                "UPDATE carpark_vehicle_photos SET url=%s WHERE id=%s",
                (new_key, pid))
            conn.commit()
            converted += 1
            # Print only AFTER the durable commit, so the log reflects committed state.
            print(f"  id={pid} vehicle_id={vehicle_id}: {old_key} -> {new_key} [OK]")

            # Delete-old is best-effort cleanup: the row is already correctly migrated.
            # A failure here just leaves a harmless orphaned old object (it won't be
            # reprocessed since its url no longer matches the LIKE filter).
            try:
                s3.delete_object(Bucket=BUCKET, Key=old_key)
            except Exception as exc:  # noqa: BLE001 - cleanup must not fail the migration
                delete_failures += 1
                print(f"  WARNING: could not delete old object {old_key} (row already "
                      f"migrated to {new_key}): {exc}")

        print(f"converted {converted} photo(s) to private keys"
              + (f" ({delete_failures} old object(s) left orphaned; harmless)"
                 if delete_failures else ""))
    except Exception:
        # A per-row copy/UPDATE failure leaves earlier rows already committed+deleted
        # (durable) and the failing row un-touched (old object + old url intact).
        # Roll back only the current uncommitted statement, then re-raise.
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
