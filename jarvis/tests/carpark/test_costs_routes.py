"""Test for cost type constants in carpark routes."""

from carpark.routes.costs import VALID_COST_TYPES


def test_achizitie_cost_type_is_valid():
    """Verify that 'achizitie' (acquisition cost) is registered in VALID_COST_TYPES."""
    assert 'achizitie' in VALID_COST_TYPES
