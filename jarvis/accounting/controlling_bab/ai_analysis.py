"""AI-powered financial analysis for BAB Controlling using Claude API."""
import logging
from decimal import Decimal

from .calculator import compute_marja_report
from .repository import BabRepository

logger = logging.getLogger('jarvis.controlling_bab.ai_analysis')

MONTH_NAMES = ['', 'Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec']

SYSTEM_PROMPT = """Ești un analist financiar senior de la una dintre firmele Big 4 (Deloitte/PwC/EY/KPMG).
Analizezi datele de marjă de vânzări (BAB - Betriebsabrechnungsbogen) pentru un dealer auto din România.

Regulile tale:
- Răspunzi ÎNTOTDEAUNA în limba română
- Folosești format markdown cu headere, tabele și bullet points
- Numerele se formatează cu separator de mii punct și separator zecimal virgulă (ex: 1.234.567,89)
- Valuta principală este EUR, cu LEI ca referință secundară
- Ești precis, concis și orientat pe acțiuni
- Semnalezi riscuri și oportunități concrete
- Nu inventezi date — folosești doar datele furnizate"""

AUTO_ANALYSIS_TEMPLATE = """Analizează următoarele date de marjă vânzări și generează un raport financiar complet.

{data_context}

Generează analiza pe următoarele secțiuni:

## 1. Rezumat Executiv
Un paragraf cu cele mai importante concluzii.

## 2. Analiza Profitabilității
- Evoluția marjei pe luni (trend crescător/descrescător)
- Marjele pe segmente (retail, flote, test drive, SH, extern)
- Cele mai profitabile și cele mai slabe segmente

## 3. Analiza Variațiilor (MoM)
- Cele mai mari creșteri și scăderi lună-over-lună
- Identifică anomalii sau schimbări brusce
- Tabel cu variațiile procentuale pe indicatori cheie

## 4. Structura Costurilor
- Ce conturi contribuie la marje negative
- Raportul dintre venituri și costuri pe segmente

## 5. Semnale de Risc ⚠️
- Trenduri negative care necesită atenție
- Marje negative persistente
- Segmente cu deteriorare continuă

## 6. Oportunități 📈
- Segmente în creștere
- Potențial de îmbunătățire identificat
- Recomandări concrete de acțiune"""

QUERY_TEMPLATE = """Bazat pe următoarele date de marjă vânzări, răspunde la întrebarea utilizatorului.

{data_context}

Întrebarea utilizatorului: {prompt}

Răspunde concis și precis, folosind datele furnizate. Formatează cu markdown."""


def _build_data_context(repo: BabRepository, company_id: int, companies: list, cross_company: bool = False) -> str:
    """Build formatted data context string for the AI prompt."""
    from database import get_db, get_cursor, release_db

    target_companies = []
    if cross_company:
        # Get all companies with BAB data
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT DISTINCT c.id, c.company FROM companies c
                JOIN bab_uploads u ON u.company_id = c.id
                ORDER BY c.company
            """)
            target_companies = [{'id': r[0], 'company': r[1]} for r in cursor.fetchall()]
        finally:
            release_db(conn)
    else:
        company_name = next((c['company'] for c in companies if c['id'] == company_id), str(company_id))
        target_companies = [{'id': company_id, 'company': company_name}]

    parts = []

    for comp in target_companies:
        cid = comp['id']
        cname = comp['company']
        parts.append(f"\n### Compania: {cname}\n")

        # Get uploads
        uploads = repo.get_periods(cid)
        if not uploads:
            parts.append("Nu există date importate.\n")
            continue

        # Get config
        config = repo.get_config(cid)

        # Build reports for each period
        period_reports = []
        for upload in sorted(uploads, key=lambda u: (u['period_year'], u['period_month'])):
            entries = repo.get_entries(upload['id'])
            eur_rate_row = repo.get_eur_rate(cid, upload['period_year'], upload['period_month'])
            eur_rate = Decimal(str(eur_rate_row['eur_rate'])) if eur_rate_row else Decimal('1')

            report = compute_marja_report(entries, eur_rate, config or None)
            period_reports.append({
                'month': upload['period_month'],
                'year': upload['period_year'],
                'label': f"{MONTH_NAMES[upload['period_month']]} {upload['period_year']}",
                'eur_rate': float(eur_rate),
                'report': report,
            })

        if not period_reports:
            parts.append("Nu există rapoarte.\n")
            continue

        # Build cross-tab text table
        months = [pr['label'] for pr in period_reports]
        header = f"| Indicator | {' | '.join(months)} |"
        separator = f"|{'---|' * (len(months) + 1)}"
        parts.append(f"Curs EUR: {', '.join(f'{pr['label']}: {pr['eur_rate']}' for pr in period_reports)}\n")
        parts.append(header)
        parts.append(separator)

        for section in period_reports[0]['report']['sections']:
            parts.append(f"| **{section['section']}** | {' | '.join([''] * len(months))} |")
            for row in section['rows']:
                vals = []
                for pr in period_reports:
                    # Find matching row in this period's report
                    found = False
                    for sec in pr['report']['sections']:
                        if sec['section'] == section['section']:
                            for r in sec['rows']:
                                if r['label'] == row['label']:
                                    vals.append(f"{float(r['eur']):,.2f} EUR / {float(r['lei']):,.2f} LEI")
                                    found = True
                                    break
                        if found:
                            break
                    if not found:
                        vals.append("—")
                parts.append(f"| {'  ' + row['label']} | {' | '.join(vals)} |")

        # Marja finala summary
        parts.append(f"\n**Marja Finală:**")
        for pr in period_reports:
            parts.append(f"- {pr['label']}: {float(pr['report']['marja_finala_eur']):,.2f} EUR / {float(pr['report']['marja_finala_lei']):,.2f} LEI")

    return '\n'.join(parts)


def analyze_bab(repo: BabRepository, company_id: int, companies: list,
                mode: str = 'auto', prompt: str = '', cross_company: bool = False) -> dict:
    """Run AI analysis on BAB data. Returns { analysis: str, tokens_used: int }."""
    from ai_agent.services.llm_client import ask

    data_context = _build_data_context(repo, company_id, companies, cross_company)

    if mode == 'auto':
        user_prompt = AUTO_ANALYSIS_TEMPLATE.format(data_context=data_context)
        max_tokens = 4096
    else:
        user_prompt = QUERY_TEMPLATE.format(data_context=data_context, prompt=prompt)
        max_tokens = 2048

    try:
        response = ask(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            model='claude-sonnet-4-5-20250514',
            max_tokens=max_tokens,
        )
        return {'analysis': response, 'tokens_used': 0}  # token count not exposed by ask()
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return {'analysis': f"Eroare la generarea analizei: {str(e)}", 'tokens_used': 0}
