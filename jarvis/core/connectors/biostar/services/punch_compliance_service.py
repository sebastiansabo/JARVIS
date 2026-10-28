"""Weekly punch-compliance digest — per-manager report of schedule divergences.

For a manager's organigram team ("My Team"), compares each member's RAW BioStar
badge punches (first = earliest, last = latest; manual adjustments are deliberately
ignored) against the Sincron working schedule. The reporting rule is HOURS-BASED:

  * worked (last-first-lunch) >= required norma      -> compliant, NOT shown, even if
    the arrival is shifted ("everyone with their hours do not show").
  * worked < required - tolerance                    -> § ① deficit  (minute lipsă = deficit)
  * 0 badges on a scheduled day                      -> § ① absent   (minute lipsă = norma)
  * 1 badge (no pair)                                -> § ① incomplete (needs review)
  * hours met BUT first punch off schedule_start by  -> § ② "program Sincron nepotrivit"
    more than tolerance                                 (OK overall; the Sincron program
                                                         likely needs correcting)

Suppressions:
  * weekends, public holidays, full-day Sincron leave codes, approved permits
    (Connecteam / bilet-de-invoire) are never reported.
  * employees with ZERO badges across the whole week are hidden (treated as on
    leave / away) — only partial-week gaps surface.
  * the eligible roster reuses the missing-punch detector's gates (active contract,
    notify_missing_punch, working_hours > 0, schedule set, not blacklisted, ghost).

Note: in production `sincron_activity_codes.is_leave` is unpopulated, so the
hardcoded _LEAVE_FALLBACK set is authoritative for leave detection.

Renders an inline-styled HTML e-mail (§ ① detailed, § ② compact) plus a synthetic
`.xlsx` (name · program · hours missing). Nothing is sent here.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from core.base_repository import BaseRepository
from core.organization.ghost import ghost_exclude_clause
from core.organization.hr_utils import get_managed_employee_ids
from core.utils.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_TOLERANCE_MINUTES = 10
WORKED_CODES = ('OZ', 'OS')
_LEAVE_FALLBACK = frozenset({'CO', 'CM', 'CMS', 'CES', 'CFS', 'CFP', 'CIC',
                             'INV', 'ZLC', 'ZLS', 'DLG'})
RO_DAYS = ('Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică')
KIND_LABEL = {'absent': 'Absent', 'incomplete': 'Pontaj incomplet', 'deficit': 'Sub normă'}
KIND_COLOR = {'absent': '#b91c1c', 'incomplete': '#b45309', 'deficit': '#be123c'}


class PunchComplianceService:
    """Builds a manager's weekly punch-compliance report from raw punch data."""

    def __init__(self):
        self.db = BaseRepository()

    # ------------------------------------------------------------------ roster
    def eligible_team_ids(self, manager_user_id, override_user_ids=None):
        """Resolve a manager's organigram team, keep only badge-tracked, active,
        notifiable, non-ghost employees. ``override_user_ids`` bypasses organigram
        resolution (ad-hoc runs)."""
        team = override_user_ids if override_user_ids is not None \
            else get_managed_employee_ids(manager_user_id)
        if not team:
            return []
        gfrag, gargs = ghost_exclude_clause('u.id', viewer_id=None)
        rows = self.db.query_all(f'''
            SELECT DISTINCT be.mapped_jarvis_user_id AS uid
            FROM biostar_employees be
            JOIN users u ON u.id = be.mapped_jarvis_user_id
            WHERE be.mapped_jarvis_user_id = ANY(%s)
              AND be.status = 'active'
              AND be.working_hours > 0
              AND be.schedule_start IS NOT NULL
              AND COALESCE(be.is_blacklisted, FALSE) = FALSE
              AND COALESCE(u.contract_status, 'active') = 'active'
              AND COALESCE(u.notify_missing_punch, TRUE) = TRUE
              {gfrag}
        ''', (list(team),) + tuple(gargs))
        return [r['uid'] for r in rows]

    # ------------------------------------------------------------------ batches
    def _primary_contract(self, user_ids):
        rows = self.db.query_all('''
            SELECT se.mapped_jarvis_user_id AS user_id,
                   to_char(se.schedule_start, 'HH24:MI') AS static_start,
                   to_char(se.schedule_end, 'HH24:MI')   AS static_end,
                   se.lunch_break_minutes AS lunch,
                   se.norma_lucru AS norma
            FROM sincron_employees se
            WHERE se.mapped_jarvis_user_id = ANY(%s)
              AND se.is_active = TRUE
              AND se.exclude_from_pontaje = FALSE
            ORDER BY se.mapped_jarvis_user_id, se.norma_lucru DESC NULLS LAST
        ''', (user_ids,))
        out = {}
        for r in rows:
            out.setdefault(r['user_id'], r)  # first = highest norma = primary
        return out

    def _timesheets(self, user_ids, start, end):
        rows = self.db.query_all('''
            SELECT se.mapped_jarvis_user_id AS user_id, st.day AS day,
                   st.short_code,
                   to_char(st.program_in, 'HH24:MI')  AS program_in,
                   to_char(st.program_out, 'HH24:MI') AS program_out,
                   st.program_break
            FROM sincron_timesheets st
            JOIN sincron_employees se ON se.sincron_employee_id = st.sincron_employee_id
                                     AND se.company_name = st.company_name
            WHERE se.mapped_jarvis_user_id = ANY(%s)
              AND st.day BETWEEN %s AND %s
        ''', (user_ids, start, end))
        out = {}
        for r in rows:
            out.setdefault((r['user_id'], _to_date(r['day'])), []).append(r)
        return out

    def _punches(self, user_ids, start, end):
        """Raw per-day first/last/count — adjustments table is never consulted."""
        rows = self.db.query_all('''
            SELECT be.mapped_jarvis_user_id AS user_id,
                   pl.event_datetime::date AS day,
                   MIN(pl.event_datetime) AS first_p,
                   MAX(pl.event_datetime) AS last_p,
                   COUNT(DISTINCT date_trunc('minute', pl.event_datetime)) AS n
            FROM biostar_employees be
            JOIN biostar_punch_logs pl ON pl.biostar_user_id = be.biostar_user_id
            WHERE be.mapped_jarvis_user_id = ANY(%s)
              AND pl.event_datetime::date BETWEEN %s AND %s
            GROUP BY be.mapped_jarvis_user_id, pl.event_datetime::date
        ''', (user_ids, start, end))
        return {
            (r['user_id'], _to_date(r['day'])): {
                'first_p': _to_dt(r['first_p']), 'last_p': _to_dt(r['last_p']), 'n': r['n'],
            } for r in rows
        }

    def _holidays(self, start, end):
        rows = self.db.query_all(
            'SELECT date FROM public_holidays WHERE date BETWEEN %s AND %s', (start, end))
        return {_to_date(r['date']) for r in rows}

    def _leave_codes(self):
        rows = self.db.query_all(
            'SELECT short_code FROM sincron_activity_codes WHERE is_leave = TRUE')
        return _LEAVE_FALLBACK | {r['short_code'] for r in rows}

    def _permits(self, user_ids, start, end):
        rows = self.db.query_all('''
            SELECT mapped_jarvis_user_id AS user_id, leave_date::date AS day
            FROM connecteam_form_submissions
            WHERE mapped_jarvis_user_id = ANY(%s)
              AND leave_date::date BETWEEN %s AND %s
              AND COALESCE(status, 'submitted') NOT IN ('rejected', 'cancelled')
            UNION
            SELECT fs.respondent_user_id, (fs.answers->>'f_bi_leave_date')::date
            FROM form_submissions fs
            JOIN forms f ON f.id = fs.form_id
            WHERE f.slug = 'bilet-de-invoire'
              AND fs.respondent_user_id = ANY(%s)
              AND fs.status NOT IN ('cancelled', 'rejected')
              AND (fs.answers->>'f_bi_leave_date') ~ '^\\d{4}-\\d{2}-\\d{2}$'
              AND (fs.answers->>'f_bi_leave_date')::date BETWEEN %s AND %s
        ''', (user_ids, start, end, user_ids, start, end))
        return {(r['user_id'], _to_date(r['day'])) for r in rows}

    def _names(self, user_ids):
        rows = self.db.query_all(
            'SELECT id, name FROM users WHERE id = ANY(%s)', (user_ids,))
        return {r['id']: r['name'] for r in rows}

    # ------------------------------------------------------------------ compute
    def compute(self, manager_name, user_ids, start, end,
                tolerance=DEFAULT_TOLERANCE_MINUTES):
        """Return the report payload for an explicit, already-eligible user set."""
        user_ids = list(user_ids)
        deficits, mismatches = [], []
        if user_ids:
            contracts = self._primary_contract(user_ids)
            timesheets = self._timesheets(user_ids, start, end)
            punches = self._punches(user_ids, start, end)
            holidays = self._holidays(start, end)
            permits = self._permits(user_ids, start, end)
            leave_codes = self._leave_codes()
            names = self._names(user_ids)
            for uid in sorted(user_ids, key=lambda u: names.get(u, '')):
                if not any(uid == k[0] for k in punches):
                    continue  # zero badges all week -> on leave / away, hide
                drows, mrows = [], []
                day = start
                while day <= end:
                    if day.weekday() < 5 and day not in holidays:
                        r = self._analyse_day(uid, day, contracts.get(uid), timesheets,
                                              punches, permits, leave_codes, tolerance)
                        if r and r['kind'] in ('absent', 'incomplete', 'deficit'):
                            drows.append(r)
                        elif r and r['kind'] == 'mismatch':
                            mrows.append(r)
                    day += timedelta(days=1)
                nm = names.get(uid, f'User {uid}')
                if drows:
                    deficits.append({'name': nm, 'user_id': uid, 'rows': drows})
                if mrows:
                    mismatches.append({'name': nm, 'user_id': uid, 'rows': mrows})
        return {
            'manager_name': manager_name,
            'start': start, 'end': end, 'tolerance': tolerance,
            'team_size': len(user_ids),
            'deficits': deficits, 'mismatches': mismatches,
            'total_days': sum(len(f['rows']) for f in deficits),
        }

    def compute_for_manager(self, manager_user_id, start, end,
                            tolerance=DEFAULT_TOLERANCE_MINUTES,
                            override_user_ids=None, manager_name=None):
        if manager_name is None:
            row = self.db.query_one('SELECT name FROM users WHERE id = %s',
                                    (manager_user_id,))
            manager_name = row['name'] if row else f'Manager {manager_user_id}'
        team = self.eligible_team_ids(manager_user_id, override_user_ids)
        return self.compute(manager_name, team, start, end, tolerance)

    def _analyse_day(self, uid, day, contract, timesheets, punches, permits,
                     leave_codes, tolerance):
        day_rows = timesheets.get((uid, day), [])
        worked = next((r for r in day_rows if r['short_code'] in WORKED_CODES), None)
        leave = next((r for r in day_rows if r['short_code'] in leave_codes), None)
        code = (worked or leave or (day_rows[0] if day_rows else {})).get('short_code') \
            if (worked or leave or day_rows) else None

        static_start = contract['static_start'] if contract else None
        scheduled = (code in WORKED_CODES) or (code is None and static_start is not None)
        excused = leave is not None or (uid, day) in permits
        if not scheduled or excused:
            return None

        s_start = (worked['program_in'] if worked else None) or static_start
        s_end = (worked['program_out'] if worked else None) \
            or (contract['static_end'] if contract else None)
        if not s_start or not s_end:
            return None  # scheduled but no usable program — can't measure

        exp_in = datetime.combine(day, datetime.strptime(s_start, '%H:%M').time())
        exp_out = datetime.combine(day, datetime.strptime(s_end, '%H:%M').time())
        lunch = int((worked['program_break'] if worked and worked.get('program_break') is not None
                     else (contract['lunch'] if contract else 60)) or 0)
        if contract and contract.get('norma'):
            required = int(round(float(contract['norma']) * 60))
        else:
            required = max(0, _mins(exp_out, exp_in) - lunch)

        p = punches.get((uid, day))
        n = (p['n'] if p else 0) or 0
        base = {'date': day, 'sched': f'{s_start}–{s_end}', 'first': '—', 'last': '—',
                'worked': None, 'required': required}
        if n == 0:
            return {**base, 'kind': 'absent', 'missing': required,
                    'reasons': ['Absent (fără pontaj)']}
        if n == 1:
            return {**base, 'kind': 'incomplete', 'first': _naive(p['first_p']).strftime('%H:%M'),
                    'missing': None, 'reasons': ['Pontaj incomplet (o singură marcare)']}
        fin, lout = _naive(p['first_p']), _naive(p['last_p'])
        worked_min = max(0, _mins(lout, fin) - lunch)
        base.update(first=fin.strftime('%H:%M'), last=lout.strftime('%H:%M'), worked=worked_min)
        deficit = required - worked_min
        if deficit > tolerance:
            late = _mins(fin, exp_in)
            ctx = f' (întârziere {late} min)' if late > tolerance else ''
            return {**base, 'kind': 'deficit', 'missing': deficit,
                    'reasons': [f'Sub normă: {_hm(worked_min)} din {_hm(required)}{ctx}']}
        if abs(_mins(fin, exp_in)) > tolerance:
            return {**base, 'kind': 'mismatch', 'missing': 0, 'reasons': []}
        return None  # worked their hours, on schedule → compliant

    # -------------------------------------------------------------------- HTML
    def build_html(self, data):
        import html as _html
        d = data
        period = f"{d['start'].strftime('%d.%m.%Y')} – {d['end'].strftime('%d.%m.%Y')}"
        tot_def = d['total_days']
        P = [f'''<div style="font-family:Segoe UI,Arial,sans-serif;max-width:820px;margin:0 auto;color:#1a2332">
      <div style="background:#0f2744;color:#fff;padding:20px 24px;border-radius:10px 10px 0 0">
        <div style="font-size:12px;letter-spacing:1px;opacity:.75;text-transform:uppercase">Raport săptămânal pontaj — abateri de la program</div>
        <div style="font-size:21px;font-weight:700;margin-top:4px">{_html.escape(d['manager_name'])}</div>
        <div style="font-size:14px;opacity:.85;margin-top:2px">Săptămâna {period} · marcaje BRUTE (necorectate) · regulă: ore lucrate &lt; normă · toleranță {d['tolerance']} min</div>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;padding:22px 24px;background:#fff">
      <div style="display:flex;gap:12px;margin-bottom:22px">
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px"><div style="font-size:26px;font-weight:700;color:#0f2744">{len(d['deficits'])}</div><div style="font-size:12px;color:#64748b">angajați cu abateri</div></div>
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px"><div style="font-size:26px;font-weight:700;color:#0f2744">{tot_def}</div><div style="font-size:12px;color:#64748b">zile cu abateri</div></div>
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px"><div style="font-size:26px;font-weight:700;color:#0f2744">{len(d['mismatches'])}</div><div style="font-size:12px;color:#64748b">program nepotrivit (OK)</div></div>
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px"><div style="font-size:26px;font-weight:700;color:#0f2744">{d['team_size']}</div><div style="font-size:12px;color:#64748b">membri echipă</div></div>
      </div>''']

        # § ① real deviations — day-by-day
        P.append('<div style="font:600 12px Segoe UI;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin:6px 0 2px">① Abateri (normă neîndeplinită / absențe / pontaj incomplet)</div>')
        if not d['deficits']:
            P.append('<div style="padding:16px;color:#16a34a;font-weight:600">✓ Nicio abatere.</div>')
        for f in d['deficits']:
            P.append(f'<div style="font-size:15px;font-weight:700;margin:16px 0 6px;color:#0f2744">{_html.escape(f["name"])}'
                     f'<span style="font-weight:400;color:#94a3b8;font-size:13px"> · {len(f["rows"])} zile</span></div>')
            P.append('<table style="width:100%;border-collapse:collapse;font-size:13px">'
                     '<tr style="background:#f8fafc;text-align:left;color:#64748b">'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Ziua</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Program</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Intrare</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Ieșire</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Lucrat</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Abatere</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0;text-align:right">Min. lipsă</th></tr>')
            for r in f['rows']:
                chip = (f'<span style="background:{KIND_COLOR[r["kind"]]}1a;color:{KIND_COLOR[r["kind"]]};'
                        f'padding:2px 8px;border-radius:10px;font-size:12px;white-space:nowrap">{KIND_LABEL[r["kind"]]}</span>')
                dname = f'{RO_DAYS[r["date"].weekday()]} {r["date"].strftime("%d.%m")}'
                worked = _hm(r['worked']) if r['worked'] is not None else '—'
                miss = '—' if r['missing'] is None else _hm(r['missing'])
                P.append(
                    f'<tr><td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{dname}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;color:#64748b">{r["sched"]}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{r["first"]}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{r["last"]}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{worked}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{chip}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;'
                    f'font-weight:600;font-variant-numeric:tabular-nums">{miss}</td></tr>')
            P.append('</table>')

        # § ② punch-outside-schedule but OK — compact, one row per person
        P.append('<div style="font:600 12px Segoe UI;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin:26px 0 2px">② Marcaje în afara programului — OK în general</div>')
        P.append('<div style="font-size:12px;color:#166534;margin-bottom:8px;background:#f0fdf4;border:1px solid #bbf7d0;'
                 'border-radius:8px;padding:9px 12px"><b>Pontează în afara programului din Sincron, dar sunt OK</b> — '
                 'și-au făcut orele (normă îndeplinită). Nu sunt abateri; posibil programul din Sincron trebuie corectat.</div>')
        if not d['mismatches']:
            P.append('<div style="padding:12px;color:#64748b">— niciunul —</div>')
        else:
            P.append('<table style="width:100%;border-collapse:collapse;font-size:13px">'
                     '<tr style="background:#f8fafc;text-align:left;color:#64748b">'
                     '<th style="padding:6px 10px;border-bottom:2px solid #e2e8f0">Nume</th>'
                     '<th style="padding:6px 10px;border-bottom:2px solid #e2e8f0;text-align:right">Zile</th>'
                     '<th style="padding:6px 10px;border-bottom:2px solid #e2e8f0">Intrare medie</th>'
                     '<th style="padding:6px 10px;border-bottom:2px solid #e2e8f0">Ieșire medie</th>'
                     '<th style="padding:6px 10px;border-bottom:2px solid #e2e8f0">Program Sincron</th></tr>')
            for f in d['mismatches']:
                P.append(
                    f'<tr><td style="padding:6px 10px;border-bottom:1px solid #f1f5f9;font-weight:600">{_html.escape(f["name"])}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #f1f5f9;text-align:right;font-variant-numeric:tabular-nums">{len(f["rows"])}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">{_avg_hhmm([r["first"] for r in f["rows"]])}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">{_avg_hhmm([r["last"] for r in f["rows"]])}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #f1f5f9;color:#64748b">{_mode_sched(f["rows"])}</td></tr>')
            P.append('</table>')

        P.append('<div style="margin-top:20px;padding:11px 14px;background:#eff6ff;border:1px solid #bfdbfe;'
                 'border-radius:8px;font-size:12px;color:#1e40af">📎 Atașat: <b>Sinteză pontaj.xlsx</b></div>')
        P.append('<div style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8">'
                 'Marcaje brute BioStar (fără corecții). Concediu / învoire / sărbători excluse. Angajatul apare '
                 'doar dacă a lucrat mai puțin decât norma. JARVIS · Autoworld</div></div></div>')
        return ''.join(P)

    # -------------------------------------------------------------------- Excel
    def build_xlsx(self, data):
        """Synthetic summary workbook → bytes. 3 sheets: Sinteză abateri, Detaliu,
        Program nepotrivit (compact)."""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = Workbook()
        hf = PatternFill('solid', fgColor='0F2744')
        hfont = Font(color='FFFFFF', bold=True)
        bd = Border(bottom=Side(style='thin', color='E2E8F0'))
        rt = Alignment(horizontal='right')

        def hdr(ws, cols):
            for i, (t, w) in enumerate(cols, 1):
                c = ws.cell(1, i, t)
                c.fill, c.font = hf, hfont
                c.alignment = Alignment(horizontal='left', vertical='center')
                ws.column_dimensions[chr(64 + i)].width = w
            ws.freeze_panes = 'A2'

        s = wb.active
        s.title = 'Sinteză abateri'
        hdr(s, [('Nume', 28), ('Program', 14), ('Zile', 8), ('Absențe', 9),
                ('Incomplet', 10), ('Sub normă (ore)', 15)])
        r = 2
        for f in data['deficits']:
            prog = _mode_sched(f['rows'])
            ab = sum(1 for x in f['rows'] if x['kind'] == 'absent')
            inc = sum(1 for x in f['rows'] if x['kind'] == 'incomplete')
            defi = sum(x['missing'] for x in f['rows'] if x['kind'] == 'deficit')
            for i, v in enumerate([f['name'], prog, len(f['rows']), ab or '', inc or '',
                                   _hm(defi) if defi else ''], 1):
                c = s.cell(r, i, v); c.border = bd
                if i >= 3: c.alignment = rt
            r += 1
        if r == 2:
            s.cell(2, 1, 'Nicio abatere în perioada analizată.')

        d = wb.create_sheet('Detaliu')
        hdr(d, [('Nume', 28), ('Data', 12), ('Program', 14), ('Intrare', 9),
                ('Ieșire', 9), ('Lucrat', 9), ('Abatere', 18), ('Min. lipsă', 11)])
        r = 2
        for f in data['deficits']:
            for x in f['rows']:
                vals = [f['name'], x['date'].strftime('%d.%m.%Y'), x['sched'], x['first'],
                        x['last'], _hm(x['worked']) if x['worked'] is not None else '—',
                        KIND_LABEL[x['kind']], '—' if x['missing'] is None else _hm(x['missing'])]
                for i, v in enumerate(vals, 1):
                    c = d.cell(r, i, v); c.border = bd
                    if i == 8: c.alignment = rt
                r += 1

        m = wb.create_sheet('Program nepotrivit (OK)')
        hdr(m, [('Nume', 28), ('Zile', 7), ('Intrare medie', 13), ('Ieșire medie', 13),
                ('Program Sincron', 16)])
        r = 2
        for f in data['mismatches']:
            vals = [f['name'], len(f['rows']), _avg_hhmm([x['first'] for x in f['rows']]),
                    _avg_hhmm([x['last'] for x in f['rows']]), _mode_sched(f['rows'])]
            for i, v in enumerate(vals, 1):
                c = m.cell(r, i, v); c.border = bd
                if i == 2: c.alignment = rt
            r += 1

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


def _to_date(v):
    """Normalize a DB value to date. This repo's cursor returns DATE as an ISO string."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _to_dt(v):
    """Normalize a DB value to a naive datetime (timestamps come back as ISO strings)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    return datetime.fromisoformat(str(v)).replace(tzinfo=None)


def _naive(ts):
    return ts.replace(tzinfo=None) if getattr(ts, 'tzinfo', None) else ts


def _mins(a, b):
    return int((a - b).total_seconds() // 60)


def _hm(mins):
    return f'{mins // 60}h{mins % 60:02d}'


def _avg_hhmm(times):
    vals = [int(t[:2]) * 60 + int(t[3:5]) for t in times if t and t != '—']
    if not vals:
        return '—'
    a = round(sum(vals) / len(vals))
    return f'{a // 60:02d}:{a % 60:02d}'


def _mode_sched(rows):
    return max((r['sched'] for r in rows), key=lambda v: sum(1 for z in rows if z['sched'] == v))
