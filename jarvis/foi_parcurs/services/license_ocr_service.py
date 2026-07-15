"""OCR extraction of Romanian driving-license fields via Claude vision.

Reuses the shared LLM client (`ai_agent.services.llm_client.call`), which wraps
ClaudeProvider with an automatic provider-fallback chain — the same path the
invoice parser uses for image extraction. Model `claude-sonnet-4-6` is the
codebase's validated vision model for this provider.
"""
import json
import logging
import re

from ai_agent.services.llm_client import call

logger = logging.getLogger('jarvis.foi_parcurs.license_ocr')

_MODEL = 'claude-sonnet-4-6'

# The fields we ask Claude to read off the license, mapped to the mobile form.
_PROMPT = """Ești un asistent care extrage date de pe un permis de conducere românesc dintr-o poză.

Întoarce DOAR un obiect JSON valid cu exact aceste chei (folosește null dacă un câmp nu e lizibil):

{
  "last_name": "Numele de familie (câmpul 1)",
  "first_name": "Prenumele (câmpul 2)",
  "full_name": "Nume și prenume complet (last_name + first_name)",
  "cnp": "CNP-ul / numărul personal (13 cifre) dacă e vizibil",
  "license_number": "Seria și numărul permisului (câmpul 5)",
  "birth_date": "Data nașterii în format YYYY-MM-DD (câmpul 3)",
  "expiry_date": "Data expirării în format YYYY-MM-DD (câmpul 4b)",
  "address": "Adresa/domiciliul (câmpul 8) dacă e vizibil, doar strada și numărul",
  "city": "Localitatea din adresă dacă e vizibilă",
  "county": "Județul din adresă dacă e vizibil"
}

Reguli:
- Datele calendaristice se normalizează la YYYY-MM-DD.
- CNP-ul are 13 cifre, fără spații.
- Nu inventa date; dacă nu poți citi un câmp, pune null.
- Întoarce DOAR JSON-ul, fără alt text."""

_FIELDS = (
    'last_name', 'first_name', 'full_name', 'cnp', 'license_number',
    'birth_date', 'expiry_date', 'address', 'city', 'county',
)


def _parse_data_url(image: str):
    """Split a `data:image/...;base64,xxx` URL into (base64_data, media_type).

    Accepts a bare base64 string too (assumes image/jpeg).
    """
    m = re.match(r'^data:(image/[a-zA-Z.+-]+);base64,(.*)$', image or '', re.DOTALL)
    if m:
        return m.group(2), m.group(1)
    return (image or ''), 'image/jpeg'


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model's response text."""
    if not text:
        return {}
    # Strip code fences if present, then grab the outermost {...}.
    match = re.search(r'\{.*\}', text, re.DOTALL)
    raw = match.group(0) if match else text
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning('License OCR: could not parse JSON from model response')
        return {}


def extract_license_data(image: str) -> dict:
    """Extract structured fields from a driving-license image (data URL or base64).

    Returns a dict with the `_FIELDS` keys (values may be None). Raises ValueError
    on empty input; lets provider/network errors propagate to the caller.
    """
    data, media_type = _parse_data_url(image)
    if not data:
        raise ValueError('image is required')

    messages = [{
        'role': 'user',
        'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': data}},
            {'type': 'text', 'text': _PROMPT},
        ],
    }]

    response_text = call(messages, model=_MODEL, max_tokens=1024)
    result = _extract_json(response_text)

    # Normalize: keep only known keys, coerce empty strings to None.
    out = {}
    for key in _FIELDS:
        val = result.get(key)
        if isinstance(val, str):
            val = val.strip() or None
        out[key] = val
    return out
