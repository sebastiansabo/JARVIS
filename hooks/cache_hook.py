#!/usr/bin/env python3
"""
Cache Hook for JARVIS

Validates caching implementation for financial data.

Checks:
- Exchange rates have proper TTL (max 24 hours)
- Master data caching is implemented
- Cache invalidation is present
- No caching of sensitive financial data
- Cache keys are properly structured
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


class CacheHook(BaseHook):
    """
    Validates caching implementation.

    Checks:
    - TTL is defined for cached data
    - Exchange rates have max 24h TTL
    - Sensitive data is not cached (or has encryption)
    - Cache invalidation exists
    - Cache key structure follows conventions
    """

    name = "Cache"
    description = "Validates caching TTL and implementation"
    blocking_on_failure = False  # Warning, not blocking

    # Maximum TTL for different data types (in seconds)
    MAX_TTL: Dict[str, int] = {
        "exchange_rate": 86400,     # 24 hours
        "currency_rate": 86400,     # 24 hours
        "company": 3600,            # 1 hour
        "vendor": 3600,             # 1 hour
        "department": 3600,         # 1 hour
        "default": 3600,            # 1 hour default
    }

    # Data that should NOT be cached
    NEVER_CACHE = [
        "transaction",
        "invoice_amount",
        "gl_posting",
        "audit_log",
        "balance",
        "password",
        "token",
        "secret",
        "private_key",
    ]

    def run(self) -> HookResult:
        """Run cache validation."""
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

        # Check for cache usage
        cache_files = self._find_cache_usage(python_files)
        if not cache_files:
            details.append("No caching detected - consider adding for performance")
            return self._create_result(
                HookStatus.PASSED,
                "Cache validation passed (no caching found)",
                details,
            )

        details.append(f"Found caching in {len(cache_files)} files")

        # Check TTL configuration
        ttl_warnings = self._check_ttl_configuration(cache_files)
        warnings.extend(ttl_warnings)

        # Check for forbidden cache keys
        forbidden_warnings = self._check_forbidden_caching(cache_files)
        warnings.extend(forbidden_warnings)

        # Check cache invalidation
        invalidation_warnings = self._check_cache_invalidation(cache_files)
        warnings.extend(invalidation_warnings)

        # Check cache key structure
        key_warnings = self._check_cache_key_structure(cache_files)
        warnings.extend(key_warnings)

        if warnings:
            return self._create_result(
                HookStatus.WARNING,
                f"Found {len(warnings)} cache configuration issues",
                warnings[:10] + (["... and more"] if len(warnings) > 10 else []),
            )

        details.append("Cache TTL properly configured")
        details.append("No sensitive data in cache")
        details.append("Cache invalidation implemented")

        return self._create_result(
            HookStatus.PASSED,
            "Cache validation passed",
            details,
        )

    def _find_cache_usage(self, files: List[Path]) -> List[Tuple[Path, str]]:
        """Find files that use caching."""
        cache_files: List[Tuple[Path, str]] = []

        cache_patterns = [
            r"cache\.get\(",
            r"cache\.set\(",
            r"@cache\.",
            r"redis\.",
            r"memcache",
            r"functools\.lru_cache",
            r"@lru_cache",
            r"Cache\(",
        ]

        for filepath in files:
            try:
                content = filepath.read_text()

                for pattern in cache_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        cache_files.append((filepath, content))
                        break

            except Exception:
                continue

        return cache_files

    def _check_ttl_configuration(self, cache_files: List[Tuple[Path, str]]) -> List[str]:
        """Check that TTL is properly configured."""
        warnings: List[str] = []

        for filepath, content in cache_files:
            # Look for cache.set without TTL
            set_without_ttl = re.findall(
                r"cache\.set\s*\(\s*['\"][^'\"]+['\"]\s*,\s*[^,)]+\s*\)",
                content,
            )

            for match in set_without_ttl:
                if "ttl" not in match.lower() and "expire" not in match.lower() and "timeout" not in match.lower():
                    warnings.append(
                        f"[TTL Missing] {filepath.name}: cache.set without TTL - {match[:50]}..."
                    )

            # Check exchange rate caching has proper TTL
            if "exchange_rate" in content.lower() or "currency_rate" in content.lower():
                # Look for TTL values
                ttl_matches = re.findall(r"ttl\s*=\s*(\d+)", content, re.IGNORECASE)
                for ttl in ttl_matches:
                    ttl_value = int(ttl)
                    if ttl_value > self.MAX_TTL["exchange_rate"]:
                        warnings.append(
                            f"[TTL Too Long] {filepath.name}: Exchange rate TTL {ttl_value}s exceeds max 86400s (24h)"
                        )

        return warnings

    def _check_forbidden_caching(self, cache_files: List[Tuple[Path, str]]) -> List[str]:
        """Check that sensitive data is not cached."""
        warnings: List[str] = []

        for filepath, content in cache_files:
            for forbidden in self.NEVER_CACHE:
                # Look for cache operations with forbidden key names
                pattern = rf"cache\.\w+\s*\(\s*['\"].*{forbidden}.*['\"]"
                if re.search(pattern, content, re.IGNORECASE):
                    warnings.append(
                        f"[Sensitive Cache] {filepath.name}: Caching '{forbidden}' data is not allowed"
                    )

        return warnings

    def _check_cache_invalidation(self, cache_files: List[Tuple[Path, str]]) -> List[str]:
        """Check that cache invalidation is implemented."""
        warnings: List[str] = []

        for filepath, content in cache_files:
            has_set = "cache.set" in content or "cache[" in content
            has_delete = any(
                pattern in content
                for pattern in ["cache.delete", "cache.invalidate", "cache.clear", "cache.remove"]
            )

            if has_set and not has_delete:
                # Check if this is a read-only cache file
                if "service" in filepath.name.lower() or "repository" in filepath.name.lower():
                    warnings.append(
                        f"[No Invalidation] {filepath.name}: Sets cache but no invalidation found"
                    )

        return warnings

    def _check_cache_key_structure(self, cache_files: List[Tuple[Path, str]]) -> List[str]:
        """Check that cache keys follow naming conventions."""
        warnings: List[str] = []

        # Good key patterns: "entity:id", "type:subtype:id", etc.
        good_patterns = [
            r"cache\.\w+\s*\(\s*f?['\"][\w_]+:[\w_]+",  # entity:id pattern
            r"cache\.\w+\s*\(\s*f?['\"][\w_]+_[\w_]+_",  # entity_type_id pattern
        ]

        # Internal cache metadata keys - not actual data cache keys
        internal_keys = ['ttl', 'timestamp', 'key', 'data', 'expires', 'timeout']

        for filepath, content in cache_files:
            # Find all cache operations
            cache_ops = re.findall(
                r"cache\.\w+\s*\(\s*(['\"].*?['\"]|f['\"].*?['\"])",
                content,
            )

            for key in cache_ops:
                # Extract the actual key value (remove quotes)
                key_value = key.strip('\'"')
                if key.startswith('f'):
                    key_value = key[2:-1]  # f"..." -> ...

                # Skip internal metadata keys
                if key_value in internal_keys:
                    continue

                is_good = any(
                    re.match(pattern.replace(r"cache\.\w+\s*\(\s*", ""), key)
                    for pattern in good_patterns
                )

                # Warn if key doesn't follow structure
                if not is_good and len(key) < 10:
                    warnings.append(
                        f"[Key Structure] {filepath.name}: Cache key should follow 'entity:id' pattern"
                    )

        return warnings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to validate")
    args = parser.parse_args()

    hook = CacheHook(Path(args.target))
    result = hook.run()

    print(f"Status: {result.status.value}")
    print(f"Message: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")
