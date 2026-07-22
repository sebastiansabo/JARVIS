"""Monthly *Foaie de Parcurs* generator (per car).

Aggregates one vehicle's driving sessions for a given month into a single
document. PDF output is AI-drafted (prose only) into a locked HTML skeleton,
rendered with Playwright. Excel output is a deterministic tabular log.

See docs/superpowers/specs/2026-07-22-monthly-foaie-parcurs-design.md
"""
import io
import re
import json
import html
import logging
from datetime import datetime

from ..repositories.foi_parcurs_repository import FoiParcursRepository
from ..repositories.vehicle_repository import FPVehicleRepository
from .pdf_service import _build_prestator_intro, _PRESTATOR_FALLBACK

logger = logging.getLogger(__name__)

_MODEL = 'claude-sonnet-4-6'
_MONTHS_RO = [
    '', 'ianuarie', 'februarie', 'martie', 'aprilie', 'mai', 'iunie',
    'iulie', 'august', 'septembrie', 'octombrie', 'noiembrie', 'decembrie',
]

_fp_repo = FoiParcursRepository()
_veh_repo = FPVehicleRepository()


def _period(c: dict):
    """(year, month) for a session — explicit columns, falling back to created_at."""
    d = c.get('created_at')
    dt = d if isinstance(d, datetime) else None
    return (c.get('year') or (dt.year if dt else None),
            c.get('month') or (dt.month if dt else None))


def _as_dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('Z', '')) if v else None
    except ValueError:
        return None


def _fmt_date(v) -> str:
    dt = _as_dt(v)
    return dt.strftime('%d.%m.%Y') if dt else (str(v) if v else '')


def _fmt_time(v) -> str:
    dt = _as_dt(v)
    return dt.strftime('%H:%M') if dt else ''


def aggregate_month(vin: str, year: int, month: int) -> dict:
    """Collect the locked-facts view of one car's month of driving sessions."""
    rows, _ = _fp_repo.get_contracts(vin=vin, per_page=2000, lean=True)
    sessions = [c for c in rows if _period(c) == (year, month)]
    # chronological by drive date (departure, else created)
    sessions.sort(key=lambda c: str(c.get('departure_datetime') or c.get('created_at') or ''))

    veh = _veh_repo.get_by_vin(vin) or {}
    company_id = sessions[0].get('company_id') if sessions else veh.get('company_id')
    company_name = (sessions[0].get('company_name') if sessions else '') or ''

    prestator = _PRESTATOR_FALLBACK
    if company_id:
        try:
            from core.organization.repositories.company_repository import CompanyRepository
            company_row = CompanyRepository().get(company_id)
            if company_row and (company_row.get('company') or '').strip():
                company_name = company_row.get('company').strip()
                phone = ''
                try:
                    from ..dealer_config import get_dealer_config
                    phone = get_dealer_config(company_name, veh.get('brand') or '').get('phone', '')
                except Exception:
                    logger.warning('dealer_config lookup failed', exc_info=True)
                prestator = _build_prestator_intro(company_row, phone)
        except Exception:
            logger.warning('Prestator lookup failed for company_id=%s', company_id, exc_info=True)

    trips = []
    for i, c in enumerate(sessions):
        trips.append({
            'id': i,
            'date': _fmt_date(c.get('departure_datetime') or c.get('created_at')),
            'ora_plecare': _fmt_time(c.get('departure_datetime')),
            'ora_sosire': _fmt_time(c.get('return_datetime')),
            'km_start': c.get('km_start') or 0,
            'km_end': c.get('km_end') or 0,
            'distance_km': c.get('distance_km') or 0,
            'route_type': c.get('route_type') or '',
            'driver': (c.get('client_name') or c.get('advisor_name') or '').strip(),
            'itinerary': (c.get('itinerary') or '').strip(),
            'fuel_consumed': float(c.get('fuel_consumed_liters') or 0),
        })

    total_km = sum(t['distance_km'] for t in trips)
    km_start = min((t['km_start'] for t in trips), default=0)
    km_end = max((t['km_end'] for t in trips), default=0)
    clients = len({t['driver'] for t in trips if t['driver']})
    consum_efectiv = round(sum(t['fuel_consumed'] for t in trips), 2)

    return {
        'company': {'id': company_id, 'name': company_name, 'prestator': prestator},
        'vehicle': {
            'vin': vin,
            'make': veh.get('mark') or '',
            'model': veh.get('model') or '',
            'registration_number': veh.get('registration_number') or (sessions[0].get('registration_number') if sessions else '') or '',
        },
        'period': {'year': year, 'month': month, 'label': f'{_MONTHS_RO[month]} {year}' if 1 <= month <= 12 else f'{month}/{year}'},
        'trips': trips,
        'totals': {'km': total_km, 'km_start': km_start, 'km_end': km_end,
                   'sessions': len(trips), 'clients': clients, 'consum_efectiv': consum_efectiv},
    }


