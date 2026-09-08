"""Tests for the AutoFox inbound webhook (carpark/connectors/autofox)."""
import io
import json
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

from app import app as flask_app
from carpark.connectors.autofox import routes as ax_routes
from carpark.connectors.autofox import service as ax_service
from carpark.connectors.autofox.service import extract_delivery

TOKEN = 'test-token-123'


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


@pytest.fixture
def connector(monkeypatch):
    row = {'id': 7, 'connector_type': 'autofox', 'status': 'disconnected',
           'credentials': {'inbound_token': TOKEN}, 'config': {}}
    logs = []
    monkeypatch.setattr(ax_routes._repo, 'get_by_type', lambda t: row)
    monkeypatch.setattr(ax_routes._repo, 'add_sync_log', lambda *a, **k: logs.append(k) or 1)
    monkeypatch.setattr(ax_routes._repo, 'update', lambda *a, **k: True)
    return row, logs


def _jpeg(size=(1200, 900)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, (10, 20, 30)).save(buf, 'JPEG')
    return buf.getvalue()


# ── payload normalisation ──

def test_extract_flat_urls():
    vin, imgs = extract_delivery({'vin': 'wba1234567890abcd', 'images': ['https://x/1.jpg', 'https://x/2.jpg']})
    assert vin == 'WBA1234567890ABCD'
    assert [i['url'] for i in imgs] == ['https://x/1.jpg', 'https://x/2.jpg']


def test_extract_nested_objects_sorted():
    p = {'vehicle': {'vin': 'WBA1234567890ABCD'},
         'data': {'photos': [{'id': 'b', 'downloadUrl': 'https://x/b.jpg', 'position': 2},
                             {'id': 'a', 'downloadUrl': 'https://x/a.jpg', 'position': 1}]}}
    vin, imgs = extract_delivery(p)
    assert vin == 'WBA1234567890ABCD'
    assert [i['source_id'] for i in imgs] == ['a', 'b']


def test_extract_missing():
    assert extract_delivery({'foo': 'bar'}) == (None, [])


# ── SSRF guard ──

@pytest.mark.parametrize('bad', [
    'http://127.0.0.1/a.jpg',            # loopback
    'http://169.254.169.254/latest/meta-data/',  # cloud metadata (link-local)
    'http://10.0.0.5/a.jpg',             # RFC1918
    'http://192.168.1.1/a.jpg',          # RFC1918
    'http://[::1]/a.jpg',                # loopback v6
    'ftp://8.8.8.8/a.jpg',               # disallowed scheme
    'file:///etc/passwd',                # disallowed scheme / no host
])
def test_validate_url_blocks_internal_and_bad_schemes(bad):
    with pytest.raises(ax_service.AutofoxIngestError):
        ax_service._validate_url(bad)


def test_validate_url_allows_public_ip():
    # literal public IP resolves locally (no DNS/network) and must pass
    ax_service._validate_url('https://8.8.8.8/a.jpg')


# ── pull client + Sync-from-AutoFox routes ──

from carpark.connectors.autofox import client as ax_client


class _FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def as_admin(monkeypatch):
    import core.utils.api_helpers as h

    class _U:
        is_authenticated = True

    monkeypatch.setattr(h, 'current_user', _U())


def test_extract_list_variants():
    ex = ax_client._extract_list
    assert ex([{'a': 1}]) == [{'a': 1}]
    assert ex({'data': [{'a': 1}]}) == [{'a': 1}]
    assert ex({'data': {'items': [{'a': 1}]}}) == [{'a': 1}]
    assert ex({'x': 1}) == []


def test_client_normalise_prefers_retouched():
    n = ax_client.AutofoxClient._normalise(
        {'id': 5, 'file_converted': 'c/a.jpg', 'file_retouched': 'c/b.jpg',
         'retouch_state': 'done'}, 'VIN')
    assert n['conversion_id'] == '5' and n['path'].endswith('b.jpg') and n['vin'] == 'VIN'
    assert ax_client.AutofoxClient._normalise({'id': 5}, 'VIN') is None  # no file path


def test_client_login_and_list():
    class _Repo:
        def get_by_type(self, t):
            return {'id': 1, 'credentials': {'login_token': 'LT'}, 'config': {}}

    c = ax_client.AutofoxClient(repo=_Repo())
    seen = {}

    class _Sess:
        def post(self, url, data=None, timeout=None):
            seen['login'] = data
            return _FakeResp(200, {'status': 1, 'data': {'access_token': 'TOK'}})

        def get(self, url, params=None, headers=None, timeout=None, stream=False):
            seen['headers'] = headers
            seen['params'] = params
            return _FakeResp(200, {'status': 1, 'data': [
                {'id': 11, 'vin': 'WBAX', 'file_converted': 'https://c/1.jpg',
                 'file_retouched': 'https://c/1r.jpg', 'retouch_state': 'done'},
                {'id': 12, 'vin': 'WBAX', 'file_converted': 'https://c/2.jpg',
                 'retouch_state': 'retouch_not_needed'},
            ]})

    c._session = _Sess()
    out = c.list_conversions_by_vin('wbax')
    assert seen['login'] == {'login_token': 'LT'}
    assert seen['headers']['Authorization'] == 'Bearer TOK'
    # AutoFox rejects sort_by=date_modified (422) → must not be sent
    assert 'sort_by' not in seen['params'] and 'sort_direction' not in seen['params']
    assert seen['params']['vin'] == 'wbax'
    assert [p['conversion_id'] for p in out] == ['11', '12']
    assert out[0]['url'].endswith('1r.jpg')  # retouched preferred
    assert out[1]['url'].endswith('2.jpg')


