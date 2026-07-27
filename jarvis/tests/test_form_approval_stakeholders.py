from forms.services.form_service import FormService


def test_no_second_approver_returns_primary_only():
    assert FormService._build_stakeholder_ids(10, {}) == [10]


def test_distinct_second_appended():
    assert FormService._build_stakeholder_ids(10, {'f_bi_second_approver': '22'}) == [10, 22]


def test_second_equal_primary_deduped():
    assert FormService._build_stakeholder_ids(10, {'f_bi_second_approver': '10'}) == [10]


def test_non_numeric_second_ignored():
    assert FormService._build_stakeholder_ids(10, {'f_bi_second_approver': 'abc'}) == [10]


def test_no_primary_still_returns_second():
    assert FormService._build_stakeholder_ids(None, {'f_bi_second_approver': '22'}) == [22]