# ── AI: compose the route/purpose prose + monthly summary (prose only) ──

def _ai_prose(data: dict) -> dict:
    """Return {'trips': {id: text}, 'summary': text}. Falls back to stored
    itineraries (and empty summary) on any AI/parse failure — never raises."""
    trips_for_ai = [
        {'id': t['id'], 'data': t['date'],
         'km_parcursi': t['distance_km'], 'sofer': t['driver'], 'traseu_existent': t['itinerary']}
        for t in data['trips']
    ]
    fallback = {'trips': {t['id']: (t['itinerary'] or '') for t in data['trips']}, 'summary': ''}
    if not trips_for_ai:
        return fallback

    system = (
        'Ești asistent pentru completarea foilor de parcurs auto (document legal românesc). '
        'Nu inventa și nu modifica niciun număr, dată sau kilometraj. '
        'Compune DOAR un text scurt de traseu/scop pentru fiecare sesiune de rulare '
        '(localități/rută plauzibilă) și un rezumat lunar de 1-2 fraze. '
        'Răspunde STRICT în JSON, fără alt text.'
    )
    prompt = (
        'Vehicul: {make} {model} ({vin}), nr. {reg}. Perioada: {period}.\n'
        'Curse (folosește exact aceste id-uri):\n{trips}\n\n'
        'Returnează JSON de forma: '
        '{{"trips": {{"0": "traseu/scop", "1": "..."}}, "summary": "rezumat lunar"}}'
    ).format(
        make=data['vehicle']['make'], model=data['vehicle']['model'], vin=data['vehicle']['vin'],
        reg=data['vehicle']['registration_number'], period=data['period']['label'],
        trips=json.dumps(trips_for_ai, ensure_ascii=False),
    )

    try:
        from ai_agent.services.llm_client import ask
        raw = ask(prompt, system=system, model=_MODEL, max_tokens=2000)
        match = re.search(r'\{.*\}', raw or '', re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
        out_trips = {}
        for t in data['trips']:
            txt = (parsed.get('trips', {}) or {}).get(str(t['id'])) or (parsed.get('trips', {}) or {}).get(t['id'])
            out_trips[t['id']] = (txt or t['itinerary'] or '').strip()
        return {'trips': out_trips, 'summary': (parsed.get('summary') or '').strip()}
    except Exception:
        logger.warning('Route-sheet AI prose failed; using stored itineraries', exc_info=True)
        return fallback


def _rows_with_gaps(trips: list) -> list:
    """Order trips by odometer and interleave gap markers wherever the odometer
    jumps between logged sessions (km moved without a logged drive). Gap dict:
    {'gap': True, 'date', 'km_start', 'km_end', 'distance_km'}; trip:
    {'gap': False, 'trip': <trip>}. The gap's date is the session that revealed it."""
    ordered = sorted(trips, key=lambda t: (t['km_start'], t['km_end']))
    rows = []
    prev_end = None
    for t in ordered:
        if prev_end is not None and t['km_start'] > prev_end:
            rows.append({'gap': True, 'date': t['date'], 'km_start': prev_end,
                         'km_end': t['km_start'], 'distance_km': t['km_start'] - prev_end})
        rows.append({'gap': False, 'trip': t})
        prev_end = max(prev_end or 0, t['km_end'])
    return rows


# ── HTML skeleton (locked numbers) + Playwright render ──

def _skeleton_html(data: dict, prose: dict) -> str:
    e = html.escape
    v = data['vehicle']
    rows = []
    for r in _rows_with_gaps(data['trips']):
        if r['gap']:
            rows.append(
                '<tr class="gap">'
                f'<td>{e(r["date"])}</td>'
                '<td class="c">—</td>'
                '<td class="route">Gap kilometraj (nejustificat)</td>'
                '<td>—</td>'
                f'<td class="n">{r["km_start"]:,}</td>'
                f'<td class="n">{r["km_end"]:,}</td>'
                f'<td class="n">{r["distance_km"]:,}</td>'
                '</tr>'
            )
            continue
        t = r['trip']
        ora = ' – '.join(x for x in (t.get('ora_plecare'), t.get('ora_sosire')) if x) or '—'
        rows.append(
            '<tr>'
            f'<td>{e(t["date"])}</td>'
            f'<td class="c">{e(ora)}</td>'
            f'<td class="route">{e(prose["trips"].get(t["id"], "") or "—")}</td>'
            f'<td>{e(t["driver"] or "—")}</td>'
            f'<td class="n">{t["km_start"]:,}</td>'
            f'<td class="n">{t["km_end"]:,}</td>'
            f'<td class="n">{t["distance_km"]:,}</td>'
            '</tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="7" class="empty">Nicio sesiune în această lună.</td></tr>')
    tot = data['totals']
    summary_html = f'<p class="summary">{e(prose["summary"])}</p>' if prose.get('summary') else ''

    # Fuel block (Normă + Alimentări are user-entered; consum efectiv from sessions)
    fuel = data.get('fuel', {}) or {}
    alim = fuel.get('alimentari') or []
    alim_rows = ''.join(
        f'<tr><td>{e(str(a.get("date", "") or "—"))}</td>'
        f'<td>{e(str(a.get("bon", "") or "—"))}</td>'
        f'<td class="n">{float(a.get("liters", 0) or 0):g}</td></tr>'
        for a in alim
    ) or '<tr><td colspan="3" class="empty">Fără alimentări înregistrate.</td></tr>'
    alim_total = round(sum(float(a.get('liters', 0) or 0) for a in alim), 2)
    norma = fuel.get('norma')
    consum_normat = round((float(norma) * tot['km'] / 100), 2) if norma else None
    fuel_block = f"""
<div class="fuel">
  <table class="kv">
    <tr><td class="k">Normă consum</td><td>{norma if norma is not None else '—'} l/100 km</td></tr>
    <tr><td class="k">Consum normat</td><td>{consum_normat if consum_normat is not None else '—'} l</td></tr>
    <tr><td class="k">Consum efectiv</td><td>{tot.get('consum_efectiv', 0):g} l</td></tr>
  </table>
  <table class="trips alim">
    <thead><tr><th>Data alimentare</th><th>Bon fiscal</th><th>Litri</th></tr></thead>
    <tbody>{alim_rows}
      <tr class="totals"><td colspan="2">Total alimentat</td><td class="n">{alim_total:g}</td></tr>
    </tbody>
  </table>
</div>"""
    return f"""<!doctype html><html lang="ro"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color:#1a1a2e; font-size:11px; margin:0; }}
.doc {{ padding:0; }}
h1 {{ font-size:18px; text-align:center; margin:0 0 2px; }}
.sub {{ text-align:center; color:#555; margin:0 0 10px; font-size:11px; }}
.rule {{ border:0; border-top:1.5px solid #1a1a2e; margin:8px 0 12px; }}
.prestator {{ font-size:9px; text-align:justify; color:#333; line-height:1.4; margin-bottom:12px; }}
.meta {{ width:100%; margin-bottom:10px; border-collapse:collapse; }}
.meta td {{ padding:2px 6px; font-size:11px; }}
.meta td.k {{ color:#555; width:120px; }}
table.trips {{ width:100%; border-collapse:collapse; margin-top:6px; }}
table.trips th, table.trips td {{ border:0.5px solid #cfcfd8; padding:4px 6px; font-size:10px; }}
table.trips th {{ background:#1a1a2e; color:#fff; text-align:left; font-weight:600; }}
table.trips td.n {{ text-align:right; white-space:nowrap; }}
table.trips td.c {{ text-align:center; white-space:nowrap; }}
table.trips td.route {{ color:#222; }}
tr.totals td {{ font-weight:700; background:#f2f2f6; }}
tr.gap td {{ background:#fff7ed; font-style:italic; color:#9a6a00; }}
.empty {{ text-align:center; color:#888; }}
.summary {{ margin-top:12px; font-size:10.5px; line-height:1.5; }}
.fuel {{ display:flex; gap:16px; margin-top:12px; align-items:flex-start; }}
.fuel .kv {{ border-collapse:collapse; }}
.fuel .kv td {{ padding:3px 8px; font-size:10px; border:0.5px solid #cfcfd8; }}
.fuel .kv td.k {{ color:#555; background:#f7f7fa; }}
table.alim {{ flex:1; margin-top:0; }}
.sign {{ margin-top:34px; display:flex; justify-content:space-between; font-size:10px; }}
.sign .box {{ width:30%; border-top:0.5px solid #999; padding-top:4px; text-align:center; color:#555; }}
</style></head><body><div class="doc">
<h1>Foaie de Parcurs</h1>
<p class="sub">{e(v['make'])} {e(v['model'])} • {e(v['vin'])} • {e(data['period']['label'])}</p>
<hr class="rule">
<p class="prestator">{e(data['company']['prestator'])}</p>
<table class="meta">
  <tr><td class="k">Companie</td><td>{e(data['company']['name'] or '—')}</td>
      <td class="k">Nr. înmatriculare</td><td>{e(v['registration_number'] or '—')}</td></tr>
  <tr><td class="k">Vehicul</td><td>{e((v['make'] + ' ' + v['model']).strip() or '—')}</td>
      <td class="k">VIN</td><td>{e(v['vin'])}</td></tr>
</table>
<table class="trips">
  <thead><tr>
    <th>Data</th><th>Ora (plecare–sosire)</th><th>Traseu / Scop</th><th>Șofer</th>
    <th>KM start</th><th>KM end</th><th>KM parcurși</th>
  </tr></thead>
  <tbody>
    {''.join(rows)}
    <tr class="totals"><td colspan="4">Total — {tot['sessions']} sesiuni, {tot['clients']} șoferi</td>
      <td class="n">{tot['km_start']:,}</td><td class="n">{tot['km_end']:,}</td><td class="n">{tot['km']:,}</td></tr>
  </tbody>
</table>
{fuel_block}
{summary_html}
<div class="sign"><div class="box">Conducător auto</div><div class="box">Întocmit</div><div class="box">Aprobat</div></div>
</div></body></html>"""


def _html_to_pdf_bytes(html_str: str) -> bytes:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html_str, wait_until='load')
            return page.pdf(
                format='A4', print_background=True,
                margin={'top': '16mm', 'bottom': '16mm', 'left': '16mm', 'right': '16mm'},
            )
        finally:
            browser.close()


