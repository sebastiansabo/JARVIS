#!/usr/bin/env python3
"""
JARVIS Layer B — session-level Jira enhancement (Claude + Atlassian MCP).

Issue *creation* is owned entirely by Layer A (the git pre-push hook
.claude/hooks/jira_commit_sync.py). This Stop hook is intentionally a no-op:
the "smart grouping / re-filing" behaviour requires the Atlassian MCP tools,
which are only callable by Claude itself, not by a hook subprocess. It exists
as a wired, documented seam and must never create duplicate issues.
"""
import sys

if __name__ == "__main__":
    sys.exit(0)
