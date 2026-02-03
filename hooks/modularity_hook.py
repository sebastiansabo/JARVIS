#!/usr/bin/env python3
"""
Modularity Hook for JARVIS

Validates module ownership and prevents duplicate entity definitions.

Core Financial Entities and Their Owners:
- Company: jarvis_core
- Transaction: jarvis_core (IMMUTABLE)
- Invoice: jarvis_core (IMMUTABLE amounts)
- Vendor: jarvis_core
- Account: accounting_core
- GLPosting: accounting_core (IMMUTABLE)
- BankAccount: jarvis_core
- JournalEntry: accounting_core

Rules:
- Each entity defined in EXACTLY one module
- Other modules use ForeignKey references
- ForeignKeys must use on_delete=PROTECT for financial entities
- No duplicate table names
"""

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

hooks_dir = Path(__file__).parent
sys.path.insert(0, str(hooks_dir))

try:
    from .master_hook import BaseHook, HookResult, HookStatus
except ImportError:
    from master_hook import BaseHook, HookResult, HookStatus


class ModularityHook(BaseHook):
    """
    Validates module ownership and duplicate entity detection.

    Checks:
    - No duplicate entity definitions
    - Correct module ownership
    - Proper ForeignKey usage (on_delete=PROTECT)
    - No cross-module entity creation
    """

    name = "Modularity"
    description = "Validates module ownership and duplicate entity detection"
    blocking_on_failure = True

    # Entity ownership map
    ENTITY_OWNERS: Dict[str, str] = {
        # Core entities
        "Company": "core",
        "Transaction": "core",
        "Invoice": "invoicing",
        "Vendor": "core",
        "BankAccount": "core",
        "User": "auth",

        # Accounting entities
        "Account": "accounting",
        "GLPosting": "accounting",
        "JournalEntry": "accounting",
        "Reconciliation": "reconciliation",

        # HR entities
        "Employee": "hr",
        "Event": "hr",
        "EventBonus": "hr",

        # Statements
        "BankStatement": "statements",
        "VendorMapping": "statements",

        # E-Factura
        "EfacturaInvoice": "efactura",
    }

    # Immutable entities - must not have update/delete operations
    IMMUTABLE_ENTITIES = {
        "Transaction",
        "GLPosting",
        "AuditLog",
    }

    # Entities that require on_delete=PROTECT
    PROTECTED_FK_ENTITIES = {
        "Transaction",
        "Invoice",
        "GLPosting",
        "JournalEntry",
        "Account",
        "Company",
        "Vendor",
    }

    def run(self) -> HookResult:
        """Run modularity validation."""
        details: List[str] = []
        violations: List[str] = []

        python_files = list(self.target_path.rglob("*.py"))
        if not python_files:
            return self._create_result(
                HookStatus.WARNING,
                "No Python files found",
                [],
            )

        details.append(f"Scanning {len(python_files)} Python files")

        # Find all entity definitions
        entity_definitions = self._find_entity_definitions(python_files)

        # Check for duplicates
        duplicate_violations = self._check_duplicates(entity_definitions)
        violations.extend(duplicate_violations)

        # Check ownership
        ownership_violations = self._check_ownership(entity_definitions)
        violations.extend(ownership_violations)

        # Check ForeignKey usage
        fk_violations = self._check_foreign_keys(python_files)
        violations.extend(fk_violations)

        # Check for cross-module entity creation
        creation_violations = self._check_cross_module_creation(python_files)
        violations.extend(creation_violations)

        if violations:
            return self._create_result(
                HookStatus.FAILED,
                f"Found {len(violations)} modularity violations",
                violations[:10] + (["... and more"] if len(violations) > 10 else []),
            )

        details.append(f"Validated {len(entity_definitions)} entity definitions")
        details.append("No duplicate entities found")
        details.append("Module ownership verified")

        return self._create_result(
            HookStatus.PASSED,
            "Modularity validation passed",
            details,
        )

    def _find_entity_definitions(self, files: List[Path]) -> Dict[str, List[Tuple[Path, str]]]:
        """
        Find all entity class definitions.

        Returns:
            Dict mapping entity name to list of (file, module) tuples
        """
        entities: Dict[str, List[Tuple[Path, str]]] = defaultdict(list)

        for filepath in files:
            try:
                content = filepath.read_text()

                # Find class definitions that look like models
                class_matches = re.findall(
                    r"class\s+(\w+)\s*\([^)]*(?:Base|Model|db\.Model)[^)]*\)",
                    content,
                )

                for class_name in class_matches:
                    # Determine module from file path
                    module = self._get_module_from_path(filepath)
                    entities[class_name].append((filepath, module))

            except Exception:
                continue

        return entities

    def _get_module_from_path(self, filepath: Path) -> str:
        """Extract module name from file path."""
        parts = filepath.parts
        for part in parts:
            if part in ["core", "accounting", "hr", "statements", "auth", "efactura", "invoicing", "reconciliation"]:
                return part
        return "unknown"

    def _check_duplicates(self, entities: Dict[str, List[Tuple[Path, str]]]) -> List[str]:
        """Check for duplicate entity definitions."""
        violations: List[str] = []

        for entity_name, locations in entities.items():
            if len(locations) > 1:
                files = [str(loc[0].name) for loc in locations]
                violations.append(
                    f"Duplicate entity '{entity_name}' defined in: {', '.join(files)}"
                )

        return violations

    def _check_ownership(self, entities: Dict[str, List[Tuple[Path, str]]]) -> List[str]:
        """Check that entities are defined in their owning module."""
        violations: List[str] = []

        for entity_name, locations in entities.items():
            if entity_name in self.ENTITY_OWNERS:
                expected_owner = self.ENTITY_OWNERS[entity_name]

                for filepath, module in locations:
                    if module != expected_owner and module != "unknown":
                        violations.append(
                            f"Entity '{entity_name}' defined in '{module}' but should be in '{expected_owner}'"
                        )

        return violations

    def _check_foreign_keys(self, files: List[Path]) -> List[str]:
        """Check ForeignKey usage for protected entities."""
        violations: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()

                # Find ForeignKey definitions
                fk_matches = re.findall(
                    r"ForeignKey\s*\(\s*['\"]?(\w+)['\"]?(?:\.id)?['\"]?\s*(?:,\s*([^)]+))?\)",
                    content,
                )

                for match in fk_matches:
                    entity_ref = match[0]
                    options = match[1] if len(match) > 1 else ""

                    # Check if this entity requires PROTECT
                    entity_name = entity_ref.replace("_id", "").replace("_", "").title()

                    if entity_name in self.PROTECTED_FK_ENTITIES:
                        if "on_delete" not in options or "PROTECT" not in options.upper():
                            violations.append(
                                f"{filepath.name}: ForeignKey to '{entity_ref}' must use on_delete=PROTECT"
                            )

            except Exception:
                continue

        return violations

    def _check_cross_module_creation(self, files: List[Path]) -> List[str]:
        """Check for cross-module entity creation (should only read)."""
        violations: List[str] = []

        # Patterns that indicate entity creation
        creation_patterns = [
            (r"(\w+)\.create\(", "create"),
            (r"(\w+)\.insert\(", "insert"),
            (r"(\w+)\(\s*[^)]+\)\.save\(", "save"),
            (r"session\.add\s*\(\s*(\w+)", "add"),
        ]

        for filepath in files:
            try:
                content = filepath.read_text()
                current_module = self._get_module_from_path(filepath)

                for pattern, operation in creation_patterns:
                    matches = re.findall(pattern, content)
                    for entity_ref in matches:
                        # Normalize entity name
                        entity_name = entity_ref.title()

                        # Check if this module owns the entity
                        if entity_name in self.ENTITY_OWNERS:
                            owner = self.ENTITY_OWNERS[entity_name]
                            if current_module != owner and current_module != "unknown":
                                violations.append(
                                    f"{filepath.name}: Module '{current_module}' should not create '{entity_name}' (owned by '{owner}')"
                                )

            except Exception:
                continue

        return violations


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = ModularityHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
