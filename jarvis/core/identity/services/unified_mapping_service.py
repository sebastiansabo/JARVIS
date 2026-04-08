"""Unified mapping service — orchestrates Sincron + BioStar employee mapping.

Delegates all writes to the existing per-connector repositories so that
SincronRepository and BioStarRepository remain the single source of truth for
their own tables. Only the read-side unified view and the auto-map pipeline
live here.
"""

import logging

from core.connectors.sincron.repositories.sincron_repository import SincronRepository
from core.connectors.biostar.repositories.biostar_repository import BioStarRepository

from ..repositories.unified_mapping_repository import UnifiedMappingRepository


logger = logging.getLogger('jarvis.identity.service')


class UnifiedMappingService:
    """Cross-connector orchestration for employee mapping."""

    def __init__(self):
        self.repo = UnifiedMappingRepository()
        self.sincron_repo = SincronRepository()
        self.biostar_repo = BioStarRepository()

    # ── Read-side ──

    def get_unified_view(self):
        """Return per-user unified rows, orphan lists, and aggregate stats."""
        users = self.repo.get_unified_view()
        return {
            'users': users,
            'orphan_sincron': self.repo.get_orphan_sincron(),
            'orphan_biostar': self.repo.get_orphan_biostar(),
            'stats': self.repo.get_stats() or {},
        }

    def get_stats(self):
        """Return aggregate stats only (cheap)."""
        return self.repo.get_stats() or {}

    def get_jarvis_users(self):
        """Active JARVIS users for manual mapping dropdowns."""
        return self.repo.get_jarvis_users()

    # ── Auto-map pipeline ──

    def auto_map_all(self):
        """Run the full 5-step pipeline.

        Steps:
            1. Sincron by CNP       (confidence 100)
            2. Sincron by name      (confidence 85 / 80)
            3. BioStar by CNP       (confidence 100)
            4. BioStar by email     (confidence 100)
            5. BioStar by name      (confidence 90)
            6. BioStar cross-verify (confidence 95, via Sincron)

        Returns a dict of per-step counts.
        """
        results = {}
        try:
            results['sincron_cnp'] = self.sincron_repo.auto_map_by_cnp() or 0
        except Exception as exc:
            logger.exception('sincron_cnp auto-map failed')
            results['sincron_cnp_error'] = str(exc)
            results['sincron_cnp'] = 0

        try:
            results['sincron_name'] = self.sincron_repo.auto_map_by_name() or 0
        except Exception as exc:
            logger.exception('sincron_name auto-map failed')
            results['sincron_name_error'] = str(exc)
            results['sincron_name'] = 0

        try:
            results['biostar_cnp'] = self.biostar_repo.auto_map_by_cnp() or 0
        except Exception as exc:
            logger.exception('biostar_cnp auto-map failed')
            results['biostar_cnp_error'] = str(exc)
            results['biostar_cnp'] = 0

        try:
            results['biostar_email'] = self.biostar_repo.auto_map_by_email() or 0
        except Exception as exc:
            logger.exception('biostar_email auto-map failed')
            results['biostar_email_error'] = str(exc)
            results['biostar_email'] = 0

        try:
            results['biostar_name'] = self.biostar_repo.auto_map_by_name() or 0
        except Exception as exc:
            logger.exception('biostar_name auto-map failed')
            results['biostar_name_error'] = str(exc)
            results['biostar_name'] = 0

        try:
            results['biostar_cross'] = self.biostar_repo.auto_map_cross_verified() or 0
        except Exception as exc:
            logger.exception('biostar_cross auto-map failed')
            results['biostar_cross_error'] = str(exc)
            results['biostar_cross'] = 0

        results['total_mapped'] = (
            results.get('sincron_cnp', 0)
            + results.get('sincron_name', 0)
            + results.get('biostar_cnp', 0)
            + results.get('biostar_email', 0)
            + results.get('biostar_name', 0)
            + results.get('biostar_cross', 0)
        )
        return results

    # ── Manual mapping ──

    def set_mapping(self, user_id, source, external_id, company_name=None):
        """Manually set a mapping. Delegates to the right repo.

        Args:
            user_id: JARVIS users.id
            source: 'sincron' or 'biostar'
            external_id: sincron_employee_id or biostar_user_id
            company_name: required for Sincron (part of composite PK)
        """
        if source == 'sincron':
            if not company_name:
                raise ValueError('company_name is required for Sincron mappings')
            self.sincron_repo.update_mapping(external_id, company_name, user_id, method='manual')
            return {'source': 'sincron', 'external_id': external_id,
                    'company_name': company_name, 'user_id': user_id}
        if source == 'biostar':
            self.biostar_repo.update_mapping(external_id, user_id, method='manual', confidence=100.0)
            return {'source': 'biostar', 'external_id': external_id, 'user_id': user_id}
        raise ValueError(f"Unknown source: {source!r}")

    def remove_mapping(self, source, external_id, company_name=None):
        """Remove a mapping. Delegates to the right repo."""
        if source == 'sincron':
            if not company_name:
                raise ValueError('company_name is required for Sincron mappings')
            self.sincron_repo.remove_mapping(external_id, company_name)
            return {'source': 'sincron', 'external_id': external_id,
                    'company_name': company_name}
        if source == 'biostar':
            self.biostar_repo.remove_mapping(external_id)
            return {'source': 'biostar', 'external_id': external_id}
        raise ValueError(f"Unknown source: {source!r}")
