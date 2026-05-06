"""F10S (Bilant Prescurtat) computation engine.

Computes F10S (shortened balance sheet, cod 20) values from balanta SFD/SFC data.
Based on ANAF OMF 2036/2025 standard formulas.

Pure computation — no Flask or DB dependencies.
"""

import pandas as pd


# ── F10S Row definitions ──
# Row order matches XFA datasets positional structure.

F10S_ROW_ORDER = [
    'R01', 'R02', 'R03', 'R04',        # A. Active imobilizate
    'R05', 'R301', 'R302', 'R06',       # B. Active circulante
    'R07', 'R08', 'R09',
    'R10', 'R11', 'R12',                # C. Cheltuieli in avans
    'R13', 'R14', 'R15', 'R16',         # D-G. Datorii / Total active
    'R17', 'R18',                        # H-I. Provizioane / Venituri in avans
    'R19', 'R20', 'R21', 'R22',
    'R23', 'R24', 'R25',
    'R26', 'R27', 'R28',                # Fondul comercial negativ
    'R29', 'R30', 'R31', 'R32', 'R33',  # J. Capital
    'R34', 'R35', 'R36', 'R37',         # Prime, Rezerve, Profit reportat
    'R38', 'R39', 'R40', 'R41', 'R42',  # Acțiuni proprii, etc.
    'R43', 'R44', 'R45',                # Profit/Pierdere exercițiu
    'R46', 'R47', 'R48', 'R49',         # Capitaluri total
]


