"""Approver-email body for a Bilet de Învoire: the full leave summary plus two
one-tap action buttons (Aprobă / Respinge) that link to the signed decide endpoint.
Rendered into `_approval_email_base` (which still adds the 'Vezi cererea' CTA)."""


def _row(label, value):
    return (f'<tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;'
            f'border:1px solid #ddd;width:38%;">{label}</td>'
            f'<td style="padding:8px 12px;border:1px solid #ddd;">{value}</td></tr>')


def _btn(url, label, color):
    return (f'<a href="{url}" style="display:inline-block;background:{color};color:#fff;'
            f'text-decoration:none;padding:10px 26px;border-radius:6px;font-size:14px;'
            f'font-weight:bold;margin-right:10px;">{label}</a>')


def leave_approval_email_body(approver_name, summary, approve_url, reject_url):
    """HTML body: greeting + leave-detail table + Aprobă/Respinge action buttons."""
    s = summary or {}
    notes_row = _row('Detalii', s.get('notes')) if s.get('notes') else ''
    actions = ''
    if approve_url and reject_url:
        actions = f"""
    <p style="margin:20px 0 10px;color:#555;font-size:13px;">Puteți decide direct de aici:</p>
    <div style="margin-bottom:8px;">
      {_btn(approve_url, 'Aprobă', '#16a34a')}
      {_btn(reject_url, 'Respinge', '#dc2626')}
    </div>"""
    return f"""
    <p>Buna ziua {approver_name},</p>
    <p><strong>{s.get('requester_name', 'Un angajat')}</strong> a solicitat un bilet de învoire
    care așteaptă decizia dumneavoastră:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      {_row('Angajat', s.get('requester_name', ''))}
      {_row('Data', s.get('leave_date', ''))}
      {_row('Interval', f"{s.get('start','')}–{s.get('end','')} ({s.get('hours','')}h)")}
      {_row('Motiv', s.get('reason', ''))}
      {notes_row}
    </table>{actions}
    """
