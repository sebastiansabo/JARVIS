#!/usr/bin/env python3
"""
Master Hook Orchestrator for JARVIS

Coordinates all validation hooks and produces a consolidated report.
Run after code generation to validate financial code quality.

Usage:
    python hooks/master_hook.py jarvis/ --output markdown
    python hooks/master_hook.py jarvis/ --output json
    python hooks/master_hook.py jarvis/ --watch  # Continuous monitoring
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class HookStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class HookResult:
    """Result from a single hook execution."""
    hook_name: str
    status: HookStatus
    message: str
    details: List[str] = field(default_factory=list)
    blocking: bool = False
    execution_time_ms: float = 0.0


@dataclass
class ValidationReport:
    """Consolidated report from all hooks."""
    timestamp: str
    target_path: str
    hooks_run: int
    hooks_passed: int
    hooks_failed: int
    hooks_warnings: int
    blocking_issues: List[str]
    results: List[HookResult]
    overall_status: HookStatus
    total_execution_time_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "target_path": self.target_path,
            "summary": {
                "hooks_run": self.hooks_run,
                "hooks_passed": self.hooks_passed,
                "hooks_failed": self.hooks_failed,
                "hooks_warnings": self.hooks_warnings,
            },
            "overall_status": self.overall_status.value,
            "blocking_issues": self.blocking_issues,
            "results": [
                {
                    "hook": r.hook_name,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                    "blocking": r.blocking,
                    "execution_time_ms": r.execution_time_ms,
                }
                for r in self.results
            ],
            "total_execution_time_ms": self.total_execution_time_ms,
        }

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            "# JARVIS Validation Report",
            "",
            f"**Timestamp:** {self.timestamp}",
            f"**Target:** `{self.target_path}`",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Hooks Run | {self.hooks_run} |",
            f"| Passed | {self.hooks_passed} |",
            f"| Failed | {self.hooks_failed} |",
            f"| Warnings | {self.hooks_warnings} |",
            f"| Execution Time | {self.total_execution_time_ms:.2f}ms |",
            "",
        ]

        # Overall status with emoji
        status_emoji = {
            HookStatus.PASSED: "",
            HookStatus.FAILED: "",
            HookStatus.WARNING: "",
            HookStatus.SKIPPED: "",
        }

        lines.append(f"**Overall Status:** {status_emoji.get(self.overall_status, '')} {self.overall_status.value.upper()}")
        lines.append("")

        # Blocking issues
        if self.blocking_issues:
            lines.extend([
                "## Blocking Issues",
                "",
                "The following issues MUST be resolved before code can be merged:",
                "",
            ])
            for issue in self.blocking_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Detailed results
        lines.extend([
            "## Hook Results",
            "",
        ])

        for result in self.results:
            emoji = status_emoji.get(result.status, "")
            lines.append(f"### {emoji} {result.hook_name}")
            lines.append("")
            lines.append(f"**Status:** {result.status.value}")
            lines.append(f"**Message:** {result.message}")

            if result.details:
                lines.append("")
                lines.append("**Details:**")
                for detail in result.details:
                    lines.append(f"- {detail}")

            lines.append("")

        return "\n".join(lines)


class BaseHook:
    """Base class for all validation hooks."""

    name: str = "BaseHook"
    description: str = "Base hook class"
    blocking_on_failure: bool = False

    def __init__(self, target_path: Path):
        self.target_path = target_path

    def run(self) -> HookResult:
        """Execute the hook validation. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement run()")

    def _create_result(
        self,
        status: HookStatus,
        message: str,
        details: Optional[List[str]] = None,
    ) -> HookResult:
        return HookResult(
            hook_name=self.name,
            status=status,
            message=message,
            details=details or [],
            blocking=self.blocking_on_failure and status == HookStatus.FAILED,
        )


