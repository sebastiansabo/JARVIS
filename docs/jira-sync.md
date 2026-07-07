# Jira Sync — Push Session Work to Jira

You are a development session summarizer. Analyze what was accomplished in THIS Claude Code session and push structured updates to Jira via REST API.

## Step 1: Gather Session Context

Run ALL of these to understand what happened:

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS

# Recent commits (last 4 hours)
git log --oneline --since="$(date -v-4H +%Y-%m-%dT%H:%M:%S)" --no-merges 2>/dev/null || git log --oneline -10

# Modified files
git diff --name-only HEAD~5 2>/dev/null || git status --short

# Change log
cat .claude/jarvis_changes.jsonl 2>/dev/null | tail -20

# Test status
python -m pytest --tb=no -q 2>&1 | tail -5
```

## Step 2: Search Existing Jira Tickets First

Before creating anything, check what already exists:

```bash
curl -s -X POST \
  "https://${JIRA_DOMAIN}/rest/api/3/search/jql" \
  -H "Authorization: Basic $(echo -n "${JIRA_EMAIL}:${JIRA_API_TOKEN}" | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "jql": "project='"${JIRA_PROJECT_KEY}"' AND status != Done ORDER BY updated DESC",
    "maxResults": 20,
    "fields": ["summary","status","labels","updated"]
  }'
```

If an open ticket covers the same module/feature you worked on → ADD A COMMENT to it instead of creating a new ticket.

## Step 3: Classify & Group Changes

Group related commits into ONE logical unit. Classify each:
- **feat**: New feature or capability
- **fix**: Bug fix
- **refactor**: Code restructuring
- **test**: Test additions/modifications
- **docs**: Documentation
- **chore**: Maintenance, config, dependencies

Detect JARVIS module from file paths:
- `bank_statement/` → Bank Statements
- `invoice/` → Invoicing
- `efactura/` → e-Factura
- `reconcil` → Reconciliation
- `accounting/` → Accounting Core
- `ai_agent/` → AI Agent
- `auth/` → Auth
- `frontend/` or `src/app/` → Frontend
- `tests/` → Testing

## Step 4: Execute Jira Updates

### Create new issue (only if no matching open ticket):
```bash
curl -s -X POST \
  "https://${JIRA_DOMAIN}/rest/api/3/issue" \
  -H "Authorization: Basic $(echo -n "${JIRA_EMAIL}:${JIRA_API_TOKEN}" | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "'"${JIRA_PROJECT_KEY}"'"},
      "summary": "[Module] type: concise description",
      "description": {
        "type": "doc",
        "version": 1,
        "content": [
          {
            "type": "paragraph",
            "content": [{"type": "text", "text": "DESCRIPTION WITH: what changed, files affected, test status"}]
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
          "content": [{"type": "text", "text": "Session update (DATE):\n- What was done\n- Files: list\n- Tests: pass/fail status"}]
        }
      ]
    }
  }'
```

## Step 5: Output Summary

After all API calls complete, print:

```
━━━ JIRA SYNC COMPLETE ━━━
Created: JAR-XX — [summary]
Updated: JAR-YY — added comment
Skipped: [reason]
━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Rules
- SEARCH FIRST. Never create duplicates.
- Group related commits into ONE ticket. Don't create ticket-per-commit.
- Prefix summaries with module: `[Bank Statements] feat: Add UniCredit PDF parser`
- Include changed file paths in description.
- Include test pass/fail count.
- Be concise — Jira is for scanning, not reading.
- If env vars are missing, tell the user to configure them and exit.
