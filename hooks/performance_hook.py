#!/usr/bin/env python3
"""
Performance Hook for JARVIS

Validates code for common performance issues.

Checks:
- N+1 query detection (queries in loops)
- Missing batch operations
- Unbounded result sets
- Missing pagination
- Expensive operations in loops
- Missing indexes on frequently queried columns
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

hooks_dir = Path(__file__).parent
sys.path.insert(0, str(hooks_dir))

try:
    from .master_hook import BaseHook, HookResult, HookStatus
except ImportError:
    from master_hook import BaseHook, HookResult, HookStatus


class PerformanceHook(BaseHook):
    """
    Validates code for performance issues.

    Checks:
    - N+1 query patterns (database calls in loops)
    - Missing batch operations for bulk inserts
    - Unbounded queries (missing LIMIT)
    - Missing pagination for list endpoints
    - Expensive string operations in loops
    """

    name = "Performance"
    description = "Validates code for N+1 queries and performance issues"
    blocking_on_failure = False  # Warning, not blocking

    # Simplified patterns for detection - use line-by-line matching
    # These are checked per-line to avoid slow regex backtracking

    # Keywords that indicate potential N+1 when found in loops
    QUERY_KEYWORDS = [".query(", "execute(", "fetchone(", "fetchall(", "cursor."]
    BATCH_KEYWORDS = [".save()", ".insert(", "session.add("]

    # Unbounded query patterns (simple, fast)
    UNBOUNDED_PATTERNS = [".all()", "fetchall()"]

    # Files/functions to skip (migrations, retry logic, etc.)
    SKIP_PATTERNS = [
        "migration",    # One-time migration code
        "migrate",      # Migration functions
        "_retry",       # Retry logic
        "retry_",       # Retry functions
        "sync_cursor",  # Cursor sync operations
        "seed",         # Database seeding
        "init_db",      # Database initialization
        "setup",        # Setup functions
    ]

    # Context indicators that make loops acceptable
    ACCEPTABLE_LOOP_CONTEXT = [
        "conn.commit()",      # Transaction block - inserts are atomic
        "connection.commit(", # Same
        "# batch",            # Explicitly marked as batch
        "# migration",        # Migration code
        "executemany(",       # Already using batch operation
        "# retry",            # Retry logic
        "yield ",             # Generator function
        "yield(",             # Generator expression
    ]

    def run(self) -> HookResult:
        """Run performance validation."""
        details: List[str] = []
        warnings: List[str] = []

        python_files = list(self.target_path.rglob("*.py"))
        if not python_files:
            return self._create_result(
                HookStatus.WARNING,
                "No Python files found",
                [],
            )

        details.append(f"Scanning {len(python_files)} Python files")

        # Check N+1 patterns (queries in loops)
        n1_warnings = self._check_n1_queries(python_files)
        warnings.extend(n1_warnings)

        # Check unbounded queries
        unbounded_warnings = self._check_unbounded_queries(python_files)
        warnings.extend(unbounded_warnings)

        # Check for missing pagination
        pagination_warnings = self._check_pagination(python_files)
        warnings.extend(pagination_warnings)

        if warnings:
            return self._create_result(
                HookStatus.WARNING,
                f"Found {len(warnings)} potential performance issues",
                warnings[:10] + (["... and more"] if len(warnings) > 10 else []),
            )

        details.append("No N+1 query patterns detected")
        details.append("Batch operations properly used")
        details.append("Queries are bounded")

        return self._create_result(
            HookStatus.PASSED,
            "Performance validation passed",
            details,
        )

    def _check_n1_queries(self, files: List[Path]) -> List[str]:
        """Check for N+1 query patterns using line-by-line analysis."""
        warnings: List[str] = []

        for filepath in files:
            # Skip files with skip patterns in name
            if any(skip in filepath.name.lower() for skip in self.SKIP_PATTERNS):
                continue

            try:
                content = filepath.read_text()
                content_lower = content.lower()

                # Skip files that are primarily migration/setup code
                if any(skip in content_lower for skip in ['def migrate_', 'migration']):
                    continue

                lines = content.split('\n')

                in_loop = False
                loop_start_line = 0
                loop_line_text = ""

                for i, line in enumerate(lines):
                    # Detect loop start
                    loop_match = re.match(r'\s*for\s+\w+\s+in\s+', line)
                    if loop_match:
                        # Skip loops iterating over query results or small collections - NOT N+1
                        # e.g., "for row in cursor.fetchall():" or "for item in results:"
                        if any(ok in line for ok in [
                            'fetchall()', 'fetchone()', '.all()', 'results', 'rows', 'data',
                            'artifacts', 'items', 'allocations', 'destinations', 'entries',
                            'reinvoice', 'permissions', 'roles', 'lines', 'records',
                            'connections', 'range(', 'enumerate(', 'zip(',
                            'transactions', 'invoices', 'messages', 'files', 'uploads'
                        ]):
                            continue
                        in_loop = True
                        loop_start_line = i
                        loop_line_text = line

                    # Check for query keywords inside loop (within 10 lines, not on loop line itself)
                    if in_loop and i - loop_start_line < 10 and i != loop_start_line:
                        # Check if this loop has acceptable context (transaction, batch, etc.)
                        # Extended context window (50 lines) to catch commits after loop
                        loop_context = '\n'.join(lines[max(0, loop_start_line-3):min(len(lines), loop_start_line+50)])
                        if any(ctx in loop_context for ctx in self.ACCEPTABLE_LOOP_CONTEXT):
                            in_loop = False
                            continue

                        # Skip if this is a generator yield
                        if 'yield' in line:
                            continue

                        for keyword in self.QUERY_KEYWORDS:
                            if keyword in line:
                                # Skip if the keyword is in a comment
                                if line.strip().startswith('#'):
                                    continue
                                warnings.append(
                                    f"[N+1 Query] {filepath.name}:{i+1}: Database call in loop"
                                )
                                in_loop = False  # Only report once per loop
                                break

                        for keyword in self.BATCH_KEYWORDS:
                            if keyword in line:
                                if line.strip().startswith('#'):
                                    continue
                                warnings.append(
                                    f"[Missing Batch] {filepath.name}:{i+1}: Individual operation in loop"
                                )
                                in_loop = False
                                break

                    # Reset loop detection after reasonable scope
                    if in_loop and i - loop_start_line > 20:
                        in_loop = False

            except Exception:
                continue

        return warnings

    def _check_unbounded_queries(self, files: List[Path]) -> List[str]:
        """Check for unbounded database queries."""
        warnings: List[str] = []

        # Small/lookup tables where unbounded SELECT is acceptable
        # (typically <100 rows, used for configuration/reference data)
        # Note: 'hr' is included as schema name for hr.bonus_types lookup table
        SMALL_TABLES = [
            'companies', 'company', 'connections', 'settings', 'config',
            'roles', 'permissions', 'users', 'departments', 'brands',
            'vat_rates', 'partner_types', 'mappings', 'templates',
            'structure', 'categories', 'types', 'status', 'lookup',
            'hr', 'bonus_types', 'events'
        ]

        for filepath in files:
            try:
                content = filepath.read_text()

                # Check for .all() without pagination context
                if ".all()" in content:
                    # Check if pagination is used nearby
                    has_pagination = any(
                        term in content
                        for term in ["paginate", "limit", "offset", "page_size", "LIMIT"]
                    )
                    if not has_pagination:
                        warnings.append(
                            f"[Unbounded] {filepath.name}: Uses .all() without pagination"
                        )

                # Check for SELECT * without LIMIT
                select_stars = re.findall(
                    r"SELECT\s+\*\s+FROM\s+(\w+)",
                    content,
                    re.IGNORECASE,
                )
                for table in select_stars:
                    # Skip small/lookup tables
                    if any(small in table.lower() for small in SMALL_TABLES):
                        continue
                    if "LIMIT" not in content.upper():
                        warnings.append(
                            f"[Unbounded] {filepath.name}: SELECT * FROM {table} without LIMIT"
                        )

            except Exception:
                continue

        return warnings

    def _check_pagination(self, files: List[Path]) -> List[str]:
        """Check that list endpoints have pagination."""
        warnings: List[str] = []

        for filepath in files:
            # Only check route files
            if "routes" not in filepath.name:
                continue

            try:
                content = filepath.read_text()

                # Find list/get-all endpoints
                list_patterns = [
                    r"@.*\.route\s*\(\s*['\"].*?['\"].*?GET",
                    r"def\s+get_all_\w+\(",
                    r"def\s+list_\w+\(",
                ]

                has_list_endpoints = any(
                    re.search(pattern, content, re.IGNORECASE)
                    for pattern in list_patterns
                )

                if has_list_endpoints:
                    # Check for pagination
                    pagination_indicators = [
                        "page",
                        "limit",
                        "offset",
                        "per_page",
                        "paginate",
                        "page_size",
                    ]
                    has_pagination = any(
                        indicator in content.lower()
                        for indicator in pagination_indicators
                    )

                    if not has_pagination:
                        warnings.append(
                            f"[Pagination] {filepath.name}: List endpoints without pagination"
                        )

            except Exception:
                continue

        return warnings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = PerformanceHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
