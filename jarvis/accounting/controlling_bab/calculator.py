"""Marja (margin) calculation engine — pure function, no DB access."""
from decimal import Decimal, ROUND_HALF_UP


def compute_marja_report(entries, eur_rate):
    """Compute structured margin report from BAB entries.

    Args:
        entries: list[dict] with keys konto, saldo1, kostenstelle, konto_bez, kst_bez1
        eur_rate: Decimal — LEI/EUR exchange rate

    Returns:
        dict with sections, marja_finala_lei, marja_finala_eur, eur_rate
    """
    if not isinstance(eur_rate, Decimal):
        eur_rate = Decimal(str(eur_rate))

    if eur_rate == 0:
        raise ValueError("EUR rate cannot be zero")

    def _sum(konto_list, kst):
        """Sum saldo1 for entries matching konto codes and cost center."""
        total = Decimal('0')
        for e in entries:
            if e['kostenstelle'] == kst and e['konto'] in konto_list:
                total += Decimal(str(e['saldo1']))
        return total

    def _to_eur(lei):
        return (lei / eur_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def _line(label, lei, accounts, kst):
        return {
            'label': label,
            'lei': lei,
            'eur': _to_eur(lei),
            'accounts': accounts,
            'kst': kst,
        }

    # ── KST 211 — PKW INTERN ──

    retail_venit_sales  = _sum([707111, 707116], 211)
    retail_marja_bruta  = _sum([707111, 707116, 607111], 211)
    retail_bonus_import = _sum([609010], 211)
    retail_venit_td     = _sum([707112], 211)
    retail_marja_td     = _sum([707112, 607112], 211)

    flote_venit_sales   = _sum([707110, 707115], 211)
    flote_marja_bruta   = _sum([707110, 707115, 607110], 211)
    flote_bonus_import  = _sum([609011], 211)

    bonus_pfg           = _sum([708001], 211)
    discount_accesorii  = _sum([704315, 902700], 211)

    # MARJA FINALA PKW — 7 components
    marja_finala = (
        retail_marja_bruta + retail_bonus_import + retail_marja_td
        + flote_marja_bruta + flote_bonus_import
        + bonus_pfg + discount_accesorii
    )

    # ── KST 215 — PKW EXTERN ──

    extern_venit_sales  = _sum([707127], 215)
    extern_marja_bruta  = _sum([707127, 607127], 215)
    extern_bonus_import = _sum([609012], 215)
    extern_marja_total  = extern_marja_bruta + extern_bonus_import

    # ── Build report structure ──

    sections = [
        {
            'section': 'VW PKW INTERN (retail) — KST 211',
            'rows': [
                _line('Venit Sales realizat', retail_venit_sales, [707111, 707116], 211),
                _line('Marjă Brută realizată', retail_marja_bruta, [707111, 707116, 607111], 211),
                _line('Bonus trimestrial (importator)', retail_bonus_import, [609010], 211),
                _line('Venit Test Drive', retail_venit_td, [707112], 211),
                _line('Marjă Test Drive', retail_marja_td, [707112, 607112], 211),
            ],
        },
        {
            'section': 'VW PKW INTERN (flote) — KST 211',
            'rows': [
                _line('Venit Sales realizat', flote_venit_sales, [707110, 707115], 211),
                _line('Marjă Brută realizată', flote_marja_bruta, [707110, 707115, 607110], 211),
                _line('Bonus trimestrial (importator)', flote_bonus_import, [609011], 211),
            ],
        },
        {
            'section': 'Bonus & Discount — KST 211',
            'rows': [
                _line('Bonus PFG', bonus_pfg, [708001], 211),
                _line('Discount accesorii', discount_accesorii, [704315, 902700], 211),
            ],
        },
        {
            'section': 'MARJA FINALĂ PKW',
            'rows': [
                _line('MARJA FINALĂ', marja_finala, [], 211),
            ],
        },
        {
            'section': 'VW PKW EXTERN — KST 215',
            'rows': [
                _line('Venit Sales realizat', extern_venit_sales, [707127], 215),
                _line('Marjă Brută realizată', extern_marja_bruta, [707127, 607127], 215),
                _line('Bonus trimestrial (importator)', extern_bonus_import, [609012], 215),
                _line('Marjă Totală Extern', extern_marja_total, [], 215),
            ],
        },
    ]

    return {
        'sections': sections,
        'marja_finala_lei': marja_finala,
        'marja_finala_eur': _to_eur(marja_finala),
        'eur_rate': eur_rate,
    }
