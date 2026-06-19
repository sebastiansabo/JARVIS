"""Marja (margin) calculation engine — config-driven, no DB access."""
from decimal import Decimal, ROUND_HALF_UP
from collections import OrderedDict


def compute_marja_report(entries, eur_rate, config=None):
    """Compute structured margin report from BAB entries.

    Args:
        entries: list[dict] with keys konto, saldo1, kostenstelle, konto_bez, kst_bez1
        eur_rate: Decimal — LEI/EUR exchange rate
        config: list[dict] from bab_report_config table (optional, uses hardcoded default if None)

    Returns:
        dict with sections, marja_finala_lei, marja_finala_eur, eur_rate
    """
    if not isinstance(eur_rate, Decimal):
        eur_rate = Decimal(str(eur_rate))

    if eur_rate == 0:
        raise ValueError("EUR rate cannot be zero")

    def _sum(konto_list, kst):
        total = Decimal('0')
        for e in entries:
            if e['kostenstelle'] == kst and e['konto'] in konto_list:
                total += Decimal(str(e['saldo1']))
        return total

    def _to_eur(lei):
        return (lei / eur_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    if config is None:
        config = _default_config()

    # Compute each row value
    computed = OrderedDict()  # key = (group_name, item_label) → Decimal value
    for row in sorted(config, key=lambda r: r.get('sort_order', 0)):
        kst = row['kst']
        label = row['item_label']
        group = row['group_name']
        row_key = f"{group}|{label}"

        if row.get('row_type') == 'subtotal' and row.get('subtotal_of'):
            # Subtotal: sum of referenced rows
            # Supports both "Label" (legacy) and "Group → Label" (qualified) format
            ref_labels = [s.strip() for s in row['subtotal_of'].split(',') if s.strip()]
            total = Decimal('0')
            for ref in ref_labels:
                if '→' in ref:
                    # Qualified: "Group → Label" → match "Group|Label"
                    parts = ref.split('→', 1)
                    ref_key = f"{parts[0].strip()}|{parts[1].strip()}"
                    if ref_key in computed:
                        total += computed[ref_key]
                else:
                    # Legacy: just label → match any row ending with |Label
                    for ck, cv in computed.items():
                        if ck.endswith(f'|{ref}'):
                            total += cv
                            break
            computed[row_key] = total
        else:
            # Sum: aggregate from entries
            konto_str = row.get('konto_list', '')
            konto_list = [int(k.strip()) for k in konto_str.split(',') if k.strip()]
            computed[row_key] = _sum(konto_list, kst) if konto_list else Decimal('0')

    # Build sections (group by group_name, preserving order)
    sections = OrderedDict()
    for row in sorted(config, key=lambda r: r.get('sort_order', 0)):
        group = row['group_name']
        kst = row['kst']
        label = row['item_label']
        row_key = f"{group}|{label}"
        section_key = f"{group} — KST {kst}" if 'MARJA FINALĂ' not in group else group

        if section_key not in sections:
            sections[section_key] = {'section': section_key, 'rows': []}

        konto_str = row.get('konto_list', '')
        konto_list = [int(k.strip()) for k in konto_str.split(',') if k.strip()]
        lei = computed.get(row_key, Decimal('0'))

        sections[section_key]['rows'].append({
            'label': label,
            'lei': lei,
            'eur': _to_eur(lei),
            'accounts': konto_list,
            'kst': kst,
            'row_type': row.get('row_type', 'sum'),
        })

    # Main total = sum of all starred (is_main_total) subtotal rows
    marja_finala = Decimal('0')
    has_starred = False
    for row in sorted(config, key=lambda r: r.get('sort_order', 0)):
        if row.get('is_main_total') and row.get('row_type') == 'subtotal':
            row_key = f"{row['group_name']}|{row['item_label']}"
            marja_finala += computed.get(row_key, Decimal('0'))
            has_starred = True
    # Fallback if no starred rows: look for any subtotal row
    if not has_starred:
        for row in sorted(config, key=lambda r: r.get('sort_order', 0)):
            if row.get('row_type') == 'subtotal':
                row_key = f"{row['group_name']}|{row['item_label']}"
                marja_finala += computed.get(row_key, Decimal('0'))

    return {
        'sections': list(sections.values()),
        'marja_finala_lei': marja_finala,
        'marja_finala_eur': _to_eur(marja_finala),
        'eur_rate': eur_rate,
    }


def _default_config():
    """Hardcoded fallback config if no DB config exists."""
    return [
        {'sort_order': 10,  'kst': 211, 'group_name': 'VW PKW INTERN (retail)',  'item_label': 'Venit Sales realizat',           'konto_list': '707111,707116',        'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 20,  'kst': 211, 'group_name': 'VW PKW INTERN (retail)',  'item_label': 'Marjă Brută realizată',          'konto_list': '707111,707116,607111', 'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 30,  'kst': 211, 'group_name': 'VW PKW INTERN (retail)',  'item_label': 'Bonus trimestrial (importator)', 'konto_list': '609010',               'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 40,  'kst': 211, 'group_name': 'VW PKW INTERN (retail)',  'item_label': 'Venit Test Drive',               'konto_list': '707112',               'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 50,  'kst': 211, 'group_name': 'VW PKW INTERN (retail)',  'item_label': 'Marjă Test Drive',               'konto_list': '707112,607112',        'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 60,  'kst': 211, 'group_name': 'VW PKW INTERN (flote)',   'item_label': 'Venit Sales realizat',           'konto_list': '707110,707115',        'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 70,  'kst': 211, 'group_name': 'VW PKW INTERN (flote)',   'item_label': 'Marjă Brută realizată',          'konto_list': '707110,707115,607110', 'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 80,  'kst': 211, 'group_name': 'VW PKW INTERN (flote)',   'item_label': 'Bonus trimestrial (importator)', 'konto_list': '609011',               'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 90,  'kst': 211, 'group_name': 'Bonus & Discount',        'item_label': 'Bonus PFG',                     'konto_list': '708001',               'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 100, 'kst': 211, 'group_name': 'Bonus & Discount',        'item_label': 'Discount accesorii',             'konto_list': '704315,902700',        'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 110, 'kst': 211, 'group_name': 'MARJA FINALĂ PKW',        'item_label': 'MARJA FINALĂ',                   'konto_list': '',                     'row_type': 'subtotal', 'subtotal_of': 'Marjă Brută realizată,Bonus trimestrial (importator),Marjă Test Drive,Marjă Brută realizată,Bonus trimestrial (importator),Bonus PFG,Discount accesorii'},
        {'sort_order': 120, 'kst': 215, 'group_name': 'VW PKW EXTERN',           'item_label': 'Venit Sales realizat',           'konto_list': '707127',               'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 130, 'kst': 215, 'group_name': 'VW PKW EXTERN',           'item_label': 'Marjă Brută realizată',          'konto_list': '707127,607127',        'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 140, 'kst': 215, 'group_name': 'VW PKW EXTERN',           'item_label': 'Bonus trimestrial (importator)', 'konto_list': '609012',               'row_type': 'sum', 'subtotal_of': None},
        {'sort_order': 150, 'kst': 215, 'group_name': 'VW PKW EXTERN',           'item_label': 'Marjă Totală Extern',            'konto_list': '',                     'row_type': 'subtotal', 'subtotal_of': 'Marjă Brută realizată,Bonus trimestrial (importator)'},
    ]
