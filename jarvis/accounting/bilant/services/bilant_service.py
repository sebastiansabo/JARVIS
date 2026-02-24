"""Bilant Service — orchestrates upload → engine → persist."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ..repositories import BilantTemplateRepository, BilantGenerationRepository
from ..formula_engine import process_bilant_from_template, calculate_metrics_from_config
from ..excel_handler import read_balanta_from_excel, read_bilant_sheet_for_import, generate_output_excel, generate_anaf_excel
from ..pdf_handler import generate_bilant_pdf
from ..anaf_parser import parse_anaf_pdf, generate_row_mapping, fill_anaf_pdf, generate_anaf_xml, generate_anaf_txt, _nr_rd_to_anaf

logger = logging.getLogger('jarvis.bilant.service')

FINANCIAL_ANALYST_SYSTEM_PROMPT = """You are a senior financial analyst specializing in Romanian accounting standards (OMFP 1802/2014).
You analyze bilant (balance sheet) data and provide clear, actionable insights for business owners.

Your analysis MUST be in Romanian language and use Romanian number formatting (1.234,56).
Use markdown formatting with headers, bullet points, and bold for emphasis.

Structure your response with these sections:
## Stare Financiara Generala
A 2-3 sentence overview of the company's financial health.

## Puncte Forte
- List 2-4 key financial strengths based on the data

## Zone de Risc
- List 2-4 risk areas or concerns, if any exist

## Recomandari
- List 2-3 specific, actionable recommendations

## Indicatori Cheie
Brief commentary on the most notable financial ratios and what they mean for this company.

