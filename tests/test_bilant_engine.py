"""Tests for the Bilant formula engine — parsing, evaluation, metrics."""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.bilant.formula_engine import (
    prepare_balanta,
    extract_ct_formula,
    extract_row_formula,
    parse_ct_formula,
    sum_accounts_by_prefix,
    eval_ct_expression,
    eval_row_formula,
    process_bilant_from_template,
    calculate_metrics_from_config,
)


# ── Fixtures ──

def make_balanta(rows):
    """Create a Balanta DataFrame from list of (account, sfd, sfc) tuples."""
    return pd.DataFrame(rows, columns=['Cont', 'SFD', 'SFC'])


@pytest.fixture
def sample_balanta():
    return make_balanta([
        ('201', 50000, 2500),
        ('2801', 2500, 0),
        ('203', 30000, 0),
        ('2803', 3000, 0),
        ('2903', 1000, 0),
        ('211', 100000, 0),
        ('212', 80000, 0),
        ('2811', 10000, 0),
        ('2812', 5000, 0),
        ('345', 0, 15000),
        ('346', 20000, 0),
        ('348', 5000, 3000),
        ('4428', 1200, 0),
    ])


# ══════════════════════════════════════════════════════════════
# prepare_balanta
# ══════════════════════════════════════════════════════════════

class TestPrepareBalanta:
    def test_skip_header_row(self):
        df = pd.DataFrame([['Cont', 'SFD', 'SFC'], ['201', 50000, 0]])
        result = prepare_balanta(df)
        assert len(result) == 1
        assert result.iloc[0, 0] == '201'

    def test_no_header_row(self):
        df = make_balanta([('201', 50000, 0)])
        result = prepare_balanta(df)
        assert len(result) == 1

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=['Cont', 'SFD', 'SFC'])
        result = prepare_balanta(df)
        assert len(result) == 0


# ══════════════════════════════════════════════════════════════
# extract_ct_formula
# ══════════════════════════════════════════════════════════════

class TestExtractCtFormula:
    def test_simple(self):
        assert extract_ct_formula("1.Cheltuieli (ct.201-2801)") == "201-2801"

    def test_complex(self):
        assert extract_ct_formula("Item (ct. 205 + 208 - 2805 - 2808 - 2905 - 2908)") == "205+208-2805-2808-2905-2908"

    def test_dynamic_sign(self):
        assert extract_ct_formula("Item (ct.345+346+/-348)") == "345+346+/-348"

    def test_dinct(self):
        assert extract_ct_formula("Item (ct.345-dinct.4428)") == "345-dinct.4428"

    def test_no_formula(self):
        assert extract_ct_formula("A. ACTIVE IMOBILIZATE") == ""

    def test_none(self):
        assert extract_ct_formula(None) == ""

    def test_nan(self):
        assert extract_ct_formula(float('nan')) == ""

    def test_asterisks_removed(self):
        assert extract_ct_formula("Item (ct.*201*-*2801*)") == "201-2801"

    def test_whitespace_removed(self):
        assert extract_ct_formula("Item (ct. 201 + 202 )") == "201+202"

    def test_no_dot_no_match(self):
        """'ct' without dot should not match (e.g., 'active')."""
        assert extract_ct_formula("Active circulante totale") == ""


# ══════════════════════════════════════════════════════════════
# extract_row_formula
# ══════════════════════════════════════════════════════════════

class TestExtractRowFormula:
    def test_range(self):
        assert extract_row_formula("TOTAL (rd. 01 la 06)") == "01+02+03+04+05+06"

    def test_range_two_digits(self):
        assert extract_row_formula("TOTAL (rd. 08 la 16)") == "08+09+10+11+12+13+14+15+16"

    def test_simple_addition(self):
        result = extract_row_formula("TOTAL (rd. 31+32+33)")
        assert '31' in result and '32' in result and '33' in result

    def test_35a_conversion(self):
        """35a should be converted to 36."""
        result = extract_row_formula("TOTAL (rd. 35a)")
        assert '36' in result

    def test_no_formula(self):
        assert extract_row_formula("Just a description") == ""

    def test_none(self):
        assert extract_row_formula(None) == ""


# ══════════════════════════════════════════════════════════════
# parse_ct_formula
# ══════════════════════════════════════════════════════════════

