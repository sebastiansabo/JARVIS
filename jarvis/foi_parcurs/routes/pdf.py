"""PDF download + email routes for foi de parcurs contracts."""
import os
import io
import re
import base64
import html as _html
from datetime import datetime
from flask import send_file
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger, _fp_repo, _vehicle_repo
from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf
from ..dealer_config import get_dealer_config

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _decode_doc(data_url, base_name):
    """Decode a base64 data-URL document → (filename, bytes), or (None, None)."""
    if not data_url or ',' not in data_url:
        return None, None
    try:
        header, b64 = data_url.split(',', 1)
        raw = base64.b64decode(b64)
    except Exception:
        return None, None
    ext = 'pdf' if 'pdf' in header else ('png' if 'png' in header else 'jpg')
    return f'{base_name}.{ext}', raw


def _fmt_date(v):
    """Format a datetime/ISO string as dd.mm.yyyy; '' when missing."""
    if not v:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%d.%m.%Y')
    try:
        return datetime.fromisoformat(str(v).replace('Z', '')).strftime('%d.%m.%Y')
    except ValueError:
        return str(v)


def _qr_png(url):
    """PNG bytes of a QR code for `url`, or None (missing url / lib / failure)."""
    if not url:
        return None
    try:
        import segno
        buf = io.BytesIO()
        segno.make(url, error='m').save(buf, kind='png', scale=6, border=2)
        return buf.getvalue()
    except Exception:
        logger.warning('QR generation failed for %s', url, exc_info=True)
        return None


def _consilier_contact(advisor_name):
    """Resolve the consilier's contact details. Looks the advisor up by name in
    the `users` table (name/email/phone); falls back to the sending user for any
    missing field. Returns {'name', 'email', 'phone'} (values may be '')."""
    name = (advisor_name or '').strip()
    out = {'name': name, 'email': '', 'phone': ''}
    if name:
        try:
            row = _fp_repo.query_one(
                'SELECT name, email, phone FROM users WHERE LOWER(name) = LOWER(%s) ORDER BY id LIMIT 1',
                (name,),
            )
            if row:
                out = {
                    'name': (row.get('name') or name).strip(),
                    'email': (row.get('email') or '').strip(),
                    'phone': (row.get('phone') or '').strip(),
                }
        except Exception:
            logger.warning('Consilier lookup failed for %s', name, exc_info=True)
    # Fall back to the logged-in sender for anything still missing.
    if not out['name']:
        out['name'] = (getattr(current_user, 'name', '') or '').strip()
    if not out['email']:
        out['email'] = (getattr(current_user, 'email', '') or '').strip()
    if not out['phone']:
        out['phone'] = (getattr(current_user, 'phone', '') or '').strip()
    return out


