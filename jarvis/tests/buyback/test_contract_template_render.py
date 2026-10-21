"""Tests for buyback contract template rendering engine."""
import pytest
from buyback.services.contract_template import (
    render_contract_template,
    PLACEHOLDERS,
)


def test_substitutes_whitelisted_tokens():
    out = render_contract_template('Marca {brand}, VIN {vin}', {'brand': 'Volvo', 'vin': 'YV1'})
    assert out == 'Marca Volvo, VIN YV1'


def test_none_value_renders_empty():
    assert render_contract_template('Pret {price_eur} EUR', {'price_eur': None}) == 'Pret  EUR'


def test_unknown_token_left_literal():
    assert render_contract_template('Hi {not_a_token}', {}) == 'Hi {not_a_token}'


def test_empty_template_returns_empty():
    assert render_contract_template('', {'brand': 'X'}) == ''


def test_consignment_tokens_present_in_whitelist():
    for t in ('owner_price', 'min_price', 'promo_price', 'commission', 'monthly_fee'):
        assert t in PLACEHOLDERS
