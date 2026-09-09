"""Shopify Standard Product Taxonomy constants for CarPark vehicles."""

CARS_CATEGORY_GID = 'gid://shopify/TaxonomyCategory/vp-2-2-1'

# Dimensions with a native Shopify choice-list attribute (value GID mapping).
DIMENSION_ATTRIBUTES = {
    'fuel_type':    'gid://shopify/TaxonomyAttribute/2177',  # Fuel supply
    'transmission': 'gid://shopify/TaxonomyAttribute/2699',  # Transmission type
    'drive_type':   'gid://shopify/TaxonomyAttribute/2576',  # Drive type
    'color':        'gid://shopify/TaxonomyAttribute/1',     # Color
    'condition':    'gid://shopify/TaxonomyAttribute/2680',  # Item condition
}

# All mapped dimensions (native attrs + free dimensions).
DIMENSIONS = list(DIMENSION_ATTRIBUTES.keys()) + ['brand', 'body_type', 'category']

# dimension -> carpark_vehicles column it reads from.
_VEHICLE_FIELD = {
    'fuel_type': 'fuel_type',
    'transmission': 'transmission',
    'drive_type': 'drive_type',
    'color': 'color_exterior',
    'condition': 'state',
    'brand': 'brand',
    'body_type': 'body_type',
    'category': 'vehicle_type',
}


def vehicle_field_for(dimension: str) -> str:
    return _VEHICLE_FIELD[dimension]
