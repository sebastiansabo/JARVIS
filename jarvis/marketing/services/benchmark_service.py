"""Generate industry benchmark data for KPI definitions using LLM."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger('jarvis.marketing.benchmark_service')

SYSTEM_PROMPT = """You are a marketing analytics expert specializing in the Romanian automotive industry \
(car dealerships, auto parts, service centers, aftermarket — specifically the Romanian market). \
Generate industry benchmark data for marketing KPIs based on 2025-2026 Romanian automotive industry standards.

Return ONLY valid JSON (no markdown fences, no explanation) with this exact structure:
{
  "industry": "auto_dealership_romania",
  "segments": [
    {"name": "segment name", "average": 0.0, "good": 0.0, "excellent": 0.0, "source": "data source"}
  ]
}

Rules:
- Include 2-3 segments relevant to the Romanian car dealership industry
- Common segments: Vânzări Vehicule (Vehicle Sales), Piese & Accesorii (Parts & Accessories), Service/Aftermarket
- Values must be numeric (not strings) and reflect Romanian market conditions (RON currency where applicable)
- "good" should be better than "average", "excellent" better than "good"
- For "lower is better" KPIs (like CPC, CPL), lower values = better performance
- Source should reference the data origin (e.g. "Google Ads Romania auto industry 2025", "Meta Ads Romania 2025")
- Consider Romanian market specifics: lower CPCs than Western Europe, regional ad costs, local competition levels
- Generate text fields (segment names, sources) in the same language as the user's request
"""


def generate_benchmarks(kpi_name, kpi_slug, unit, direction, formula=None, description=None):
    """Call LLM to generate industry benchmark data for a KPI definition.

    Returns dict with industry, generated_at, segments[] or raises on failure.
    """
    from ai_agent.repositories import ModelConfigRepository
    from ai_agent.providers import ClaudeProvider, OpenAIProvider, GroqProvider, GeminiProvider

    # Get default model
    model_repo = ModelConfigRepository()
    model_config = model_repo.get_default()
    if not model_config:
        raise ValueError('No default AI model configured. Set one in Settings > AI Agent.')

    # Get provider
    providers = {
        'claude': ClaudeProvider,
        'openai': OpenAIProvider,
        'groq': GroqProvider,
        'gemini': GeminiProvider,
    }
    provider_cls = providers.get(model_config.provider.value)
    if not provider_cls:
        raise ValueError(f'Unknown provider: {model_config.provider.value}')
    provider = provider_cls()

    # Build user prompt
    user_prompt = f"""Generate benchmark data for this KPI:
Name: {kpi_name} ({kpi_slug})
Unit: {unit}
Direction: {direction} is better
Formula: {formula or 'N/A (raw metric)'}
Description: {description or 'N/A'}

Include 2-3 relevant segments for the Romanian car dealership industry (vehicle sales, parts & accessories, service where applicable).
Values should reflect 2025-2026 Romanian automotive market standards and best practices.
Use RON for currency-based KPIs."""

    messages = [{'role': 'user', 'content': user_prompt}]

    logger.info(f'Generating benchmarks for {kpi_slug} via {model_config.provider.value}/{model_config.model_name}')

    try:
        benchmarks = provider.generate_structured(
            model_name=model_config.model_name,
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
            system=SYSTEM_PROMPT,
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f'Failed to parse benchmark JSON: {e}')
        raise ValueError(f'AI returned invalid JSON: {e}')

    # Validate structure
    if 'segments' not in benchmarks or not isinstance(benchmarks['segments'], list):
        raise ValueError('AI response missing "segments" array')

    for seg in benchmarks['segments']:
        for field in ('name', 'average', 'good', 'excellent'):
            if field not in seg:
                raise ValueError(f'Segment missing required field: {field}')

    benchmarks['generated_at'] = datetime.now(timezone.utc).isoformat()
    return benchmarks