def _render_td_email(contract, dealer, consilier, simple=False):
    """Build (subject, plain-text body, html body) for the test-drive contract
    email — a plain, standard-looking mail (HTML paragraphs, no icons, no
    formatting tricks). Any placeholder without a value has its line omitted.

    `simple=True` is the start-of-session email: just a short greeting to the
    client + the consilier's contact block + the contract PDF attached — no
    review request, QR, offer document or thank-you-for-today framing."""
    contract_nr = str(contract.get('contract_id') or contract.get('id') or '')
    client_name = (contract.get('client_name') or '').strip()
    vehicul = ' '.join(x for x in (
        (contract.get('vehicle_mark') or '').strip(),
        (contract.get('vehicle_model') or '').strip(),
        (contract.get('vehicle_fuel_type') or '').strip(),   # motorizare (best available)
    ) if x)
    vin = (contract.get('vin') or '').strip()
    data_td = _fmt_date(contract.get('departure_datetime'))
    cons_nume = (consilier.get('name') or '').strip()
    cons_tel = (consilier.get('phone') or '').strip()
    cons_email = (consilier.get('email') or '').strip()
    review = dealer.get('review_url')
    footer = ' | '.join(x for x in (dealer.get('address'), dealer.get('phone'), 'www.autoworld.ro') if x)

    detail = [(l, v) for l, v in (('Contract', contract_nr), ('Vehicul', vehicul),
                                  ('VIN', vin), ('Data', data_td)) if v]
    cons = [(l, v) for l, v in (('Nume', cons_nume), ('Telefon', cons_tel),
                                ('Email', cons_email)) if v]

    if simple:
        # Start-of-session mail: client greeting + consilier contact only.
        e = _html.escape
        subject = 'Contract test drive — AUTOWORLD'
        T = [f'Bună ziua {client_name},' if client_name else 'Bună ziua,',
             'Atașat găsiți contractul de test drive.']
        if cons:
            T.append('Consilier\n' + '\n'.join(f'{l}: {v}' for l, v in cons))
        T.append('Cu stimă,\nEchipa AUTOWORLD')
        H = [f'<p>Bună ziua {e(client_name)},</p>' if client_name else '<p>Bună ziua,</p>',
             '<p>Atașat găsiți contractul de test drive.</p>']
        if cons:
            H.append('<p><strong>Consilier</strong><br>'
                     + '<br>'.join(f'{l}: {e(v)}' for l, v in cons) + '</p>')
        H.append('<p>Cu stimă,<br>Echipa AUTOWORLD</p>')
        return subject, '\n\n'.join(T), '\n'.join(H)

    # ---- plain-text alternative ----
    T = [f'Bună ziua {client_name},' if client_name else 'Bună ziua,',
         'Vă mulțumim că ați ales AUTOWORLD pentru test drive-ul de astăzi! '
         'Sperăm că experiența la volan a fost pe măsura așteptărilor.',
         'Atașat găsiți foaia de parcurs / contractul de test drive.']
    if detail:
        T.append('Detalii test drive\n' + '\n'.join(f'{l}: {v}' for l, v in detail))
    if cons:
        T.append('Consilierul dumneavoastră\n' + '\n'.join(f'{l}: {v}' for l, v in cons))
        T.append('Pentru orice întrebare legată de vehicul, ofertă sau pașii următori, '
                 'consilierul dumneavoastră vă stă la dispoziție.')
    if review:
        T.append('Părerea dumneavoastră contează. Ne-ați ajuta enorm cu o recenzie de '
                 '30 de secunde pe Google:\n' + review + '\n(sau scanați codul QR atașat)')
    T.append('Vă mulțumim și vă așteptăm cu drag înapoi!')
    T.append('Cu stimă,\nEchipa AUTOWORLD' + (('\n' + footer) if footer else ''))
    text = '\n\n'.join(T)

    # ---- HTML alternative (plain paragraphs) ----
    e = _html.escape
    H = [f'<p>Bună ziua {e(client_name)},</p>' if client_name else '<p>Bună ziua,</p>',
         '<p>Vă mulțumim că ați ales AUTOWORLD pentru test drive-ul de astăzi! '
         'Sperăm că experiența la volan a fost pe măsura așteptărilor.</p>',
         '<p>Atașat găsiți foaia de parcurs / contractul de test drive.</p>']
    if detail:
        H.append('<p><strong>Detalii test drive</strong><br>'
                 + '<br>'.join(f'{l}: {e(v)}' for l, v in detail) + '</p>')
    if cons:
        H.append('<p><strong>Consilierul dumneavoastră</strong><br>'
                 + '<br>'.join(f'{l}: {e(v)}' for l, v in cons) + '</p>')
        H.append('<p>Pentru orice întrebare legată de vehicul, ofertă sau pașii următori, '
                 'consilierul dumneavoastră vă stă la dispoziție.</p>')
    if review:
        H.append('<p>Părerea dumneavoastră contează. Ne-ați ajuta enorm cu o recenzie de '
                 '30 de secunde pe Google:<br>'
                 f'<a href="{e(review)}">Lăsați o recenzie</a> (sau scanați codul QR atașat).</p>')
    H.append('<p>Vă mulțumim și vă așteptăm cu drag înapoi!</p>')
    H.append('<p>Cu stimă,<br>Echipa AUTOWORLD'
             + (f'<br>{e(footer)}' if footer else '') + '</p>')
    html = '\n'.join(H)

    subject = 'Mulțumim pentru test drive!'
    return subject, text, html


