"""Deep-link landing: send approval notification links to the app or the web,
plus one-tap email approve/reject for Bilet de Învoire (signed-token authenticated)."""
from flask import Blueprint, request, redirect, render_template_string, current_app
from core.approvals.action_token import read_action_token

deeplink_bp = Blueprint('deeplink', __name__)

_MOBILE_UA = ('iphone', 'ipad', 'ipod', 'android')


# The approver lands on the Hub "De aprobat" tab (their pending-approval queue).
_WEB_URL = '/app/hub?module=hr&hrtab=leave-approvals'


def resolve_deeplink(user_agent, request_id):
    """('redirect', web_url) on desktop, ('interstitial', app_url) on mobile."""
    ua = (user_agent or '').lower()
    if any(tok in ua for tok in _MOBILE_UA):
        return 'interstitial', f'com.jarvis.mobile2://approvals?request={request_id}'
    return 'redirect', _WEB_URL


_INTERSTITIAL = """<!doctype html><html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS — Aprobare</title>
<style>body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f5f5f5;margin:0;
display:flex;min-height:100vh;align-items:center;justify-content:center}
.card{background:#fff;border-radius:12px;padding:28px;max-width:340px;width:88%;text-align:center;
box-shadow:0 6px 24px rgba(0,0,0,.08)}h1{font-size:18px;margin:0 0 8px}p{color:#666;font-size:14px;margin:0 0 20px}
a{display:block;padding:12px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;margin-top:10px}
.app{background:#4f46e5;color:#fff}.web{background:#eee;color:#333}</style></head>
<body><div class="card"><h1>Cerere de aprobare</h1>
<p>Deschide în aplicația JARVIS?</p>
<a class="app" href="{{ app_url }}">Deschide în aplicație</a>
<a class="web" href="{{ web_url }}">Continuă în browser</a></div></body></html>"""


@deeplink_bp.route('/go/approval/<int:request_id>')
def approval_landing(request_id):
    kind, target = resolve_deeplink(request.headers.get('User-Agent', ''), request_id)
    if kind == 'redirect':
        return redirect(target)
    return render_template_string(_INTERSTITIAL, app_url=target, web_url=_WEB_URL)


# ── One-tap email decide (Bilet de Învoire) ─────────────────────────────────
# The email carries a signed per-approver token. GET renders a no-login confirm
# page and NEVER mutates (so mail-client link scanners can't auto-decide); the
# decision only happens on POST. Indirection helpers below are the seams tests
# patch and keep heavy imports lazy.

def _load_request(rid):
    from core.approvals.handlers._shared import _get_request
    return _get_request(rid)


def _leave_summary_for(req):
    if req.get('entity_type') == 'form_submission' and req.get('entity_id'):
        from core.approvals.handlers.leave_summary import build_leave_summary
        return build_leave_summary(req['entity_id'])
    return None


def _do_decide(rid, decision, decided_by, comment):
    from core.approvals.engine import ApprovalEngine
    ApprovalEngine().decide(rid, decision, decided_by=decided_by, comment=comment)


_ACT = {
    'approve': ('Aprobă învoirea', 'Aprobă', '#16a34a'),
    'reject': ('Respinge învoirea', 'Respinge', '#dc2626'),
}


def _confirm_ctx(act, token, summary, reason=''):
    heading, cta, color = _ACT[act]
    return {'heading': heading, 'cta': cta, 'color': color, 'act': act,
            'token': token, 'summary': summary, 'reason': reason}


@deeplink_bp.route('/go/approval/act', methods=['GET', 'POST'])
def approval_act():
    token = request.values.get('token', '')
    data = read_action_token(token, current_app.secret_key)
    if not data:
        return _msg('Link invalid', 'Acest link de aprobare este invalid sau a expirat.'), 400
    rid, uid, act = data['rid'], data['uid'], data['act']
    req = _load_request(rid)
    if not req:
        return _msg('Cerere inexistentă', 'Cererea nu a fost găsită.'), 404
    if req.get('status') not in ('pending', 'in_progress'):
        return _msg('Deja procesată', 'Această cerere a fost deja procesată.'), 200
    summary = _leave_summary_for(req)

    if request.method == 'GET':
        return render_template_string(_CONFIRM, error=None, **_confirm_ctx(act, token, summary))

    reason = (request.form.get('reason') or '').strip()
    if act == 'reject' and not reason:
        return render_template_string(
            _CONFIRM, error='Motivul respingerii este obligatoriu.',
            **_confirm_ctx(act, token, summary, reason)), 400
    decision = 'approved' if act == 'approve' else 'rejected'
    try:
        _do_decide(rid, decision, decided_by=uid, comment=reason or None)
    except Exception as e:
        return _msg('Nu s-a putut procesa', str(e)), 409
    done = 'aprobată' if act == 'approve' else 'respinsă'
    return _msg('Gata', f'Învoire {done}. Mulțumim!',
                color='#16a34a' if act == 'approve' else '#dc2626'), 200


_STYLE = """body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f5f5f5;margin:0;
display:flex;min-height:100vh;align-items:center;justify-content:center}
.card{background:#fff;border-radius:12px;padding:28px;max-width:380px;width:90%;
box-shadow:0 6px 24px rgba(0,0,0,.08)}h1{font-size:18px;margin:0 0 14px;text-align:center}
table{width:100%;border-collapse:collapse;margin:0 0 16px;font-size:14px}
td{padding:7px 10px;border:1px solid #eee}td:first-child{color:#666;width:38%}
.err{color:#dc2626;font-size:13px;margin:0 0 12px}textarea{width:100%;box-sizing:border-box;
min-height:70px;border:1px solid #ddd;border-radius:8px;padding:10px;font:inherit;margin-bottom:12px}
button{display:block;width:100%;padding:12px;border:0;border-radius:8px;color:#fff;
font-weight:600;font-size:15px;cursor:pointer}p{color:#555;font-size:14px;text-align:center}"""

_CONFIRM = """<!doctype html><html lang=ro><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>JARVIS — {{ heading }}</title>
<style>""" + _STYLE + """</style></head><body><div class=card><h1>{{ heading }}</h1>
{% if summary %}<table>
<tr><td>Angajat</td><td>{{ summary.requester_name }}</td></tr>
<tr><td>Data</td><td>{{ summary.leave_date }}</td></tr>
<tr><td>Interval</td><td>{{ summary.start }}–{{ summary.end }} ({{ summary.hours }}h)</td></tr>
<tr><td>Motiv</td><td>{{ summary.reason }}</td></tr>
{% if summary.notes %}<tr><td>Detalii</td><td>{{ summary.notes }}</td></tr>{% endif %}
</table>{% endif %}
{% if error %}<p class=err>{{ error }}</p>{% endif %}
<form method=post action="/go/approval/act">
<input type=hidden name=token value="{{ token }}">
{% if act == 'reject' %}<textarea name=reason placeholder="Motivul respingerii (obligatoriu)" required>{{ reason }}</textarea>{% endif %}
<button type=submit style="background:{{ color }}">{{ cta }}</button>
</form></div></body></html>"""

_MSG = """<!doctype html><html lang=ro><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>JARVIS — {{ title }}</title>
<style>""" + _STYLE + """</style></head><body><div class=card>
<h1 style="color:{{ color }}">{{ title }}</h1><p>{{ text }}</p></div></body></html>"""


def _msg(title, text, color='#111'):
    return render_template_string(_MSG, title=title, text=text, color=color)