class TestParseCtFormula:
    def test_simple_plus(self):
        items = parse_ct_formula("201")
        assert items == [('201', 'normal_plus')]

    def test_plus_minus(self):
        items = parse_ct_formula("201-2801")
        assert items == [('201', 'normal_plus'), ('2801', 'normal_minus')]

    def test_multiple(self):
        items = parse_ct_formula("205+208-2805-2808")
        assert len(items) == 4
        assert items[0] == ('205', 'normal_plus')
        assert items[1] == ('208', 'normal_plus')
        assert items[2] == ('2805', 'normal_minus')
        assert items[3] == ('2808', 'normal_minus')

    def test_dynamic(self):
        items = parse_ct_formula("345+346+/-348")
        assert items == [
            ('345', 'normal_plus'),
            ('346', 'normal_plus'),
            ('348', 'dynamic'),
        ]

    def test_dinct(self):
        items = parse_ct_formula("345-dinct.4428")
        assert items == [
            ('345', 'normal_plus'),
            ('4428', 'normal_minus'),
        ]

    def test_empty(self):
        assert parse_ct_formula("") == []
        assert parse_ct_formula(None) == []

    def test_complex_mixed(self):
        items = parse_ct_formula("345+346-2801+/-348-dinct.4428")
        assert len(items) == 5
        assert ('345', 'normal_plus') in items
        assert ('346', 'normal_plus') in items
        assert ('2801', 'normal_minus') in items
        assert ('348', 'dynamic') in items
        assert ('4428', 'normal_minus') in items


# ══════════════════════════════════════════════════════════════
# sum_accounts_by_prefix
# ══════════════════════════════════════════════════════════════

class TestSumAccountsByPrefix:
    def test_normal_sum(self, sample_balanta):
        total, details = sum_accounts_by_prefix(sample_balanta, '201', use_net=False)
        assert total == 52500  # abs(50000) + abs(2500)
        assert len(details) == 1

    def test_net_sum(self, sample_balanta):
        total, details = sum_accounts_by_prefix(sample_balanta, '348', use_net=True)
        assert total == 2000  # 5000 - 3000
        assert len(details) == 1

    def test_prefix_matching(self, sample_balanta):
        """Prefix '28' should match all accounts starting with 28."""
        total, details = sum_accounts_by_prefix(sample_balanta, '28', use_net=False)
        assert len(details) == 4  # 2801, 2803, 2811, 2812

    def test_no_match(self, sample_balanta):
        total, details = sum_accounts_by_prefix(sample_balanta, '999', use_net=False)
        assert total == 0
        assert len(details) == 0


# ══════════════════════════════════════════════════════════════
# eval_ct_expression
# ══════════════════════════════════════════════════════════════

class TestEvalCtExpression:
    def test_simple_subtraction(self, sample_balanta):
        total, details = eval_ct_expression("201-2801", sample_balanta)
        # 201: abs(50000)+abs(2500)=52500, minus 2801: abs(2500)+abs(0)=2500
        assert total == 50000  # 52500 - 2500

    def test_no_accounts(self, sample_balanta):
        total, details = eval_ct_expression("999", sample_balanta)
        assert total == 0
        assert any(d[1] == 'No Val.' for d in details)

    def test_dynamic_sign(self, sample_balanta):
        total, details = eval_ct_expression("+/-348", sample_balanta)
        assert total == 2000  # SFD(5000) - SFC(3000)


# ══════════════════════════════════════════════════════════════
# eval_row_formula
# ══════════════════════════════════════════════════════════════

class TestEvalRowFormula:
    def test_simple_sum(self):
        values = {'1': 100, '2': 200, '3': 300}
        assert eval_row_formula("1+2+3", values) == 600

    def test_subtraction(self):
        values = {'1': 100, '2': 50}
        assert eval_row_formula("1-2", values) == 50

    def test_leading_zeros(self):
        values = {'1': 100, '2': 200}
        assert eval_row_formula("01+02", values) == 300

    def test_missing_row(self):
        values = {'1': 100}
        assert eval_row_formula("1+2", values) == 100  # row 2 defaults to 0

    def test_empty(self):
        assert eval_row_formula("", {}) == 0
        assert eval_row_formula(None, {}) == 0


# ══════════════════════════════════════════════════════════════
# process_bilant_from_template
# ══════════════════════════════════════════════════════════════

class TestProcessBilantFromTemplate:
    def test_ct_and_rd_formulas(self, sample_balanta):
        template_rows = [
            {'id': 1, 'description': 'Row 1 (ct.201-2801)', 'nr_rd': '1',
             'formula_ct': '201-2801', 'formula_rd': '', 'row_type': 'data',
             'is_bold': False, 'indent_level': 0, 'sort_order': 0},
            {'id': 2, 'description': 'Row 2 (ct.203-2803-2903)', 'nr_rd': '2',
             'formula_ct': '203-2803-2903', 'formula_rd': '', 'row_type': 'data',
             'is_bold': False, 'indent_level': 0, 'sort_order': 1},
            {'id': 3, 'description': 'TOTAL', 'nr_rd': '3',
             'formula_ct': '', 'formula_rd': '1+2', 'row_type': 'total',
             'is_bold': True, 'indent_level': 0, 'sort_order': 2},
        ]

        bilant_values, results = process_bilant_from_template(sample_balanta, template_rows)

        assert len(results) == 3
        # Row 1: 201(52500) - 2801(2500) = 50000
        assert results[0]['value'] == 50000
        # Row 2: 203(30000) - 2803(3000) - 2903(1000) = 26000
        assert results[1]['value'] == 26000
        # Row 3 (TOTAL): row1 + row2 = 76000
        assert results[2]['value'] == 76000
        assert bilant_values['3'] == 76000

    def test_empty_template(self, sample_balanta):
        bilant_values, results = process_bilant_from_template(sample_balanta, [])
        assert len(results) == 0
        assert len(bilant_values) == 0

    def test_verification_details(self, sample_balanta):
        template_rows = [
            {'id': 1, 'description': 'Test', 'nr_rd': '1',
             'formula_ct': '201', 'formula_rd': '', 'row_type': 'data',
             'is_bold': False, 'indent_level': 0, 'sort_order': 0},
        ]
        _, results = process_bilant_from_template(sample_balanta, template_rows)
        assert '201' in results[0]['verification']
        assert '52500.00' in results[0]['verification']