# ── Storage: durable per (vin, year, month) record in fp_route_sheets ──

from core.base_repository import BaseRepository  # noqa: E402
_store = BaseRepository()


def get_stored_pdf(vin: str, year: int, month: int) -> bytes | None:
    """The stored PDF bytes for a sheet, or None if not generated yet."""
    row = _store.query_one(
        'SELECT pdf_bytes FROM fp_route_sheets WHERE vin=%s AND year=%s AND month=%s',
        (vin, year, month),
    )
    if row and row.get('pdf_bytes') is not None:
        return bytes(row['pdf_bytes'])
    return None


def list_stored(company_id: int | None, year: int, month: int) -> list:
    """Metadata for every stored sheet in a period (badge + modal prefill)."""
    return _store.query_all(
        'SELECT vin, session_count, total_km, norma_combustibil, alimentari, '
        'generated_by_name, generated_at '
        'FROM fp_route_sheets WHERE (%s IS NULL OR company_id=%s) AND year=%s AND month=%s',
        (company_id, company_id, year, month),
    )


def _save_sheet(data: dict, pdf_bytes: bytes, prose: dict, user_id, user_name) -> None:
    from psycopg2 import Binary
    from psycopg2.extras import Json
    fuel = data.get('fuel', {}) or {}
    _store.execute(
        '''INSERT INTO fp_route_sheets
             (vin, company_id, year, month, pdf_bytes, ai_summary, ai_trips_json,
              norma_combustibil, alimentari, session_count, total_km,
              generated_by, generated_by_name, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
           ON CONFLICT (vin, year, month) DO UPDATE SET
             pdf_bytes=EXCLUDED.pdf_bytes, ai_summary=EXCLUDED.ai_summary,
             ai_trips_json=EXCLUDED.ai_trips_json, norma_combustibil=EXCLUDED.norma_combustibil,
             alimentari=EXCLUDED.alimentari, session_count=EXCLUDED.session_count,
             total_km=EXCLUDED.total_km, generated_by=EXCLUDED.generated_by,
             generated_by_name=EXCLUDED.generated_by_name, updated_at=NOW()''',
        (data['vehicle']['vin'], data['company'].get('id'),
         data['period']['year'], data['period']['month'], Binary(pdf_bytes),
         prose.get('summary', ''), Json(prose.get('trips', {})),
         fuel.get('norma'), Json(fuel.get('alimentari') or []),
         data['totals']['sessions'], data['totals']['km'], user_id, user_name),
    )


