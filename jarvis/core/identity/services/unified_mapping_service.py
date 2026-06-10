"""Unified mapping service — orchestrates Sincron + BioStar + Connecteam employee mapping.

Delegates all writes to the existing per-connector repositories so that
SincronRepository, BioStarRepository, and ConnecteamRepository remain the
single source of truth for their own tables. Only the read-side unified view
and the auto-map pipeline live here.
"""

import logging

from core.connectors.sincron.repositories.sincron_repository import SincronRepository
from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
from core.connectors.connecteam.repositories.connecteam_repository import ConnecteamRepository
from core.auth.repositories.user_repository import UserRepository

from ..repositories.unified_mapping_repository import UnifiedMappingRepository


logger = logging.getLogger('jarvis.identity.service')


class UnifiedMappingService:
    """Cross-connector orchestration for employee mapping."""

    def __init__(self):
        self.repo = UnifiedMappingRepository()
        self.sincron_repo = SincronRepository()
        self.biostar_repo = BioStarRepository()
        self.connecteam_repo = ConnecteamRepository()
        self.user_repo = UserRepository()

    # ── Read-side ──

    def get_unified_view(self):
        """Return per-user unified rows, orphan lists, and aggregate stats."""
        users = self.repo.get_unified_view()
        return {
            'users': users,
            'orphan_sincron': self.repo.get_orphan_sincron(),
            'orphan_biostar': self.repo.get_orphan_biostar(),
            'orphan_connecteam': self.repo.get_orphan_connecteam(),
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

        try:
            results['connecteam_name'] = self.connecteam_repo.auto_map_by_name() or 0
        except Exception as exc:
            logger.exception('connecteam_name auto-map failed')
            results['connecteam_name_error'] = str(exc)
            results['connecteam_name'] = 0

        results['total_mapped'] = (
            results.get('sincron_cnp', 0)
            + results.get('sincron_name', 0)
            + results.get('biostar_cnp', 0)
            + results.get('biostar_email', 0)
            + results.get('biostar_name', 0)
            + results.get('biostar_cross', 0)
            + results.get('connecteam_name', 0)
        )

        # Propagate CNP from Sincron → users (canonical source of truth)
        try:
            results['cnp_propagated'] = self.sincron_repo.propagate_cnp_to_users() or 0
        except Exception as exc:
            logger.exception('CNP propagation failed')
            results['cnp_propagated_error'] = str(exc)
            results['cnp_propagated'] = 0

        return results

    # ── Manual mapping ──

    def set_mapping(self, user_id, source, external_id, company_name=None):
        """Manually set a mapping. Delegates to the right repo.

        Args:
            user_id: JARVIS users.id
            source: 'sincron', 'biostar', or 'connecteam'
            external_id: sincron_employee_id, biostar_user_id, or connecteam_user_id
            company_name: required for Sincron (part of composite PK)
        """
        if source == 'sincron':
            if not company_name:
                raise ValueError('company_name is required for Sincron mappings')
            self.sincron_repo.update_mapping(external_id, company_name, user_id, method='manual')
            # Propagate CNP from Sincron → users (canonical source)
            try:
                self.sincron_repo.propagate_cnp_to_users()
            except Exception:
                logger.exception('CNP propagation failed after manual Sincron mapping')
            return {'source': 'sincron', 'external_id': external_id,
                    'company_name': company_name, 'user_id': user_id}
        if source == 'biostar':
            self.biostar_repo.update_mapping(external_id, user_id, method='manual', confidence=100.0)
            return {'source': 'biostar', 'external_id': external_id, 'user_id': user_id}
        if source == 'connecteam':
            self.connecteam_repo.update_user_mapping(int(external_id), user_id, method='manual')
            self.connecteam_repo.update_submissions_mapping(int(external_id), user_id)
            return {'source': 'connecteam', 'external_id': external_id, 'user_id': user_id}
        raise ValueError(f"Unknown source: {source!r}")

    def create_user_from_sincron(self, sincron_employee_id, company_name):
        """Create a new JARVIS user from a Sincron employee and auto-map them.

        Returns dict with user_id, name, company on success.
        Raises ValueError if employee not found or already mapped.
        """
        emp = self.sincron_repo.get_employee(sincron_employee_id, company_name)
        if not emp:
            raise ValueError('Sincron employee not found')
        if emp.get('mapped_jarvis_user_id'):
            raise ValueError('Sincron employee is already mapped to a JARVIS user')

        prenume = (emp.get('prenume') or '').strip()
        nume = (emp.get('nume') or '').strip()
        name = f'{prenume} {nume}'.strip().title()
        if not name:
            raise ValueError('Sincron employee has no name')

        # Try to find existing JARVIS user by CNP first (avoids unique constraint clash)
        cnp = emp.get('cnp')
        if cnp:
            existing_by_cnp = self.user_repo.get_by_cnp(cnp)
            if existing_by_cnp:
                user_id = existing_by_cnp['id']
                logger.info(f'Found existing JARVIS user #{user_id} by CNP '
                            f'for Sincron {sincron_employee_id}@{company_name}')
                self.sincron_repo.update_mapping(
                    sincron_employee_id, company_name, user_id, method='auto_created')
                return {'user_id': user_id, 'name': existing_by_cnp['name'],
                        'company': company_name}

        # Generate placeholder email (users.email is NOT NULL)
        import re
        slug = re.sub(r'[^a-z0-9]+', '.', name.lower()).strip('.')
        email = f'{slug}@placeholder.jarvis'

        # Reuse existing unmapped user with same placeholder email (idempotent)
        existing = self.user_repo.get_by_email(email)
        if existing:
            user_id = existing['id']
            logger.info(f'Reusing existing JARVIS user #{user_id} ({name}) '
                        f'for Sincron {sincron_employee_id}@{company_name}')
        else:
            user_id = self.user_repo.save(name=name, email=email, company=company_name)
            logger.info(f'Created JARVIS user #{user_id} ({name}) from Sincron '
                        f'{sincron_employee_id}@{company_name}')

        # Set CNP and contract start date if available
        update_kwargs = {}
        if cnp:
            update_kwargs['cnp'] = cnp
        if emp.get('data_incepere_contract'):
            update_kwargs['contract_work_date'] = emp['data_incepere_contract']
        if update_kwargs:
            self.user_repo.update(user_id, **update_kwargs)

        self.sincron_repo.update_mapping(
            sincron_employee_id, company_name, user_id, method='auto_created')

        return {'user_id': user_id, 'name': name, 'company': company_name}

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
        if source == 'connecteam':
            self.connecteam_repo.remove_user_mapping(int(external_id))
            return {'source': 'connecteam', 'external_id': external_id}
        raise ValueError(f"Unknown source: {source!r}")
