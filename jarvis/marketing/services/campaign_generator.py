"""AI-powered campaign generator — creates a complete marketing project from a brief prompt."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger('jarvis.marketing.campaign_generator')

SYSTEM_PROMPT = """You are a marketing strategist for an automotive dealership group in Romania.
Given a campaign brief, generate a complete marketing project structure.

IMPORTANT: ALL text output (name, description, objective, target_audience, OKR titles, KPI notes,
budget line descriptions) MUST be written in Romanian. Only channel codes and KPI slugs stay in English.

Return ONLY valid JSON (no markdown fences) with this exact structure:
{
  "name": "Numele Campaniei",
  "description": "2-3 paragrafe cu descrierea proiectului / brief-ul campaniei",
  "project_type": "campaign|always_on|event|launch|branding|research",
  "objective": "Declarația obiectivului strategic",
  "target_audience": "Descrierea detaliată a publicului țintă",
  "channel_mix": ["meta_ads", "google_ads", ...],
  "budget_lines": [
    {
      "channel": "meta_ads",
      "description": "Descriere scurtă a bugetului alocat",
      "planned_amount": 10000,
      "period_type": "campaign"
    }
  ],
  "kpis": [
    {
      "kpi_slug": "cpa",
      "target_value": 150,
      "weight": 60,
      "aggregation": "latest",
      "notes": "Notă scurtă despre de ce acest target"
    }
  ],
  "objectives": [
    {
      "title": "Titlu obiectiv",
      "description": "Descriere obiectiv",
      "key_results": [
        {
          "title": "Titlu rezultat cheie",
          "target_value": 500000,
          "unit": "number",
          "linked_kpi_slug": "impressions"
        }
      ]
    }
  ]
}

AVAILABLE CHANNELS (use these exact codes):
- meta_ads (Meta / Facebook & Instagram Ads)
- google_ads (Google Ads — Search, Display, YouTube)
- radio (Radio advertising)
- print (Print media)
- ooh (Out-of-Home / Outdoor — billboards, transit)
- influencer (Influencer partnerships)
- email (Email marketing)
- sms (SMS campaigns)
- events (Event sponsorships / activations)
- other (Other channels)

AVAILABLE KPI SLUGS (use these exact slugs):
{kpi_catalog}

Rules:
- Budget lines must sum to roughly the total budget provided
- Distribute budget intelligently across channels based on campaign goals
- KPI targets should be realistic for the Romanian automotive market
- Generate 2-4 KPIs that match the campaign channels and goals
- Generate 1-3 OKRs with 2-4 key results each
- Key results can reference KPIs via linked_kpi_slug (use slug from the catalog)
- All monetary values in the campaign's currency
- Be specific and actionable, not generic
- ALL generated text MUST be in Romanian (description, objective, target_audience, OKR titles/descriptions, KPI notes, budget descriptions)
- When a vehicle model/product is provided, automatically determine the target audience based on:
  - The vehicle segment (SUV, sedan, hatchback, electric, luxury, etc.)
  - Typical buyer demographics for that model in Romania (age, income, lifestyle)
  - Geographic targeting if area/counties are specified
- When geographic area is provided, incorporate it into the campaign name, description, target_audience, and budget descriptions (e.g. geo-targeted ads for those counties)"""


def generate_campaign(prompt, total_budget, currency, start_date, end_date,
                      company_id, owner_id, kpi_definitions,
                      responsible_ids=None, stakeholder_ids=None,
                      extra_context=None):
    """Generate a complete campaign structure from a prompt using the default AI model.

    Args:
        prompt: User's campaign brief / description
        total_budget: Total campaign budget
        currency: Currency code (RON, EUR, etc.)
        start_date: Campaign start date (YYYY-MM-DD)
        end_date: Campaign end date (YYYY-MM-DD)
        company_id: Primary company ID
        owner_id: Project owner user ID
        kpi_definitions: List of dicts with KPI catalog (id, name, slug, unit, direction, formula)
        responsible_ids: Optional list of user IDs for team members
        stakeholder_ids: Optional list of user IDs for stakeholders/observers
        extra_context: Optional dict with additional context

    Returns:
        dict with generated campaign data ready to be persisted
    """
    from ai_agent.repositories import ModelConfigRepository
    from ai_agent.providers import ClaudeProvider, OpenAIProvider, GroqProvider, GeminiProvider

    # Get default model
    model_repo = ModelConfigRepository()
    model_config = model_repo.get_default()
    if not model_config:
        raise ValueError('No default AI model configured. Set one in Settings > AI Agent.')

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

    # Build KPI catalog for the system prompt
    kpi_lines = []
    for d in kpi_definitions:
        line = f"- {d['slug']}: {d['name']} ({d['unit']}, {d['direction']} is better)"
        if d.get('formula'):
            line += f" — formula: {d['formula']}"
        kpi_lines.append(line)
    kpi_catalog = '\n'.join(kpi_lines)
    system = SYSTEM_PROMPT.replace('{kpi_catalog}', kpi_catalog)

    # Build user prompt
    user_prompt = f"""Generate a complete marketing campaign from this brief:

BRIEF: {prompt}