def _client_with_token():
    class _Repo:
        def get_by_type(self, t):
            return {'id': 1, 'credentials': {'login_token': 'LT'}, 'config': {}}
    c = ax_client.AutofoxClient(repo=_Repo())
    c._token = 'TOK'
    return c


def test_client_download_blocks_redirect_to_internal():
    c = _client_with_token()

    class _Redir:
        status_code = 302
        is_redirect = True
        headers = {'Location': 'http://169.254.169.254/latest/meta-data/'}

        def iter_content(self, n):
            return iter(())

        def raise_for_status(self):
            pass

    class _Sess:
        def get(self, url, **kw):
            return _Redir()

    c._session = _Sess()
    # public initial host passes, but the redirect target is link-local → blocked
    with pytest.raises(ax_service.AutofoxIngestError):
        c.download('https://8.8.8.8/img.jpg')


def test_client_download_ok():
    c = _client_with_token()

    class _Ok:
        status_code = 200
        is_redirect = False
        headers = {}

        def iter_content(self, n):
            yield b'ab'
            yield b'cd'

        def raise_for_status(self):
            pass

    class _Sess:
        def get(self, url, **kw):
            assert kw.get('allow_redirects') is False
            return _Ok()

    c._session = _Sess()
    assert c.download('https://8.8.8.8/img.jpg') == b'abcd'


def test_client_absolute_url():
    c = _client_with_token()  # config {} → base defaults to api.autofox.ai
    assert c.absolute_url('media/x.jpg') == 'https://api.autofox.ai/media/x.jpg'
    assert c.absolute_url('/media/x.jpg') == 'https://api.autofox.ai/media/x.jpg'
    assert c.absolute_url('https://cdn/x.jpg') == 'https://cdn/x.jpg'


def test_image_proxy_streams_and_rejects_bad_path(client, connector, as_admin, monkeypatch):
    monkeypatch.setattr(ax_routes._client, 'absolute_url', lambda p: 'https://api.autofox.ai/' + p)
    monkeypatch.setattr(ax_routes._client, 'download', lambda url: b'\xff\xd8imgdata')
    r = client.get('/autofox/api/image?path=media/vehicle-images/1/x.jpg')
    assert r.status_code == 200 and r.data == b'\xff\xd8imgdata' and r.mimetype == 'image/jpeg'
    assert client.get('/autofox/api/image?path=http://evil/x').status_code == 400
    assert client.get('/autofox/api/image?path=../secret').status_code == 400


def test_photos_route_flags_already_imported(client, connector, as_admin, monkeypatch):
    monkeypatch.setattr(ax_routes._client, 'list_conversions_by_vin',
                        lambda vin: [{'conversion_id': '11', 'url': 'https://c/1.jpg',
                                      'retouch_state': 'done', 'date_modified': 'x', 'vin': vin}])
    monkeypatch.setattr(ax_routes._service._vehicles, 'get_by_vin', lambda v: {'id': 42, 'vin': v})
    monkeypatch.setattr(ax_routes._service, 'imported_conversion_ids', lambda vid: {'11'})
    r = client.get('/autofox/api/photos?vin=WBA1234567890ABCD')
    assert r.status_code == 200, r.data
    j = r.get_json()
    assert j['matched_vehicle'] is True and j['vehicle_id'] == 42
    assert j['photos'][0]['already_imported'] is True


def test_import_route_downloads_and_dedups(client, connector, as_admin, monkeypatch):
    monkeypatch.setattr(ax_service.spaces_service, 'is_enabled', lambda: True)
    monkeypatch.setattr(ax_routes._service._vehicles, 'get_by_vin', lambda v: {'id': 42, 'vin': v})
    monkeypatch.setattr(ax_routes._client, 'list_conversions_by_vin',
                        lambda vin: [{'conversion_id': '11', 'url': 'https://c/1.jpg'},
                                     {'conversion_id': '12', 'url': 'https://c/2.jpg'}])
    monkeypatch.setattr(ax_routes._service, 'imported_conversion_ids', lambda vid: {'12'})
    monkeypatch.setattr(ax_routes._service._photos, 'get_by_vehicle', lambda vid, t=None: [])
    monkeypatch.setattr(ax_routes._client, 'download', lambda url: b'imgbytes')
    stored = []
    monkeypatch.setattr(ax_routes._service, 'store_photo_bytes',
                        lambda vid, raw, cid, make_primary=False: stored.append(cid) or {'id': 1})
    r = client.post('/autofox/api/import',
                    json={'vin': 'WBA1234567890ABCD', 'conversion_ids': ['11', '12']})
    assert r.status_code == 200, r.data
    j = r.get_json()
    assert j['created'] == 1 and j['skipped_duplicates'] == 1
    assert stored == ['11']  # 12 was already imported → skipped


