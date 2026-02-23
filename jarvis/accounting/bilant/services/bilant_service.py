"""Bilant Service — orchestrates upload → engine → persist."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from ..repositories import BilantTemplateRepository, BilantGenerationRepository
from ..formula_engine import process_bilant_from_template, calculate_metrics_from_config
from ..excel_handler import read_balanta_from_excel, read_bilant_sheet_for_import, generate_output_excel

logger = logging.getLogger('jarvis.bilant.service')


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