PARAMETERS:
- Total budget: {total_budget} {currency}
- Timeline: {start_date} to {end_date}
- Currency: {currency}
"""
    if extra_context:
        if extra_context.get('product'):
            user_prompt += f"- Product/Vehicle: {extra_context['product']}\n"
        if extra_context.get('scope'):
            user_prompt += f"- Scope/Goals: {extra_context['scope']}\n"
        if extra_context.get('area'):
            user_prompt += f"- Geographic Area: {extra_context['area']}\n"

    user_prompt += "\nGenerate the full campaign structure in Romanian with budget allocation, KPIs, and OKRs."
    user_prompt += "\nAuto-detect target audience based on the vehicle model/product and geographic area."

    messages = [{'role': 'user', 'content': user_prompt}]

    logger.info(f'Generating campaign via {model_config.provider.value}/{model_config.model_name}')

    try:
        result = provider.generate_structured(
            model_name=model_config.model_name,
            messages=messages,
            max_tokens=2048,
            temperature=0.4,
            system=system,
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f'Failed to parse campaign JSON: {e}')
        raise ValueError(f'AI returned invalid response: {e}')

    # Validate required fields
    for field in ('name', 'description', 'channel_mix', 'budget_lines', 'kpis', 'objectives'):
        if field not in result:
            raise ValueError(f'AI response missing required field: {field}')

    return result


def persist_campaign(ai_result, company_id, owner_id, currency, start_date, end_date,
                     total_budget, kpi_definitions, responsible_ids=None, stakeholder_ids=None):
    """Persist the AI-generated campaign into the database.

    Creates: project, budget lines, KPIs, OKRs, and team members.
    Returns the new project ID.
    """
    from marketing.repositories import (
        ProjectRepository, BudgetRepository, MemberRepository,
        ActivityRepository, KpiRepository, OkrRepository,
    )

    project_repo = ProjectRepository()
    budget_repo = BudgetRepository()
    member_repo = MemberRepository()
    activity_repo = ActivityRepository()
    kpi_repo = KpiRepository()
    okr_repo = OkrRepository()

    # Build slug-to-id map for KPI definitions
    slug_to_id = {d['slug']: d['id'] for d in kpi_definitions}

    # 1. Create the project
    project_id = project_repo.create(
        name=ai_result.get('name', 'AI Generated Campaign'),
        company_id=company_id,
        owner_id=owner_id,
        created_by=owner_id,
        description=ai_result.get('description'),
        project_type=ai_result.get('project_type', 'campaign'),
        channel_mix=ai_result.get('channel_mix', []),
        start_date=start_date,
        end_date=end_date,
        total_budget=total_budget,
        currency=currency,
        objective=ai_result.get('objective'),
        target_audience=ai_result.get('target_audience'),
        brief={'ai_generated': True, 'prompt': ai_result.get('description', '')},
    )

    # 2. Add owner as member
    member_repo.add(project_id, owner_id, 'owner', owner_id)

    # 3. Add responsibles as specialists
    for uid in (responsible_ids or []):
        if uid != owner_id:
            try:
                member_repo.add(project_id, uid, 'specialist', owner_id)
            except Exception:
                pass  # duplicate or invalid user

    # 4. Add stakeholders as observers
    for uid in (stakeholder_ids or []):
        if uid != owner_id:
            try:
                member_repo.add(project_id, uid, 'stakeholder', owner_id)
            except Exception:
                pass

    # 5. Create budget lines
    for bl in ai_result.get('budget_lines', []):
        try:
            budget_repo.create_line(
                project_id=project_id,
                channel=bl.get('channel', 'other'),
                description=bl.get('description'),
                planned_amount=bl.get('planned_amount', 0),
                currency=currency,
                period_type=bl.get('period_type', 'campaign'),
                period_start=start_date,
                period_end=end_date,
            )
        except Exception as e:
            logger.warning(f'Failed to create budget line {bl}: {e}')

    # 6. Create KPIs — map slugs to definition IDs
    kpi_slug_to_project_kpi = {}
    for kpi in ai_result.get('kpis', []):
        slug = kpi.get('kpi_slug', '')
        def_id = slug_to_id.get(slug)
        if not def_id:
            logger.warning(f'Unknown KPI slug: {slug}, skipping')
            continue
        try:
            pk_id = kpi_repo.add_project_kpi(
                project_id=project_id,
                kpi_definition_id=def_id,
                target_value=kpi.get('target_value'),
                weight=kpi.get('weight', 50),
                currency=currency,
                aggregation=kpi.get('aggregation', 'latest'),
                notes=kpi.get('notes'),
            )
            kpi_slug_to_project_kpi[slug] = pk_id
        except Exception as e:
            logger.warning(f'Failed to create KPI {slug}: {e}')

    # 7. Create OKRs with key results
    for obj_data in ai_result.get('objectives', []):
        try:
            obj_id = okr_repo.create_objective(
                project_id=project_id,
                title=obj_data.get('title', 'Objective'),
                created_by=owner_id,
                description=obj_data.get('description'),
            )
            for kr_data in obj_data.get('key_results', []):
                linked_kpi_id = None
                linked_slug = kr_data.get('linked_kpi_slug')
                if linked_slug and linked_slug in kpi_slug_to_project_kpi:
                    linked_kpi_id = kpi_slug_to_project_kpi[linked_slug]
                okr_repo.create_key_result(
                    objective_id=obj_id,
                    title=kr_data.get('title', 'Key Result'),
                    target_value=kr_data.get('target_value', 100),
                    unit=kr_data.get('unit', 'number'),
                    linked_kpi_id=linked_kpi_id,
                )
        except Exception as e:
            logger.warning(f'Failed to create OKR: {e}')

    # 8. Log activity
    activity_repo.log(project_id, 'created', actor_id=owner_id,
                      details={'source': 'ai_generator', 'name': ai_result.get('name', '')})

    return project_id
