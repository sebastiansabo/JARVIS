"""AI services for Field Sales — note structuring and visit briefing.

Uses Anthropic API (claude-sonnet-4-5-20250514) for:
  - Structuring raw visit notes into JSON
  - Generating pre-visit briefings from client 360 context
"""

import json
import logging
import os

logger = logging.getLogger('jarvis.field_sales.ai')

_MODEL = 'claude-sonnet-4-5-20250514'


def _get_client():
    """Create an Anthropic client instance."""
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))


def structure_visit_note(raw_note, client_context=None):
    """Structure a raw visit note into a JSON object using AI.

    Args:
        raw_note: Free-text note from KAM after visit.
        client_context: Optional dict with client info for better structuring.

    Returns:
        dict: Structured note with standardized fields, or error dict on failure.
    """
    if not raw_note or not raw_note.strip():
        return {'error': 'empty_note', 'raw': ''}

    context_block = ''
    if client_context:
        context_block = f"""
Client context:
- Name: {client_context.get('display_name', 'N/A')}
- Type: {client_context.get('client_type', 'N/A')}
- Fleet size: {client_context.get('fleet_size', 'N/A')}
- Last purchase: {client_context.get('last_purchase', 'N/A')}
"""

    system_prompt = """You are a CRM assistant for a car dealership group. Your job is to structure raw visit notes from Key Account Managers (KAMs) into a clean JSON format.

Extract and categorize information from the raw note into this JSON structure:
{
  "summary": "1-2 sentence summary of the visit",
  "sentiment": "positive|neutral|negative",
  "topics_discussed": ["list of main topics"],
  "client_needs": ["identified needs or interests"],
  "vehicles_of_interest": [
    {"brand": "...", "model": "...", "type": "new|used|service", "notes": "..."}
  ],
  "action_items": [
    {"task": "description", "owner": "kam|client|other", "deadline": "if mentioned or null"}
  ],
  "fleet_updates": {
    "vehicles_mentioned": ["any vehicles discussed"],
    "replacement_candidates": ["vehicles client wants to replace"],
    "service_issues": ["any service problems mentioned"]
  },
  "next_steps": "recommended next action",
  "follow_up_date": "YYYY-MM-DD if mentioned, else null",
  "deal_probability": "high|medium|low|none",
  "notes": "any additional context not fitting above categories"
}

Rules:
- Always return valid JSON and nothing else.
- If a field has no data, use null for scalars, [] for arrays, {} for objects.
- Detect language automatically but always output field names in English.
- Preserve important details and numbers mentioned.
- Be concise but comprehensive."""

    user_message = f"""{context_block}
Raw visit note:
{raw_note}

Structure this note into the JSON format specified. Return ONLY the JSON object."""

    try:
        client = _get_client()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=2000,
            system=system_prompt,
            messages=[
                {'role': 'user', 'content': user_message}
            ],
        )

        response_text = response.content[0].text.strip()

        # Try to extract JSON from response (handle markdown code blocks)
        json_text = response_text
        if json_text.startswith('```'):
            # Remove markdown code block
            lines = json_text.split('\n')
            # Remove first line (```json or ```) and last line (```)
            if lines[-1].strip() == '```':
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            json_text = '\n'.join(lines)

        structured = json.loads(json_text)
        return structured

    except json.JSONDecodeError:
        logger.warning('AI note structuring: JSON parse failed for visit note')
        return {'error': 'parse_failed', 'raw': response_text}
    except Exception as e:
        logger.error('AI note structuring failed: %s', str(e))
        return {'error': 'ai_failed', 'raw': str(e)}


