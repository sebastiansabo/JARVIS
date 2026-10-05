"""Tests for the AutoFox read-only pull connector (carpark/connectors/autofox).

Covers the SSRF URL guard, the pull client (auth, list-by-VIN, download +
redirect re-validation), and the session-authenticated photo-sync routes.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

from app import app as flask_app
from carpark.connectors.autofox import routes as ax_routes
from carpark.connectors.autofox import service as ax_service
from carpark.connectors.autofox import client as ax_client


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


@pytest.fixture
def connector(monkeypatch):
    row = {'id': 7, 'connector_type': 'autofox', 'status': 'connected',
           'credentials': {'login_token': 'LT'}, 'config': {}}
    logs = []
    monkeypatch.setattr(ax_routes._repo, 'get_by_type', lambda t: row)
    monkeypatch.setattr(ax_routes._repo, 'add_sync_log', lambda *a, **k: logs.append(k) or 1)
    monkeypatch.setattr(ax_routes._repo, 'update', lambda *a, **k: True)
    return row, logs


@pytest.fixture
def as_admin(monkeypatch):
    # A fully-permissioned user patched into BOTH namespaces: admin_required reads
    # current_user from api_helpers; carpark_required/carpark_edit_required read it
    # from carpark.routes.vehicles (autofox routes import them from there).
    import core.utils.api_helpers as h
    import carpark.routes.vehicles as v

    class _U:
        is_authenticated = True
        id = 1
        company_id = 1
        can_access_carpark = True
        can_edit_carpark = True
        can_view_carpark_finance = True
        can_access_settings = True

    u = _U()
    monkeypatch.setattr(h, 'current_user', u)
    monkeypatch.setattr(v, 'current_user', u)


def _login_as(monkeypatch, **perms):
    """Patch current_user (both namespaces) with a user carrying the given
    permission flags; everything unspecified defaults False."""
    import core.utils.api_helpers as h
    import carpark.routes.vehicles as v

    class _U:
        is_authenticated = True
        id = 2
        company_id = 1
        can_access_carpark = False
        can_edit_carpark = False
        can_view_carpark_finance = False
        can_access_settings = False

    u = _U()
    for k, val in perms.items():
        setattr(u, k, val)
    monkeypatch.setattr(h, 'current_user', u)
    monkeypatch.setattr(v, 'current_user', u)
    return u


class _FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


# ── SSRF guard ──

@pytest.mark.parametrize('bad', [
    'http://127.0.0.1/a.jpg',                    # loopback
    'http://169.254.169.254/latest/meta-data/',  # cloud metadata (link-local)
    'http://10.0.0.5/a.jpg',                     # RFC1918
    'http://192.168.1.1/a.jpg',                  # RFC1918
    'http://[::1]/a.jpg',                        # loopback v6
    'ftp://8.8.8.8/a.jpg',                       # disallowed scheme
    'file:///etc/passwd',                        # disallowed scheme / no host
])
def test_validate_url_blocks_internal_and_bad_schemes(bad):
    with pytest.raises(ax_service.AutofoxIngestError):
        ax_service._validate_url(bad)


def test_validate_url_allows_public_ip():
    # literal public IP resolves locally (no DNS/network) and must pass
    ax_service._validate_url('https://8.8.8.8/a.jpg')


# ── pull client ──

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


# ── Sync-from-AutoFox routes (session auth) ──

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


# ── route authorization + SSRF-on-write (batch-3 hardening) ──

def test_save_config_requires_admin(client, monkeypatch):
    _login_as(monkeypatch, can_access_carpark=True, can_edit_carpark=True,
              can_access_settings=False)
    r = client.post('/autofox/api/config', json={'login_token': 'x'})
    assert r.status_code == 403


def test_import_requires_edit(client, monkeypatch):
    _login_as(monkeypatch, can_access_carpark=True, can_edit_carpark=False)
    r = client.post('/autofox/api/import',
                    json={'vin': 'W' * 17, 'conversion_ids': ['1']})
    assert r.status_code == 403


def test_reads_require_carpark(client, monkeypatch):
    _login_as(monkeypatch, can_access_carpark=False)
    assert client.get('/autofox/api/config').status_code == 403
    assert client.get('/autofox/api/logs').status_code == 403
    assert client.get('/autofox/api/photos?vin=WBA1234567890ABCD').status_code == 403
    assert client.get('/autofox/api/image?path=media/x.jpg').status_code == 403


def test_save_config_rejects_ssrf_base_url(client, connector, as_admin, monkeypatch):
    # A link-local / metadata base_url must be rejected before it can be stored,
    # even for an admin (prevents SSRF credential exfiltration via the pull client).
    r = client.post('/autofox/api/config', json={'api_base_url': 'http://169.254.169.254'})
    assert r.status_code == 400


def test_save_config_accepts_public_base_url(client, as_admin, monkeypatch):
    saved = {}
    monkeypatch.setattr(ax_routes._repo, 'get_by_type', lambda t: None)
    monkeypatch.setattr(ax_routes._repo, 'save', lambda *a, **k: saved.update(k) or 5)
    monkeypatch.setattr(ax_routes._repo, 'get', lambda cid: {
        'id': 5, 'status': 'connected', 'credentials': {'login_token': 't'},
        'config': {'api_base_url': 'https://8.8.8.8'}})
    r = client.post('/autofox/api/config',
                    json={'login_token': 't', 'api_base_url': 'https://8.8.8.8'})
    assert r.status_code == 200


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
