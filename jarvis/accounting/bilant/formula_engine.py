"""Bilant Formula Engine — ported from Conta-Bilant-Generator.

Pure calculation logic: parses Romanian accounting formulas (CT/RD),
evaluates against Balanta data, computes financial ratios.
No database or Flask dependencies.
"""

import re
import pandas as pd


# Balanta column indices (0-indexed)
COL_BAL_ACCOUNT = 0  # Cont (account number)
COL_BAL_SFD = 1      # Sold Final Debit
COL_BAL_SFC = 2      # Sold Final Credit


# ── Standard ratio definitions (constant, not configurable) ──

STANDARD_RATIOS = {
    'lichiditate_curenta': {
        'label': 'Lichiditate Curenta',
        'formula': lambda m: m.get('active_circulante', 0) / m['datorii_termen_scurt'] if m.get('datorii_termen_scurt', 0) > 0 else None,
        'interpretation': 'Ideal > 1',
        'format': 'ratio',
    },
    'lichiditate_rapida': {
        'label': 'Lichiditate Rapida',
        'formula': lambda m: (m.get('active_circulante', 0) - m.get('stocuri', 0)) / m['datorii_termen_scurt'] if m.get('datorii_termen_scurt', 0) > 0 else None,
        'interpretation': 'Ideal > 0.8',
        'format': 'ratio',
    },
    'lichiditate_imediata': {
        'label': 'Lichiditate Imediata',
        'formula': lambda m: m.get('disponibilitati', 0) / m['datorii_termen_scurt'] if m.get('datorii_termen_scurt', 0) > 0 else None,
        'interpretation': 'Ideal > 0.2',
        'format': 'ratio',
    },
    'solvabilitate': {
        'label': 'Solvabilitate (%)',
        'formula': lambda m: m.get('capitaluri_proprii', 0) / m['total_active'] * 100 if m.get('total_active', 0) > 0 else None,
        'interpretation': 'Ideal > 50%',
        'format': 'percent',
    },
    'indatorare': {
        'label': 'Indatorare (%)',
        'formula': lambda m: m.get('total_datorii', 0) / m['total_active'] * 100 if m.get('total_active', 0) > 0 else None,
        'interpretation': 'Ideal < 50%',
        'format': 'percent',
    },
    'autonomie_financiara': {
        'label': 'Autonomie Financiara (%)',
        'formula': lambda m: m.get('capitaluri_proprii', 0) / (m.get('capitaluri_proprii', 0) + m.get('total_datorii', 0)) * 100 if (m.get('capitaluri_proprii', 0) + m.get('total_datorii', 0)) > 0 else None,
        'interpretation': 'Ideal > 50%',
        'format': 'percent',
    },
}


# ── Balanta preparation ──

def prepare_balanta(df_balanta):
    """Skip header row if present."""
    df = df_balanta.copy()
    if len(df) > 0 and df.iloc[0, COL_BAL_ACCOUNT] == 'Cont':
        df = df.iloc[1:].reset_index(drop=True)
    return df


# ── Formula extraction ──

def extract_ct_formula(description):
    """Extract account formula from description.
    Example: "1.Cheltuieli de constituire (ct.201-2801)" -> "201-2801"
    """
    if pd.isna(description):
        return ""
    text = str(description)
    match = re.search(r'ct\.\s*', text, re.IGNORECASE)
    if not match:
        return ""
    start_pos = match.end()
    paren_pos = text.find(')', start_pos)
    if paren_pos == -1:
        paren_pos = len(text)
    expr = text[start_pos:paren_pos].strip()
    expr = expr.replace('*', '')
    expr = re.sub(r'\s+', '', expr)
    expr = expr.replace('\r', '').replace('\n', '')
    return expr


