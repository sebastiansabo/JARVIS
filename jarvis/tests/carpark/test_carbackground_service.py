from unittest.mock import MagicMock, patch
from carpark.connectors.carbackground.service import CarBackgroundEnhanceService

def test_enhance_photo_stores_variant_and_thumb():
    photos = MagicMock()
    photos.get_by_id.return_value = {'id': 7, 'vehicle_id': 3, 'url': 'private/carpark/3/orig.jpg',
                                     'enhanced_url': None, 'enhanced_thumbnail_url': None}
    photos.set_enhanced.return_value = {'id': 7, 'enhanced_url': 'private/carpark/3/enhanced_x.jpg'}
    client = MagicMock(); client.generate.return_value = b'studiobytes'
    repo = MagicMock(); repo.get_by_type.return_value = {'config': {'background_id': 'studio-white'}}
    svc = CarBackgroundEnhanceService(client=client, photo_repo=photos, repo=repo)
    with patch('core.services.spaces_service.resolve_image_bytes', return_value=b'orig'), \
         patch('core.services.spaces_service.upload') as up, \
         patch('core.services.spaces_service.delete'), \
         patch('carpark.routes.photos._compress_jpeg', side_effect=lambda raw, **k: raw):
        out = svc.enhance_photo(7)
    client.generate.assert_called_once_with(b'orig', 'studio-white')
    assert up.call_count == 2  # full + thumb
    full_key = photos.set_enhanced.call_args.args[1]
    assert full_key.startswith('private/carpark/3/enhanced_') and full_key.endswith('.jpg')
    assert out['enhanced_url']
