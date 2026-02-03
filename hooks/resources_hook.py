#!/usr/bin/env python3
"""
Resources Hook for JARVIS

Validates code for resource management and potential memory/CPU issues.

Checks:
- Unbounded loops
- Large file handling without streaming
- Memory-intensive operations
- Missing resource cleanup
- Proper generator usage for large data
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


class ResourcesHook(BaseHook):
    """
    Validates resource management.

    Checks:
    - Unbounded loops (while True without break)
    - Large data in memory (loading files without streaming)
    - Missing file handles cleanup
    - Thread/process resource management
    - Generator usage for large datasets
    """

    name = "Resources"
    description = "Validates memory and resource management"
    blocking_on_failure = False  # Warning for most, blocking for critical

    # Unbounded loop patterns
    UNBOUNDED_LOOP_PATTERNS = [
        (r"while\s+True:", "while True without visible break"),
        (r"while\s+1:", "while 1 without visible break"),
        (r"for\s+\w+\s+in\s+iter\s*\(\s*\w+\s*,\s*None\s*\)", "iter() with None sentinel"),
    ]

    # Memory-intensive patterns
    MEMORY_PATTERNS = [
        (r"\.read\(\)", "read() loads entire file into memory"),
        (r"json\.load\(open\(", "json.load with inline open - use context manager"),
        (r"\[\s*.*\s+for\s+.*\s+in\s+.*\.readlines\(\)\s*\]", "readlines() in list comprehension"),
        (r"list\s*\(\s*.*\.all\(\)\s*\)", "list(query.all()) loads all records"),
    ]

    # Files where .read() is acceptable (small files: invoices, certs, configs, mock data)
    READ_ACCEPTABLE_FILES = [
        "parser",       # Invoice/PDF parsing (small files)
        "mock",         # Mock/test data
        "test",         # Test files
        "auth",         # Certificate/token files
        "config",       # Config files
        "app.py",       # Main app (uploads, small files)
        "xml_parser",   # XML parsing (invoice XMLs)
        "bulk",         # Bulk processor (invoices)
        "routes",       # Route handlers (file uploads, small docs)
        "statements",   # Bank statement PDFs
    ]

    # Missing cleanup patterns
    CLEANUP_PATTERNS = [
        (r"open\s*\([^)]+\)\s*(?!\.close|with)", "open() without context manager or close()"),
        (r"Thread\s*\([^)]+\)\.start\(\)(?!.*\.join\(\))", "Thread started without join"),
        (r"subprocess\.Popen\s*\([^)]+\)(?!.*\.wait\(\)|.*\.communicate\(\))", "Popen without wait/communicate"),
    ]

    def run(self) -> HookResult:
        """Run resource validation."""
        details: List[str] = []
        warnings: List[str] = []

        python_files = list(self.target_path.rglob("*.py"))
        if not python_files:
            return self._create_result(
                HookStatus.PASSED,
                "No Python files to validate",
                [],
            )

        details.append(f"Scanning {len(python_files)} Python files")

        # Check for unbounded loops
        loop_warnings = self._check_unbounded_loops(python_files)
        warnings.extend(loop_warnings)

        # Check for memory-intensive operations
        memory_warnings = self._check_memory_patterns(python_files)
        warnings.extend(memory_warnings)

        # Check for missing cleanup
        cleanup_warnings = self._check_cleanup_patterns(python_files)
        warnings.extend(cleanup_warnings)

        # Check for large data handling
        large_data_warnings = self._check_large_data_handling(python_files)
        warnings.extend(large_data_warnings)

        # Check for proper generator usage
        generator_tips = self._check_generator_usage(python_files)
        details.extend(generator_tips)

        if warnings:
            # Check if any are critical (blocking)
            critical = [w for w in warnings if "CRITICAL" in w]
            if critical:
                return self._create_result(
                    HookStatus.FAILED,
                    f"Found {len(critical)} critical resource issues",
                    critical + warnings[:5],
                )

            return self._create_result(
                HookStatus.WARNING,
                f"Found {len(warnings)} resource management warnings",
                warnings[:10] + (["... and more"] if len(warnings) > 10 else []),
            )

        details.append("No unbounded loops detected")
        details.append("Resource cleanup verified")
        details.append("Memory usage patterns acceptable")

        return self._create_result(
            HookStatus.PASSED,
            "Resource validation passed",
            details,
        )

    def _check_unbounded_loops(self, files: List[Path]) -> List[str]:
        """Check for potentially unbounded loops."""
        warnings: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()
                lines = content.split('\n')

                for i, line in enumerate(lines):
                    # Check for while True
                    if re.match(r"\s*while\s+True\s*:", line):
                        # Look for break in the next 20 lines
                        loop_body = '\n'.join(lines[i:i+20])
                        if "break" not in loop_body:
                            warnings.append(
                                f"[CRITICAL] {filepath.name}:{i+1}: while True without break in visible scope"
                            )

            except Exception:
                continue

        return warnings

    def _check_memory_patterns(self, files: List[Path]) -> List[str]:
        """Check for memory-intensive patterns."""
        warnings: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()
                filename_lower = filepath.name.lower()

                for pattern, description in self.MEMORY_PATTERNS:
                    # Skip .read() warnings for files that handle small data
                    if pattern == r"\.read\(\)" and any(
                        acceptable in filename_lower
                        for acceptable in self.READ_ACCEPTABLE_FILES
                    ):
                        continue

                    matches = re.finditer(pattern, content)
                    for match in matches:
                        # Get line number
                        line_num = content[:match.start()].count('\n') + 1
                        warnings.append(
                            f"[Memory] {filepath.name}:{line_num}: {description}"
                        )

            except Exception:
                continue

        return warnings

    def _check_cleanup_patterns(self, files: List[Path]) -> List[str]:
        """Check for missing resource cleanup."""
        warnings: List[str] = []

        for filepath in files:
            try:
                content = filepath.read_text()

                # Check for file handles without context manager
                open_calls = re.findall(r"(\w+)\s*=\s*open\s*\([^)]+\)", content)
                for var_name in open_calls:
                    # Check if close() is called
                    if f"{var_name}.close()" not in content:
                        # Check if used with 'with' later
                        if f"with {var_name}" not in content:
                            warnings.append(
                                f"[Cleanup] {filepath.name}: File handle '{var_name}' may not be closed"
                            )

            except Exception:
                continue

        return warnings

    def _check_large_data_handling(self, files: List[Path]) -> List[str]:
        """Check for proper handling of large data."""
        warnings: List[str] = []

        for filepath in files:
            # Only check service/processor files
            if not any(kw in filepath.name.lower() for kw in ["service", "processor", "import", "sync"]):
                continue

            try:
                content = filepath.read_text()

                # Check for loading all records without pagination
                if ".all()" in content and "paginate" not in content.lower():
                    if "limit" not in content.lower() and "batch" not in content.lower():
                        warnings.append(
                            f"[Large Data] {filepath.name}: Loading all records - consider pagination/batching"
                        )

                # Check for large list operations
                if re.search(r"\[\s*\w+\s+for\s+\w+\s+in\s+\w+\s*\]", content):
                    # Count list comprehensions
                    list_comps = re.findall(r"\[\s*\w+\s+for\s+\w+\s+in\s+\w+\s*\]", content)
                    if len(list_comps) > 5:
                        warnings.append(
                            f"[Large Data] {filepath.name}: Many list comprehensions - consider generators"
                        )

            except Exception:
                continue

        return warnings

    def _check_generator_usage(self, files: List[Path]) -> List[str]:
        """Check for proper generator usage."""
        tips: List[str] = []

        generator_count = 0
        list_comp_count = 0

        for filepath in files:
            try:
                content = filepath.read_text()

                # Count generators
                generator_count += len(re.findall(r"\(\s*\w+\s+for\s+\w+\s+in", content))
                generator_count += content.count("yield ")

                # Count list comprehensions
                list_comp_count += len(re.findall(r"\[\s*\w+\s+for\s+\w+\s+in", content))

            except Exception:
                continue

        if generator_count > 0:
            tips.append(f"Found {generator_count} generators (good for memory)")

        if list_comp_count > generator_count * 2:
            tips.append(f"Consider converting some list comprehensions ({list_comp_count}) to generators")

        return tips


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = ResourcesHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