def compute_f10s(df_balanta):
    """Compute F10S values from balanta DataFrame.

    Args:
        df_balanta: DataFrame with columns [Cont, SFD, SFC]

    Returns:
        dict mapping row tag (R01..R49, R301, R302) to integer value.
        Only non-zero values are included.
    """
    df = df_balanta.copy()
    df['Cont'] = df['Cont'].astype(str).str.strip()
    df['SFD'] = pd.to_numeric(df['SFD'], errors='coerce').fillna(0)
    df['SFC'] = pd.to_numeric(df['SFC'], errors='coerce').fillna(0)

    def sfd(prefixes):
        """Sum SFD (debit balances) for accounts matching prefixes."""
        total = 0
        for p in prefixes:
            total += df[df['Cont'].str.startswith(p)]['SFD'].sum()
        return total

    def sfc(prefixes):
        """Sum SFC (credit balances) for accounts matching prefixes."""
        total = 0
        for p in prefixes:
            total += df[df['Cont'].str.startswith(p)]['SFC'].sum()
        return total

    def net(prefixes):
        """Sum SFD - SFC (net value) for +/- accounts."""
        total = 0
        for p in prefixes:
            mask = df['Cont'].str.startswith(p)
            total += (df[mask]['SFD'] - df[mask]['SFC']).sum()
        return total

    v = {}

    # ══════════════════════════════════════════════════════════════════
    # A. ACTIVE IMOBILIZATE
    # ══════════════════════════════════════════════════════════════════

    # R01: I. IMOBILIZĂRI NECORPORALE
    # ct.201+203+205+206+2071+4094+208 - 280-290-4904
    v['R01'] = (sfd(['201', '203', '205', '206', '2071', '4094', '208'])
                - sfc(['280', '290', '4904']))

    # R02: II. IMOBILIZĂRI CORPORALE
    # ct.211+212+213+214+215+216+217+223+224+227+231+235+4093 - 281-291-2931-2935-4903
    v['R02'] = (sfd(['211', '212', '213', '214', '215', '216', '217',
                     '223', '224', '227', '231', '235', '4093'])
                - sfc(['281', '291', '2931', '2935', '4903']))

    # R03: III. IMOBILIZĂRI FINANCIARE
    # ct.261+262+263+264+265+266+267+269 - 296
    v['R03'] = sfd(['261', '262', '263', '264', '265', '266', '267', '269']) - sfc(['296'])

    # R04: ACTIVE IMOBILIZATE - TOTAL (rd.01+02+03)
    v['R04'] = v['R01'] + v['R02'] + v['R03']

    # ══════════════════════════════════════════════════════════════════
    # B. ACTIVE CIRCULANTE
    # ══════════════════════════════════════════════════════════════════

    # R05: I. STOCURI
    # ct.301+302+303+/-308+331+332+341+345+346+347+348+351+354+356+357+358
    #    +361+/-368+371+/-378+381+/-388+4091 - 391-392-393-394-395-396-397-398
    v['R05'] = (sfd(['301', '302', '303', '331', '332', '341', '345', '346',
                     '347', '348', '351', '354', '356', '357', '358',
                     '361', '371', '381', '4091'])
                + net(['308', '368', '378', '388'])
                - sfc(['391', '392', '393', '394', '395', '396', '397', '398']))

    # R301 (06a): II. CREANȚE - sume de încasat într-o perioadă ≤ 1 an
    # Uses SFD of receivable accounts (only debit balances = what's owed to us)
    _creante_pfx = ['4092', '411', '413', '418', '425', '4282',
                    '431', '437', '4382', '441', '4423', '4424', '4428',
                    '444', '445', '446', '447', '4482',
                    '451', '452', '456', '4582', '461', '473', '5187']
    _creante_prov = ['491', '495', '496']
    v['R301'] = sfd(_creante_pfx) - sfc(_creante_prov)

    # R302 (06b): CREANȚE > 1 an (default 0 for most SMEs)
    v['R302'] = 0

    # R06: CREANȚE TOTAL (rd.06a + 06b)
    v['R06'] = v['R301'] + v['R302']

    # R07: III. INVESTIȚII FINANCIARE PE TERMEN SCURT
    # ct.501+502+503+505+506+507+508 - 591-595-596-598
    v['R07'] = (sfd(['501', '502', '503', '505', '506', '507', '508'])
                - sfc(['591', '595', '596', '598']))

    # R08: IV. CASA ȘI CONTURI LA BĂNCI
    # ct.5112+5121+5124+5125+531+532+541+542 (net: SFD-SFC for overdraft accounts)
    v['R08'] = net(['5112', '5121', '5124', '5125', '531', '532', '541', '542'])

    # R09: ACTIVE CIRCULANTE - TOTAL (rd.05+06+07+08)
    v['R09'] = v['R05'] + v['R06'] + v['R07'] + v['R08']

    # ══════════════════════════════════════════════════════════════════
    # C. CHELTUIELI ÎN AVANS (ct.471)
    # ══════════════════════════════════════════════════════════════════

    # R10: CHELTUIELI ÎN AVANS (rd.11+12)
    v['R10'] = sfd(['471'])

    # R11: Sume de reluat ≤ 1 an
    v['R11'] = v['R10']  # All prepaid goes to ≤1 an by default

    # R12: Sume de reluat > 1 an
    v['R12'] = 0

    # ══════════════════════════════════════════════════════════════════
    # D. DATORII pe o perioadă ≤ 1 an
    # ══════════════════════════════════════════════════════════════════

    # R13: DATORII ≤ 1 an
    # Uses SFC of payable accounts. Default: all except ct.161-169 (long-term)
    _datorii_scurt_pfx = ['401', '403', '404', '405', '408', '419',
                          '421', '423', '424', '426', '427', '4281',
                          '431', '436', '437', '4381',
                          '441', '4421', '4423', '4428', '444', '446', '447', '4481',
                          '451', '452', '455', '456', '4581',
                          '462', '473', '509', '5186', '519']
    v['R13'] = sfc(_datorii_scurt_pfx)

    # E. ACTIVE CIRCULANTE NETE / DATORII CURENTE NETE
    # R14 = rd.09 + 10 - 13
    v['R14'] = v['R09'] + v['R10'] - v['R13']

    # F. TOTAL ACTIVE MINUS DATORII CURENTE
    # R15 = rd.04 + 12 + 14
    v['R15'] = v['R04'] + v['R12'] + v['R14']

    # G. DATORII pe o perioadă > 1 an
    # R16: Long-term debt (ct.161-169 by default)
    _datorii_lung_pfx = ['161', '162', '163', '164', '165', '166',
                         '167', '168', '169']
    v['R16'] = sfc(_datorii_lung_pfx)

    # ══════════════════════════════════════════════════════════════════
    # H. PROVIZIOANE
    # ══════════════════════════════════════════════════════════════════

    # R17: PROVIZIOANE (ct.151)
    v['R17'] = sfc(['151'])

    # ══════════════════════════════════════════════════════════════════
    # I. VENITURI ÎN AVANS (rd.19 + 22 + 25 + 28)
    # ══════════════════════════════════════════════════════════════════

    # R20: 1. Subvenții pt investiții ≤ 1 an (ct.475)
    v['R20'] = sfc(['475'])
    # R21: > 1 an
    v['R21'] = 0
    # R19: Subtotal subvenții (rd.20+21)
    v['R19'] = v['R20'] + v['R21']

    # R23: 2. Venituri înregistrate în avans ≤ 1 an (ct.472)
    v['R23'] = sfc(['472'])
    # R24: > 1 an
    v['R24'] = 0
    # R22: Subtotal venituri (rd.23+24)
    v['R22'] = v['R23'] + v['R24']

    # R26: 3. Venituri aferente activelor primite prin transfer ≤ 1 an (ct.478)
    v['R26'] = sfc(['478'])
    # R27: > 1 an
    v['R27'] = 0
    # R25: Subtotal transfer (rd.26+27)
    v['R25'] = v['R26'] + v['R27']

    # R28: 4. Fondul comercial negativ (ct.2075)
    v['R28'] = sfc(['2075'])

    # R18: VENITURI ÎN AVANS - TOTAL (rd.19+22+25+28)
    v['R18'] = v['R19'] + v['R22'] + v['R25'] + v['R28']

    # ══════════════════════════════════════════════════════════════════
    # J. CAPITAL ȘI REZERVE
    # ══════════════════════════════════════════════════════════════════

    # R30: 1. Capital subscris vărsat (ct.1012)
    v['R30'] = sfc(['1012'])
    # R31: 2. Capital subscris nevărsat (ct.1011)
    v['R31'] = sfc(['1011'])
    # R32: 3. Patrimoniul regiei (ct.1015)
    v['R32'] = sfc(['1015'])
    # R33: 4. Patrimoniul INCD (ct.1018)
    v['R33'] = sfc(['1018'])
    # R29: I. Capital subscris (rd.30+31+32+33)
    v['R29'] = v['R30'] + v['R31'] + v['R32'] + v['R33']

    # R34: II. Prime de capital (ct.104)
    v['R34'] = sfc(['104'])

    # R35: III. Rezerve din reevaluare (ct.105)
    v['R35'] = sfc(['105'])

    # R36: IV. Rezerve (ct.106+107)
    v['R36'] = sfc(['106', '107'])

    # R37: V. Profitul sau pierderea reportat(ă) — other reserves (ct.1175+1176)
    v['R37'] = sfc(['1175', '1176'])

    # R38: Acțiuni proprii (ct.109) — se scade
    v['R38'] = sfd(['109'])

    # R39: Câștiguri legate de instrumente de capitaluri proprii (ct.141)
    v['R39'] = sfc(['141'])

    # R40: Pierderi legate de instrumente de capitaluri proprii (ct.149)
    v['R40'] = sfd(['149'])

    # R41: VI. Profitul sau pierderea reportat(ă) — Sold C (ct.117 SFC)
    v['R41'] = sfc(['117'])

    # R42: VI. Profitul sau pierderea reportat(ă) — Sold D (ct.117 SFD)
    v['R42'] = sfd(['117'])

    # VII. PROFITUL SAU PIERDEREA EXERCIŢIULUI FINANCIAR
    # R43: Sold C — profit (ct.121 SFC)
    v['R43'] = sfc(['121'])

    # R44: Sold D — pierdere (ct.121 SFD)
    v['R44'] = sfd(['121'])

    # R45: Repartizarea profitului (ct.129)
    v['R45'] = sfd(['129'])

    # R46: CAPITALURI PROPRII
    # = R29 + R34 + R35 + R36 + R37 - R38 + R39 - R40 + R41 - R42 + R43 - R44 - R45
    v['R46'] = (v['R29'] + v['R34'] + v['R35'] + v['R36'] + v['R37']
                - v['R38'] + v['R39'] - v['R40']
                + v['R41'] - v['R42']
                + v['R43'] - v['R44'] - v['R45'])

    # R47: Patrimoniul public (ct.1016)
    v['R47'] = sfc(['1016'])

    # R48: Capitaluri — alte elemente
    v['R48'] = 0

    # R49: CAPITALURI - TOTAL (rd.46+47+48)
    v['R49'] = v['R46'] + v['R47'] + v['R48']

    # Round all values to integers and filter non-zero
    result = {}
    for k, val in v.items():
        rounded = round(val)
        if rounded != 0:
            result[k] = rounded

    return result
