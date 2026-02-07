#!/usr/bin/env python3
"""
User Guide Hook for JARVIS

Validates that the User Guide documentation exists and has required sections.
The guide is manually maintained at docs/USER_GUIDE.md.

Required sections:
- Accounting (Bugetare, e-Factura, Statements)
- HR (Events)
- Core (Settings, Profile)
- Common Workflows
"""

import re
import sys
from pathlib import Path
from typing import List

hooks_dir = Path(__file__).parent
sys.path.insert(0, str(hooks_dir))

try:
    from .master_hook import BaseHook, HookResult, HookStatus
except ImportError:
    from master_hook import BaseHook, HookResult, HookStatus


class UserGuideHook(BaseHook):
    """
    Validates User Guide documentation completeness.

    Checks:
    - docs/USER_GUIDE.md exists
    - Required sections are present
    - Key features are documented
    """

    name = "UserGuide"
    description = "Validates user guide documentation"
    blocking_on_failure = False

    GUIDE_PATH = "docs/USER_GUIDE.md"

    # Required top-level sections
    REQUIRED_SECTIONS = [
        "Accounting",
        "HR",
        "Core",
        "Common Workflows",
    ]

    # Required subsections per section
    REQUIRED_SUBSECTIONS = {
        "Accounting": ["Add Invoice", "Accounting Dashboard", "e-Factura", "Bank Statements"],
        "HR": ["Event Bonuses", "Events"],
        "Core": ["Settings", "Profile"],
    }

    # Required URLs that must be documented
    REQUIRED_URLS = [
        "/add-invoice",
        "/accounting",
        "/accounting/efactura",
        "/statements/",
        "/hr/events/",
        "/settings",
        "/profile",
    ]

    def run(self) -> HookResult:
        """Validate user guide completeness."""
        details: List[str] = []
        warnings: List[str] = []
        project_root = self.target_path.parent
        guide_path = project_root / self.GUIDE_PATH

        # Check guide exists
        if not guide_path.exists():
            return self._create_result(
                HookStatus.FAILED,
                f"User guide missing: {self.GUIDE_PATH}",
                ["Create docs/USER_GUIDE.md with required sections"],
            )

        content = guide_path.read_text()
        details.append(f"Found {self.GUIDE_PATH}")

        # Check required sections
        missing_sections = []
        for section in self.REQUIRED_SECTIONS:
            if f"## " in content and section in content:
                continue
            # Check with emoji prefix too
            if not re.search(rf"##\s+.?\s*{section}", content):
                missing_sections.append(section)

        if missing_sections:
            for s in missing_sections:
                warnings.append(f"Missing section: {s}")

        # Check required subsections
        for section, subsections in self.REQUIRED_SUBSECTIONS.items():
            for sub in subsections:
                if f"### {sub}" not in content:
                    warnings.append(f"Missing subsection: {sub} (under {section})")

        # Check required URLs are documented
        missing_urls = []
        for url in self.REQUIRED_URLS:
            if url not in content:
                missing_urls.append(url)

        if missing_urls:
            for url in missing_urls:
                warnings.append(f"Undocumented URL: {url}")

        # Check for outdated content indicators
        if "TODO" in content or "FIXME" in content:
            warnings.append("Guide contains TODO/FIXME markers")

        if warnings:
            return self._create_result(
                HookStatus.WARNING,
                f"User guide has {len(warnings)} issues",
                warnings[:10] + (["... and more"] if len(warnings) > 10 else []),
            )

        details.append("All required sections present")
        details.append("All key URLs documented")

        return self._create_result(
            HookStatus.PASSED,
            "User guide validated",
            details,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = UserGuideHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