def extract_row_formula(description):
    """Extract row formula from description.
    Example: "TOTAL (rd. 01 la 06)" -> "01+02+03+04+05+06"
    """
    if pd.isna(description):
        return ""
    text = str(description).lower()
    match = re.search(r'rd\.?\s*([^)]+)', text)
    if not match:
        return ""
    raw = match.group(1).strip()
    raw = re.sub(r'\s+', '', raw)
    la_match = re.search(r'(\d+)la(\d+)', raw)
    if la_match:
        start = int(la_match.group(1))
        end = int(la_match.group(2))
        width = len(la_match.group(1))
        if end >= start:
            parts = [str(i).zfill(width) for i in range(start, end + 1)]
            expanded = '+'.join(parts)
            raw = raw[:la_match.start()] + expanded + raw[la_match.end():]
    result = re.sub(r'[^0-9a-z+\-]', '', raw)
    result = re.sub(r'35a', '36', result)
    return result


# ── CT formula parsing and evaluation ──

def parse_ct_formula(expr):
    """Parse CT formula into list of (prefix, sign_type) tuples.
    sign_type: 'normal_plus', 'normal_minus', 'dynamic'
    """
    if not expr:
        return []
    items = []
    i = 0
    sign = 1
    while i < len(expr):
        if expr[i:i + 3] == '+/-':
            i += 3
            num = ''
            while i < len(expr) and expr[i].isdigit():
                num += expr[i]
                i += 1
            if num:
                items.append((num, 'dynamic'))
            continue
        if expr[i:i + 6].lower() == 'dinct.':
            i += 6
            num = ''
            while i < len(expr) and expr[i].isdigit():
                num += expr[i]
                i += 1
            if num:
                items.append((num, 'normal_minus'))
            continue
        if expr[i] == '+':
            sign = 1
            i += 1
            continue
        elif expr[i] == '-':
            sign = -1
            i += 1
            continue
        if expr[i].isdigit():
            num = ''
            while i < len(expr) and expr[i].isdigit():
                num += expr[i]
                i += 1
            if num:
                sign_type = 'normal_plus' if sign == 1 else 'normal_minus'
                items.append((num, sign_type))
            sign = 1
            continue
        i += 1
    return items


def sum_accounts_by_prefix(df_balanta, prefix, use_net=False):
    """Sum all accounts starting with prefix. Returns (total, details)."""
    total = 0
    details = []
    for _, row in df_balanta.iterrows():
        acct = str(row.iloc[COL_BAL_ACCOUNT])
        if acct.endswith('.0'):
            acct = acct[:-2]
        if acct.startswith(prefix):
            sfd = pd.to_numeric(row.iloc[COL_BAL_SFD], errors='coerce') or 0
            sfc = pd.to_numeric(row.iloc[COL_BAL_SFC], errors='coerce') or 0
            if use_net:
                val = sfd - sfc
            else:
                val = abs(sfd) + abs(sfc)
            total += val
            details.append((acct, val))
    return total, details


def eval_ct_expression(expr, df_balanta):
    """Evaluate CT expression. Returns (result, verification_details)."""
    items = parse_ct_formula(expr)
    total = 0
    all_details = []
    for prefix, sign_type in items:
        if sign_type == 'dynamic':
            subtotal, details = sum_accounts_by_prefix(df_balanta, prefix, use_net=True)
            if not details:
                all_details.append((prefix, 'No Val.', prefix, 'dynamic'))
            else:
                for acct, val in details:
                    all_details.append((acct, val, prefix, 'dynamic'))
            total += subtotal
        elif sign_type == 'normal_plus':
            subtotal, details = sum_accounts_by_prefix(df_balanta, prefix, use_net=False)
            if not details:
                all_details.append((prefix, 'No Val.', prefix, '+'))
            else:
                for acct, val in details:
                    all_details.append((acct, val, prefix, '+'))
            total += subtotal
        elif sign_type == 'normal_minus':
            subtotal, details = sum_accounts_by_prefix(df_balanta, prefix, use_net=False)
            if not details:
                all_details.append((prefix, 'No Val.', prefix, '-'))
            else:
                for acct, val in details:
                    all_details.append((acct, -val, prefix, '-'))
            total -= subtotal
    return total, all_details


# ── Row formula evaluation ──

