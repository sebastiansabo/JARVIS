"""Auto-tag rule evaluation service.

Evaluates auto-tag rules against entity data and applies matching tags.
"""
import re
import logging
from decimal import Decimal

from database import get_db, get_cursor, release_db
from .repositories import AutoTagRepository, TagRepository

logger = logging.getLogger('jarvis.core.tags.auto_tag_service')

# Fields available per entity type (for frontend dropdown)
ENTITY_FIELDS = {
    'invoice': ['supplier', 'invoice_number', 'invoice_value', 'currency', 'status',
                 'payment_status', 'comment', 'invoice_template'],
    'efactura_invoice': ['partner_name', 'partner_cif', 'invoice_number', 'total_amount',
                         'currency', 'direction', 'status'],
    'transaction': ['vendor_name', 'description', 'amount', 'currency', 'status',
                     'company_name', 'transaction_type'],
    'event': ['name', 'company', 'brand', 'description'],
}

OPERATORS = {
    'eq': lambda v, c: str(v).lower() == str(c).lower(),
    'neq': lambda v, c: str(v).lower() != str(c).lower(),
    'contains': lambda v, c: str(c).lower() in str(v).lower(),
    'not_contains': lambda v, c: str(c).lower() not in str(v).lower(),
    'starts_with': lambda v, c: str(v).lower().startswith(str(c).lower()),
    'ends_with': lambda v, c: str(v).lower().endswith(str(c).lower()),
    'gt': lambda v, c: _to_decimal(v) > _to_decimal(c),
    'gte': lambda v, c: _to_decimal(v) >= _to_decimal(c),
    'lt': lambda v, c: _to_decimal(v) < _to_decimal(c),
    'lte': lambda v, c: _to_decimal(v) <= _to_decimal(c),
    'regex': lambda v, c: bool(re.search(c, str(v), re.IGNORECASE)),
}


def _to_decimal(val) -> Decimal:
    """Safely convert to Decimal for numeric comparisons."""
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(0)


class AutoTagService:
    def __init__(self):
        self._rule_repo = AutoTagRepository()
        self._tag_repo = TagRepository()

    def evaluate_rules_for_entity(self, entity_type: str, entity_id: int,
                                   user_id: int = None) -> int:
        """Evaluate all active rules for an entity. Returns count of tags applied."""
        rules = self._rule_repo.get_rules(entity_type=entity_type, active_only=True)
        if not rules:
            return 0

        entity_data = self._fetch_entity(entity_type, entity_id)
        if not entity_data:
            return 0

        count = 0
        for rule in rules:
            if not rule.get('run_on_create', True):
                continue
            conditions = rule.get('conditions', [])
            if isinstance(conditions, str):
                import json
                conditions = json.loads(conditions)
            if self._check_conditions(entity_data, conditions, rule.get('match_mode', 'all')):
                tagged_by = user_id or rule.get('created_by')
                if tagged_by:
                    added = self._tag_repo.add_entity_tag(
                        rule['tag_id'], entity_type, entity_id, tagged_by
                    )
                    if added:
                        count += 1
        return count

    def run_rule(self, rule_id: int, user_id: int) -> dict:
        """Run a rule against all entities of its type. Returns {matched, tagged}."""
        rule = self._rule_repo.get_rule(rule_id)
        if not rule:
            return {'matched': 0, 'tagged': 0}

        conditions = rule.get('conditions', [])
        if isinstance(conditions, str):
            import json
            conditions = json.loads(conditions)

        entities = self._fetch_all_entities(rule['entity_type'])
        matched = 0
        tagged = 0
        for entity in entities:
            if self._check_conditions(entity, conditions, rule.get('match_mode', 'all')):
                matched += 1
                added = self._tag_repo.add_entity_tag(
                    rule['tag_id'], rule['entity_type'], entity['id'], user_id
                )
                if added:
                    tagged += 1
        return {'matched': matched, 'tagged': tagged}

    def _check_conditions(self, entity_data: dict, conditions: list, match_mode: str = 'all') -> bool:
        """Evaluate conditions. match_mode='all' (AND) or 'any' (OR)."""
        if not conditions:
            return True
        for cond in conditions:
            field = cond.get('field', '')
            operator = cond.get('operator', 'contains')
            value = cond.get('value', '')
            entity_value = entity_data.get(field)
            if entity_value is None:
                entity_value = ''
            op_fn = OPERATORS.get(operator)
            if not op_fn:
                continue
            try:
                result = op_fn(entity_value, value)
            except Exception:
                result = False
            if match_mode == 'any' and result:
                return True
            if match_mode != 'any' and not result:
                return False
        # 'all': all passed → True; 'any': none matched → False
        return match_mode != 'any'

    def _fetch_entity(self, entity_type: str, entity_id: int) -> dict | None:
        """Fetch a single entity by type and ID."""
        table = self._entity_table(entity_type)
        if not table:
            return None
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(f'SELECT * FROM {table} WHERE id = %s', (entity_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def _fetch_all_entities(self, entity_type: str) -> list:
        """Fetch all entities of a given type (for "Run Now")."""
        table = self._entity_table(entity_type)
        if not table:
            return []
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            extra = ''
            if entity_type == 'invoice':
                extra = ' WHERE deleted_at IS NULL'
            elif entity_type == 'efactura_invoice':
                extra = ' WHERE deleted_at IS NULL'
            cursor.execute(f'SELECT * FROM {table}{extra}')
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    @staticmethod
    def _entity_table(entity_type: str) -> str | None:
        """Map entity type to table name."""
        return {
            'invoice': 'invoices',
            'efactura_invoice': 'efactura_invoices',
            'transaction': 'bank_statement_transactions',
            'event': 'hr.events',
        }.get(entity_type)
