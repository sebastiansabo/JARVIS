# Commit → Jira Sync (Hybrid) — Design

**Date:** 2026-07-07
**Status:** Approved, ready for implementation plan
**Repo:** JARVIS (`/Users/sebastiansabo/Documents/Git/JARVIS`), branch `dev`

## Goal

Automatically place git commits onto the Jira **JAR** board in the project's
epic → story → task structure, driven from the VS Code / Claude Code workflow.
Every push is reflected on the board without manual ticket creation.

## Board structure (verified against live JAR project)

The project uses custom Romanian issue types. The user's "epic / story / task"
maps onto them as:

| User term | JARVIS issue type | Type id | Parent |
|-----------|-------------------|---------|--------|
| Epic      | **Workstream**            | 10285 | (top level) |
| Story     | **Activitate**            | 10286 | Workstream |
| Task      | **Activitate secundară**  | 10287 | Activitate (subtask) |

Existing top-level Workstreams: JAR-1 Platform & Infrastructure, JAR-2 Accounting
& Invoice, JAR-3 e-Factura ANAF, JAR-4 Bank Statement, JAR-5 HR Events & Bonuses,
JAR-6 AI Agent & Analytics, JAR-7 React Frontend Migration, JAR-8 User Management
& Permissions, JAR-9 Tagging & Auto-Classification, JAR-10 Email Notification,
JAR-62/JAR-63 Universal Approval Engine.

## Architecture — two layers, one source of truth

### Layer A — Deterministic (built now, works today)

```
git PRE-PUSH hook  →  .claude/hooks/jira_commit_sync.py  →  Jira REST v3
```

- Fires on every `git push`; reads the pushed commit range from stdin.
- Groups the push's commits by mapped scope; creates **one Task
  (Activitate secundară) per scope group** under the scope's Story, under its
  Workstream.
- Uses Jira REST API v3 with Basic auth (creds already in env:
  `JIRA_DOMAIN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY=JAR`).
- No Claude / MCP required. Works for commits from any tool or person.

### Layer B — Smart / optional (graceful no-op until authorized)

```
Claude STOP hook  →  .claude/hooks/jira_session_enhance.py  →  Atlassian MCP
```

- Runs only when Claude is driving **and** the Atlassian MCP connector is
  authenticated (authorized by the user via claude.ai connector settings; cannot
  be authorized from a non-interactive session).
- Reads the ledger, improves grouping/summaries, creates missing Workstreams,
  re-files misclassified tasks. **Never creates duplicates** — the git hook is
  the sole creator; Layer B only edits existing issues referenced in the ledger.
- If the MCP is unavailable, it exits 0 as a no-op. Everything still works via
  Layer A.

## Placement model

Per push:
1. Collect non-merge commits in the pushed range not already in the ledger.
2. Determine each commit's **scope** from the conventional-commit subject
   (`type(scope): subject`); fall back to changed-file paths when no scope.
3. Group commits by scope → Workstream / Story mapping (below).
4. For each group: ensure the Story exists (find or auto-create under the
   Workstream), then create one Task listing the group's commits.
5. Record `sha → issueKey` and `scope → storyKey` in the ledger.

One push touching two modules produces two Tasks under two Stories — faithful to
the epic/story/task hierarchy, not a single blob.

## De-duplication across dev → staging → main

The strict git flow pushes the same SHAs multiple times. The **ledger**
(`.git/jira-sync-ledger.json`, git-local, not committed) records every synced
SHA. The first push (to staging) creates the Task; the later push (to main) sees
the SHAs already present and skips them. Idempotent by construction.

## Scope → Workstream / Story map

Primary signal: commit-message scope. Fallback: changed file paths.

| Scope keywords | Workstream | Preferred Story | If no story |
|---|---|---|---|
| invoice, facturare, allocations | JAR-2 | JAR-16 | — |
| reinvoice | JAR-2 | JAR-17 | — |
| efactura, anaf | JAR-3 | JAR-21 | — |
| bank, statement, reconciliation | JAR-4 | JAR-26 | — |
| hr, employees, bonus, leave | JAR-5 | JAR-28 | — |
| pontaje, sincron, connecteam | JAR-5 | (auto-create) | create `[scope] work` story under JAR-5 |
| ai, ai_agent, rag, analytics, chat | JAR-6 | JAR-31 | — |
| frontend, ui, react | JAR-7 | JAR-36 | — |
| auth, permissions, rbac, profile, users | JAR-8 | JAR-41 | — |
| tag, auto_tag | JAR-9 | JAR-43 | — |
| notification, email | JAR-10 | JAR-46 | — |
| approval, approvals | JAR-63 | (auto-create) | create under JAR-63 |
| db, migration, deploy, perf, infra, foi-parcurs | JAR-1 | JAR-14 | — |

**Decisions locked:** pontaje / sincron / connecteam stay under **JAR-5 HR**
(auto-create a story such as "Pontaje & timesheet"); **foi-parcurs** stays under
**JAR-1 Platform** (JAR-14). No new Workstreams are created by default.

Unknown scope → JAR-1 Platform (JAR-14), logged as unmapped for later review.

## Task content

Each created Task (Activitate secundară):
- **summary**: `[<ModuleLabel>] <n> commit(s) — YYYY-MM-DD HH:MM` (≤ 80 chars)
- **description** (ADF): synced-from note, branch, short commit list
  (`abc1234 fix(pontaje): …`), file-count.
- **labels**: `["claude-code"]`
- **assignee**: the configured account id
- transitioned to **In Progress** after creation.

## Error handling & safety

- **A push must never fail because of Jira.** All Jira/network work is wrapped;
  any failure logs a warning and the hook exits 0.
- Silent no-op if `JIRA_*` env vars are unset (matches current behavior).
- Merge commits skipped.
- Read + create only. **Never deletes Jira issues.** No production DB access.
- Ledger writes are best-effort and local to `.git/`.

## Files

- **New:** `.claude/hooks/jira_commit_sync.py` — Layer A core (REST).
- **New:** `.git/hooks/pre-push` — invokes the sync (append if a pre-push
  already exists).
- **New:** `.claude/hooks/jira_session_enhance.py` — Layer B (MCP-optional
  no-op until connector authorized).
- **Edit:** `.claude/settings.local.json` — repoint the `Stop` hook from
  `jira_auto_sync.py` to `jira_session_enhance.py`.
- **Retire:** `.claude/hooks/jira_auto_sync.py` → keep as `.bak`.

## Out of scope

- Authorizing the Atlassian MCP connector (user action, browser OAuth).
- Closing/transitioning Tasks to Done (commits mark work In Progress only).
- Back-filling historical commits already on the board.