def eval_row_formula(expr, bilant_values):
    """Evaluate row formula referencing other Bilant rows."""
    if not expr:
        return 0
    total = 0
    sign = 1
    row_ref = ''
    for ch in expr + '+':
        if ch.isdigit() or ch.isalpha():
            row_ref += ch
        elif ch in '+-':
            if row_ref:
                match = re.match(r'^0*(\d+[a-z]*)$', row_ref)
                if match:
                    row_num = match.group(1) or '0'
                else:
                    row_num = row_ref
                val = bilant_values.get(row_num, 0)
                total += sign * val
                row_ref = ''
            sign = 1 if ch == '+' else -1
    return total


# ── Main processing (template-driven) ──

def process_bilant_from_template(df_balanta, template_rows):
    """Process Balanta against template rows from DB.

    Args:
        df_balanta: Balanta DataFrame (Cont, SFD, SFC)
        template_rows: list of dicts with keys: id, description, nr_rd,
                       formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order

    Returns:
        (bilant_values, results) where:
        - bilant_values: dict mapping nr_rd -> value
        - results: list of dicts with keys: template_row_id, nr_rd, description,
                   formula_ct, formula_rd, value, verification, sort_order
    """
    df_balanta = prepare_balanta(df_balanta)
    bilant_values = {}
    results = []

    # First pass: CT formulas
    for row in template_rows:
        nr_rd = str(row.get('nr_rd') or '').strip()
        formula_ct = (row.get('formula_ct') or '').strip()
        formula_rd = (row.get('formula_rd') or '').strip()

        val = 0
        verification = ''

        if formula_ct:
            val, details = eval_ct_expression(formula_ct, df_balanta)
            verif_lines = []
            for acct, acct_val, prefix, sign_type in details:
                if acct_val == 'No Val.':
                    verif_lines.append(f"{acct} = No Val.")
                else:
                    verif_lines.append(f"{acct} = {acct_val:.2f}")
            verification = '\n'.join(verif_lines)

        if nr_rd:
            bilant_values[nr_rd] = val

        results.append({
            'template_row_id': row.get('id'),
            'nr_rd': nr_rd,
            'description': row.get('description', ''),
            'formula_ct': formula_ct,
            'formula_rd': formula_rd,
            'value': val,
            'verification': verification,
            'sort_order': row.get('sort_order', 0),
        })

    # Second pass: RD formulas (for rows without CT formula)
    for i, row in enumerate(template_rows):
        formula_ct = (row.get('formula_ct') or '').strip()
        formula_rd = (row.get('formula_rd') or '').strip()

        if formula_rd and not formula_ct:
            val = eval_row_formula(formula_rd, bilant_values)
            results[i]['value'] = val
            results[i]['verification'] = f"Sum of rows: {formula_rd}"
            nr_rd = str(row.get('nr_rd') or '').strip()
            if nr_rd:
                bilant_values[nr_rd] = val

    return bilant_values, results


# ── Safe metric formula evaluator ──

_METRIC_TOKEN_RE = re.compile(r'''
    ([a-z_][a-z0-9_]*)   |  # identifier
    (\d+(?:\.\d+)?)       |  # number
    ([+\-*/])             |  # operator
    ([()])                |  # parens
    (\s+)                    # whitespace (skip)
''', re.VERBOSE)