def generate_and_store(vin: str, year: int, month: int, user_id=None, user_name=None,
                       regenerate: bool = False, norma=None, alimentari=None) -> bytes:
    """Return the stored PDF (unless `regenerate`), else build it with AI +
    Playwright, persist it to fp_route_sheets, and return the bytes. `norma`
    (l/100km) and `alimentari` (list of {date, bon, liters}) are user-entered."""
    if not regenerate:
        cached = get_stored_pdf(vin, year, month)
        if cached is not None:
            return cached
    data = aggregate_month(vin, year, month)
    data['fuel'] = {'norma': norma, 'alimentari': alimentari or []}
    prose = _ai_prose(data)
    pdf_bytes = _html_to_pdf_bytes(_skeleton_html(data, prose))
    _save_sheet(data, pdf_bytes, prose, user_id, user_name)
    return pdf_bytes


def render_xlsx(vin: str, year: int, month: int) -> bytes:
    """Deterministic monthly route-sheet workbook (no AI)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    data = aggregate_month(vin, year, month)
    v = data['vehicle']
    wb = Workbook()
    ws = wb.active
    ws.title = 'Foaie de parcurs'

    bold = Font(bold=True)
    head = Font(bold=True, color='FFFFFF')
    fill = PatternFill('solid', fgColor='1A1A2E')

    ws['A1'] = 'Foaie de Parcurs'; ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f"{v['make']} {v['model']}".strip(); ws['A3'] = f"VIN: {v['vin']}"
    ws['A4'] = f"Nr. înmatriculare: {v['registration_number'] or '—'}"
    ws['A5'] = f"Companie: {data['company']['name'] or '—'}"
    ws['A6'] = f"Perioada: {data['period']['label']}"

    headers = ['Data', 'Ora (plecare–sosire)', 'Traseu / Scop', 'Șofer', 'KM start', 'KM end', 'KM parcurși']
    hrow = 8
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=hrow, column=col, value=h)
        cell.font = head; cell.fill = fill; cell.alignment = Alignment(horizontal='center')

    r = hrow + 1
    for row in _rows_with_gaps(data['trips']):
        if row['gap']:
            ws.cell(row=r, column=1, value=row['date'])
            ws.cell(row=r, column=3, value='Gap kilometraj (nejustificat)')
            ws.cell(row=r, column=5, value=row['km_start'])
            ws.cell(row=r, column=6, value=row['km_end'])
            ws.cell(row=r, column=7, value=row['distance_km'])
            r += 1
            continue
        t = row['trip']
        ora = ' – '.join(x for x in (t.get('ora_plecare'), t.get('ora_sosire')) if x)
        ws.cell(row=r, column=1, value=t['date'])
        ws.cell(row=r, column=2, value=ora)
        ws.cell(row=r, column=3, value=t['itinerary'] or '')
        ws.cell(row=r, column=4, value=t['driver'] or '')
        ws.cell(row=r, column=5, value=t['km_start'])
        ws.cell(row=r, column=6, value=t['km_end'])
        ws.cell(row=r, column=7, value=t['distance_km'])
        r += 1

    tot = data['totals']
    ws.cell(row=r, column=1, value='Total').font = bold
    ws.cell(row=r, column=4, value=f"{tot['sessions']} sesiuni").font = bold
    ws.cell(row=r, column=5, value=tot['km_start']).font = bold
    ws.cell(row=r, column=6, value=tot['km_end']).font = bold
    ws.cell(row=r, column=7, value=tot['km']).font = bold

    # Fuel block — Normă + Alimentări come from the stored sheet (user-entered)
    stored = _store.query_one(
        'SELECT norma_combustibil, alimentari FROM fp_route_sheets WHERE vin=%s AND year=%s AND month=%s',
        (vin, year, month),
    ) or {}
    norma = stored.get('norma_combustibil')
    alimentari = stored.get('alimentari') or []
    consum_normat = round(float(norma) * tot['km'] / 100, 2) if norma else None

    fr = r + 3
    ws.cell(row=fr, column=1, value='Combustibil').font = bold
    ws.cell(row=fr + 1, column=1, value='Normă consum (l/100km)'); ws.cell(row=fr + 1, column=2, value=float(norma) if norma else None)
    ws.cell(row=fr + 2, column=1, value='Consum normat (l)'); ws.cell(row=fr + 2, column=2, value=consum_normat)
    ws.cell(row=fr + 3, column=1, value='Consum efectiv (l)'); ws.cell(row=fr + 3, column=2, value=tot.get('consum_efectiv', 0))

    ar = fr + 5
    for col, h in enumerate(['Data alimentare', 'Bon fiscal', 'Litri'], start=1):
        cell = ws.cell(row=ar, column=col, value=h)
        cell.font = head; cell.fill = fill; cell.alignment = Alignment(horizontal='center')
    ar += 1
    alim_total = 0.0
    for a in alimentari:
        ws.cell(row=ar, column=1, value=str(a.get('date', '') or ''))
        ws.cell(row=ar, column=2, value=str(a.get('bon', '') or ''))
        ws.cell(row=ar, column=3, value=float(a.get('liters', 0) or 0))
        alim_total += float(a.get('liters', 0) or 0)
        ar += 1
    ws.cell(row=ar, column=1, value='Total alimentat').font = bold
    ws.cell(row=ar, column=3, value=round(alim_total, 2)).font = bold

    widths = [22, 18, 40, 22, 12, 12, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
