"""DigitalOcean Spaces image storage — all objects private. Env-configured.

Mirrors drive_service's guard pattern: when creds are absent, is_enabled() is
False and callers fall back to their existing base64/local behaviour.
"""
import base64
import logging
import os

logger = logging.getLogger('jarvis.core.services.spaces')

_client = None


def _cfg():
    return {
        'key': os.environ.get('DO_SPACES_KEY'),
        'secret': os.environ.get('DO_SPACES_SECRET'),
        'bucket': os.environ.get('DO_SPACES_BUCKET'),
        'region': os.environ.get('DO_SPACES_REGION'),
    }


def is_enabled():
    c = _cfg()
    return bool(c['key'] and c['secret'] and c['bucket'] and c['region'])


def _get_client():
    global _client
    if _client is None:
        import boto3
        c = _cfg()
        _client = boto3.client(
            's3', region_name=c['region'],
            endpoint_url=f"https://{c['region']}.digitaloceanspaces.com",
            aws_access_key_id=c['key'], aws_secret_access_key=c['secret'])
    return _client


def upload(data, key, content_type, acl='private'):
    """Store bytes under key. Returns the key.

    acl defaults to 'private' (served via the authenticated /api/media proxy or
    a presigned URL). Pass acl='public-read' to make the object world-readable
    via the Spaces CDN edge (see cdn_url) — only for non-sensitive assets the
    caller has explicitly opted to expose publicly.
    """
    public = acl == 'public-read'
    _get_client().put_object(
        Bucket=_cfg()['bucket'], Key=key, Body=data,
        ACL=acl, ContentType=content_type,
        CacheControl='public, max-age=31536000, immutable' if public else 'private, max-age=86400')
    return key


def cdn_url(key):
    """Public URL for a *public-read* object (see upload). Serves from the DO
    Spaces CDN *edge* host (region.cdn.digitaloceanspaces.com) for edge caching.

    DO_SPACES_CDN_BASE is honored only when it already points at a CDN edge
    (contains '.cdn.') or a custom CDN domain (non-digitaloceanspaces host); the
    stock value points at the non-cached origin, so we upgrade to the edge host
    by default. Returns the key unchanged when Spaces is not configured so
    callers degrade gracefully. Only resolves to a working URL for public-read
    objects."""
    if not key:
        return key
    base = (os.environ.get('DO_SPACES_CDN_BASE') or '').strip()
    if base and ('.cdn.' in base or 'digitaloceanspaces.com' not in base):
        return f"{base.rstrip('/')}/{key}"
    if not is_enabled():
        return key
    c = _cfg()
    return f"https://{c['bucket']}.{c['region']}.cdn.digitaloceanspaces.com/{key}"


def fetch(key):
    """Return (bytes, content_type) for a stored key."""
    obj = _get_client().get_object(Bucket=_cfg()['bucket'], Key=key)
    return obj['Body'].read(), obj.get('ContentType', 'application/octet-stream')


def delete(key):
    _get_client().delete_object(Bucket=_cfg()['bucket'], Key=key)


def presigned_url(key, expires=3600):
    """Return a time-limited public GET URL for a private object key.

    Objects are stored private (see upload); consumers that cannot authenticate to
    Spaces (e.g. Shopify fetching an image server-side) need a signed URL instead.
    Returns the key unchanged when Spaces is not configured, so callers degrade to
    their pre-existing behaviour rather than crashing.
    """
    if not is_enabled():
        return key
    return _get_client().generate_presigned_url(
        'get_object',
        Params={'Bucket': _cfg()['bucket'], 'Key': key},
        ExpiresIn=expires)


def resolve_image_bytes(value):
    """Accept an old base64 data-URL OR a Spaces key; return raw bytes."""
    if not value:
        return None
    if value.startswith('data:'):
        _, _, payload = value.partition(',')
        return base64.b64decode(payload)
    return fetch(value)[0]