class MasterHook:
    """
    Master hook orchestrator that runs all validation hooks.

    Hooks are run in order of priority:
    1. Testing (most critical for financial code)
    2. Architecture (layer isolation)
    3. Modularity (duplicate detection)
    4. Performance (query optimization)
    5. Cache (TTL validation)
    6. Database (ACID, pools)
    7. Resources (memory, loops)
    """

    def __init__(self, target_path: str):
        self.target_path = Path(target_path)
        self.hooks: List[BaseHook] = []
        self._register_hooks()

    def _register_hooks(self):
        """Register all available hooks."""
        # Handle both module and script execution
        try:
            # Try relative imports first (when used as a module)
            from .testing_hook import TestingHook
            from .architecture_hook import ArchitectureHook
            from .modularity_hook import ModularityHook
            from .performance_hook import PerformanceHook
            from .cache_hook import CacheHook
            from .database_hook import DatabaseHook
            from .resources_hook import ResourcesHook
        except ImportError:
            # Fall back to absolute imports (when run as a script)
            hooks_dir = Path(__file__).parent
            sys.path.insert(0, str(hooks_dir))
            from testing_hook import TestingHook
            from architecture_hook import ArchitectureHook
            from modularity_hook import ModularityHook
            from performance_hook import PerformanceHook
            from cache_hook import CacheHook
            from database_hook import DatabaseHook
            from resources_hook import ResourcesHook

        hook_classes = [
            TestingHook,
            ArchitectureHook,
            ModularityHook,
            PerformanceHook,
            CacheHook,
            DatabaseHook,
            ResourcesHook,
        ]

        for hook_class in hook_classes:
            self.hooks.append(hook_class(self.target_path))

    def run(self) -> ValidationReport:
        """Run all hooks and produce a validation report."""
        start_time = time.time()
        results: List[HookResult] = []
        blocking_issues: List[str] = []

        for hook in self.hooks:
            hook_start = time.time()
            try:
                result = hook.run()
                result.execution_time_ms = (time.time() - hook_start) * 1000
                results.append(result)

                if result.blocking:
                    blocking_issues.append(f"[{hook.name}] {result.message}")

            except Exception as e:
                # Hook itself failed - treat as blocking
                result = HookResult(
                    hook_name=hook.name,
                    status=HookStatus.FAILED,
                    message=f"Hook execution error: {str(e)}",
                    details=[str(e)],
                    blocking=True,
                    execution_time_ms=(time.time() - hook_start) * 1000,
                )
                results.append(result)
                blocking_issues.append(f"[{hook.name}] Hook execution failed: {str(e)}")

        # Calculate summary
        passed = sum(1 for r in results if r.status == HookStatus.PASSED)
        failed = sum(1 for r in results if r.status == HookStatus.FAILED)
        warnings = sum(1 for r in results if r.status == HookStatus.WARNING)

        # Determine overall status
        if failed > 0:
            overall_status = HookStatus.FAILED
        elif warnings > 0:
            overall_status = HookStatus.WARNING
        else:
            overall_status = HookStatus.PASSED

        total_time = (time.time() - start_time) * 1000

        return ValidationReport(
            timestamp=datetime.utcnow().isoformat(),
            target_path=str(self.target_path),
            hooks_run=len(results),
            hooks_passed=passed,
            hooks_failed=failed,
            hooks_warnings=warnings,
            blocking_issues=blocking_issues,
            results=results,
            overall_status=overall_status,
            total_execution_time_ms=total_time,
        )


def run_all_hooks(target_path: str, output_format: str = "markdown") -> str:
    """
    Convenience function to run all hooks and return formatted output.

    Args:
        target_path: Path to the code to validate
        output_format: "markdown" or "json"

    Returns:
        Formatted validation report
    """
    master = MasterHook(target_path)
    report = master.run()

    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2)
    else:
        return report.to_markdown()


def main():
    parser = argparse.ArgumentParser(
        description="JARVIS Master Hook - Validate financial code quality"
    )
    parser.add_argument(
        "target",
        help="Path to code directory to validate (e.g., jarvis/)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Watch mode - continuously validate on changes",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Watch interval in seconds (default: 5)",
    )

    args = parser.parse_args()

    if args.watch:
        print(f"Watching {args.target} for changes (Ctrl+C to stop)...")
        try:
            while True:
                output = run_all_hooks(args.target, args.output)
                print("\033[2J\033[H")  # Clear screen
                print(output)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped watching.")
    else:
        output = run_all_hooks(args.target, args.output)
        print(output)

        # Exit with error code if validation failed
        master = MasterHook(args.target)
        report = master.run()
        if report.overall_status == HookStatus.FAILED:
            sys.exit(1)


if __name__ == "__main__":
    main()
