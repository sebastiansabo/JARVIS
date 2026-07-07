#!/usr/bin/env python3
"""
JARVIS Layer A — deterministic git-push → Jira board sync.

Runs from .git/hooks/pre-push. Groups the pushed commits by conventional-commit
scope and creates one Task (Activitate secundara) per scope group under the
mapped Story (Activitate) / Workstream (Epic). Never blocks a push.
"""

import os
import re
import sys
import json
import base64
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

# ── Config (verified against live JAR project) ──
DOMAIN = os.environ.get("JIRA_DOMAIN", "")
EMAIL = os.environ.get("JIRA_EMAIL", "")
TOKEN = os.environ.get("JIRA_API_TOKEN", "")
PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "JAR")
ACCT_ID = "5bd1c8d1f8460347a10cb16d"
PROJECT_DIR = "/Users/sebastiansabo/Documents/Git/JARVIS"

TYPE_WORKSTREAM = "10285"
TYPE_ACTIVITATE = "10286"
TYPE_SUBTASK = "10287"
TRANSITION_IN_PROGRESS = "31"

# scope keyword -> (workstream_key, preferred_story_key or None to auto-create)
SCOPE_ROUTES = {
    "invoice": ("JAR-2", "JAR-16"),
    "facturare": ("JAR-2", "JAR-16"),
    "allocations": ("JAR-2", "JAR-16"),
    "reinvoice": ("JAR-2", "JAR-17"),
    "efactura": ("JAR-3", "JAR-21"),
    "anaf": ("JAR-3", "JAR-21"),
    "bank": ("JAR-4", "JAR-26"),
    "statement": ("JAR-4", "JAR-26"),
    "reconciliation": ("JAR-4", "JAR-26"),
    "hr": ("JAR-5", "JAR-28"),
    "employees": ("JAR-5", "JAR-28"),
    "bonus": ("JAR-5", "JAR-28"),
    "leave": ("JAR-5", "JAR-28"),
    "pontaje": ("JAR-5", None),
    "sincron": ("JAR-5", None),
    "connecteam": ("JAR-5", None),
    "ai": ("JAR-6", "JAR-31"),
    "ai_agent": ("JAR-6", "JAR-31"),
    "rag": ("JAR-6", "JAR-31"),
    "analytics": ("JAR-6", "JAR-31"),
    "chat": ("JAR-6", "JAR-31"),
    "frontend": ("JAR-7", "JAR-36"),
    "ui": ("JAR-7", "JAR-36"),
    "react": ("JAR-7", "JAR-36"),
    "auth": ("JAR-8", "JAR-41"),
    "permissions": ("JAR-8", "JAR-41"),
    "rbac": ("JAR-8", "JAR-41"),
    "profile": ("JAR-8", "JAR-41"),
    "users": ("JAR-8", "JAR-41"),
    "tag": ("JAR-9", "JAR-43"),
    "auto_tag": ("JAR-9", "JAR-43"),
    "notification": ("JAR-10", "JAR-46"),
    "email": ("JAR-10", "JAR-46"),
    "approval": ("JAR-63", None),
    "approvals": ("JAR-63", None),
    "db": ("JAR-1", "JAR-14"),
    "database": ("JAR-1", "JAR-14"),
    "migration": ("JAR-1", "JAR-14"),
    "deploy": ("JAR-1", "JAR-14"),
    "perf": ("JAR-1", "JAR-14"),
    "infra": ("JAR-1", "JAR-14"),
    "foi-parcurs": ("JAR-1", "JAR-14"),
}
DEFAULT_ROUTE = ("JAR-1", "JAR-14")

WORKSTREAM_LABEL = {
    "JAR-1": "Platform", "JAR-2": "Accounting", "JAR-3": "e-Factura",
    "JAR-4": "Bank", "JAR-5": "HR", "JAR-6": "AI Agent", "JAR-7": "Frontend",
    "JAR-8": "Users", "JAR-9": "Tags", "JAR-10": "Notifications",
    "JAR-62": "Approvals", "JAR-63": "Approvals",
}

# ordered (path fragment, scope) — first match wins
PATH_HINTS = [
    ("efactura", "efactura"),
    ("bank_statement", "bank"),
    ("reinvoice", "reinvoice"),
    ("allocations", "allocations"),
    ("invoice", "invoice"),
    ("ai_agent", "ai_agent"),
    ("auto_tag", "auto_tag"),
    ("notification", "notification"),
    ("permission", "permissions"),
    ("routes/auth", "auth"),
    ("frontend/src", "frontend"),
    ("migrations/", "migration"),
    ("database.py", "database"),
    ("pontaj", "pontaje"),
    ("sincron", "sincron"),
    ("connecteam", "connecteam"),
    ("foi_parcurs", "foi-parcurs"),
    ("foi-parcurs", "foi-parcurs"),
    ("/tag", "tag"),
    ("/hr/", "hr"),
]

