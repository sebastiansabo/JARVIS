import base64
from unittest import mock
import importlib


def _reload(monkeypatch, **env):
    for k in ('DO_SPACES_KEY', 'DO_SPACES_SECRET', 'DO_SPACES_BUCKET', 'DO_SPACES_REGION'):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import core.services.spaces_service as s
    return importlib.reload(s)


def test_is_enabled_false_without_creds(monkeypatch):
    s = _reload(monkeypatch)
    assert s.is_enabled() is False


def test_is_enabled_true_with_creds(monkeypatch):
    s = _reload(monkeypatch, DO_SPACES_KEY='k', DO_SPACES_SECRET='x',
                DO_SPACES_BUCKET='b', DO_SPACES_REGION='fra1')
    assert s.is_enabled() is True


def test_upload_puts_private_and_returns_key(monkeypatch):
    s = _reload(monkeypatch, DO_SPACES_KEY='k', DO_SPACES_SECRET='x',
                DO_SPACES_BUCKET='jrvimagebank', DO_SPACES_REGION='fra1')
    client = mock.Mock()
    monkeypatch.setattr(s, '_get_client', lambda: client)
    key = s.upload(b'abc', 'private/carpark/1/01.jpg', 'image/jpeg')
    assert key == 'private/carpark/1/01.jpg'
    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs['Bucket'] == 'jrvimagebank'
    assert kwargs['ACL'] == 'private'
    assert kwargs['ContentType'] == 'image/jpeg'


def test_fetch_returns_bytes_and_content_type(monkeypatch):
    s = _reload(monkeypatch, DO_SPACES_KEY='k', DO_SPACES_SECRET='x',
                DO_SPACES_BUCKET='b', DO_SPACES_REGION='fra1')
    body = mock.Mock(); body.read.return_value = b'xyz'
    client = mock.Mock(); client.get_object.return_value = {'Body': body, 'ContentType': 'image/png'}
    monkeypatch.setattr(s, '_get_client', lambda: client)
    data, ct = s.fetch('private/logos/1/a.png')
    assert data == b'xyz' and ct == 'image/png'


def test_resolve_image_bytes_data_url(monkeypatch):
    s = _reload(monkeypatch)
    payload = base64.b64encode(b'hello').decode()
    assert s.resolve_image_bytes(f'data:image/png;base64,{payload}') == b'hello'


def test_resolve_image_bytes_key_calls_fetch(monkeypatch):
    s = _reload(monkeypatch, DO_SPACES_KEY='k', DO_SPACES_SECRET='x',
                DO_SPACES_BUCKET='b', DO_SPACES_REGION='fra1')
    monkeypatch.setattr(s, 'fetch', lambda key: (b'raw', 'image/jpeg'))
    assert s.resolve_image_bytes('private/carpark/1/01.jpg') == b'raw'
