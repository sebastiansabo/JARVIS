import base64, pytest
from unittest.mock import MagicMock, patch
from carpark.connectors.carbackground.client import CarBackgroundClient
from carpark.connectors.carbackground.service import CarBackgroundError, BROWSER_UA

def _client():
    repo = MagicMock()
    repo.get_by_type.return_value = {'credentials': {'api_key': 'cbg_test'}, 'config': {}}
    return CarBackgroundClient(repo=repo)

def test_generate_sends_browser_ua_and_returns_bytes():
    c = _client()
    gen_resp = MagicMock(status_code=200); gen_resp.json.return_value = {
        'status': 'succeeded', 'image_url': 'https://cdn.example.com/out.jpg', 'credits_charged': 1}
    dl_resp = MagicMock(status_code=200, is_redirect=False, headers={})
    dl_resp.iter_content.return_value = [b'\xff\xd8\xff', b'rest']
    with patch.object(c._session, 'post', return_value=gen_resp) as post, \
         patch.object(c._session, 'get', return_value=dl_resp), \
         patch('carpark.connectors.carbackground.service._validate_url', return_value=None):
        out = c.generate(b'origbytes', 'studio-white')
    assert out == b'\xff\xd8\xffrest'
    # UA present on the generate call (Cloudflare 1010 guard)
    assert post.call_args.kwargs['headers']['User-Agent'] == BROWSER_UA
    body = post.call_args.kwargs['json']
    assert body['background_id'] == 'studio-white'
    assert base64.b64decode(body['image_base64']) == b'origbytes'

def test_generate_no_credits_raises_402():
    c = _client()
    resp = MagicMock(status_code=402); resp.json.return_value = {'error': {'code': 'insufficient'}}
    with patch.object(c._session, 'post', return_value=resp):
        with pytest.raises(CarBackgroundError) as e:
            c.generate(b'x', 'studio-white')
    assert e.value.status == 402
