import os, uuid, pytest
pytestmark = pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='needs real DB')

from carpark.repositories.photo_repository import PhotoRepository


def _vehicle():
    """Insert a minimal carpark_vehicles row (FK target) and return its id.

    Uses a fresh unique VIN each run since the shared local DB persists rows.
    """
    repo = PhotoRepository()  # BaseRepository.execute is inherited
    vin = ('T' + uuid.uuid4().hex)[:17]
    row = repo.execute(
        "INSERT INTO carpark_vehicles (vin, brand, model) VALUES (%s,%s,%s) RETURNING id",
        (vin, 'TestBrand', 'TestModel'), returning=True)
    return row['id']


def test_set_and_clear_enhanced():
    repo = PhotoRepository()
    vid = _vehicle()
    p = repo.create(vehicle_id=vid, url='private/carpark/x/orig.jpg')
    out = repo.set_enhanced(p['id'], 'private/carpark/x/enhanced_ab.jpg',
                            'private/carpark/x/enhanced_ab_thumb.jpg', 'studio-white')
    assert out['enhanced_url'].endswith('enhanced_ab.jpg')
    assert out['enhanced_background_id'] == 'studio-white'
    assert out['enhanced_published'] is False
    pub = repo.set_enhanced_published(p['id'], True)
    assert pub['enhanced_published'] is True
    cleared = repo.clear_enhanced(p['id'])
    assert cleared['enhanced_url'] is None and cleared['enhanced_published'] is False
