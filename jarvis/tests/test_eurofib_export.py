from core.suppliers.eurofib_export import HEADER, build_csv, build_medline_rows

_SAMPLE_CONFIG = {
    'klient': '140',
    'konto_credit': '40102793',
    'konto_debit': '628701',
    'gegenkonto_credit': '628701',
    'gegenkonto_debit': '',
    'kostenstelle_debit': '0393',
    'kostenstelle_credit': '',
    'extbeleg_credit': 'invoice_number',
    'extbeleg_debit': '',
    'steuercode': '621',
    'belegart': 'JC',
    'text_template': '.SERVICII SPATII VERZI - INTRETINERE',
}

_SAMPLE_INVOICE = {
    'supplier': 'Some Supplier SRL',
    'invoice_number': '17278',
    'invoice_date': '2026-08-31',
    'due_date': '2026-09-30',
    'net_amount': 3042.00,
    'vat_amount': 638.82,
    'gross_amount': 3680.82,
}


def _col(row, name):
    return row[HEADER.index(name)]


def test_header_has_56_columns():
    assert len(HEADER) == 56
    assert HEADER[0] == ''


def test_build_medline_rows_returns_credit_then_debit():
    rows = build_medline_rows(_SAMPLE_INVOICE, _SAMPLE_CONFIG)
    assert len(rows) == 2
    for row in rows:
        assert len(row) == 56

    credit, debit = rows
    assert _col(credit, 'konto') == '40102793'
    assert _col(credit, 'soll_haben') == 'h'
    assert _col(credit, 'betrag') == '3680.82'
    assert _col(credit, 'klient') == '140'
    assert _col(credit, 'gegenkonto') == '628701'
    assert _col(credit, 'extbeleg') == '17278'

    assert _col(debit, 'konto') == '628701'
    assert _col(debit, 'soll_haben') == 's'
    assert _col(debit, 'betrag') == '3042.00'
    assert _col(debit, 'steuercode') == '621'
    assert _col(debit, 'steuerbetrag') == '638.82'
    assert _col(debit, 'kostenstelle') == '0393'


def test_credit_row_marker_and_belegart_same_both():
    credit, debit = build_medline_rows(_SAMPLE_INVOICE, _SAMPLE_CONFIG)
    assert credit[0] == 'x'
    assert debit[0] == ''
    assert _col(credit, 'belegart') == 'JC'
    assert _col(debit, 'belegart') == 'JC'


def test_belegnummer_numeric_rightmost6():
    credit, debit = build_medline_rows({**_SAMPLE_INVOICE, 'invoice_number': 'MEDL2 195'}, _SAMPLE_CONFIG)
    assert _col(credit, 'belegnummer') == '2195'
    assert _col(debit, 'belegnummer') == '2195'
    assert _col(credit, 'extbeleg') == '2195'
    c2, _ = build_medline_rows({**_SAMPLE_INVOICE, 'invoice_number': 'AB-1234567'}, _SAMPLE_CONFIG)
    assert _col(c2, 'belegnummer') == '234567'


def test_valuta_and_brutto_netto_same_on_both_lines():
    credit, debit = build_medline_rows(_SAMPLE_INVOICE, _SAMPLE_CONFIG)
    assert _col(credit, 'valuta') == '2026-09-30'
    assert _col(debit, 'valuta') == '2026-09-30'
    assert _col(credit, 'brutto_netto') == 'N'
    assert _col(debit, 'brutto_netto') == 'N'


def test_debit_row_has_blank_klient_and_marker():
    credit, debit = build_medline_rows(_SAMPLE_INVOICE, _SAMPLE_CONFIG)
    assert _col(debit, 'klient') == ''


def test_extbeleg_same_on_both_when_configured_either_side():
    config = dict(_SAMPLE_CONFIG, extbeleg_credit='', extbeleg_debit='invoice_number')
    credit, debit = build_medline_rows(_SAMPLE_INVOICE, config)
    assert _col(credit, 'extbeleg') == '17278'
    assert _col(debit, 'extbeleg') == '17278'


def test_build_csv_has_bom_semicolons_header_and_two_rows_per_invoice():
    csv_text = build_csv([(_SAMPLE_INVOICE, _SAMPLE_CONFIG)])
    assert csv_text.startswith('﻿')
    body = csv_text[1:]
    lines = [l for l in body.split('\r\n') if l]
    assert len(lines) == 3  # header + credit + debit
    assert lines[0].split(';')[1] == 'klient'
    assert '40102793' in lines[1]
    assert '628701' in lines[2]


def test_build_csv_groups_and_orders_by_supplier():
    inv_a = dict(_SAMPLE_INVOICE, supplier='Zeta SRL', invoice_number='1')
    inv_b = dict(_SAMPLE_INVOICE, supplier='Alpha SRL', invoice_number='2')
    csv_text = build_csv([(inv_a, _SAMPLE_CONFIG), (inv_b, _SAMPLE_CONFIG)])
    body = csv_text[1:]
    lines = [l for l in body.split('\r\n') if l]
    # header, then Alpha's 2 rows, then Zeta's 2 rows
    assert 'Alpha' not in lines[0]
    first_data_belegnummer = lines[1].split(';')[HEADER.index('belegnummer')]
    assert first_data_belegnummer == '2'  # Alpha SRL's invoice comes first


def test_build_csv_skips_incomplete_config_and_missing_amounts():
    incomplete_config = dict(_SAMPLE_CONFIG, konto_debit='')
    missing_amount_invoice = dict(_SAMPLE_INVOICE, invoice_number='3', net_amount=None)
    good_invoice = dict(_SAMPLE_INVOICE, invoice_number='4')

    skipped = []
    csv_text = build_csv(
        [
            (dict(_SAMPLE_INVOICE, invoice_number='2'), incomplete_config),
            (missing_amount_invoice, _SAMPLE_CONFIG),
            (good_invoice, _SAMPLE_CONFIG),
        ],
        skipped=skipped,
    )
    body = csv_text[1:]
    lines = [l for l in body.split('\r\n') if l]
    assert len(lines) == 3  # header + only the good invoice's 2 rows
    assert len(skipped) == 2
    reasons = {s['reason'] for s in skipped}
    assert reasons == {'incomplete_config', 'missing_amounts'}