def test_download_rejects_redirect(monkeypatch):
    class _Resp:
        is_redirect = True
        status_code = 302

        def raise_for_status(self):  # pragma: no cover - not reached
            pass

        def iter_content(self, n):  # pragma: no cover - not reached
            return iter(())

    monkeypatch.setattr(ax_service, '_validate_url', lambda u: None)
    monkeypatch.setattr(ax_service.requests, 'get', lambda *a, **k: _Resp())
    with pytest.raises(ax_service.AutofoxIngestError):
        ax_service._download('https://public.example/redir.jpg')


# ── webhook ──

def test_webhook_rejects_bad_token(client, connector):
    r = client.post('/autofox/webhook', json={'vin': 'X'}, headers={'Authorization': 'Bearer nope'})
    assert r.status_code == 401


def test_webhook_ip_allowlist_is_advisory(client, connector, monkeypatch):
    # A valid token from a non-allowlisted IP must NOT be rejected (XFF is
    # spoofable); the delivery proceeds and the mismatch is logged advisory.
    connector[0]['config'] = {'allowed_ips': ['10.0.0.1']}
    monkeypatch.setattr(ax_service.spaces_service, 'is_enabled', lambda: True)
    monkeypatch.setattr(ax_routes._service._vehicles, 'get_by_vin', lambda v: {'id': 42, 'vin': v})
    monkeypatch.setattr(ax_routes._service._photos, 'get_by_vehicle', lambda vid, t=None: [])
    r = client.post('/autofox/webhook', json={'vin': 'WBA1234567890ABCD', 'images': []},
                    headers={'Authorization': f'Bearer {TOKEN}'})
    assert r.status_code == 200
    assert connector[1][-1]['details']['ip_allowed'] is False


def test_webhook_unknown_vin_404(client, connector, monkeypatch):
    monkeypatch.setattr(ax_service.spaces_service, 'is_enabled', lambda: True)
    monkeypatch.setattr(ax_routes._service._vehicles, 'get_by_vin', lambda v: None)
    r = client.post('/autofox/webhook', json={'vin': 'WBA1234567890ABCD', 'images': []},
                    headers={'X-API-Key': TOKEN})
    assert r.status_code == 404
    assert connector[1][-1]['details']['vin'] == 'WBA1234567890ABCD'


def test_webhook_json_urls_ingested_and_deduped(client, connector, monkeypatch):
    uploaded, created = [], []
    monkeypatch.setattr(ax_service.spaces_service, 'is_enabled', lambda: True)
    monkeypatch.setattr(ax_service.spaces_service, 'upload', lambda d, k, ct: uploaded.append(k))
    monkeypatch.setattr(ax_service, '_download', lambda url: _jpeg())
    monkeypatch.setattr(ax_routes._service._vehicles, 'get_by_vin', lambda v: {'id': 42, 'vin': v})
    monkeypatch.setattr(ax_routes._service._photos, 'get_by_vehicle', lambda vid, t=None: list(created))

    def _create(**kw):
        row = {'id': len(created) + 1, **kw}
        created.append(row)
        return row
    monkeypatch.setattr(ax_routes._service._photos, 'create', _create)

    body = {'vin': 'WBA1234567890ABCD', 'images': ['https://x/1.jpg', 'https://x/2.jpg']}
    r = client.post('/autofox/webhook', json=body, headers={'Authorization': f'Bearer {TOKEN}'})
    assert r.status_code == 200, r.data
    j = r.get_json()
    # identical bytes → identical hash → second image deduped
    assert j['received'] == 2 and j['created'] == 1 and j['skipped_duplicates'] == 1
    assert created[0]['is_primary'] is True
    assert uploaded[0].startswith('private/carpark/42/autofox_')
    assert connector[1][-1]['details']['created'] == 1


def test_webhook_multipart(client, connector, monkeypatch):
    created = []
    monkeypatch.setattr(ax_service.spaces_service, 'is_enabled', lambda: True)
    monkeypatch.setattr(ax_service.spaces_service, 'upload', lambda d, k, ct: None)
    monkeypatch.setattr(ax_routes._service._vehicles, 'get_by_vin', lambda v: {'id': 5, 'vin': v})
    monkeypatch.setattr(ax_routes._service._photos, 'get_by_vehicle', lambda vid, t=None: list(created))
    monkeypatch.setattr(ax_routes._service._photos, 'create',
                        lambda **kw: created.append(kw) or {'id': 1, **kw})
    data = {'vin': 'WBA1234567890ABCD',
            'files': [(io.BytesIO(_jpeg()), 'a.jpg'), (io.BytesIO(_jpeg((800, 600))), 'b.jpg')]}
    r = client.post('/autofox/webhook', data=data, content_type='multipart/form-data',
                    headers={'X-Autofox-Token': TOKEN})
    assert r.status_code == 200, r.data
    assert r.get_json()['created'] == 2
