"""Mapping Rule Repository — Data access for logistics_mapping_rules
("Reguli Dispo" — event -> action rules, versioned with a Simulare/Activ
mode per §3/§4.5 of the design spec).

Task 1 exposes the active-rules read path the intake pipeline (Task 2)
consumes; the rule-builder CRUD (Setări → Reguli editor) is Phase 2 of the
design spec's phasing (§6) and lands in a later task.
"""
from typing import Any, Dict, List

from core.base_repository import BaseRepository

_ACTIVE_MODE = 'Activ'


class MappingRuleRepository(BaseRepository):
    """Data access for logistics_mapping_rules."""

    def get_active_rules(self, company_id: int = None, trigger_code: str = None) -> List[Dict[str, Any]]:
        """Published, live rules (mode='Activ', is_active=TRUE) — the
        published rule map the intake pipeline (`GET /api/logistics/intake/
        mapping`, a later task) and event processor apply. Optionally scoped
        to a company and/or a single trigger_code."""
        where = ['is_active = TRUE', 'mode = %s']
        params: list = [_ACTIVE_MODE]
        if company_id is not None:
            where.append('company_id = %s')
            params.append(company_id)
        if trigger_code is not None:
            where.append('trigger_code = %s')
            params.append(trigger_code)
        return self.query_all(
            f"SELECT * FROM logistics_mapping_rules WHERE {' AND '.join(where)} ORDER BY trigger_code, rev DESC",
            tuple(params),
        )