# ══════════════════════════════════════════════════════════════
# calculate_metrics_from_config
# ══════════════════════════════════════════════════════════════

class TestCalculateMetricsFromConfig:
    def test_basic_metrics(self):
        bilant_values = {
            '25': 60000,   # Active Imobilizate
            '42': 40000,   # Active Circulante
            '30': 15000,   # Stocuri
            '39': 8000,    # Disponibilitati
            '40': 17000,   # Creante
            '54': 25000,   # Datorii < 1 an
            '55': 10000,   # Datorii > 1 an
            '101': 65000,  # Capitaluri Proprii
            '81': 30000,   # Capital Social
        }
        metric_configs = [
            {'metric_key': 'active_imobilizate', 'metric_label': 'Active Imobilizate', 'nr_rd': '25', 'metric_group': 'summary'},
            {'metric_key': 'active_circulante', 'metric_label': 'Active Circulante', 'nr_rd': '42', 'metric_group': 'summary'},
            {'metric_key': 'stocuri', 'metric_label': 'Stocuri', 'nr_rd': '30', 'metric_group': 'ratio_input'},
            {'metric_key': 'disponibilitati', 'metric_label': 'Disponibilitati', 'nr_rd': '39', 'metric_group': 'ratio_input'},
            {'metric_key': 'creante', 'metric_label': 'Creante', 'nr_rd': '40', 'metric_group': 'ratio_input'},
            {'metric_key': 'datorii_termen_scurt', 'metric_label': 'Datorii < 1 an', 'nr_rd': '54', 'metric_group': 'ratio_input'},
            {'metric_key': 'datorii_termen_lung', 'metric_label': 'Datorii > 1 an', 'nr_rd': '55', 'metric_group': 'ratio_input'},
            {'metric_key': 'capitaluri_proprii', 'metric_label': 'Capitaluri Proprii', 'nr_rd': '101', 'metric_group': 'summary'},
            {'metric_key': 'capital_social', 'metric_label': 'Capital Social', 'nr_rd': '81', 'metric_group': 'ratio_input'},
        ]

        metrics = calculate_metrics_from_config(bilant_values, metric_configs)

        # Summary
        assert metrics['summary']['total_active'] == 100000
        assert metrics['summary']['active_imobilizate'] == 60000
        assert metrics['summary']['active_circulante'] == 40000
        assert metrics['summary']['capitaluri_proprii'] == 65000
        assert metrics['summary']['total_datorii'] == 35000

        # Ratios
        assert metrics['ratios']['lichiditate_curenta'] == 1.6   # 40000 / 25000
        assert metrics['ratios']['lichiditate_rapida'] == 1.0    # (40000-15000) / 25000
        assert metrics['ratios']['lichiditate_imediata'] == 0.32  # 8000 / 25000
        assert metrics['ratios']['solvabilitate'] == 65.0         # 65000/100000*100
        assert metrics['ratios']['indatorare'] == 35.0            # 35000/100000*100
        assert metrics['ratios']['autonomie_financiara'] == 65.0  # 65000/(65000+35000)*100

        # Structure
        assert len(metrics['structure']['assets']) == 4
        assert len(metrics['structure']['liabilities']) == 3

    def test_zero_denom(self):
        """Ratios should be None when denominators are 0."""
        bilant_values = {'25': 0, '42': 0}
        metric_configs = [
            {'metric_key': 'active_imobilizate', 'metric_label': 'AI', 'nr_rd': '25', 'metric_group': 'summary'},
            {'metric_key': 'active_circulante', 'metric_label': 'AC', 'nr_rd': '42', 'metric_group': 'summary'},
        ]
        metrics = calculate_metrics_from_config(bilant_values, metric_configs)
        assert metrics['ratios']['lichiditate_curenta'] is None
        assert metrics['ratios']['solvabilitate'] is None

    def test_empty_configs(self):
        metrics = calculate_metrics_from_config({'25': 100}, [])
        assert metrics['summary']['total_active'] == 0
        assert metrics['ratios']['lichiditate_curenta'] is None