def eval_metric_formula(expr, metric_values):
    """Safely evaluate a metric formula like 'active_circulante / datorii_termen_scurt'.

    Uses recursive descent parsing — no eval().
    Returns float or None (on division by zero or missing variables).
    Raises ValueError on invalid tokens.
    """
    if not expr or not expr.strip():
        return None

    # Tokenize
    tokens = []
    pos = 0
    while pos < len(expr):
        m = _METRIC_TOKEN_RE.match(expr, pos)
        if not m:
            raise ValueError(f"Invalid character in formula at position {pos}: '{expr[pos]}'")
        if m.group(5):  # whitespace — skip
            pos = m.end()
            continue
        if m.group(1):
            tokens.append(('IDENT', m.group(1)))
        elif m.group(2):
            tokens.append(('NUM', float(m.group(2))))
        elif m.group(3):
            tokens.append(('OP', m.group(3)))
        elif m.group(4):
            tokens.append(('PAREN', m.group(4)))
        pos = m.end()

    # Recursive descent parser
    idx = [0]  # mutable index

    def peek():
        return tokens[idx[0]] if idx[0] < len(tokens) else None

    def advance():
        tok = tokens[idx[0]]
        idx[0] += 1
        return tok

    def parse_expr():
        """expr = term (('+' | '-') term)*"""
        left = parse_term()
        if left is None:
            return None
        while True:
            tok = peek()
            if tok and tok[0] == 'OP' and tok[1] in ('+', '-'):
                advance()
                right = parse_term()
                if right is None:
                    return None
                left = left + right if tok[1] == '+' else left - right
            else:
                break
        return left

    def parse_term():
        """term = unary (('*' | '/') unary)*"""
        left = parse_unary()
        if left is None:
            return None
        while True:
            tok = peek()
            if tok and tok[0] == 'OP' and tok[1] in ('*', '/'):
                advance()
                right = parse_unary()
                if right is None:
                    return None
                if tok[1] == '*':
                    left = left * right
                else:
                    if right == 0:
                        return None  # division by zero
                    left = left / right
            else:
                break
        return left

    def parse_unary():
        """unary = '-' unary | atom"""
        tok = peek()
        if tok and tok[0] == 'OP' and tok[1] == '-':
            advance()
            val = parse_unary()
            return -val if val is not None else None
        return parse_atom()

    def parse_atom():
        """atom = NUMBER | IDENTIFIER | '(' expr ')'"""
        tok = peek()
        if not tok:
            raise ValueError("Unexpected end of formula")
        if tok[0] == 'NUM':
            advance()
            return tok[1]
        if tok[0] == 'IDENT':
            advance()
            val = metric_values.get(tok[1])
            if val is None:
                return None  # missing variable
            return float(val)
        if tok[0] == 'PAREN' and tok[1] == '(':
            advance()
            val = parse_expr()
            closing = peek()
            if not closing or closing[0] != 'PAREN' or closing[1] != ')':
                raise ValueError("Missing closing parenthesis")
            advance()
            return val
        raise ValueError(f"Unexpected token: {tok}")

    result = parse_expr()
    if idx[0] < len(tokens):
        raise ValueError(f"Unexpected token after expression: {tokens[idx[0]]}")
    return result


# ── Metric calculation (config-driven) ──

