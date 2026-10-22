"""Tests for buyback.seller_identity.seller_display_name — the single
person-vs-company name resolver shared by contracts, PDFs, emails,
notifications, list views and the CarPark hand-off. No DB, no I/O."""

from buyback.seller_identity import seller_display_name


def test_person_uses_seller_name():
    assert seller_display_name(
        {'client_type': 'person', 'seller_name': 'Ion Pop', 'seller_company_name': ''}
    ) == 'Ion Pop'


def test_company_uses_company_name_not_seller_name():
    # The firm is the party; a stray person value in seller_name is ignored.
    assert seller_display_name(
        {'client_type': 'company', 'seller_name': 'Ion Pop', 'seller_company_name': 'Auto SRL'}
    ) == 'Auto SRL'


def test_legacy_company_falls_back_to_seller_name():
    # Records created before seller_company_name existed stored the firm in
    # seller_name — still render the firm.
    assert seller_display_name(
        {'client_type': 'company', 'seller_name': 'Legacy Firm SRL'}
    ) == 'Legacy Firm SRL'


def test_company_with_blank_company_name_falls_back():
    assert seller_display_name(
        {'client_type': 'company', 'seller_name': 'X SRL', 'seller_company_name': '   '}
    ) == 'X SRL'


def test_empty_record_returns_empty_string():
    assert seller_display_name(None) == ''
    assert seller_display_name({}) == ''