def generate_visit_brief(client_360):
    """Generate a pre-visit briefing from client 360 data.

    Args:
        client_360: dict with keys: profile, fleet, purchases, visit_history,
                    renewal_candidates, etc.

    Returns:
        str: Briefing text, or empty string on error.
    """
    if not client_360:
        return ''

    # Build context from 360 data
    profile = client_360.get('profile') or {}
    fleet = client_360.get('fleet') or []
    purchases = client_360.get('purchases') or []
    visit_history = client_360.get('visit_history') or []
    renewal_candidates = client_360.get('renewal_candidates') or []
    fiscal = client_360.get('fiscal') or {}

    context_parts = []

    # Profile section
    context_parts.append(f"Client: {profile.get('display_name', 'Unknown')}")
    context_parts.append(f"Type: {profile.get('client_type', 'N/A')}")
    context_parts.append(f"Priority: {profile.get('priority', 'N/A')}")
    context_parts.append(f"Renewal score: {profile.get('renewal_score', 0)}/100")
    context_parts.append(f"Fleet size: {profile.get('fleet_size', 0)} vehicles")

    if profile.get('industry'):
        context_parts.append(f"Industry: {profile['industry']}")
    if profile.get('estimated_annual_value'):
        context_parts.append(f"Est. annual value: EUR {profile['estimated_annual_value']}")

    # Fleet details
    if fleet:
        context_parts.append(f"\nFleet ({len(fleet)} vehicles):")
        for v in fleet[:10]:  # Show top 10
            line = f"  - {v.get('vehicle_make', '?')} {v.get('vehicle_model', '?')} ({v.get('vehicle_year', '?')})"
            if v.get('financing_expiry'):
                line += f" | Financing expires: {v['financing_expiry']}"
            if v.get('warranty_expiry'):
                line += f" | Warranty expires: {v['warranty_expiry']}"
            if v.get('status') != 'active':
                line += f" | Status: {v['status']}"
            context_parts.append(line)

    # Renewal candidates
    if renewal_candidates:
        context_parts.append(f"\nRenewal candidates ({len(renewal_candidates)}):")
        for v in renewal_candidates[:5]:
            line = f"  - {v.get('vehicle_make', '?')} {v.get('vehicle_model', '?')} ({v.get('vehicle_year', '?')})"
            if v.get('renewal_reason'):
                line += f" — {v['renewal_reason']}"
            context_parts.append(line)

    # Purchase history
    if purchases:
        context_parts.append(f"\nRecent purchases ({len(purchases)} shown):")
        for p in purchases[:5]:
            line = f"  - {p.get('brand', '?')} {p.get('model_name', '?')}"
            if p.get('contract_date'):
                line += f" ({p['contract_date']})"
            if p.get('sale_price_net'):
                line += f" | EUR {p['sale_price_net']}"
            context_parts.append(line)

    # Visit history
    if visit_history:
        context_parts.append(f"\nRecent visits ({len(visit_history)} shown):")
        for vis in visit_history[:5]:
            line = f"  - {vis.get('planned_date', '?')} | {vis.get('visit_type', '?')} | {vis.get('status', '?')}"
            if vis.get('outcome'):
                line += f" | Outcome: {vis['outcome']}"
            context_parts.append(line)

    # Fiscal data
    if fiscal:
        context_parts.append("\nFiscal data (ANAF):")
        if fiscal.get('denumire'):
            context_parts.append(f"  Company: {fiscal['denumire']}")
        if fiscal.get('adresa'):
            context_parts.append(f"  Address: {fiscal['adresa']}")
        if fiscal.get('scpTVA') is not None:
            context_parts.append(f"  VAT payer: {'Yes' if fiscal.get('scpTVA') else 'No'}")
        if fiscal.get('statusInactivi') is not None:
            context_parts.append(f"  Inactive: {'Yes' if fiscal.get('statusInactivi') else 'No'}")

    full_context = '\n'.join(context_parts)

    system_prompt = """You are a KAM (Key Account Manager) briefing assistant for an automotive dealership group. Generate a concise, actionable pre-visit briefing.

Structure your briefing as:

1. CLIENT SNAPSHOT (2-3 lines: who they are, relationship status)
2. KEY OPPORTUNITIES (bullet points: renewal candidates, upsell potential, fleet needs)
3. WATCH OUT FOR (any risks: inactive fiscal status, blacklist, overdue payments, complaints)
4. TALKING POINTS (3-5 suggested topics for the visit)
5. RECOMMENDED APPROACH (1-2 sentences: strategic advice for this visit)

Rules:
- Be direct and practical — this is read on mobile before a visit.
- Focus on actionable intelligence, not data recitation.
- If fleet has vehicles with expiring financing/warranty, highlight as opportunities.
- If renewal score is high (>60), emphasize urgency.
- Keep under 300 words.
- Write in English."""

    user_message = f"""Generate a pre-visit briefing for this client:

{full_context}"""

    try:
        client = _get_client()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1000,
            system=system_prompt,
            messages=[
                {'role': 'user', 'content': user_message}
            ],
        )

        return response.content[0].text.strip()

    except Exception as e:
        logger.error('AI brief generation failed: %s', str(e))
        return ''