def _ensure_pdf_path(contract, contract_id, pdf_type):
    """Return the on-disk path for the contract's PDF, generating + persisting it
    if missing. Raises on generation failure."""
    path_field = f'pdf_{pdf_type}_path'
    pdf_path = contract.get(path_field)
    if not pdf_path or not os.path.exists(pdf_path):
        pdf_path = generate_legal_pdf(contract) if pdf_type == 'legal' else generate_custom_pdf(contract)
        _fp_repo.execute(
            f'UPDATE foi_de_parcurs SET {path_field} = %s WHERE id = %s',
            (pdf_path, contract_id),
        )
    return pdf_path


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/pdf/<pdf_type>', methods=['GET'])
@login_required
def api_download_pdf(id, pdf_type):
    if pdf_type not in ('legal', 'custom'):
        return jsonify({'success': False, 'error': 'Invalid PDF type'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    try:
        pdf_path = _ensure_pdf_path(contract, id, pdf_type)
    except Exception as e:
        logger.exception('Failed to generate PDF for contract %s', id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500

    return send_file(pdf_path, as_attachment=True,
                     download_name=f'foaie-parcurs-{contract["contract_id"]}-{pdf_type}.pdf')


def email_contract_pdf(contract, to_email, pdf_type='legal', simple=False):
    """Render + send the test-drive contract email (PDF + review QR attached) to
    one recipient. Returns (ok: bool, err: str). Reused by the manual email route
    and the auto-send on TD completion. `simple=True` sends the simplified
    start-of-session mail with ONLY the contract PDF (no review QR / offer doc)."""
    to_email = (to_email or '').strip()
    if not to_email or not _EMAIL_RE.match(to_email):
        return False, 'Adresă de email invalidă sau lipsă.'
    from core.services.notification_service import send_email, is_smtp_configured
    if not is_smtp_configured():
        return False, 'Trimiterea de email nu este configurată.'

    cid = contract.get('id')
    try:
        pdf_path = _ensure_pdf_path(contract, cid, pdf_type)
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
    except Exception as e:
        logger.exception('Failed to generate PDF for contract %s', cid)
        return False, str(e)[:200]

    contract_code = contract.get('contract_id') or cid
    dealer = get_dealer_config(contract.get('company_name'), contract.get('vehicle_brand'))
    consilier = _consilier_contact(contract.get('advisor_name'))
    subject, text_body, html_body = _render_td_email(contract, dealer, consilier, simple=simple)
    attachments = [(f'foaie-parcurs-{contract_code}.pdf', pdf_bytes)]
    if not simple:
        qr = _qr_png(dealer.get('review_url'))
        if qr:
            attachments.append(('recenzie-google-qr.png', qr))

        # Attach the vehicle's offer document, only if one is on file.
        try:
            vin = contract.get('vin')
            veh = _vehicle_repo.get_by_vin(vin) if vin else None
            offer_fn, offer_bytes = _decode_doc((veh or {}).get('offer_doc') or '', 'oferta')
            if offer_bytes:
                attachments.append((offer_fn, offer_bytes))
        except Exception:
            logger.warning('Could not attach offer for contract %s', contract.get('id'), exc_info=True)

    return send_email(to_email=to_email, subject=subject, html_body=html_body,
                      text_body=text_body, attachments=attachments, from_name='AUTOWORLD')


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/email', methods=['POST'])
@login_required
def api_email_pdf(id):
    """Email the contract PDF (default: legal) to a recipient. Body:
    {"to_email": "...", "pdf_type": "legal"|"custom"}. If to_email is omitted,
    falls back to the client's email on file."""
    data = request.get_json(silent=True) or {}
    pdf_type = (data.get('pdf_type') or 'legal').strip()
    if pdf_type not in ('legal', 'custom'):
        return jsonify({'success': False, 'error': 'Invalid PDF type'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    to_email = (data.get('to_email') or contract.get('client_email') or '').strip()
    ok, err = email_contract_pdf(contract, to_email, pdf_type)
    if not ok:
        logger.error('Failed to email contract %s to %s: %s', id, to_email, err)
        code = 400 if 'invalid' in err.lower() or 'lipsă' in err.lower() else 502
        return jsonify({'success': False, 'error': err}), code

    return jsonify({'success': True, 'sent_to': to_email})
