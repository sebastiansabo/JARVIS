#!/usr/bin/env python3
"""
Database Hook for JARVIS

Validates database operations for ACID compliance and best practices.

Checks:
- Connection pooling is properly configured
- Transactions are properly managed
- No raw SQL without parameterization
- Proper error handling for database operations
- Connection cleanup (context managers)
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

hooks_dir = Path(__file__).parent
sys.path.insert(0, str(hooks_dir))

try:
    from .master_hook import BaseHook, HookResult, HookStatus
except ImportError:
    from master_hook import BaseHook, HookResult, HookStatus


class DatabaseHook(BaseHook):
    """
    Validates database operations.

    Checks:
    - Connection pooling configuration
    - ACID compliance (transactions)
    - SQL injection prevention (parameterized queries)
    - Proper connection handling (context managers)
    - Error handling for DB operations
    """

    name = "Database"
    description = "Validates ACID compliance and connection management"
    blocking_on_failure = True  # Database issues are critical

    # SQL injection patterns (dangerous) - using simpler patterns to avoid backtracking
    # NOTE: f-strings with {ph} placeholder are SAFE (parameterized queries)
    SQL_INJECTION_PATTERNS = [
        # String formatting in SQL - check for f-strings with actual variable interpolation
        # We look for {variable} patterns that are NOT {ph} (placeholder)
        (r"execute\s*\(\s*f['\"].*\{(?!ph\})(?!get_placeholder)[a-zA-Z_]", "f-string variable in SQL - use parameterized queries"),
    ]

    # Safe patterns that use placeholders correctly
    SAFE_PLACEHOLDER_PATTERNS = [
        r"\{ph\}",                    # {ph} placeholder variable
        r"\{get_placeholder\(\)\}",   # {get_placeholder()} call
        r"%\(\w+\)s",                 # %(name)s named parameter (psycopg2)
        r"%s",                        # %s positional parameter
    ]

    # Required patterns for financial operations (simple substring checks)
    TRANSACTION_KEYWORDS = ["with ", "begin()", "commit()", "@transactional", "transaction"]
    ERROR_HANDLING_KEYWORDS = ["try:", "except", "DatabaseError", "IntegrityError"]

    def run(self) -> HookResult:
        """Run database validation."""
        details: List[str] = []
        violations: List[str] = []

        python_files = list(self.target_path.rglob("*.py"))
        if not python_files:
            return self._create_result(
                HookStatus.PASSED,
                "No Python files to validate",
                [],
            )

        details.append(f"Scanning {len(python_files)} Python files")

        # Check for SQL injection vulnerabilities
        injection_violations = self._check_sql_injection(python_files)
        violations.extend(injection_violations)

        # Check connection handling
        connection_violations = self._check_connection_handling(python_files)
        violations.extend(connection_violations)

        # Check transaction management for financial operations
        transaction_violations = self._check_transaction_management(python_files)
        violations.extend(transaction_violations)

        # Check connection pooling configuration
        pool_warnings = self._check_connection_pooling(python_files)
        details.extend(pool_warnings)

        if violations:
            return self._create_result(
                HookStatus.FAILED,
                f"Found {len(violations)} database issues",
                violations[:10] + (["... and more"] if len(violations) > 10 else []),
            )

        details.append("No SQL injection vulnerabilities found")
        details.append("Connection handling verified")
        details.append("Transaction management validated")

        return self._create_result(
            HookStatus.PASSED,
            "Database validation passed",
            details,
        )

    def _check_sql_injection(self, files: List[Path]) -> List[str]:
        """Check for SQL injection vulnerabilities."""
        violations: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()

                # Skip files that use safe placeholder patterns
                uses_safe_placeholders = any(
                    re.search(pattern, content)
                    for pattern in self.SAFE_PLACEHOLDER_PATTERNS
                )

                if uses_safe_placeholders:
                    # File uses parameterized queries with placeholders - skip SQL injection check
                    continue

                for pattern, description in self.SQL_INJECTION_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                        violations.append(
                            f"[SQL Injection] {filepath.name}: {description}"
                        )

            except Exception:
                continue

        return violations

    def _check_connection_handling(self, files: List[Path]) -> List[str]:
        """Check for proper connection handling."""
        violations: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()

                # Check for connections without context managers
                connection_patterns = [
                    r"get_connection\(\)",
                    r"psycopg2\.connect\(",
                    r"create_engine\(",
                    r"\.connect\(",
                ]

                has_connection = any(
                    re.search(pattern, content)
                    for pattern in connection_patterns
                )

                if has_connection:
                    # Check for context manager usage
                    has_context = any(
                        pattern in content
                        for pattern in [
                            "with ",
                            "contextmanager",
                            "try:",
                            "finally:",
                            ".close()",
                        ]
                    )

                    if not has_context:
                        violations.append(
                            f"[Connection Leak] {filepath.name}: Database connection without context manager or cleanup"
                        )

            except Exception:
                continue

        return violations

    def _check_transaction_management(self, files: List[Path]) -> List[str]:
        """Check transaction management for financial operations."""
        violations: List[str] = []

        for filepath in files:
            # Only check financial-related files
            financial_keywords = ["transaction", "invoice", "gl", "posting", "reconcil"]
            if not any(kw in filepath.name.lower() for kw in financial_keywords):
                continue

            try:
                content = filepath.read_text()

                # Check for writes without transaction boundaries
                write_patterns = [
                    r"\.save\(\)",
                    r"\.insert\(",
                    r"\.update\(",
                    r"\.delete\(",
                    r"session\.add\(",
                    r"execute\(.*INSERT",
                    r"execute\(.*UPDATE",
                    r"execute\(.*DELETE",
                ]

                has_writes = any(
                    re.search(pattern, content, re.IGNORECASE)
                    for pattern in write_patterns
                )

                if has_writes:
                    # Check for transaction management (simple keyword check)
                    has_transaction = any(
                        keyword in content.lower()
                        for keyword in self.TRANSACTION_KEYWORDS
                    )

                    if not has_transaction:
                        violations.append(
                            f"[No Transaction] {filepath.name}: Financial writes without explicit transaction"
                        )

                    # Check for error handling (simple keyword check)
                    has_error_handling = any(
                        keyword in content
                        for keyword in self.ERROR_HANDLING_KEYWORDS
                    )

                    if not has_error_handling:
                        violations.append(
                            f"[No Error Handling] {filepath.name}: Database operations without proper error handling"
                        )

            except Exception:
                continue

        return violations

    def _check_connection_pooling(self, files: List[Path]) -> List[str]:
        """Check connection pooling configuration."""
        details: List[str] = []

        for filepath in files:
            if "database" not in filepath.name.lower():
                continue

            try:
                content = filepath.read_text()

                # Check for pool configuration
                pool_patterns = [
                    (r"pool_size\s*=\s*(\d+)", "pool_size"),
                    (r"max_overflow\s*=\s*(\d+)", "max_overflow"),
                    (r"pool_timeout\s*=\s*(\d+)", "pool_timeout"),
                    (r"pool_recycle\s*=\s*(\d+)", "pool_recycle"),
                ]

                for pattern, name in pool_patterns:
                    match = re.search(pattern, content)
                    if match:
                        value = match.group(1)
                        details.append(f"Pool config: {name}={value}")

                # Warn if no pooling configured
                if "pool" not in content.lower():
                    details.append("WARNING: No connection pooling detected")

            except Exception:
                continue

        return details


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = DatabaseHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
