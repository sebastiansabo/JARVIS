from core.suppliers.normalize import normalize_cui, normalize_nr_reg

def test_normalize_cui_strips_ro_prefix_and_spaces():
    assert normalize_cui('RO9997007') == '9997007'
    assert normalize_cui(' ro 999 70 07 ') == '9997007'
    assert normalize_cui('9997007') == '9997007'

def test_normalize_cui_empty_is_none():
    assert normalize_cui('') is None
    assert normalize_cui(None) is None
    assert normalize_cui('RO') is None

def test_normalize_nr_reg_upper_no_space_keeps_slashes():
    assert normalize_nr_reg('j40 / 1234 / 2020') == 'J40/1234/2020'
    assert normalize_nr_reg(None) is None
    assert normalize_nr_reg('   ') is None
