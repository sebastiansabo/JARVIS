"""Deep-link landing: send approval notification links to the app or the web."""
from flask import Blueprint, request, redirect, render_template_string

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