AUTOCREATE_STORY_TITLE = {
    "pontaje": "Pontaje & timesheet sync",
    "sincron": "Sincron timesheet integration",
    "connecteam": "Connecteam permissions integration",
    "approval": "Approval engine follow-ups",
    "approvals": "Approval engine follow-ups",
}

_SCOPE_RE = re.compile(r"^\w+\(([^)]+)\)!?:")


def parse_commit_scope(subject):
    """Return the scope from a conventional-commit subject, lowercased, or None."""
    m = _SCOPE_RE.match((subject or "").strip())
    return m.group(1).strip().lower() if m else None


def path_hint_scope(files):
    """Infer a scope keyword from changed file paths, or None."""
    for f in files or []:
        for frag, scope in PATH_HINTS:
            if frag in f:
                return scope
    return None


def route_for_scope(scope):
    """Map a scope to (workstream_key, preferred_story_key)."""
    if scope and scope in SCOPE_ROUTES:
        return SCOPE_ROUTES[scope]
    return DEFAULT_ROUTE


def module_label(scope):
    """Human-readable module label derived from the mapped workstream."""
    workstream, _ = route_for_scope(scope)
    return WORKSTREAM_LABEL.get(workstream, "General")


def effective_scope(commit):
    """Best scope for a commit: subject scope, else path hint, else '__default__'."""
    return (
        parse_commit_scope(commit.get("subject", ""))
        or path_hint_scope(commit.get("files", []))
        or "__default__"
    )


def group_commits(commits):
    """Group commits into an insertion-ordered dict keyed by effective scope."""
    groups = {}
    for c in commits:
        groups.setdefault(effective_scope(c), []).append(c)
    return groups


def build_summary(scope, commits, now_str):
    """Build a <=80 char Task summary."""
    n = len(commits)
    plural = "s" if n != 1 else ""
    summary = f"[{module_label(scope)}] {n} commit{plural} — {now_str}"
    return summary[:80]


def build_description_adf(scope, commits, branch, now_str):
    """Build an Atlassian Document Format description body."""
    lines = [
        f"Auto-synced from git push — {now_str}",
        f"Branch: {branch}",
        f"Scope: {scope}",
        "",
        "Commits:",
    ]
    for c in commits:
        lines.append(f"- {c['sha'][:7]} {c['subject']}")
    text = "\n".join(lines)
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ],
    }


class Ledger:
    """Git-local JSON store of synced commit SHAs and auto-created stories."""

    def __init__(self, path):
        self.path = path
        self.data = self._load()

    def _load(self):
        data = {}
        try:
            with open(self.path) as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except Exception:
            # Corrupt ledger: preserve it for inspection instead of silently
            # discarding it, then fall back to an empty ledger.
            try:
                os.replace(self.path, self.path + ".corrupt")
            except Exception:
                pass
            data = {}
        data.setdefault("commits", {})
        data.setdefault("stories", {})
        return data

    def is_synced(self, sha):
        return sha in self.data["commits"]

    def mark_commit(self, sha, issue_key):
        self.data["commits"][sha] = issue_key

    def story_for(self, scope):
        return self.data["stories"].get(scope)

    def set_story(self, scope, issue_key):
        self.data["stories"][scope] = issue_key

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass


class JiraClient:
    """Thin Jira REST v3 client with an injectable transport for testing."""

    def __init__(self, domain, email, token, transport=None, account_id=ACCT_ID):
        self.domain = domain
        self.email = email
        self.token = token
        self.account_id = account_id
        self.transport = transport or self._default_transport

    def _default_transport(self, method, endpoint, data=None):
        url = f"https://{self.domain}/rest/api/3{endpoint}"
        auth = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode())
            except Exception:
                return {"_error": str(e)}
        except Exception as e:
            return {"_error": str(e)}

    def find_story(self, workstream_key, title):
        safe = title.replace("\\", " ").replace('"', " ")
        jql = (
            f'project={PROJECT_KEY} AND issuetype="Activitate" '
            f'AND parent={workstream_key} AND summary~"{safe}"'
        )
        resp = self.transport(
            "POST", "/search/jql",
            {"jql": jql, "maxResults": 1, "fields": ["summary"]},
        )
        issues = resp.get("issues", []) if isinstance(resp, dict) else []
        return issues[0]["key"] if issues else None

    def create_story(self, workstream_key, title):
        data = {
            "fields": {
                "project": {"key": PROJECT_KEY},
                "issuetype": {"id": TYPE_ACTIVITATE},
                "parent": {"key": workstream_key},
                "summary": title[:80],
                "labels": ["claude-code"],
            }
        }
        return self.transport("POST", "/issue", data).get("key")

    def create_task(self, story_key, summary, description_adf):
        data = {
            "fields": {
                "project": {"key": PROJECT_KEY},
                "issuetype": {"id": TYPE_SUBTASK},
                "parent": {"key": story_key},
                "summary": summary,
                "description": description_adf,
                "labels": ["claude-code"],
                "assignee": {"accountId": self.account_id},
            }
        }
        return self.transport("POST", "/issue", data).get("key")

    def transition_in_progress(self, key):
        self.transport(
            "POST", f"/issue/{key}/transitions",
            {"transition": {"id": TRANSITION_IN_PROGRESS}},
        )


