"""Talon / CIV document OCR extraction via AI vision.

Generalises the CIV-only extraction so a single upload can be either a Romanian
talon (Certificat de Înmatriculare) or a CIV (Cartea de Identitate a
Vehiculului): the model auto-detects which document it is and extracts the
fields that document carries. Pure parsing/normalisation lives here so it can be
tested without the HTTP layer; the route is a thin wrapper.
"""
import base64
import json
import re

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
MAX_BYTES = 12 * 1024 * 1024  # 12 MB

# Documents share most field codes, so one prompt covers both; the model tags
# which document it read via `document_type` so the UI can label the source.
DOCUMENT_PROMPT = (
    "Ești un extractor de date dintr-un document auto românesc: fie un TALON "
    "(Certificat de Înmatriculare), fie o CIV (Cartea de Identitate a Vehiculului). "
    "Identifică tipul documentului și citește câmpurile. Returnează DOAR un obiect JSON "
    "valid (fără text suplimentar, fără Markdown, fără blocuri ```), cu următoarele chei. "
    "Omite orice cheie pe care nu o găsești clar în document; nu inventa valori.\n"
    "- document_type: exact una dintre valorile: talon, civ\n"
    "- registration_number: numărul de înmatriculare (câmp A, doar pe talon), ex: B123ABC\n"
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
    "Dacă documentul nu este un talon sau o CIV sau nu poți citi nimic, returnează {}."
)

_VALID_DOCUMENT_TYPES = {'talon', 'civ'}


def _llm_call(messages, max_tokens=1024):
    """Call the shared AI vision client. Imported lazily to avoid import-time env issues."""
    from ai_agent.services.llm_client import call as llm_call
    return llm_call(messages, max_tokens=max_tokens)


def parse_document_response(text):
    """Parse an AI-vision response into (vehicle_fields, document_type).

    `document_type` is normalised to 'talon' | 'civ' | 'unknown' and stripped
    out of the returned vehicle fields. Empty values are dropped and horsepower
    is derived from kW when only kW is present.
    """
    match = re.search(r'\{.*\}', text or '', re.DOTALL)
    if not match:
        return {}, 'unknown'
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return {}, 'unknown'
    if not isinstance(parsed, dict):
        return {}, 'unknown'

    raw_type = str(parsed.pop('document_type', '') or '').strip().lower()
    document_type = raw_type if raw_type in _VALID_DOCUMENT_TYPES else 'unknown'

    fields = {k: v for k, v in parsed.items() if v not in (None, '', [])}

    kw = fields.get('engine_power_kw')
    if kw and not fields.get('engine_power_hp'):
        try:
            fields['engine_power_hp'] = round(float(kw) * 1.35962)
        except (ValueError, TypeError):
            pass

    return fields, document_type


def build_media_block(raw, mime):
    """Build the Anthropic multimodal content block for an image or PDF upload."""
    mime = (mime or '').lower()
    b64 = base64.standard_b64encode(raw).decode('ascii')
    if 'pdf' in mime:
        return {
            'type': 'document',
            'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': b64},
        }
    media_type = mime if mime in ALLOWED_IMAGE_TYPES else 'image/jpeg'
    return {
        'type': 'image',
        'source': {'type': 'base64', 'media_type': media_type, 'data': b64},
    }


def extract_vehicle_document(raw, mime):
    """Run AI vision over an uploaded talon/CIV and return (vehicle_fields, document_type)."""
    media_block = build_media_block(raw, mime)
    messages = [{
        'role': 'user',
        'content': [media_block, {'type': 'text', 'text': DOCUMENT_PROMPT}],
    }]
    text = _llm_call(messages, max_tokens=1024)
    return parse_document_response(text)
