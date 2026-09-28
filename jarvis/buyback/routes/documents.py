"""Buyback document decoding — extract vehicle fields from an uploaded CIV
(Cartea de Identitate a Vehiculului) or talon (Certificat de Înmatriculare)
via AI vision, mapped to the buyback intake form's field names.

Mirrors carpark/routes/vin.py::decode_civ (same AI-vision approach + envelope
shape) but is buyback-owned and gated on `buyback.record.create` so BuyBack
users don't need CarPark access, and it also handles the talon variant.

  POST /api/buyback/documents/decode   (multipart: file + doc_type=civ|talon)
    -> {success, data: {vehicle_fields, provider, confidence}}
       where vehicle_fields uses BUYBACK field names.
"""
import base64
import json
import logging
import re

from flask import request, jsonify
from flask_login import login_required

from core.roles.decorators import v2_permission_required
from .. import buyback_bp

logger = logging.getLogger('jarvis.buyback.documents')

_ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
_MAX_BYTES = 12 * 1024 * 1024  # 12 MB

# Both RO documents use the same EU-standard alphanumeric field codes, so the
# extraction spec is shared — only the document name differs.
def _prompt(doc_label: str) -> str:
    return (
        f"Ești un extractor de date dintr-un {doc_label} românesc. "
        "Citește documentul și returnează DOAR un obiect JSON valid (fără text "
        "suplimentar, fără Markdown, fără blocuri ```), cu următoarele chei. "
        "Omite orice cheie pe care nu o găsești clar în document; nu inventa valori.\n"
        "- vin: seria de șasiu / VIN (câmp E)\n"
        "- brand: marca (câmp D.1)\n"
        "- model: modelul / tipul comercial (câmp D.3, sau D.2 dacă D.3 lipsește)\n"
        "- variant: varianta / versiunea, dacă e distinctă\n"
        "- first_registration_date: prima înmatriculare (câmp B) în format YYYY-MM-DD\n"
        "- engine_capacity_cm3: capacitatea cilindrică în cmc, număr întreg (câmp P.1)\n"
        "- fuel_type: combustibilul (câmp P.3), exact una dintre valorile: "
        "petrol, diesel, electric, hybrid, plugin-hybrid, petrol-lpg, petrol-cng, hydrogen\n"
        "Valorile numerice trebuie să fie numere JSON, nu string-uri. "
        f"Dacă documentul nu este un {doc_label} sau nu poți citi nimic, returnează {{}}."
    )


_DOC_LABELS = {
    'civ': 'CIV (Cartea de Identitate a Vehiculului)',
    'talon': 'talon (Certificat de Înmatriculare)',
}

# Only these keys are surfaced to the form — all are native buyback intake fields.
_ALLOWED_FIELDS = {
    'vin', 'brand', 'model', 'variant',
    'first_registration_date', 'engine_capacity_cm3', 'fuel_type',
}


@buyback_bp.route('/documents/decode', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'create')
def decode_document():
    """Extract intake fields from an uploaded CIV or talon (image or PDF)."""
    doc_type = (request.form.get('doc_type') or 'civ').strip().lower()
    if doc_type not in _DOC_LABELS:
        return jsonify({'success': False, 'error': 'Tip document invalid (civ sau talon).'}), 400

    f = request.files.get('file')
    if f is None or not getattr(f, 'filename', ''):
        return jsonify({'success': False, 'error': 'Încarcă un fișier.'}), 400

    raw = f.read()
    if not raw:
        return jsonify({'success': False, 'error': 'Fișierul este gol.'}), 400
    if len(raw) > _MAX_BYTES:
        return jsonify({'success': False, 'error': 'Fișierul este prea mare (max 12MB).'}), 413

    mime = (f.mimetype or '').lower()
    b64 = base64.standard_b64encode(raw).decode('ascii')
    if 'pdf' in mime:
        media_block = {
            'type': 'document',
            'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': b64},
        }
    else:
        media_type = mime if mime in _ALLOWED_IMAGE_TYPES else 'image/jpeg'
        media_block = {
            'type': 'image',
            'source': {'type': 'base64', 'media_type': media_type, 'data': b64},
        }

    try:
        from ai_agent.services.llm_client import call as llm_call
        messages = [{
            'role': 'user',
            'content': [media_block, {'type': 'text', 'text': _prompt(_DOC_LABELS[doc_type])}],
        }]
        text = llm_call(messages, max_tokens=1024)
    except Exception as e:
        logger.warning(f'{doc_type} extraction failed: {e}')
        return jsonify({'success': False, 'error': 'Extragerea a eșuat. Încearcă din nou.'}), 502

    match = re.search(r'\{.*\}', text or '', re.DOTALL)
    if not match:
        return jsonify({'success': False, 'error': 'Nu am putut citi datele din document.'}), 422
    try:
        fields = json.loads(match.group(0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Răspuns invalid de la AI.'}), 422
    if not isinstance(fields, dict):
        fields = {}

    # Keep only whitelisted, non-empty fields; normalize the VIN like the form.
    clean = {}
    for k, v in fields.items():
        if k not in _ALLOWED_FIELDS or v in (None, '', []):
            continue
        if k == 'vin' and isinstance(v, str):
            v = v.strip().upper()
        clean[k] = v

    return jsonify({
        'success': True,
        'data': {'vehicle_fields': clean, 'provider': doc_type.upper(), 'confidence': 0.9},
    })