def calculate_metrics_from_config(bilant_values, metric_configs):
    """Calculate BI metrics using configurable row→metric mappings.

    Supports 5 metric groups:
    - summary: maps nr_rd → value (stat cards)
    - ratio_input: maps nr_rd → value (hidden, feeds ratios)
    - ratio: computed via formula_expr (ratio cards)
    - structure: maps nr_rd → value with structure_side (chart breakdown)
    - derived: computed via formula_expr (stat cards)

    Falls back to STANDARD_RATIOS if no ratio configs exist (backward compat).
    """
    # Pass 1: collect values from nr_rd-mapped configs (summary, ratio_input, structure)
    metric_values = {}
    has_ratio_configs = False
    has_structure_configs = False

    for cfg in metric_configs:
        key = cfg['metric_key']
        group = cfg.get('metric_group', 'summary')
        nr_rd = (cfg.get('nr_rd') or '')
        if isinstance(nr_rd, (int, float)):
            nr_rd = str(int(nr_rd))
        nr_rd = str(nr_rd).strip()
        formula_expr = (cfg.get('formula_expr') or '').strip()

        if group in ('summary', 'ratio_input'):
            if nr_rd:
                metric_values[key] = bilant_values.get(nr_rd, 0)
        elif group == 'structure':
            has_structure_configs = True
            if nr_rd:
                metric_values[key] = bilant_values.get(nr_rd, 0)
        elif group in ('ratio', 'derived'):
            if group == 'ratio':
                has_ratio_configs = True

    # Auto-derive total_active / total_datorii if not explicitly set
    if 'total_active' not in metric_values:
        metric_values['total_active'] = (
            metric_values.get('active_imobilizate', 0) + metric_values.get('active_circulante', 0)
        )
    if 'total_datorii' not in metric_values:
        metric_values['total_datorii'] = (
            metric_values.get('datorii_termen_scurt', 0) + metric_values.get('datorii_termen_lung', 0)
        )

    # Pass 2: evaluate formula_expr for derived/ratio configs
    for cfg in metric_configs:
        key = cfg['metric_key']
        group = cfg.get('metric_group', 'summary')
        formula_expr = (cfg.get('formula_expr') or '').strip()

        if group == 'derived' and formula_expr:
            try:
                val = eval_metric_formula(formula_expr, metric_values)
                if val is not None:
                    metric_values[key] = val
            except ValueError:
                metric_values[key] = 0

    # Build summary from summary + derived configs
    summary = {}
    for cfg in metric_configs:
        group = cfg.get('metric_group', 'summary')
        if group in ('summary', 'derived'):
            key = cfg['metric_key']
            summary[key] = metric_values.get(key, 0)

    # Always include auto-derived totals in summary if not already there
    if 'total_active' not in summary and metric_values.get('total_active', 0) != 0:
        summary['total_active'] = metric_values['total_active']
    if 'total_datorii' not in summary and metric_values.get('total_datorii', 0) != 0:
        summary['total_datorii'] = metric_values['total_datorii']

    # Build ratios
    ratios = {}
    if has_ratio_configs:
        for cfg in metric_configs:
            if cfg.get('metric_group') != 'ratio':
                continue
            key = cfg['metric_key']
            formula_expr = (cfg.get('formula_expr') or '').strip()
            display_format = cfg.get('display_format', 'ratio')
            if not formula_expr:
                continue
            try:
                val = eval_metric_formula(formula_expr, metric_values)
                if val is not None:
                    val = round(val, 2 if display_format == 'ratio' else 1)
                ratios[key] = {
                    'value': val,
                    'label': cfg.get('metric_label', key),
                    'interpretation': cfg.get('interpretation'),
                }
            except ValueError:
                ratios[key] = {'value': None, 'label': cfg.get('metric_label', key), 'interpretation': None}
    else:
        # Fallback: use hardcoded STANDARD_RATIOS for old templates
        for key, spec in STANDARD_RATIOS.items():
            val = spec['formula'](metric_values)
            if val is not None:
                val = round(val, 2 if spec['format'] == 'ratio' else 1)
            ratios[key] = val

    # Build structure
    structure = {'assets': [], 'liabilities': []}
    if has_structure_configs:
        total_active = metric_values.get('total_active', 0)
        total_pasive = metric_values.get('capitaluri_proprii', 0) + metric_values.get('total_datorii', 0)
        for cfg in metric_configs:
            if cfg.get('metric_group') != 'structure':
                continue
            key = cfg['metric_key']
            side = cfg.get('structure_side', 'assets')
            v = metric_values.get(key, 0)
            denom = total_active if side == 'assets' else total_pasive
            structure[side].append({
                'name': cfg.get('metric_label', key),
                'value': v,
                'percent': round(v / denom * 100, 1) if denom > 0 else 0,
            })
    else:
        # Fallback: hardcoded structure for old templates
        total_active = metric_values.get('total_active', 0)
        if total_active > 0:
            for key, label in [('active_imobilizate', 'Active Imobilizate'), ('stocuri', 'Stocuri'),
                               ('creante', 'Creante'), ('disponibilitati', 'Disponibilitati')]:
                v = metric_values.get(key, 0)
                structure['assets'].append({
                    'name': label, 'value': v,
                    'percent': round(v / total_active * 100, 1),
                })
        total_pasive = metric_values.get('capitaluri_proprii', 0) + metric_values.get('total_datorii', 0)
        if total_pasive > 0:
            for key, label in [('capitaluri_proprii', 'Capitaluri Proprii'),
                               ('datorii_termen_scurt', 'Datorii < 1 an'),
                               ('datorii_termen_lung', 'Datorii > 1 an')]:
                v = metric_values.get(key, 0)
                structure['liabilities'].append({
                    'name': label, 'value': v,
                    'percent': round(v / total_pasive * 100, 1),
                })

    return {'summary': summary, 'ratios': ratios, 'structure': structure}
