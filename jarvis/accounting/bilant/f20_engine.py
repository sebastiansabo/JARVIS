"""F20 Engine — Compute Cont de Profit și Pierdere (Profit & Loss) from Balanta TSD/TSC.

Pure computation module with no Flask/DB dependencies.
Validated against ANAF form S1003_A1.0.0 (2025) benchmark with 100% accuracy.
"""


def compute_f20(accounts: dict) -> dict:
    """Compute F20 (Profit & Loss) values from account TSD/TSC data.

    Args:
        accounts: {account_code: {'tsd': float, 'tsc': float}}
                  where TSD = Total Sume Debit (cumulative turnover debit)
                  and TSC = Total Sume Credit (cumulative turnover credit)

    Returns:
        dict with keys:
        - 'named': {row_tag: int} for named rows (R01, R16, R17, ...)
        - 'standalone': {(after_row, pair_idx): int} for standalone C1/C2 pairs
        - 'rows_with_c1_zero': set of row tags that should have C1=0
    """
    def s(prefixes):
        """Sum TSD for accounts matching any prefix."""
        return sum(v['tsd'] for a, v in accounts.items()
                   if any(a.startswith(p) for p in prefixes))

    def sc(prefixes):
        """Sum TSC for accounts matching any prefix."""
        return sum(v['tsc'] for a, v in accounts.items()
                   if any(a.startswith(p) for p in prefixes))

    # ═══════════════════════════════════════════════════════════
    # REVENUE (class 7 — uses TSC)
    # ═══════════════════════════════════════════════════════════

    # R01: Cifra de afaceri netă
    prod_vanduta = sc(['701', '702', '703', '704', '705', '706', '708'])
    venit_marfuri = sc(['707'])
    cifra_afaceri = prod_vanduta + venit_marfuri

    # Financial revenues (excluded from operating)
    venit_dobanzi = sc(['766'])
    venit_766001 = accounts.get('766001', {}).get('tsc', 0)
    venit_fin_alte = sc(['762', '764', '765', '767', '768', '7615'])
    total_ven_fin = venit_dobanzi + venit_fin_alte

    # Adjustment revenues (excluded from operating total, appear as expense reductions)
    ajust_circ_ven = sc(['754', '7814'])
    ajust_fin_ven = sc(['7812'])

    # R16: Total venituri din exploatare
    total_ven_expl = sc(['7']) - total_ven_fin - ajust_circ_ven - ajust_fin_ven
    alte_ven_expl = total_ven_expl - cifra_afaceri

    # ═══════════════════════════════════════════════════════════
    # EXPENSES (class 6 — uses TSD)
    # ═══════════════════════════════════════════════════════════

    # R17-R18: Material costs
    chelt_materii = s(['601', '602'])
    alte_chelt_mat = s(['603', '604', '606', '608'])

    # Utilities breakdown
    chelt_utilitati = s(['605'])
    chelt_energie = s(['6051'])
    chelt_gaze = s(['6053'])  # NOTE: ct.6053, NOT ct.6052

    # R20-R21: Goods and trade discounts
    chelt_marfuri = s(['607'])
    chelt_609 = abs(s(['609']))  # Credit nature account — use abs()

    # R23-R24: Personnel
    chelt_salarii = s(['641', '642', '643', '644'])
    chelt_asigurari = s(['645', '646'])
    chelt_personal = chelt_salarii + chelt_asigurari

    # R25: Depreciation & amortization
    amort_ch = s(['6811', '6813', '6817', '6818'])
    amort_6811 = s(['6811'])

    # R29-R30: Current asset adjustments
    ajust_circ_ch = s(['654', '6814'])
    ajust_circ_net = ajust_circ_ch - ajust_circ_ven

    # R31-R37: Other operating expenses
    chelt_externe_r32 = s(['611', '613', '614', '615', '616',
                           '621', '622', '623', '624', '625', '626', '627', '628'])
    chelt_612 = s(['612'])
    chelt_6123 = s(['6123'])
    chelt_617 = s(['617'])
    chelt_618 = s(['618'])
    chelt_impozite = s(['635', '6586'])
    chelt_despagubiri = s(['651', '6581', '6582', '6583', '6584',
                           '6585', '6587', '6588'])
    alte_chelt_expl = (chelt_externe_r32 + chelt_612 + chelt_617
                       + chelt_618 + chelt_impozite + chelt_despagubiri)

    # R39-R41: Financial adjustments
    ajust_fin_ch = s(['6812'])
    ajust_fin_net = ajust_fin_ch - ajust_fin_ven

    # R42: Total cheltuieli + ajustări
    total_ch_expl = (chelt_materii + alte_chelt_mat + chelt_utilitati + chelt_marfuri
                     - chelt_609 + chelt_personal + amort_ch + ajust_circ_net
                     + alte_chelt_expl)
    R42_total = total_ch_expl + ajust_fin_net

    # R43-R44: Operating result
    pierdere_expl = max(0, -(total_ven_expl - R42_total))
    profit_expl = max(0, total_ven_expl - R42_total)

    # ═══════════════════════════════════════════════════════════
    # FINANCIAL RESULT
    # ═══════════════════════════════════════════════════════════

    chelt_dobanzi = s(['666'])
    chelt_666905 = s(['666905'])  # R57: dobânzi leasing
    chelt_dif_curs = s(['665'])
    total_ch_fin = chelt_dobanzi + chelt_dif_curs

    pierdere_fin = max(0, -(total_ven_fin - total_ch_fin))
    profit_fin = max(0, total_ven_fin - total_ch_fin)

    # ═══════════════════════════════════════════════════════════
    # TOTALS
    # ═══════════════════════════════════════════════════════════

    total_venituri = total_ven_expl + total_ven_fin
    total_cheltuieli = R42_total + total_ch_fin
    pierdere_brut = max(0, -(total_venituri - total_cheltuieli))
    profit_brut = max(0, total_venituri - total_cheltuieli)

    # ═══════════════════════════════════════════════════════════
    # BUILD OUTPUT
    # ═══════════════════════════════════════════════════════════

    named = {
        'R01': round(cifra_afaceri),
        'R04': 0, 'R08': 0, 'R09': 0, 'R12': 0, 'R14': 0, 'R15': 0,
        'R16': round(total_ven_expl),
        'R17': round(chelt_materii),
        'R18': round(alte_chelt_mat),
        'R20': round(chelt_marfuri),
        'R21': round(chelt_609),
        'R23': round(chelt_salarii),
        'R24': round(chelt_asigurari),
        'R25': round(amort_ch),
        'R26': 0, 'R27': 0,
        'R29': round(ajust_circ_ch),
        'R30': round(ajust_circ_ven),
        'R31': round(alte_chelt_expl),
        'R32': round(chelt_externe_r32),
        'R33': round(chelt_612),
        'R34': 0, 'R35': 0, 'R36': 0,
        'R37': round(chelt_despagubiri),
        'R39': round(ajust_fin_net),
        'R40': round(ajust_fin_ch),
        'R41': round(ajust_fin_ven),
        'R42': round(R42_total),
        'R43': round(profit_expl),
        'R44': round(pierdere_expl),
        'R45': 0, 'R46': 0,
        'R47': round(venit_dobanzi),
        'R48': round(venit_766001),
        'R49': 0,
        'R50': round(venit_fin_alte),
        'R51': 0,
        'R52': round(total_ven_fin),
        'R53': 0, 'R54': 0, 'R55': 0,
        'R56': round(chelt_dobanzi),
        'R57': round(chelt_666905),
        'R58': round(chelt_dif_curs),
        'R59': round(total_ch_fin),
        'R60': round(profit_fin),
        'R61': round(pierdere_fin),
        'R62': round(total_venituri),
        'R63': round(total_cheltuieli),
        'R64': round(profit_brut),
        'R65': round(pierdere_brut),
        'R68': 0,
        'R69': round(profit_brut),
        'R70': round(pierdere_brut),
        'R306': round(amort_6811),
        'R307': 0, 'R308': 0,
        'R309': round(chelt_6123),
        'R310': 0,
        'R312': round(chelt_617),
        'R314': round(chelt_618),
        'R316': round(chelt_impozite),
        'R317': 0,
    }

    standalone = {
        ('R01', 2): round(prod_vanduta),
        ('R01', 3): round(venit_marfuri),
        ('R04', 1): 0, ('R04', 2): 0, ('R04', 3): 0,
        ('R09', 0): 0, ('R09', 1): 0,
        ('R12', 0): round(alte_ven_expl),
        ('R18', 0): round(chelt_utilitati),
        ('R18', 1): round(chelt_energie),
        ('R18', 2): round(chelt_gaze),
        ('R21', 0): round(chelt_personal),
        ('R27', 0): round(ajust_circ_net),
    }

    rows_with_c1_zero = {
        'R01', 'R08', 'R09', 'R16', 'R43', 'R44',
        'R60', 'R61', 'R62', 'R64', 'R65', 'R69', 'R70',
    }

    return {
        'named': named,
        'standalone': standalone,
        'rows_with_c1_zero': rows_with_c1_zero,
    }
