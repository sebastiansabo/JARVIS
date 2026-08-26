import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
import pytest
from foi_parcurs.repositories.rental_category_repository import RentalCategoryRepository


def _repo():
    return RentalCategoryRepository()


def test_list_categories_attaches_price_map():
    repo = _repo()
    repo.query_all = MagicMock(side_effect=[
        [{'id': 7, 'name': 'SUV+', 'franchise_eur': 250, 'extra_km_eur': 0.25,
          'models_note': 'x', 'sort_order': 0, 'is_active': True}],   # categories
        [{'category_id': 7, 'interval_id': 2, 'eur_per_day': 31},
         {'category_id': 7, 'interval_id': 1, 'eur_per_day': 33}],    # prices
    ])
    cats = repo.list_categories(11)
    assert cats[0]['prices'] == {2: 31, 1: 33}


def test_price_for_uses_selected_interval():
    repo = _repo()
    repo.query_one = MagicMock(side_effect=[
        {'id': 7, 'franchise_eur': 250, 'extra_km_eur': 0.25},   # category
        {'eur_per_day': 28},                                     # price row
    ])
    repo.query_all = MagicMock(return_value=[
        {'id': 1, 'label': 'Short term', 'min_days': 1, 'max_days': 8},
        {'id': 3, 'label': 'Medium term', 'min_days': 31, 'max_days': 90},
    ])
    out = repo.price_for(11, 7, 45)   # 45 days -> interval id 3
    assert out['eur_per_day'] == 28
    assert out['interval_id'] == 3
    assert out['franchise_eur'] == 250
    assert out['extra_km_eur'] == 0.25


def test_price_for_missing_category_returns_none():
    repo = _repo()
    repo.query_one = MagicMock(return_value=None)
    assert repo.price_for(11, 999, 5) is None


def test_price_for_no_matching_interval_returns_none():
    repo = _repo()
    repo.query_one = MagicMock(return_value={'id': 7, 'franchise_eur': 250, 'extra_km_eur': 0.25})
    repo.query_all = MagicMock(return_value=[{'id': 1, 'label': 'Short term', 'min_days': 10, 'max_days': 20}])
    assert repo.price_for(11, 7, 5) is None


def test_delete_category_refuses_when_cars_reference_it():
    repo = _repo()
    repo.query_one = MagicMock(return_value={'n': 3})
    with pytest.raises(ValueError):
        repo.delete_category(11, 7)


def test_add_category_rejects_blank_name():
    repo = _repo()
    with pytest.raises(ValueError):
        repo.add_category(11, '   ')
