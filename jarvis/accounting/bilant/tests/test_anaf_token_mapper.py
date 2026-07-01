"""Tests for ANAF token mapper."""
import pytest


def test_map_f10_c2_basic():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R01': 20550, 'R02': 2369495, 'R04': 2390045, 'R49': 8173633}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    assert tokens['F10_0012'] == 20550
    assert tokens['F10_0022'] == 2369495
    assert tokens['F10_0042'] == 2390045
    assert tokens['F10_0492'] == 8173633
    # No C1 tokens when prior_values is None
    assert 'F10_0011' not in tokens


def test_map_f10_with_prior():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R01': 20550}
    prior = {'R01': 10000}
    tokens = map_f10_to_tokens(f10s, prior_values=prior, entity_type='UU')
    assert tokens['F10_0012'] == 20550
    assert tokens['F10_0011'] == 10000


def test_map_f10_sub_rows():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R301': 21777201, 'R302': 0}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    assert tokens['F10_3012'] == 21777201
    assert 'F10_3022' not in tokens  # zero values omitted


def test_map_f10_skips_zero():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R01': 0, 'R02': 100}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    assert 'F10_0012' not in tokens  # zero omitted
    assert tokens['F10_0022'] == 100


def test_map_f10_validates_tokens():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    # R99 does not exist in S1005 F10 schema
    f10s = {'R99': 999}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    # Should silently skip invalid tokens (R99 doesn't map to a valid F10 token)
    assert not any('F10_0992' in k for k in tokens)


def test_map_f20_micro():
    from accounting.bilant.anaf_token_mapper import map_f20_to_tokens
    f20 = {'named': {'R01': 242230516, 'R04': 0}, 'standalone': {}, 'rows_with_c1_zero': set()}
    tokens = map_f20_to_tokens(f20, entity_type='UU')
    assert tokens['F20_0012'] == 242230516
    assert 'F20_0042' not in tokens  # zero omitted
