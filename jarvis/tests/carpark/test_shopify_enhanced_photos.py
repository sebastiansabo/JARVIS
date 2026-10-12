"""Tests for Shopify enhanced photo variant publishing logic."""
from carpark.connectors.shopify.connector import _effective_key


def test_effective_key_prefers_published_enhanced():
    """When enhanced_published=True and enhanced_url exists, use the enhanced URL."""
    assert _effective_key({'url': 'orig.jpg', 'enhanced_url': 'enh.jpg',
                           'enhanced_published': True}) == 'enh.jpg'


def test_effective_key_falls_back_when_not_published():
    """When enhanced_published=False, fall back to original URL even if enhanced exists."""
    assert _effective_key({'url': 'orig.jpg', 'enhanced_url': 'enh.jpg',
                           'enhanced_published': False}) == 'orig.jpg'


def test_effective_key_falls_back_when_variant_missing():
    """When enhanced_published=True but enhanced_url is None, fall back to original."""
    assert _effective_key({'url': 'orig.jpg', 'enhanced_url': None,
                           'enhanced_published': True}) == 'orig.jpg'
