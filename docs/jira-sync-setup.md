# JARVIS → Jira Auto-Sync Setup

## Prerequisites

1. **Jira API Token**: Generate at https://id.atlassian.com/manage-profile/security/api-tokens
2. **Store credentials** (run once in terminal):

```bash
# Replace with your actual values
export JIRA_DOMAIN="autoworldro.atlassian.net"
export JIRA_EMAIL="sebastian.sabo@autoworld.ro"
export JIRA_API_TOKEN="your-api-token"
export JIRA_PROJECT_KEY="JAR"

# Persist in shell profile
cat >> ~/.zshrc << 'EOF'
export JIRA_DOMAIN="autoworldro.atlassian.net"
export JIRA_EMAIL="sebastian.sabo@autoworld.ro"
export JIRA_API_TOKEN="your-api-token"
export JIRA_PROJECT_KEY="JAR"
EOF
```

---

## Option A: Claude Code Slash Command (Manual Trigger)

Create the file `.claude/commands/jira-sync.md` in your JARVIS project:

```
/Users/sebastiansabo/Documents/Git/JARVIS/.claude/commands/jira-sync.md
```

### Content of `jira-sync.md`:

```markdown
# Jira Sync — Push Session Work to Jira

You are a development session summarizer. Your job is to analyze what was accomplished in THIS session and push structured updates to Jira.

## Step 1: Gather Session Context

Run these commands to collect what happened:

1. Check recent git commits (last session):
```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git log --oneline --since="$(date -v-4H +%Y-%m-%dT%H:%M:%S)" --no-merges 2>/dev/null || git log --oneline -10
```

2. Check modified files:
```bash
git diff --name-only HEAD~5 2>/dev/null || git status --short
```

3. Check the change log if it exists:
```bash
cat .claude/jarvis_changes.jsonl 2>/dev/null | tail -20
```

4. Check recent test results:
```bash
python -m pytest --tb=no -q 2>&1 | tail -5
```

## Step 2: Classify Changes

Categorize each change into ONE of:
- **feat**: New feature or capability
- **fix**: Bug fix
- **refactor**: Code restructuring
- **test**: Test additions/modifications
- **docs**: Documentation updates
- **chore**: Maintenance, dependencies, config

## Step 3: Determine Jira Action

For EACH logical unit of work, decide:

**A) If a Jira ticket already exists for this work:**
- Add a comment with what was done
- Transition status if appropriate (e.g., "In Progress" → "In Review")

**B) If NO ticket exists:**
- Create a new ticket with:
  - Summary: `[type]: concise description`
  - Description: detailed what/why/how
  - Labels: `claude-code`, `auto-logged`
  - Components: the JARVIS module affected (e.g., `bank-statements`, `invoicing`, `efactura`, `reconciliation`, `ai-agent`)

## Step 4: Execute Jira API Calls

Use `curl` to interact with Jira REST API.

### Create a new issue:
```bash
curl -s -X POST \
  "https://${JIRA_DOMAIN}/rest/api/3/issue" \
  -H "Authorization: Basic $(echo -n "${JIRA_EMAIL}:${JIRA_API_TOKEN}" | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "'"${JIRA_PROJECT_KEY}"'"},
      "summary": "SUMMARY_HERE",
      "description": {
        "type": "doc",
        "version": 1,
        "content": [
          {
            "type": "paragraph",
            "content": [{"type": "text", "text": "DESCRIPTION_HERE"}]
          }
        ]
      },
      "issuetype": {"name": "Task"},
      "labels": ["claude-code", "auto-logged"]
    }
  }'
```

### Add comment to existing issue:
```bash
curl -s -X POST \
  "https://${JIRA_DOMAIN}/rest/api/3/issue/ISSUE_KEY/comment" \
  -H "Authorization: Basic $(echo -n "${JIRA_EMAIL}:${JIRA_API_TOKEN}" | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "body": {
      "type": "doc",
      "version": 1,
      "content": [
        {
          "type": "paragraph",
          "content": [{"type": "text", "text": "COMMENT_HERE"}]
        }
      ]
    }
  }'
```

### Search for existing issues (to avoid duplicates):
```bash
curl -s -X POST \
  "https://${JIRA_DOMAIN}/rest/api/3/search/jql" \
  -H "Authorization: Basic $(echo -n "${JIRA_EMAIL}:${JIRA_API_TOKEN}" | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "jql": "project='"${JIRA_PROJECT_KEY}"' AND labels=claude-code ORDER BY created DESC",
    "maxResults": 20,
    "fields": ["summary","status","labels"]
  }'
```

## Step 5: Output Summary

After all API calls, print a clean summary:

```
━━━ JIRA SYNC COMPLETE ━━━
Created: [list new tickets with keys]
Updated: [list updated tickets with keys]  
Skipped: [anything not worth tracking]
━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Rules
- Group related commits into ONE ticket, don't create ticket-per-commit
- Use the module/component as prefix: `[Bank Statements] Add UniCredit PDF parser`
- If unsure whether a ticket exists, SEARCH FIRST
- Never create duplicate tickets
- Include file paths changed in the description
- Include test status in the description
- Be concise — Jira descriptions should be scannable, not essays
```

---

## Option B: Auto-Sync Hook (Fires Every Session End)

Add to `.claude/settings.json` in the JARVIS project:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/sebastiansabo/Documents/Git/JARVIS/.claude/hooks/jira_auto_sync.py"
          }
        ]
      }
    ]
  }
}
```

### Create the hook script:

**File:** `/Users/sebastiansabo/Documents/Git/JARVIS/.claude/hooks/jira_auto_sync.py`

