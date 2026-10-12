import pytest
from unittest.mock import MagicMock, patch
from carpark.connectors.carbackground.service import CarBackgroundEnhanceService, CarBackgroundError
from carpark.routes.photos import _InvalidImage

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


def test_enhance_photo_corrupt_generated_image_maps_to_422():
    """A non-decodable generated image must surface as a 422 CarBackgroundError,
    not a raw crash — pins the try/except _InvalidImage -> CarBackgroundError(422)
    in enhance_photo (mandated Review-Focus corrupt-image case)."""
    photos = MagicMock()
    photos.get_by_id.return_value = {'id': 7, 'vehicle_id': 3, 'url': 'private/carpark/3/orig.jpg',
                                     'enhanced_url': None, 'enhanced_thumbnail_url': None}
    client = MagicMock(); client.generate.return_value = b'studiobytes'
    repo = MagicMock(); repo.get_by_type.return_value = {'config': {'background_id': 'studio-white'}}
    svc = CarBackgroundEnhanceService(client=client, photo_repo=photos, repo=repo)
    with patch('core.services.spaces_service.resolve_image_bytes', return_value=b'orig'), \
         patch('core.services.spaces_service.upload') as up, \
         patch('core.services.spaces_service.delete'), \
         patch('carpark.routes.photos._compress_jpeg', side_effect=_InvalidImage('bad decode')):
        with pytest.raises(CarBackgroundError) as e:
            svc.enhance_photo(7)
    assert e.value.status == 422
    up.assert_not_called()
    photos.set_enhanced.assert_not_called()
