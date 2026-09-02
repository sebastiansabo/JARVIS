"""VIN Decoder API routes.

Endpoints:
  GET /api/carpark/vin/decode/<vin>   — Decode VIN (with caching)
  GET /api/carpark/vin/validate/<vin> — Validate VIN format
  GET /api/carpark/vin/providers      — Provider status

All endpoints require authentication + carpark access permission.
"""
import logging

from flask import request, jsonify
from flask_login import login_required

from carpark import carpark_bp
from carpark.routes.vehicles import carpark_required
from carpark.connectors.vin_decoder import (
    VINDecoderClient,
    VINDecoderError,
    VINValidationError,
    VINNotFoundError,
    QuotaExhaustedError,
    ProviderUnavailableError,
)

logger = logging.getLogger('jarvis.carpark.vin_decoder')

_vin_client = None


def _get_vin_client() -> VINDecoderClient:
    """Lazy-init VIN decoder client (avoids import-time env var issues)."""
    global _vin_client
    if _vin_client is None:
        _vin_client = VINDecoderClient()
    return _vin_client


@carpark_bp.route('/vin/decode/<vin>', methods=['GET'])
@login_required
@carpark_required
def decode_vin(vin):
    """Decode VIN and return vehicle specs.

    Query params:
        refresh=true — skip cache and re-decode from provider
    """
    skip_cache = request.args.get('refresh', 'false').lower() == 'true'

    try:
        client = _get_vin_client()
        specs = client.decode(vin, skip_cache=skip_cache)
        return jsonify({
            'success': True,
            'data': {
                'specs': specs.to_dict(),
                'vehicle_fields': specs.to_vehicle_fields(),
                'provider': specs.provider,
                'confidence': specs.confidence_score,
            },
        })
    except VINValidationError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 400
    except VINNotFoundError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 404
    except QuotaExhaustedError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 429
    except ProviderUnavailableError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 503
    except VINDecoderError as e:
        logger.exception(f'VIN decode failed: {e}')
        return jsonify({
            'success': False, 'error': 'Internal error',
        }), 500


# CIV (Cartea de Identitate a Vehiculului) → structured vehicle fields via AI vision.
_CIV_ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
_CIV_MAX_BYTES = 12 * 1024 * 1024  # 12 MB

_CIV_PROMPT = (
    "Ești un extractor de date dintr-o CIV românească (Cartea de Identitate a Vehiculului). "
    "Citește documentul și returnează DOAR un obiect JSON valid (fără text suplimentar, fără Markdown, "
    "fără blocuri ```), cu următoarele chei. Omite orice cheie pe care nu o găsești clar în document; "
    "nu inventa valori.\n"
    "- vin: seria de șasiu / VIN (câmp E)\n"
    "- brand: marca (câmp D.1)\n"
    "- model: modelul / tipul comercial (câmp D.3, sau D.2 dacă D.3 lipsește)\n"
    "- variant: varianta / versiunea, dacă e distinctă\n"
    "- year_of_manufacture: anul de fabricație ca număr întreg (ex: 2023)\n"
    "- first_registration_date: prima înmatriculare (câmp B) în format YYYY-MM-DD\n"
    "- engine_displacement_cc: capacitatea cilindrică în cmc, număr întreg (câmp P.1)\n"
    "- engine_power_kw: puterea maximă netă în kW, număr întreg (câmp P.2)\n"
    "- fuel_type: combustibilul (câmp P.3), exact una dintre valorile: "
    "petrol, diesel, electric, hybrid, plugin-hybrid, petrol-lpg, petrol-cng, hydrogen\n"
    "- seats: numărul de locuri pe scaune, număr întreg (câmp S.1)\n"
    "- max_weight_kg: masa maximă tehnic admisibilă în kg, număr întreg (câmp F.1)\n"
    "- color_exterior: culoarea (câmp R)\n"
    "- euro_standard: norma de poluare (câmp V.9), în format 'euro-6', 'euro-5' etc.\n"
    "Valorile numerice trebuie să fie numere JSON, nu string-uri. "
    "Dacă documentul nu este o CIV sau nu poți citi nimic, returnează {}."
)


@carpark_bp.route('/vin/decode-civ', methods=['POST'])
@login_required
@carpark_required
def decode_civ():
    """Extract vehicle fields from an uploaded CIV (image or PDF) via AI vision.

    Accepts multipart/form-data with a single `file` (image/* or application/pdf).
    Returns the same envelope shape as /vin/decode so the frontend can reuse the
    prefill flow: {success, data: {vehicle_fields, provider, confidence}}.
    """
    import base64
    import json
    import re

    f = request.files.get('file')
    if f is None or not getattr(f, 'filename', ''):
        return jsonify({'success': False, 'error': 'Încarcă un fișier CIV.'}), 400

    raw = f.read()
    if not raw:
        return jsonify({'success': False, 'error': 'Fișierul CIV este gol.'}), 400
    if len(raw) > _CIV_MAX_BYTES:
        return jsonify({'success': False, 'error': 'Fișierul CIV este prea mare (max 12MB).'}), 413

    mime = (f.mimetype or '').lower()
    b64 = base64.standard_b64encode(raw).decode('ascii')
    if 'pdf' in mime:
        media_block = {
            'type': 'document',
            'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': b64},
        }
    else:
        media_type = mime if mime in _CIV_ALLOWED_IMAGE_TYPES else 'image/jpeg'
        media_block = {
            'type': 'image',
            'source': {'type': 'base64', 'media_type': media_type, 'data': b64},
        }

    try:
        from ai_agent.services.llm_client import call as llm_call
        messages = [{
            'role': 'user',
            'content': [media_block, {'type': 'text', 'text': _CIV_PROMPT}],
        }]
        text = llm_call(messages, max_tokens=1024)
    except Exception as e:
        logger.warning(f'CIV extraction failed: {e}')
        return jsonify({'success': False, 'error': 'Extragerea din CIV a eșuat. Încearcă din nou.'}), 502

    match = re.search(r'\{.*\}', text or '', re.DOTALL)
    if not match:
        return jsonify({'success': False, 'error': 'Nu am putut citi datele din CIV.'}), 422
    try:
        fields = json.loads(match.group(0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Răspuns invalid de la AI.'}), 422
    if not isinstance(fields, dict):
        fields = {}

    # Drop empty values; derive HP from kW when only kW is present (1 kW ≈ 1.35962 CP).
    fields = {k: v for k, v in fields.items() if v not in (None, '', [])}
    kw = fields.get('engine_power_kw')
    if kw and not fields.get('engine_power_hp'):
        try:
            fields['engine_power_hp'] = round(float(kw) * 1.35962)
        except (ValueError, TypeError):
            pass

    return jsonify({
        'success': True,
        'data': {'vehicle_fields': fields, 'provider': 'CIV', 'confidence': 0.9},
    })


@carpark_bp.route('/vin/validate/<vin>', methods=['GET'])
@login_required
@carpark_required
def validate_vin(vin):
    """Validate VIN format without decoding (no API calls)."""
    client = _get_vin_client()
    result = client.validate(vin)
    return jsonify({'success': True, 'data': result})


@carpark_bp.route('/vin/providers', methods=['GET'])
@login_required
@carpark_required
def vin_provider_status():
    """Get status of VIN decoder providers."""
    client = _get_vin_client()
    status = client.get_provider_status()
    return jsonify({'success': True, 'data': status})