```python
#!/usr/bin/env python3
"""
Auto-sync JARVIS session changes to Jira.
Runs on Claude Code session Stop event.
"""

import json
import subprocess
import os
import sys
from datetime import datetime, timedelta
from base64 import b64encode
from pathlib import Path

# ── Config ──
DOMAIN = os.environ.get("JIRA_DOMAIN", "")
EMAIL = os.environ.get("JIRA_EMAIL", "")
TOKEN = os.environ.get("JIRA_API_TOKEN", "")
PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "JAR")
PROJECT_DIR = os.environ.get(
    "CLAUDE_PROJECT_DIR",
    "/Users/sebastiansabo/Documents/Git/JARVIS"
)

if not all([DOMAIN, EMAIL, TOKEN]):
    print("⚠️  Jira credentials not configured. Skipping sync.")
    sys.exit(0)

AUTH = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {AUTH}",
    "Content-Type": "application/json"
}

# ── Gather Changes ──
def get_recent_commits(hours=4):
    """Get commits from the last N hours."""
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--oneline", "--no-merges"],
            capture_output=True, text=True, cwd=PROJECT_DIR
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception:
        return []

def get_changed_files():
    """Get files changed in recent commits."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~5"],
            capture_output=True, text=True, cwd=PROJECT_DIR
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception:
        return []

def get_change_log():
    """Read the JARVIS changes log if it exists."""
    log_path = Path(PROJECT_DIR) / ".claude" / "jarvis_changes.jsonl"
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text().strip().split("\n")[-20:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries

# ── Jira API ──
def jira_request(method, endpoint, data=None):
    """Make a Jira API request via curl."""
    cmd = [
        "curl", "-s", "-X", method,
        f"https://{DOMAIN}/rest/api/3{endpoint}",
        "-H", f"Authorization: Basic {AUTH}",
        "-H", "Content-Type: application/json"
    ]
    if data:
        cmd.extend(["-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

def create_issue(summary, description, labels=None):
    """Create a Jira issue."""
    data = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}]
                }]
            },
            "issuetype": {"name": "Task"},
            "labels": labels or ["claude-code", "auto-logged"]
        }
    }
    return jira_request("POST", "/issue", data)

def add_comment(issue_key, comment_text):
    """Add a comment to an existing issue."""
    data = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": comment_text}]
            }]
        }
    }
    return jira_request("POST", f"/issue/{issue_key}/comment", data)

# ── Main ──
def main():
    commits = get_recent_commits()
    files = get_changed_files()
    changes = get_change_log()

    if not commits and not changes:
        print("No changes detected. Skipping Jira sync.")
        return

    # Build summary
    summary_parts = []
    if commits:
        summary_parts.append(f"{len(commits)} commits")
    if files:
        summary_parts.append(f"{len(files)} files changed")

    # Detect module from file paths
    modules = set()
    module_map = {
        "bank_statement": "Bank Statements",
        "invoice": "Invoicing",
        "efactura": "e-Factura",
        "reconcil": "Reconciliation",
        "accounting": "Accounting",
        "ai_agent": "AI Agent",
        "auth": "Auth",
        "api": "API",
        "frontend": "Frontend",
        "test": "Testing",
    }
    for f in files:
        for key, label in module_map.items():
            if key in f.lower():
                modules.add(label)

    module_str = ", ".join(modules) if modules else "General"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary = f"[{module_str}] Session update — {date_str}"
    description_lines = [
        f"Auto-logged from Claude Code session at {date_str}",
        "",
        "## Commits",
        *[f"- {c}" for c in commits[:15]],
        "",
        "## Files Changed",
        *[f"- {f}" for f in files[:20]],
    ]

    if changes:
        description_lines.extend([
            "",
            "## Session Actions",
            *[f"- [{c.get('tool', '?')}] {c.get('description', c.get('file', ''))}"
              for c in changes[-10:]]
        ])

    description = "\n".join(description_lines)

    result = create_issue(summary, description)
    key = result.get("key", "UNKNOWN")
    print(f"✅ Created Jira issue: {key} — {summary}")

if __name__ == "__main__":
    main()
```

Make it executable:
```bash
chmod +x /Users/sebastiansabo/Documents/Git/JARVIS/.claude/hooks/jira_auto_sync.py
```

---

## Usage

### Option A — Manual (recommended to start):
In Claude Code, after any JARVIS session:
```
/jira-sync
```

Claude Code reads the command, analyzes the session, and intelligently creates/updates Jira tickets.

### Option B — Automatic:
Every time Claude Code finishes a response, the hook fires and logs to Jira. **Warning**: this creates a lot of tickets. Recommended only after you've tuned the script to your workflow.

### Hybrid (best approach):
Use Option A as the slash command, but modify it to also check for an open "sprint ticket" and append session notes as comments rather than creating new tickets every time.

---

## Recommended Jira Structure for JARVIS

```
Project: JARVIS (JAR)

Epic → Module
  JAR-EP1: Bank Statement Processing
  JAR-EP2: Invoicing & Billing
  JAR-EP3: e-Factura Integration
  JAR-EP4: Reconciliation Engine
  JAR-EP5: AI Agent
  JAR-EP6: Accounting Core
  JAR-EP7: Frontend/UI
  JAR-EP8: Infrastructure & DevOps

Labels:
  claude-code     — auto-generated from Claude Code
  auto-logged     — session auto-sync
  manual          — manually created
  bug-fix         — fix type
  feature         — feature type
  refactor        — refactor type
```

This way every auto-synced ticket links to the right Epic/module and your Jira board stays organized.