def resolve_story(client, ledger, scope, route):
    """Return the Story key for a scope: preferred -> cached -> find -> create."""
    workstream, preferred = route
    if preferred:
        return preferred
    cached = ledger.story_for(scope)
    if cached:
        return cached
    safe_scope = re.sub(r"[^\w \-]", "", scope or "")
    title = AUTOCREATE_STORY_TITLE.get(scope, f"{safe_scope.capitalize()} work")
    key = client.find_story(workstream, title) or client.create_story(workstream, title)
    if key:
        ledger.set_story(scope, key)
    return key


def _run_git(args):
    try:
        r = subprocess.run(
            ["git"] + args, capture_output=True, text=True, cwd=PROJECT_DIR
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _is_zero(sha):
    return set(sha) == {"0"}


def get_pushed_commits(stdin_text, run_git=None):
    """Parse pre-push stdin into commit dicts (newest-first, no merges)."""
    run_git = run_git or _run_git
    ranges = []
    for line in (stdin_text or "").strip().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if _is_zero(local_sha):
            continue  # branch deletion
        if _is_zero(remote_sha):
            ranges.append([local_sha, "--not", "--remotes"])
        else:
            ranges.append([f"{remote_sha}..{local_sha}"])
    if not ranges:
        if (stdin_text or "").strip():
            return []  # only deletions -> nothing to sync
        ranges = [["-n", "5", "HEAD"]]  # manual/dry-run fallback

    seen, ordered = set(), []
    for rng in ranges:
        for sha in run_git(["rev-list", "--no-merges"] + rng).splitlines():
            sha = sha.strip()
            if sha and sha not in seen:
                seen.add(sha)
                ordered.append(sha)

    commits = []
    for sha in ordered:
        subject = run_git(["show", "-s", "--format=%s", sha]).strip()
        files = [
            f for f in run_git(["show", "--name-only", "--format=", sha]).splitlines()
            if f.strip()
        ]
        commits.append({"sha": sha, "subject": subject, "files": files})
    return commits


def ledger_path(run_git=None):
    run_git = run_git or _run_git
    gitdir = run_git(["rev-parse", "--git-common-dir"]).strip() or ".git"
    if not os.path.isabs(gitdir):
        gitdir = os.path.join(PROJECT_DIR, gitdir)
    return os.path.join(gitdir, "jira-sync-ledger.json")


def main(argv, stdin_text=None, overrides=None):
    """Entry point. Always returns 0 — a push must never fail on Jira."""
    overrides = overrides or {}
    dry = "--dry-run" in (argv or [])
    domain = overrides.get("domain", DOMAIN)
    email = overrides.get("email", EMAIL)
    token = overrides.get("token", TOKEN)
    run_git = overrides.get("run_git", _run_git)

    if not all([domain, email, token]):
        return 0
    try:
        commits = get_pushed_commits(stdin_text or "", run_git=run_git)
        ledger = overrides.get("ledger") or Ledger(ledger_path(run_git))
        fresh = [c for c in commits if not ledger.is_synced(c["sha"])]
        if not fresh:
            return 0

        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip() or "?"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        client = overrides.get("client") or JiraClient(domain, email, token)

        for scope, group in group_commits(fresh).items():
            route = route_for_scope(scope)
            summary = build_summary(scope, group, now_str)
            if dry:
                story = route[1] or "(auto-create)"
                print(f"[dry-run] {story} ← {len(group)} commit(s) [{scope}]: {summary}")
                continue
            story = resolve_story(client, ledger, scope, route)
            if not story:
                print(f"Jira: could not resolve story for scope '{scope}'")
                continue
            key = client.create_task(story, summary, build_description_adf(scope, group, branch, now_str))
            if key:
                client.transition_in_progress(key)
                for c in group:
                    ledger.mark_commit(c["sha"], key)
                ledger.save()
                print(f"Jira: {key} ← {len(group)} commit(s) [{scope}] under {story}")
            else:
                print(f"Jira: failed to create task for scope '{scope}'")
        if not dry:
            ledger.save()
    except Exception as e:
        print(f"Jira sync: skipped ({e})")
    return 0


if __name__ == "__main__":
    _stdin = "" if sys.stdin.isatty() else sys.stdin.read()
    sys.exit(main(sys.argv[1:], stdin_text=_stdin))
