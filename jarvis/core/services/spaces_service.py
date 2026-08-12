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


def upload(data, key, content_type):
    """Store bytes under key with PRIVATE acl. Returns the key."""
    _get_client().put_object(
        Bucket=_cfg()['bucket'], Key=key, Body=data,
        ACL='private', ContentType=content_type,
        CacheControl='private, max-age=86400')
    return key


def fetch(key):
    """Return (bytes, content_type) for a stored key."""
    obj = _get_client().get_object(Bucket=_cfg()['bucket'], Key=key)
    return obj['Body'].read(), obj.get('ContentType', 'application/octet-stream')


def delete(key):
    _get_client().delete_object(Bucket=_cfg()['bucket'], Key=key)


def resolve_image_bytes(value):
    """Accept an old base64 data-URL OR a Spaces key; return raw bytes."""
    if not value:
        return None
    if value.startswith('data:'):
        _, _, payload = value.partition(',')
        return base64.b64decode(payload)
    return fetch(value)[0]
