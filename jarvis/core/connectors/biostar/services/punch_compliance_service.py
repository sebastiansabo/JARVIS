"""Weekly punch-compliance digest — per-manager report of schedule divergences.

For a manager's organigram team, compares each member's RAW BioStar badge punches
(first = earliest, last = latest; manual adjustments are deliberately ignored)
against the Sincron working schedule and flags only the days that diverge:

  * late arrival   — first punch more than TOLERANCE minutes after schedule start
  * early leave    — last punch more than TOLERANCE minutes before schedule end
  * incomplete     — a single badge event (no check-out pair)
  * absent         — scheduled working day with no badge at all

Weekends, public holidays, full-day Sincron leave codes and approved permits
(Connecteam / bilet-de-invoire) are never flagged. The eligible roster reuses the
same gates as the missing-punch detector (active contract, notify_missing_punch,
working_hours > 0, schedule set, not blacklisted, ghost-excluded) so staff who are
not expected to badge are not reported as absent.

The digest renders an inline-styled HTML e-mail plus a synthetic ``.xlsx`` summary
(name · program · minutes missing). Nothing is sent from here — ``tasks``/routes
compose the e-mail.
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
WORKED_CODES = ('OZ', 'OS')          # Sincron codes that mark a scheduled working day
# Fallback full-day leave codes, used alongside sincron_activity_codes.is_leave.
_LEAVE_FALLBACK = frozenset({'CO', 'CM', 'CMS', 'CES', 'CFS', 'CFP', 'CIC',
                             'INV', 'ZLC', 'ZLS', 'DLG'})
RO_DAYS = ('Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică')


class PunchComplianceService:
    """Builds a manager's weekly punch-compliance report from raw punch data."""

    def __init__(self):
        self.db = BaseRepository()

    # ------------------------------------------------------------------ roster
    def eligible_team_ids(self, manager_user_id, override_user_ids=None):
        """Resolve a manager's organigram team, then keep only badge-tracked,
        active, notifiable, non-ghost employees. ``override_user_ids`` bypasses
        organigram resolution (used for ad-hoc test runs)."""
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
        """Highest-norma active contract per user → static schedule + norma."""
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
                   to_char(st.program_out, 'HH24:MI') AS program_out
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
                'first_p': _to_dt(r['first_p']),
                'last_p': _to_dt(r['last_p']),
                'n': r['n'],
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
        flagged = []
        if user_ids:
            contracts = self._primary_contract(user_ids)
            timesheets = self._timesheets(user_ids, start, end)
            punches = self._punches(user_ids, start, end)
            holidays = self._holidays(start, end)
            permits = self._permits(user_ids, start, end)
            leave_codes = self._leave_codes()
            names = self._names(user_ids)
            for uid in sorted(user_ids, key=lambda u: names.get(u, '')):
                rows = self._analyse_user(uid, start, end, contracts.get(uid),
                                          timesheets, punches, holidays, permits,
                                          leave_codes, tolerance)
                if rows:
                    flagged.append({'name': names.get(uid, f'User {uid}'),
                                    'user_id': uid, 'rows': rows})
        return {
            'manager_name': manager_name,
            'start': start, 'end': end, 'tolerance': tolerance,
            'team_size': len(user_ids),
            'flagged': flagged,
            'total_days': sum(len(f['rows']) for f in flagged),
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

    def _analyse_user(self, uid, start, end, contract, timesheets, punches,
                      holidays, permits, leave_codes, tolerance):
        rows = []
        day = start
        while day <= end:
            if day.weekday() < 5 and day not in holidays:
                rows.extend(self._analyse_day(
                    uid, day, contract, timesheets, punches, permits,
                    leave_codes, tolerance))
            day += timedelta(days=1)
        return rows

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
            return []

        s_start = (worked['program_in'] if worked else None) or static_start
        s_end = (worked['program_out'] if worked else None) \
            or (contract['static_end'] if contract else None)
        if not s_start or not s_end:
            return []  # scheduled but no usable program — can't measure divergence

        exp_in = datetime.combine(day, datetime.strptime(s_start, '%H:%M').time())
        exp_out = datetime.combine(day, datetime.strptime(s_end, '%H:%M').time())
        norma_min = int(round(float(contract['norma'] or 8) * 60)) if contract else 480

        p = punches.get((uid, day))
        n = (p['n'] if p else 0) or 0
        reasons, late, early, absent, incomplete = [], 0, 0, 0, False
        first_s = last_s = '—'
        if n == 0:
            absent = norma_min
            reasons.append('Absent (fără pontaj)')
        elif n == 1:
            incomplete = True
            first_s = _naive(p['first_p']).strftime('%H:%M')
            reasons.append('Pontaj incomplet (o singură marcare)')
        else:
            fin, lout = _naive(p['first_p']), _naive(p['last_p'])
            first_s, last_s = fin.strftime('%H:%M'), lout.strftime('%H:%M')
            if _mins(fin, exp_in) > tolerance:
                late = _mins(fin, exp_in)
                reasons.append(f'Întârziere {late} min')
            if _mins(exp_out, lout) > tolerance:
                early = _mins(exp_out, lout)
                reasons.append(f'Plecare devreme {early} min')
        if not reasons:
            return []
        return [{
            'date': day, 'sched': f'{s_start}–{s_end}',
            'first': first_s, 'last': last_s, 'reasons': reasons,
            'late': late, 'early': early, 'absent': absent, 'incomplete': incomplete,
            'missing': late + early + absent,
        }]

    # -------------------------------------------------------------------- HTML
    def build_html(self, data):
        import html as _html
        d = data
        period = f"{d['start'].strftime('%d.%m.%Y')} – {d['end'].strftime('%d.%m.%Y')}"
        P = [f'''<div style="font-family:Segoe UI,Arial,sans-serif;max-width:760px;margin:0 auto;color:#1a2332">
      <div style="background:#0f2744;color:#fff;padding:20px 24px;border-radius:10px 10px 0 0">
        <div style="font-size:12px;letter-spacing:1px;opacity:.75;text-transform:uppercase">Raport săptămânal pontaj — abateri de la program</div>
        <div style="font-size:21px;font-weight:700;margin-top:4px">{_html.escape(d['manager_name'])}</div>
        <div style="font-size:14px;opacity:.85;margin-top:2px">Săptămâna {period} · marcaje BRUTE (necorectate) · toleranță {d['tolerance']} min</div>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;padding:22px 24px;background:#fff">''']
        P.append(f'''<div style="display:flex;gap:12px;margin-bottom:20px">
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px">
          <div style="font-size:26px;font-weight:700;color:#0f2744">{len(d['flagged'])}</div>
          <div style="font-size:12px;color:#64748b">angajați cu abateri</div></div>
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px">
          <div style="font-size:26px;font-weight:700;color:#0f2744">{d['total_days']}</div>
          <div style="font-size:12px;color:#64748b">zile cu abateri</div></div>
        <div style="flex:1;background:#f1f5f9;border-radius:8px;padding:12px 14px">
          <div style="font-size:26px;font-weight:700;color:#0f2744">{d['team_size']}</div>
          <div style="font-size:12px;color:#64748b">membri echipă</div></div>
      </div>''')
        if not d['flagged']:
            P.append('<div style="padding:28px;text-align:center;color:#16a34a;font-size:15px;'
                     'font-weight:600">✓ Nicio abatere în săptămâna analizată. '
                     'Toată echipa a respectat programul.</div>')
        for f in d['flagged']:
            P.append(f'<div style="font-size:15px;font-weight:700;margin:18px 0 6px;color:#0f2744">'
                     f'{_html.escape(f["name"])}<span style="font-weight:400;color:#94a3b8;'
                     f'font-size:13px"> · {len(f["rows"])} zile</span></div>')
            P.append('<table style="width:100%;border-collapse:collapse;font-size:13px">'
                     '<tr style="background:#f8fafc;text-align:left;color:#64748b">'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Ziua</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Program</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Intrare</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Ieșire</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0">Abatere</th>'
                     '<th style="padding:7px 10px;border-bottom:2px solid #e2e8f0;text-align:right">'
                     'Min. lipsă</th></tr>')
            for r in f['rows']:
                badge = ' · '.join(
                    f'<span style="background:#fee2e2;color:#b91c1c;padding:2px 8px;'
                    f'border-radius:10px;font-size:12px;white-space:nowrap">'
                    f'{_html.escape(x)}</span>' for x in r['reasons'])
                dname = f'{RO_DAYS[r["date"].weekday()]} {r["date"].strftime("%d.%m")}'
                miss = '—' if r['incomplete'] else str(r['missing'])
                P.append(
                    f'<tr><td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{dname}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;color:#64748b">{r["sched"]}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{r["first"]}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{r["last"]}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9">{badge}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;'
                    f'font-weight:600;font-variant-numeric:tabular-nums">{miss}</td></tr>')
            P.append('</table>')
        P.append('<div style="margin-top:18px;padding:11px 14px;background:#eff6ff;'
                 'border:1px solid #bfdbfe;border-radius:8px;font-size:12px;color:#1e40af">'
                 '📎 Atașat: <b>Sinteză pontaj.xlsx</b> — nume, program și minute lipsă per angajat.</div>')
        P.append('<div style="margin-top:14px;padding-top:14px;border-top:1px solid #e2e8f0;'
                 'font-size:11px;color:#94a3b8">Generat automat din marcajele brute BioStar '
                 '(fără corecții manuale). Angajații aflați în concediu, învoire aprobată sau zile '
                 'libere legale nu sunt raportați. JARVIS · Autoworld</div></div></div>')
        return ''.join(P)

    # -------------------------------------------------------------------- Excel
    def build_xlsx(self, data):
        """Synthetic summary workbook → bytes. Sheet 1 one row per employee
        (Nume · Program · minute lipsă), Sheet 2 one row per divergent day."""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = Workbook()
        hdr_fill = PatternFill('solid', fgColor='0F2744')
        hdr_font = Font(color='FFFFFF', bold=True, size=11)
        bold = Font(bold=True)
        border = Border(bottom=Side(style='thin', color='E2E8F0'))
        right = Alignment(horizontal='right')

        def header(ws, cols):
            for i, (title, w) in enumerate(cols, 1):
                c = ws.cell(1, i, title)
                c.fill, c.font = hdr_fill, hdr_font
                c.alignment = Alignment(horizontal='left', vertical='center')
                ws.column_dimensions[chr(64 + i)].width = w
            ws.row_dimensions[1].height = 22
            ws.freeze_panes = 'A2'

        s = wb.active
        s.title = 'Sinteză'
        header(s, [('Nume', 30), ('Program', 16), ('Zile cu abateri', 15),
                   ('Întârziere (min)', 15), ('Plecări (min)', 14),
                   ('Absențe (min)', 14), ('Total minute lipsă', 17)])
        r = 2
        for f in data['flagged']:
            rows = f['rows']
            prog = max((x['sched'] for x in rows),
                       key=lambda v: sum(1 for z in rows if z['sched'] == v))
            late = sum(x['late'] for x in rows)
            early = sum(x['early'] for x in rows)
            absent = sum(x['absent'] for x in rows)
            vals = [f['name'], prog, len(rows), late or '', early or '',
                    absent or '', late + early + absent]
            for i, v in enumerate(vals, 1):
                c = s.cell(r, i, v)
                c.border = border
                if i >= 3:
                    c.alignment = right
                if i == 7:
                    c.font = bold
            r += 1
        if r == 2:
            s.cell(2, 1, 'Nicio abatere în perioada analizată.')

        d = wb.create_sheet('Detaliu')
        header(d, [('Nume', 30), ('Data', 14), ('Zi', 10), ('Program', 16),
                   ('Intrare', 10), ('Ieșire', 10), ('Abatere', 34), ('Min. lipsă', 11)])
        r = 2
        for f in data['flagged']:
            for x in f['rows']:
                vals = [f['name'], x['date'].strftime('%d.%m.%Y'),
                        RO_DAYS[x['date'].weekday()], x['sched'], x['first'],
                        x['last'], '; '.join(x['reasons']),
                        '—' if x['incomplete'] else x['missing']]
                for i, v in enumerate(vals, 1):
                    c = d.cell(r, i, v)
                    c.border = border
                    if i == 8:
                        c.alignment = right
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
    """Drop tzinfo so we can diff against a naive schedule datetime."""
    return ts.replace(tzinfo=None) if getattr(ts, 'tzinfo', None) else ts


def _mins(a, b):
    return int((a - b).total_seconds() // 60)
