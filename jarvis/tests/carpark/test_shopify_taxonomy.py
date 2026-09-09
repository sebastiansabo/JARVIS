# jarvis/tests/carpark/test_shopify_taxonomy.py
from carpark.connectors.shopify import taxonomy as tx

def test_dimensions_and_attribute_gids():
    assert tx.CARS_CATEGORY_GID.endswith('vp-2-2-1')
    assert tx.DIMENSION_ATTRIBUTES['fuel_type'] == 'gid://shopify/TaxonomyAttribute/2177'
    assert tx.DIMENSION_ATTRIBUTES['transmission'] == 'gid://shopify/TaxonomyAttribute/2699'
    assert tx.DIMENSION_ATTRIBUTES['drive_type'] == 'gid://shopify/TaxonomyAttribute/2576'
    assert tx.DIMENSION_ATTRIBUTES['color'] == 'gid://shopify/TaxonomyAttribute/1'
    assert tx.DIMENSION_ATTRIBUTES['condition'] == 'gid://shopify/TaxonomyAttribute/2680'
    assert set(tx.DIMENSIONS) == {'fuel_type','transmission','drive_type','color',
                                  'condition','brand','body_type','category'}

def test_vehicle_field_for():
    assert tx.vehicle_field_for('fuel_type') == 'fuel_type'
    assert tx.vehicle_field_for('color') == 'color_exterior'
    assert tx.vehicle_field_for('condition') == 'state'
    assert tx.vehicle_field_for('category') == 'vehicle_type'
