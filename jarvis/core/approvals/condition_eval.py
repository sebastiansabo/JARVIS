"""Condition evaluator for JSONB conditions against context dicts.

Used for both flow trigger_conditions and step skip_conditions.

Example:
    conditions = {"budget_gte": 5000, "project_type": "campaign"}
    context = {"budget": 12000, "project_type": "campaign"}
    ConditionEvaluator.evaluate(conditions, context) → True

Operators (key suffix):
    _gte, _gt, _lte, _lt   — numeric comparison
    _eq, _neq               — equality
    _in, _not_in            — membership in list
    _exists                 — key presence (value is bool)
    _contains               — substring match
    (no suffix)             — exact equality

All conditions are AND'd together.
"""

import logging

logger = logging.getLogger('jarvis.core.approvals.conditions')

# Operator suffixes in order of longest-first to avoid partial matches
_OPERATORS = [
    ('_not_in', 'not_in'),
    ('_contains', 'contains'),
    ('_exists', 'exists'),
    ('_gte', 'gte'),
    ('_gt', 'gt'),
    ('_lte', 'lte'),
    ('_lt', 'lt'),
    ('_neq', 'neq'),
    ('_eq', 'eq'),
    ('_in', 'in'),
]


class ConditionEvaluator:

    @staticmethod
    def evaluate(conditions: dict, context: dict) -> bool:
        """Evaluate all conditions against context. Returns True if ALL match."""
        if not conditions:
            return True

        for key, expected in conditions.items():
            field, op = ConditionEvaluator._parse_key(key)

            if op == 'exists':
                if expected and field not in context:
                    return False
                if not expected and field in context:
                    return False
                continue

            actual = context.get(field)

            if op == 'eq':
                if actual != expected:
                    return False
            elif op == 'neq':
                if actual == expected:
                    return False
            elif op in ('gte', 'gt', 'lte', 'lt'):
                if actual is None:
                    return False
                try:
                    a = float(actual)
                    e = float(expected)
                except (ValueError, TypeError):
                    return False
                if op == 'gte' and not (a >= e):
                    return False
                if op == 'gt' and not (a > e):
                    return False
                if op == 'lte' and not (a <= e):
                    return False
                if op == 'lt' and not (a < e):
                    return False
            elif op == 'in':
                if not isinstance(expected, list):
                    return False
                if actual not in expected:
                    return False
            elif op == 'not_in':
                if not isinstance(expected, list):
                    return False
                if actual in expected:
                    return False
            elif op == 'contains':
                if actual is None or expected is None:
                    return False
                if str(expected) not in str(actual):
                    return False
            else:
                # No operator — exact equality
                if actual != expected:
                    return False

        return True

    @staticmethod
    def _parse_key(key: str) -> tuple:
        """Parse 'budget_gte' into ('budget', 'gte'). Returns (key, None) for bare keys."""
        for suffix, op_name in _OPERATORS:
            if key.endswith(suffix):
                field = key[:-len(suffix)]
                if field:  # Ensure we actually have a field name
                    return field, op_name
        return key, None
