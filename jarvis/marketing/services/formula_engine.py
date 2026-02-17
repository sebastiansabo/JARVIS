"""Safe formula evaluator for KPI calculations.

Parses formula strings like 'spent / leads' or '(likes + comments) / impressions * 100'
and evaluates them with variable substitution. Uses Python's ast module with a strict
whitelist to prevent code injection.
"""

import ast

# Only these AST node types are allowed in formulas
_SAFE_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    # Operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
)


def extract_variables(formula):
    """Extract variable names from a formula string, in order of appearance.

    Args:
        formula: Formula string like 'spent / leads' or None.

    Returns:
        List of unique variable names, e.g. ['spent', 'leads'].
        Empty list if formula is None/empty.
    """
    if not formula or not formula.strip():
        return []
    try:
        tree = ast.parse(formula.strip(), mode='eval')
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in names:
            names.append(node.id)
    return names


def validate(formula):
    """Validate a formula string for safety and syntax.

    Args:
        formula: Formula string to validate.

    Returns:
        Tuple of (is_valid: bool, error: str | None, variables: list[str]).
    """
    if not formula or not formula.strip():
        return True, None, []

    try:
        tree = ast.parse(formula.strip(), mode='eval')
    except SyntaxError as e:
        return False, f'Syntax error: {e}', []

    # Check all nodes are safe
    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_NODES):
            return False, f'Unsafe construct: {type(node).__name__}', []

    variables = extract_variables(formula)

    # Test evaluation with dummy values
    try:
        dummy = {v: 1.0 for v in variables}
        evaluate(formula, dummy)
    except ZeroDivisionError:
        pass  # Division by zero is valid syntax, just bad data
    except Exception as e:
        return False, str(e), variables

    return True, None, variables


def evaluate(formula, variables):
    """Safely evaluate a formula with variable values.

    Args:
        formula: Formula string, e.g. 'spent / leads'.
        variables: Dict mapping variable names to float values,
                   e.g. {'spent': 1000.0, 'leads': 50.0}.

    Returns:
        Float result of the formula evaluation.

    Raises:
        ValueError: If formula is empty, contains unsafe constructs,
                    or references undefined variables.
        ZeroDivisionError: If formula divides by zero.
    """
    if not formula or not formula.strip():
        raise ValueError('Empty formula')

    formula = formula.strip()
    tree = ast.parse(formula, mode='eval')

    # Validate all nodes are safe
    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_NODES):
            raise ValueError(f'Unsafe formula construct: {type(node).__name__}')

    # Validate all variables are defined
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in variables:
            raise ValueError(f'Undefined variable: {node.id}')

    code = compile(tree, '<formula>', 'eval')
    result = eval(code, {'__builtins__': {}}, variables)

    if not isinstance(result, (int, float)):
        raise ValueError(f'Formula did not produce a number: {type(result).__name__}')

    return float(result)