Keep the total response under 800 words. Be specific — reference actual numbers from the data."""


@dataclass
class ServiceResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 200


class BilantService:
    def __init__(self):
        self.template_repo = BilantTemplateRepository()
        self.generation_repo = BilantGenerationRepository()

    def process_upload(self, file_bytes, filename, template_id, company_id,
                       period_label, period_date, user_id):
        """Upload Balanta Excel → process against template → persist results + metrics."""
        try:
            # Validate template
            template = self.template_repo.get_by_id(template_id)
            if not template:
                return ServiceResult(success=False, error='Template not found', status_code=404)

            # Read Balanta
            try:
                df_balanta = read_balanta_from_excel(file_bytes)
            except ValueError as e:
                return ServiceResult(success=False, error=str(e), status_code=400)

            # Load template rows and metric configs
            template_rows = self.template_repo.get_rows(template_id)
            if not template_rows:
                return ServiceResult(success=False, error='Template has no rows', status_code=400)
            metric_configs = self.template_repo.get_metric_configs(template_id)

            # Create generation record
            generation_id = self.generation_repo.create(
                template_id=template_id,
                company_id=company_id,
                generated_by=user_id,
                period_label=period_label,
                period_date=period_date,
                original_filename=filename,
            )

            # Run formula engine
            bilant_values, results = process_bilant_from_template(df_balanta, template_rows)

            # Calculate metrics
            metrics = {}
            if metric_configs:
                metrics = calculate_metrics_from_config(bilant_values, metric_configs)

            # Persist results and metrics
            self.generation_repo.save_results(generation_id, results)
            if metrics:
                self.generation_repo.save_metrics(generation_id, metrics)

            # Mark completed
            self.generation_repo.update_status(generation_id, 'completed')

            logger.info(f'Bilant generation {generation_id} completed: {len(results)} rows, template={template_id}')
            return ServiceResult(success=True, data={
                'generation_id': generation_id,
                'row_count': len(results),
                'summary': metrics.get('summary', {}),
            })

        except Exception as e:
            logger.exception(f'Bilant processing failed: {e}')
            if 'generation_id' in dir():
                self.generation_repo.update_status(generation_id, 'error', str(e))
            return ServiceResult(success=False, error=str(e), status_code=500)

    def get_generation_detail(self, generation_id):
        """Get full generation with results and metrics."""
        generation = self.generation_repo.get_by_id(generation_id)
        if not generation:
            return ServiceResult(success=False, error='Generation not found', status_code=404)
        results = self.generation_repo.get_results(generation_id)
        metrics_rows = self.generation_repo.get_metrics(generation_id)

        # Reconstruct metrics dict from DB rows
        metrics = {'summary': {}, 'ratios': {}, 'structure': {'assets': [], 'liabilities': []}}
        for m in metrics_rows:
            if m['metric_group'] == 'summary':
                metrics['summary'][m['metric_key']] = float(m['value']) if m['value'] is not None else 0
            elif m['metric_group'] == 'ratio':
                metrics['ratios'][m['metric_key']] = {
                    'value': float(m['value']) if m['value'] is not None else None,
                    'label': m['metric_label'],
                    'interpretation': m.get('interpretation'),
                }
            elif m['metric_group'] == 'structure_assets':
                metrics['structure']['assets'].append({
                    'name': m['metric_label'],
                    'value': float(m['value']) if m['value'] is not None else 0,
                    'percent': float(m['percent']) if m.get('percent') is not None else 0,
                })
            elif m['metric_group'] == 'structure_liabilities':
                metrics['structure']['liabilities'].append({
                    'name': m['metric_label'],
                    'value': float(m['value']) if m['value'] is not None else 0,
                    'percent': float(m['percent']) if m.get('percent') is not None else 0,
                })

        # Load template metric configs for dynamic rendering
        metric_configs = self.template_repo.get_metric_configs(generation['template_id'])

        return ServiceResult(success=True, data={
            'generation': generation,
            'results': results,
            'metrics': metrics,
            'metric_configs': metric_configs,
            'ai_analysis': generation.get('ai_analysis'),
        })

    def generate_excel(self, generation_id):
        """Generate downloadable Excel from persisted generation."""
        detail = self.get_generation_detail(generation_id)
        if not detail.success:
            return detail
        generation = detail.data['generation']
        results = detail.data['results']
        metrics = detail.data['metrics']
        try:
            output = generate_output_excel(generation, results, metrics)
            return ServiceResult(success=True, data=output)
        except Exception as e:
            logger.exception(f'Excel generation failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def import_template_from_excel(self, file_bytes, name, company_id, user_id):
        """Import template from uploaded Excel with Bilant sheet."""
        try:
            rows = read_bilant_sheet_for_import(file_bytes)
            if not rows:
                return ServiceResult(success=False, error='No rows found in Bilant sheet', status_code=400)

            template_id = self.template_repo.create(
                name=name, created_by=user_id, company_id=company_id,
                description=f'Imported from Excel ({len(rows)} rows)'
            )
            self.template_repo.bulk_add_rows(template_id, rows)
            logger.info(f'Template {template_id} imported: {len(rows)} rows')
            return ServiceResult(success=True, data={'template_id': template_id, 'row_count': len(rows)})
        except ValueError as e:
            return ServiceResult(success=False, error=str(e), status_code=400)
        except Exception as e:
            logger.exception(f'Template import failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def compare_generations(self, generation_ids):
        """Compare metrics across multiple generations."""
        if len(generation_ids) < 2:
            return ServiceResult(success=False, error='At least 2 generations required', status_code=400)
        metrics = self.generation_repo.get_metrics_for_comparison(generation_ids)
        generations = []
        for gid in generation_ids:
            gen = self.generation_repo.get_by_id(gid)
            if gen:
                generations.append(gen)
        return ServiceResult(success=True, data={
            'generations': generations,
            'metrics': metrics,
        })

    def import_from_anaf_pdf(self, pdf_bytes, name, company_id, user_id):
        """Parse ANAF PDF → create template with rows + metric configs."""
        try:
            parsed = parse_anaf_pdf(pdf_bytes)
            rows = parsed['rows']
            if not rows:
                return ServiceResult(success=False, error='No rows found in PDF', status_code=400)

            form_type = parsed['form_type']
            template_id = self.template_repo.create(
                name=name,
                created_by=user_id,
                company_id=company_id,
                description=f'Imported from ANAF {form_type} PDF ({len(rows)} rows)',
            )
            self.template_repo.bulk_add_rows(template_id, rows)

            # Add standard metric configs for the new template
            from ..fixtures import get_default_metric_configs
            for cfg in get_default_metric_configs():
                self.template_repo.set_metric_config(template_id=template_id, **cfg)

            logger.info(f'ANAF template {template_id} imported: {len(rows)} rows from {form_type}')
            return ServiceResult(success=True, data={
                'template_id': template_id,
                'row_count': len(rows),
                'form_type': form_type,
            })
        except ValueError as e:
            return ServiceResult(success=False, error=str(e), status_code=400)
        except Exception as e:
            logger.exception(f'ANAF PDF import failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def _get_prior_results(self, company_id, current_generation_id):
        """Find most recent completed generation for same company (prior period).

        Returns dict {nr_rd: value} or None.
        """
        prior = self.generation_repo.get_prior_generation(company_id, current_generation_id)
        if not prior:
            return None
        prior_results_list = self.generation_repo.get_results(prior['id'])
        return {r['nr_rd']: r.get('value', 0) for r in prior_results_list if r.get('nr_rd')}

    def generate_pdf(self, generation_id):
        """Generate ANAF-styled PDF from persisted generation."""
        detail = self.get_generation_detail(generation_id)
        if not detail.success:
            return detail
        generation = detail.data['generation']
        results = detail.data['results']
        try:
            prior = self._get_prior_results(generation['company_id'], generation_id)
            output = generate_bilant_pdf(generation, results, prior_results=prior)
            return ServiceResult(success=True, data=output)
        except Exception as e:
            logger.exception(f'PDF generation failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def generate_filled_pdf(self, generation_id):
        """Generate filled ANAF XFA PDF — original template with computed values in C1/C2 fields."""
        detail = self.get_generation_detail(generation_id)
        if not detail.success:
            return detail
        generation = detail.data['generation']
        results = detail.data['results']
        try:
            # Build nr_rd → value map
            values = {}
            for r in results:
                nr = r.get('nr_rd')
                if nr:
                    values[nr] = r.get('value', 0) or 0
            prior = self._get_prior_results(generation['company_id'], generation_id)
            output = fill_anaf_pdf(values, prior_values=prior)
            return ServiceResult(success=True, data=output)
        except Exception as e:
            logger.exception(f'Filled PDF generation failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def _build_values_and_prior(self, generation_id):
        """Shared helper: load generation, build nr_rd→value maps and company info."""
        detail = self.get_generation_detail(generation_id)
        if not detail.success:
            return detail
        generation = detail.data['generation']
        results = detail.data['results']
        values = {}
        for r in results:
            nr = r.get('nr_rd')
            if nr:
                values[nr] = r.get('value', 0) or 0
        prior = self._get_prior_results(generation['company_id'], generation_id)
        return ServiceResult(success=True, data={
            'generation': generation, 'results': results,
            'values': values, 'prior': prior,
        })

    def generate_anaf_import_xml(self, generation_id):
        """Generate ANAF XML import file (form1 > F10L > Table1 structure)."""
        loaded = self._build_values_and_prior(generation_id)
        if not loaded.success:
            return loaded
        gen = loaded.data['generation']
        values = loaded.data['values']
        prior = loaded.data['prior']
        try:
            xml_bytes = generate_anaf_xml(
                values, prior_values=prior,
                company_name=gen.get('company_name', ''),
                cif='',  # CIF not stored on generation
                period_date=gen.get('period_date'),
                form='F10L',
            )
            return ServiceResult(success=True, data=xml_bytes)
        except Exception as e:
            logger.exception(f'ANAF XML generation failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def generate_anaf_import_txt(self, generation_id):
        """Generate ANAF balanta.txt import file."""
        loaded = self._build_values_and_prior(generation_id)
        if not loaded.success:
            return loaded
        gen = loaded.data['generation']
        values = loaded.data['values']
        prior = loaded.data['prior']
        try:
            txt_content = generate_anaf_txt(
                values, prior_values=prior,
                company_name=gen.get('company_name', ''),
                cif='',
                form='F10L',
            )
            return ServiceResult(success=True, data=txt_content)
        except Exception as e:
            logger.exception(f'ANAF TXT generation failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def generate_ai_analysis(self, generation_id, force=False, model_id=None):
        """Generate AI financial analysis for a bilant generation.

        Returns cached analysis if available (unless force=True).
        model_id: optional specific model config ID to use instead of global default.
        """
        generation = self.generation_repo.get_by_id(generation_id)
        if not generation:
            return ServiceResult(success=False, error='Generation not found', status_code=404)

        # Return cached if available and not forcing regeneration
        if generation.get('ai_analysis') and not force:
            return ServiceResult(success=True, data=generation['ai_analysis'])

        # Load full detail for analysis
        detail = self.get_generation_detail(generation_id)
        if not detail.success:
            return detail

        try:
            from ai_agent.repositories import ModelConfigRepository
            from ai_agent.providers import ClaudeProvider, OpenAIProvider, GroqProvider, GeminiProvider

            model_repo = ModelConfigRepository()
            model_config = None
            if model_id:
                model_config = model_repo.get_by_id(model_id)
            if not model_config:
                model_config = model_repo.get_default()
            if not model_config:
                return ServiceResult(success=False, error='No AI model configured', status_code=400)

            providers = {
                'claude': ClaudeProvider,
                'openai': OpenAIProvider,
                'groq': GroqProvider,
                'gemini': GeminiProvider,
            }
            provider_cls = providers.get(model_config.provider.value)
            if not provider_cls:
                return ServiceResult(success=False, error=f'Unsupported provider: {model_config.provider.value}', status_code=400)

            provider = provider_cls()
            prompt = self._build_analysis_prompt(detail.data)

            response = provider.generate(
                model_name=model_config.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=2048,
                temperature=0.3,
                system=FINANCIAL_ANALYST_SYSTEM_PROMPT,
            )

            analysis = {
                'content': response.content,
                'model': response.model,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'input_tokens': response.input_tokens,
                'output_tokens': response.output_tokens,
            }

            # Persist to DB
            self.generation_repo.update_ai_analysis(generation_id, analysis)

            logger.info(f'AI analysis generated for generation {generation_id} ({response.input_tokens}+{response.output_tokens} tokens)')
            return ServiceResult(success=True, data=analysis)

        except Exception as e:
            logger.exception(f'AI analysis failed for generation {generation_id}: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def clear_ai_analysis(self, generation_id):
        """Clear cached AI analysis to allow regeneration."""
        generation = self.generation_repo.get_by_id(generation_id)
        if not generation:
            return ServiceResult(success=False, error='Generation not found', status_code=404)
        self.generation_repo.update_ai_analysis(generation_id, None)
        return ServiceResult(success=True)

    def _build_analysis_prompt(self, detail_data):
        """Build the user prompt with all financial data for AI analysis."""
        gen = detail_data['generation']
        metrics = detail_data['metrics']

        parts = [
            f"Analizeaza bilantul pentru compania **{gen.get('company_name', 'N/A')}**, "
            f"perioada **{gen.get('period_label', 'N/A')}**.",
            "",
            "### Date financiare:",
        ]

        # Summary
        summary = metrics.get('summary', {})
        if summary:
            parts.append("\n**Sumar:**")
            for key, val in summary.items():
                label = key.replace('_', ' ').title()
                parts.append(f"- {label}: {val:,.2f} RON")

        # Ratios
        ratios = metrics.get('ratios', {})
        if ratios:
            parts.append("\n**Indicatori financiari:**")
            for key, raw in ratios.items():
                if isinstance(raw, dict) and 'value' in raw:
                    val = raw['value']
                    label = raw.get('label', key.replace('_', ' ').title())
                    interp = raw.get('interpretation', '')
                    if val is not None:
                        parts.append(f"- {label}: {val:.4f}" + (f" ({interp})" if interp else ""))
                elif isinstance(raw, (int, float)):
                    parts.append(f"- {key.replace('_', ' ').title()}: {raw:.4f}")

        # Structure
        structure = metrics.get('structure', {})
        for side, label in [('assets', 'Active'), ('liabilities', 'Pasive')]:
            items = structure.get(side, [])
            if items:
                parts.append(f"\n**Structura {label}:**")
                for item in items:
                    parts.append(f"- {item['name']}: {item['value']:,.2f} RON ({item['percent']}%)")

        return "\n".join(parts)

    def generate_anaf_excel(self, generation_id):
        """Generate ANAF-format Excel with F10 field codes."""
        detail = self.get_generation_detail(generation_id)
        if not detail.success:
            return detail
        generation = detail.data['generation']
        results = detail.data['results']
        try:
            # Build row mapping from results
            row_mapping = {}
            for r in results:
                nr = r.get('nr_rd')
                if not nr:
                    continue
                anaf_code = _nr_rd_to_anaf(nr)
                padded = anaf_code.zfill(3)
                for c in ('1', '2'):
                    row_mapping[f'F10_{padded}{c}'] = {'row': nr, 'col': f'C{c}'}

            prior = self._get_prior_results(generation['company_id'], generation_id)
            output = generate_anaf_excel(generation, results, row_mapping=row_mapping, prior_results=prior)
            return ServiceResult(success=True, data=output)
        except Exception as e:
            logger.exception(f'ANAF Excel generation failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)
