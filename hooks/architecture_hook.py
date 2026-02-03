#!/usr/bin/env python3
"""
Architecture Hook for JARVIS

Validates architectural layer isolation and module boundaries.

Layer Hierarchy (top to bottom):
- routes.py (HTTP layer)
- services.py (business logic)
- repositories.py (data access)
- models.py (data structures)
- database.py (connection layer)

Rules:
- Routes can call Services (NOT repositories or database directly)
- Services can call Repositories
- Repositories can call Database
- No circular dependencies
- Financial modules must use proper data access patterns
"""

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

hooks_dir = Path(__file__).parent
sys.path.insert(0, str(hooks_dir))

try:
    from .master_hook import BaseHook, HookResult, HookStatus
except ImportError:
    from master_hook import BaseHook, HookResult, HookStatus


class ArchitectureHook(BaseHook):
    """
    Validates layer isolation and architectural boundaries.

    Checks:
    - Routes don't access database directly
    - Services don't import routes
    - Proper repository pattern for data access
    - No circular module dependencies
    - Financial operations use service layer
    """

    name = "Architecture"
    description = "Validates layer isolation and module boundaries"
    blocking_on_failure = False  # Changed to warning during refactoring transition

    # Layer definitions (lower number = higher in stack)
    LAYERS = {
        "routes": 1,
        "services": 2,
        "repositories": 3,
        "models": 4,
        "database": 5,
    }

    # Files to skip during transition period (legacy code being refactored)
    # Remove entries as modules are refactored to proper architecture
    TRANSITION_EXCEPTIONS = [
        "app.py",                    # Main app - Phase 5
        # "hr/events/routes.py",     # HR Events - COMPLETED (Phase 2)
        # "statements/routes.py",    # Statements - COMPLETED (Phase 3)
        # "efactura/routes.py",      # e-Factura - COMPLETED (Phase 4)
        # "auth/routes.py",          # Auth - COMPLETED (Phase 1)
    ]

    # Forbidden imports by layer
    # Note: Importing encapsulated database functions (like get_user_invoices) is allowed
    # Only raw database utilities (get_db, cursor, execute) are forbidden in routes
    FORBIDDEN_IMPORTS: Dict[str, List[str]] = {
        "routes": [
            "psycopg2",
            "sqlalchemy.orm.Session",
            "from database import get_db",      # Raw database connection
            "from database import get_cursor",  # Raw cursor access
            "from database import release_db",  # Raw connection management
            "get_db_connection",
            "execute_query",
        ],
        "services": [
            "flask.request",
            "flask.Response",
            "@app.route",
            "routes import",
        ],
    }

    # Required patterns for financial code
    FINANCIAL_PATTERNS = {
        "Transaction": {
            "must_have": ["audit", "immutable"],
            "must_not_have": ["update(", "delete("],
        },
        "Invoice": {
            "must_have": ["audit"],
            "must_not_have": ["update(amount", "delete("],
        },
        "GLPosting": {
            "must_have": ["balanced", "audit"],
            "must_not_have": ["update(", "delete("],
        },
    }

    def run(self) -> HookResult:
        """Run architecture validation."""
        details: List[str] = []
        violations: List[str] = []

        # Scan all Python files
        python_files = list(self.target_path.rglob("*.py"))
        if not python_files:
            return self._create_result(
                HookStatus.WARNING,
                "No Python files found",
                ["Ensure code is in the correct directory"],
            )

        details.append(f"Scanning {len(python_files)} Python files")

        # Check layer violations
        layer_violations = self._check_layer_violations(python_files)
        violations.extend(layer_violations)

        # Check forbidden imports
        import_violations = self._check_forbidden_imports(python_files)
        violations.extend(import_violations)

        # Check circular dependencies
        circular = self._check_circular_dependencies(python_files)
        violations.extend(circular)

        # Check financial operation patterns
        financial_violations = self._check_financial_patterns(python_files)
        violations.extend(financial_violations)

        if violations:
            return self._create_result(
                HookStatus.FAILED,
                f"Found {len(violations)} architecture violations",
                violations[:10] + (["... and more"] if len(violations) > 10 else []),
            )

        details.append("Layer isolation verified")
        details.append("No forbidden imports found")
        details.append("No circular dependencies detected")

        return self._create_result(
            HookStatus.PASSED,
            "Architecture validation passed",
            details,
        )

    def _get_layer_from_filename(self, filepath: Path) -> str:
        """Determine the layer from filename."""
        name = filepath.stem
        for layer in self.LAYERS:
            if layer in name:
                return layer
        return "unknown"

    def _is_transition_exception(self, filepath: Path) -> bool:
        """Check if file is in transition exception list."""
        filepath_str = str(filepath)
        return any(exc in filepath_str for exc in self.TRANSITION_EXCEPTIONS)

    def _check_layer_violations(self, files: List[Path]) -> List[str]:
        """Check for layer isolation violations."""
        violations: List[str] = []

        for filepath in files:
            # Skip transition exceptions
            if self._is_transition_exception(filepath):
                continue

            try:
                content = filepath.read_text()
                layer = self._get_layer_from_filename(filepath)

                if layer == "routes":
                    # Routes should not have direct SQL
                    sql_patterns = [
                        r"cursor\.execute\(",
                        r"session\.execute\(",
                        r"\.query\(",
                        r"SELECT\s+.*\s+FROM",
                        r"INSERT\s+INTO",
                        r"UPDATE\s+\w+\s+SET",
                        r"DELETE\s+FROM",
                    ]
                    for pattern in sql_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            violations.append(
                                f"{filepath.name}: Routes should not contain SQL ({pattern})"
                            )
                            break

                elif layer == "services":
                    # Services should not have Flask imports
                    flask_patterns = [
                        r"from flask import request",
                        r"from flask import Response",
                        r"@.*\.route\(",
                    ]
                    for pattern in flask_patterns:
                        if re.search(pattern, content):
                            violations.append(
                                f"{filepath.name}: Services should not import Flask web components"
                            )
                            break

            except Exception:
                continue

        return violations

    def _check_forbidden_imports(self, files: List[Path]) -> List[str]:
        """Check for forbidden imports in each layer."""
        violations: List[str] = []

        for filepath in files:
            # Skip transition exceptions
            if self._is_transition_exception(filepath):
                continue

            try:
                content = filepath.read_text()
                layer = self._get_layer_from_filename(filepath)

                if layer in self.FORBIDDEN_IMPORTS:
                    for forbidden in self.FORBIDDEN_IMPORTS[layer]:
                        if forbidden in content:
                            violations.append(
                                f"{filepath.name}: Forbidden import/usage in {layer}: {forbidden}"
                            )

            except Exception:
                continue

        return violations

    def _check_circular_dependencies(self, files: List[Path]) -> List[str]:
        """Detect circular import dependencies."""
        violations: List[str] = []

        # Build import graph
        import_graph: Dict[str, Set[str]] = defaultdict(set)

        for filepath in files:
            try:
                content = filepath.read_text()
                module_name = filepath.stem

                # Find imports
                import_matches = re.findall(
                    r"from\s+\.(\w+)\s+import|import\s+\.(\w+)",
                    content,
                )
                for match in import_matches:
                    imported = match[0] or match[1]
                    if imported:
                        import_graph[module_name].add(imported)

            except Exception:
                continue

        # Check for cycles (simple DFS)
        def has_cycle(node: str, visited: Set[str], path: Set[str]) -> bool:
            visited.add(node)
            path.add(node)

            for neighbor in import_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, path):
                        return True
                elif neighbor in path:
                    violations.append(
                        f"Circular dependency detected: {node} -> {neighbor}"
                    )
                    return True

            path.remove(node)
            return False

        visited: Set[str] = set()
        for node in import_graph:
            if node not in visited:
                has_cycle(node, visited, set())

        return violations

    def _check_financial_patterns(self, files: List[Path]) -> List[str]:
        """Check that financial entities follow required patterns."""
        violations: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()

                for entity, patterns in self.FINANCIAL_PATTERNS.items():
                    # Check if this file handles this entity
                    if entity.lower() not in filepath.name.lower():
                        continue

                    # Check for forbidden operations
                    for forbidden in patterns.get("must_not_have", []):
                        # Look for patterns like Transaction.update(
                        pattern = rf"{entity}\.{forbidden}"
                        if re.search(pattern, content):
                            violations.append(
                                f"{filepath.name}: {entity} should not use {forbidden} - use reversals instead"
                            )

                    # Check class definitions for required comments/patterns
                    if f"class {entity}" in content:
                        for required in patterns.get("must_have", []):
                            if required not in content.lower():
                                violations.append(
                                    f"{filepath.name}: {entity} should implement {required}"
                                )

            except Exception:
                continue

        return violations


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = ArchitectureHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
