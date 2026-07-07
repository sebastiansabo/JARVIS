# Commit → Jira Sync (Layer A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A git `pre-push` hook that places each push's commits onto the Jira JAR board as Tasks (Activitate secundară) under the correct Story (Activitate) / Workstream (Epic), deterministically and without ever blocking a push.

**Architecture:** A single self-contained Python module `.claude/hooks/jira_commit_sync.py` with pure functions (commit parsing, scope→board routing, grouping, payload building), a git-local JSON ledger for de-duplication, and a `JiraClient` with an **injectable transport** so all logic is unit-testable without network. A thin `.git/hooks/pre-push` shell script invokes it. The existing `Stop` hook is repointed to a no-op Layer B stub.

**Tech Stack:** Python 3 stdlib only (`urllib.request`, `json`, `base64`, `re`, `subprocess`), pytest for tests. Jira REST API v3.

## Global Constraints

- Python 3 standard library only — no third-party imports in the hook module.
- **A push must NEVER fail because of Jira.** All network/Jira work is wrapped; any failure logs a warning and the process exits 0.
- Silent no-op (exit 0) if any of `JIRA_DOMAIN`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars are unset.
- **Read + create only. NEVER delete or transition-to-Done any Jira issue.** No production DB access.
- Jira issue type ids (verified against live JAR project): Workstream `10285`, Activitate `10286`, Activitate secundară `10287`. "In Progress" transition id `31`.
- Project key `JAR`. Assignee account id `5bd1c8d1f8460347a10cb16d`. New issues carry label `claude-code`.
- Ledger lives at `<git-dir>/jira-sync-ledger.json` (git-local, never committed).
- Run all tests with: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v` from repo root.
- Work on branch `dev` only. Do not push during implementation (that would fire the hook we are building).
- Commit message trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

- **Create** `.claude/hooks/jira_commit_sync.py` — Layer A core (all logic + `main`).
- **Create** `tests/test_jira_commit_sync.py` — unit tests (loads the module by path).
- **Create** `.git/hooks/pre-push` — shell shim invoking the module (chmod +x).
- **Create** `.claude/hooks/jira_session_enhance.py` — Layer B no-op stub.
- **Modify** `.claude/settings.local.json` — repoint the `Stop` hook command.
- **Rename** `.claude/hooks/jira_auto_sync.py` → `.claude/hooks/jira_auto_sync.py.bak` (retire).

Test files load the hook module by absolute path (it lives outside `tests/`). Every test file starts with this loader:

```python
import importlib.util, pathlib

_MOD = pathlib.Path(__file__).resolve().parent.parent / ".claude/hooks/jira_commit_sync.py"
_spec = importlib.util.spec_from_file_location("jira_commit_sync", _MOD)
jcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jcs)
```

---

## Task 1: Module scaffold + commit-scope parsing + board routing

**Files:**
- Create: `.claude/hooks/jira_commit_sync.py`
- Test: `tests/test_jira_commit_sync.py`

**Interfaces:**
- Produces: `parse_commit_scope(subject: str) -> str | None`, `path_hint_scope(files: list[str]) -> str | None`, `route_for_scope(scope: str | None) -> tuple[str, str | None]` (returns `(workstream_key, preferred_story_key)`), `module_label(scope: str | None) -> str`, and module constants `SCOPE_ROUTES`, `DEFAULT_ROUTE`, `WORKSTREAM_LABEL`, `PATH_HINTS`, `AUTOCREATE_STORY_TITLE`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_jira_commit_sync.py`:

```python
import importlib.util, pathlib

_MOD = pathlib.Path(__file__).resolve().parent.parent / ".claude/hooks/jira_commit_sync.py"
_spec = importlib.util.spec_from_file_location("jira_commit_sync", _MOD)
jcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jcs)


def test_parse_commit_scope_extracts_scope():
    assert jcs.parse_commit_scope("fix(pontaje): read holidays") == "pontaje"
    assert jcs.parse_commit_scope("feat(foi-parcurs): add form") == "foi-parcurs"
    assert jcs.parse_commit_scope("docs(hr)!: breaking") == "hr"


def test_parse_commit_scope_none_without_scope():
    assert jcs.parse_commit_scope("chore: bump deps") is None
    assert jcs.parse_commit_scope("random text") is None


def test_route_for_scope_known_and_default():
    assert jcs.route_for_scope("reinvoice") == ("JAR-2", "JAR-17")
    assert jcs.route_for_scope("pontaje") == ("JAR-5", None)
    assert jcs.route_for_scope("totally-unknown") == ("JAR-1", "JAR-14")
    assert jcs.route_for_scope(None) == ("JAR-1", "JAR-14")


def test_path_hint_scope_from_files():
    assert jcs.path_hint_scope(["jarvis/repos/efactura/x.py"]) == "efactura"
    assert jcs.path_hint_scope(["jarvis/frontend/src/App.tsx"]) == "frontend"
    assert jcs.path_hint_scope(["README.md"]) is None


def test_module_label_maps_workstream():
    assert jcs.module_label("pontaje") == "HR"
    assert jcs.module_label("reinvoice") == "Accounting"
    assert jcs.module_label("totally-unknown") == "Platform"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v`
Expected: FAIL — `ModuleNotFoundError` / `FileNotFoundError` (module file doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `.claude/hooks/jira_commit_sync.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/jira_commit_sync.py tests/test_jira_commit_sync.py
git commit -m "feat(jira-sync): commit-scope parsing and board routing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Commit grouping + summary + ADF description builders

**Files:**
- Modify: `.claude/hooks/jira_commit_sync.py`
- Test: `tests/test_jira_commit_sync.py`

**Interfaces:**
- Consumes: `parse_commit_scope`, `path_hint_scope`, `route_for_scope`, `module_label` from Task 1.
- Produces: `effective_scope(commit: dict) -> str` (returns `"__default__"` when nothing matches), `group_commits(commits: list[dict]) -> dict[str, list[dict]]`, `build_summary(scope: str, commits: list[dict], now_str: str) -> str`, `build_description_adf(scope: str, commits: list[dict], branch: str, now_str: str) -> dict`. A `commit` dict has keys `sha`, `subject`, `files`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_jira_commit_sync.py`:

```python
def _commit(sha, subject, files=None):
    return {"sha": sha, "subject": subject, "files": files or []}


def test_effective_scope_prefers_subject_then_path_then_default():
    assert jcs.effective_scope(_commit("a1", "fix(hr): x")) == "hr"
    assert jcs.effective_scope(_commit("a2", "misc change", ["jarvis/repos/efactura/y.py"])) == "efactura"
    assert jcs.effective_scope(_commit("a3", "misc change", ["README.md"])) == "__default__"


def test_group_commits_buckets_by_scope():
    commits = [
        _commit("a1", "fix(pontaje): 1"),
        _commit("a2", "feat(facturare): 2"),
        _commit("a3", "fix(pontaje): 3"),
    ]
    groups = jcs.group_commits(commits)
    assert set(groups.keys()) == {"pontaje", "facturare"}
    assert [c["sha"] for c in groups["pontaje"]] == ["a1", "a3"]


def test_build_summary_labels_and_truncates():
    s = jcs.build_summary("pontaje", [_commit("a1", "x"), _commit("a2", "y")], "2026-07-07 21:00")
    assert s.startswith("[HR] 2 commits — 2026-07-07 21:00")
    assert len(s) <= 80


def test_build_summary_singular():
    s = jcs.build_summary("reinvoice", [_commit("a1", "x")], "2026-07-07 21:00")
    assert s.startswith("[Accounting] 1 commit — ")


def test_build_description_adf_lists_commits():
    adf = jcs.build_description_adf(
        "pontaje", [_commit("abcdef1234", "fix(pontaje): read holidays")],
        "dev", "2026-07-07 21:00")
    assert adf["type"] == "doc" and adf["version"] == 1
    text = adf["content"][0]["content"][0]["text"]
    assert "Branch: dev" in text
    assert "abcdef1 fix(pontaje): read holidays" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v -k "effective_scope or group_commits or build_summary or build_description"`
Expected: FAIL — `AttributeError: module ... has no attribute 'effective_scope'`.

- [ ] **Step 3: Write minimal implementation**

Append to `.claude/hooks/jira_commit_sync.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/jira_commit_sync.py tests/test_jira_commit_sync.py
git commit -m "feat(jira-sync): commit grouping and Jira payload builders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: De-duplication ledger

**Files:**
- Modify: `.claude/hooks/jira_commit_sync.py`
- Test: `tests/test_jira_commit_sync.py`

**Interfaces:**
- Produces: `class Ledger` with `__init__(self, path)`, `is_synced(sha) -> bool`, `mark_commit(sha, issue_key)`, `story_for(scope) -> str | None`, `set_story(scope, issue_key)`, `save()`. Missing/corrupt file loads as empty. `save()` is best-effort (never raises).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_jira_commit_sync.py`:

```python
def test_ledger_roundtrip(tmp_path):
    p = tmp_path / "ledger.json"
    led = jcs.Ledger(str(p))
    assert led.is_synced("sha1") is False
    led.mark_commit("sha1", "JAR-900")
    led.set_story("pontaje", "JAR-901")
    led.save()

    reloaded = jcs.Ledger(str(p))
    assert reloaded.is_synced("sha1") is True
    assert reloaded.story_for("pontaje") == "JAR-901"
    assert reloaded.story_for("missing") is None


def test_ledger_handles_missing_and_corrupt(tmp_path):
    assert jcs.Ledger(str(tmp_path / "nope.json")).is_synced("x") is False
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    led = jcs.Ledger(str(bad))
    assert led.is_synced("x") is False
    led.save()  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v -k ledger`
Expected: FAIL — `AttributeError: module ... has no attribute 'Ledger'`.

- [ ] **Step 3: Write minimal implementation**

Append to `.claude/hooks/jira_commit_sync.py`:

```python
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
        except Exception:
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
            with open(self.path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v -k ledger`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/jira_commit_sync.py tests/test_jira_commit_sync.py
git commit -m "feat(jira-sync): add de-duplication ledger

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: JiraClient (injectable transport) + story resolution

**Files:**
- Modify: `.claude/hooks/jira_commit_sync.py`
- Test: `tests/test_jira_commit_sync.py`

**Interfaces:**
- Consumes: `Ledger` (Task 3), `AUTOCREATE_STORY_TITLE`, `TYPE_*`, `ACCT_ID`, `TRANSITION_IN_PROGRESS` (Task 1).
- Produces:
  - `class JiraClient(domain, email, token, transport=None, account_id=ACCT_ID)` with `find_story(workstream_key, title) -> str | None`, `create_story(workstream_key, title) -> str | None`, `create_task(story_key, summary, description_adf) -> str | None`, `transition_in_progress(key) -> None`. `transport(method, endpoint, data) -> dict` is injectable; default uses `urllib`.
  - `resolve_story(client, ledger, scope, route) -> str | None` — returns preferred story, else ledger-cached, else finds/creates one and caches it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_jira_commit_sync.py`:

```python
class FakeTransport:
    """Records calls; mints JAR-9NN keys for POST /issue; canned search."""

    def __init__(self, search_issues=None):
        self.calls = []
        self.search_issues = search_issues or []
        self._counter = 0

    def __call__(self, method, endpoint, data=None):
        self.calls.append((method, endpoint, data))
        if endpoint == "/search/jql":
            return {"issues": self.search_issues}
        if endpoint == "/issue" and method == "POST":
            self._counter += 1
            return {"key": f"JAR-9{self._counter:02d}"}
        return {}


def test_create_task_payload_shape():
    ft = FakeTransport()
    client = jcs.JiraClient("d", "e", "t", transport=ft)
    key = client.create_task("JAR-28", "[HR] 1 commit — now", {"type": "doc"})
    assert key == "JAR-901"
    method, endpoint, data = ft.calls[-1]
    assert (method, endpoint) == ("POST", "/issue")
    f = data["fields"]
    assert f["issuetype"]["id"] == "10287"
    assert f["parent"]["key"] == "JAR-28"
    assert f["assignee"]["accountId"] == jcs.ACCT_ID
    assert f["labels"] == ["claude-code"]


def test_resolve_story_uses_preferred():
    ft = FakeTransport()
    client = jcs.JiraClient("d", "e", "t", transport=ft)
    led = jcs.Ledger("/tmp/does-not-matter-unused")
    key = jcs.resolve_story(client, led, "reinvoice", ("JAR-2", "JAR-17"))
    assert key == "JAR-17"
    assert ft.calls == []  # no network when a preferred story exists


def test_resolve_story_autocreates_and_caches(tmp_path):
    ft = FakeTransport(search_issues=[])  # not found -> create
    client = jcs.JiraClient("d", "e", "t", transport=ft)
    led = jcs.Ledger(str(tmp_path / "l.json"))
    key = jcs.resolve_story(client, led, "pontaje", ("JAR-5", None))
    assert key == "JAR-901"
    assert led.story_for("pontaje") == "JAR-901"
    # created a story (Activitate) under JAR-5 with the mapped title
    create_calls = [c for c in ft.calls if c[1] == "/issue"]
    fields = create_calls[-1][2]["fields"]
    assert fields["issuetype"]["id"] == "10286"
    assert fields["parent"]["key"] == "JAR-5"
    assert fields["summary"] == "Pontaje & timesheet sync"


def test_resolve_story_reuses_ledger_cache():
    ft = FakeTransport()
    client = jcs.JiraClient("d", "e", "t", transport=ft)
    led = jcs.Ledger("/tmp/unused-cache-test")
    led.set_story("sincron", "JAR-555")
    key = jcs.resolve_story(client, led, "sincron", ("JAR-5", None))
    assert key == "JAR-555"
    assert ft.calls == []  # cache hit, no network


def test_resolve_story_finds_existing_before_creating(tmp_path):
    ft = FakeTransport(search_issues=[{"key": "JAR-300"}])
    client = jcs.JiraClient("d", "e", "t", transport=ft)
    led = jcs.Ledger(str(tmp_path / "l.json"))
    key = jcs.resolve_story(client, led, "connecteam", ("JAR-5", None))
    assert key == "JAR-300"
    assert led.story_for("connecteam") == "JAR-300"
    assert all(c[0:2] != ("POST", "/issue") for c in ft.calls)  # never created
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v -k "payload or resolve_story"`
Expected: FAIL — `AttributeError: module ... has no attribute 'JiraClient'`.

- [ ] **Step 3: Write minimal implementation**

Append to `.claude/hooks/jira_commit_sync.py`:

```python
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
        safe = title.replace('"', " ")
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
    title = AUTOCREATE_STORY_TITLE.get(scope, f"{scope.capitalize()} work")
    key = client.find_story(workstream, title) or client.create_story(workstream, title)
    if key:
        ledger.set_story(scope, key)
    return key
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v`
Expected: PASS (17 tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/jira_commit_sync.py tests/test_jira_commit_sync.py
git commit -m "feat(jira-sync): JiraClient with injectable transport and story resolution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Pushed-commit extraction + `main()` orchestration + `--dry-run`

**Files:**
- Modify: `.claude/hooks/jira_commit_sync.py`
- Test: `tests/test_jira_commit_sync.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `get_pushed_commits(stdin_text: str, run_git=None) -> list[dict]` — parses pre-push stdin lines (`<local_ref> <local_sha> <remote_ref> <remote_sha>`), computes commit ranges, returns commit dicts (`sha`, `subject`, `files`), newest-first, no merges. Empty stdin → falls back to last 5 commits of `HEAD`. `run_git(args: list[str]) -> str` is injectable.
  - `main(argv: list[str], stdin_text: str | None = None) -> int` — env-guarded, ledger-deduped, groups + creates tasks, honors `--dry-run`. Always returns 0.
  - Module `__main__` block calling `sys.exit(main(sys.argv[1:], sys.stdin.read() if not sys.stdin.isatty() else ""))`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_jira_commit_sync.py`:

```python
ZERO = "0" * 40


def _fake_git(rev_list_map, subjects, files_map):
    """Build a run_git stub. rev_list_map: tuple(args)->newline SHAs."""
    def run_git(args):
        if args[:2] == ["rev-list"]:
            return rev_list_map.get(tuple(args), "")
        if args[:2] == ["show", "-s"]:
            return subjects.get(args[-1], "")
        if args[:1] == ["show"] and "--name-only" in args:
            return files_map.get(args[-1], "")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return "dev"
        return ""
    return run_git


def test_get_pushed_commits_parses_range():
    remote = "1" * 40
    local = "2" * 40
    stdin = f"refs/heads/dev {local} refs/heads/dev {remote}\n"
    rev_list = {("rev-list", "--no-merges", f"{remote}..{local}"): "shaA\nshaB"}
    subjects = {"shaA": "fix(hr): a", "shaB": "feat(facturare): b"}
    files = {"shaA": "", "shaB": ""}
    commits = jcs.get_pushed_commits(stdin, run_git=_fake_git(rev_list, subjects, files))
    assert [c["sha"] for c in commits] == ["shaA", "shaB"]
    assert commits[0]["subject"] == "fix(hr): a"


def test_get_pushed_commits_skips_branch_deletion():
    stdin = f"(delete) {ZERO} refs/heads/old {'3'*40}\n"
    commits = jcs.get_pushed_commits(stdin, run_git=_fake_git({}, {}, {}))
    assert commits == []


def test_get_pushed_commits_empty_stdin_falls_back_to_head():
    rev_list = {("rev-list", "--no-merges", "-n", "5", "HEAD"): "shaH"}
    subjects = {"shaH": "chore: h"}
    commits = jcs.get_pushed_commits("", run_git=_fake_git(rev_list, subjects, {"shaH": ""}))
    assert [c["sha"] for c in commits] == ["shaH"]


def test_main_dry_run_creates_nothing(capsys):
    remote = "1" * 40
    local = "2" * 40
    stdin = f"refs/heads/dev {local} refs/heads/dev {remote}\n"
    rev_list = {("rev-list", "--no-merges", f"{remote}..{local}"): "shaA"}
    run_git = _fake_git(rev_list, {"shaA": "fix(pontaje): x"}, {"shaA": ""})
    rc = jcs.main(["--dry-run"], stdin_text=stdin,
                  overrides={"run_git": run_git, "domain": "d", "email": "e", "token": "t"})
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out.lower()


def test_main_creates_tasks_and_dedups(tmp_path, capsys):
    remote = "1" * 40
    local = "2" * 40
    stdin = f"refs/heads/dev {local} refs/heads/dev {remote}\n"
    rev_list = {("rev-list", "--no-merges", f"{remote}..{local}"): "shaA\nshaB"}
    run_git = _fake_git(
        rev_list,
        {"shaA": "fix(pontaje): a", "shaB": "feat(facturare): b"},
        {"shaA": "", "shaB": ""},
    )
    ft = FakeTransport(search_issues=[])
    client = jcs.JiraClient("d", "e", "t", transport=ft)
    ledger = jcs.Ledger(str(tmp_path / "l.json"))

    rc = jcs.main([], stdin_text=stdin, overrides={
        "run_git": run_git, "client": client, "ledger": ledger,
        "domain": "d", "email": "e", "token": "t",
    })
    assert rc == 0
    created = [c for c in ft.calls if c[0:2] == ("POST", "/issue")]
    # 1 auto-created story (pontaje) + 2 tasks = 3 creates
    assert len(created) == 3
    assert ledger.is_synced("shaA") and ledger.is_synced("shaB")

    # second identical push -> everything already synced -> no new creates
    ft.calls.clear()
    rc2 = jcs.main([], stdin_text=stdin, overrides={
        "run_git": run_git, "client": client, "ledger": ledger,
        "domain": "d", "email": "e", "token": "t",
    })
    assert rc2 == 0
    assert [c for c in ft.calls if c[0:2] == ("POST", "/issue")] == []


def test_main_noop_without_creds():
    assert jcs.main([], stdin_text="", overrides={"domain": "", "email": "", "token": ""}) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v -k "pushed_commits or main_"`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_pushed_commits'`.

- [ ] **Step 3: Write minimal implementation**

Append to `.claude/hooks/jira_commit_sync.py`:

```python
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
    gitdir = run_git(["rev-parse", "--git-dir"]).strip() or ".git"
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
```

> Note: `datetime.now()` is used at runtime in `main`. Tests never assert on the exact timestamp, so no injection is needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v`
Expected: PASS (24 tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/jira_commit_sync.py tests/test_jira_commit_sync.py
git commit -m "feat(jira-sync): pushed-commit extraction and main orchestration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Wire the pre-push hook, retire old Stop hook, add Layer B stub, verify

**Files:**
- Create: `.git/hooks/pre-push`
- Create: `.claude/hooks/jira_session_enhance.py`
- Modify: `.claude/settings.local.json`
- Rename: `.claude/hooks/jira_auto_sync.py` → `.claude/hooks/jira_auto_sync.py.bak`

**Interfaces:**
- Consumes: `.claude/hooks/jira_commit_sync.py` `main` via CLI.

- [ ] **Step 1: Create the Layer B no-op stub**

Create `.claude/hooks/jira_session_enhance.py`:

```python
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
```

- [ ] **Step 2: Create the pre-push hook**

Create `.git/hooks/pre-push`:

```bash
#!/bin/bash
#
# JARVIS pre-push → Jira commit sync (Layer A).
# Reads the pushed commit range on stdin and mirrors commits onto the JAR board.
# MUST NOT block the push: always exits 0.

HOOK="/Users/sebastiansabo/Documents/Git/JARVIS/.claude/hooks/jira_commit_sync.py"
PYTHON="/Users/sebastiansabo/Documents/Git/JARVIS/venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

if [ -f "$HOOK" ] && [ -n "$PYTHON" ]; then
    "$PYTHON" "$HOOK" || true
fi
exit 0
```

- [ ] **Step 3: Make hooks executable**

Run:
```bash
chmod +x .git/hooks/pre-push .claude/hooks/jira_session_enhance.py .claude/hooks/jira_commit_sync.py
ls -l .git/hooks/pre-push
```
Expected: `pre-push` listed with `-rwxr-xr-x`.

- [ ] **Step 4: Retire the old Stop hook and repoint settings**

Run:
```bash
git mv .claude/hooks/jira_auto_sync.py .claude/hooks/jira_auto_sync.py.bak 2>/dev/null \
  || mv .claude/hooks/jira_auto_sync.py .claude/hooks/jira_auto_sync.py.bak
```

Then edit `.claude/settings.local.json`: in the `Stop` array, change the command string
```
python3 /Users/sebastiansabo/Documents/Git/JARVIS/.claude/hooks/jira_auto_sync.py
```
to
```
python3 /Users/sebastiansabo/Documents/Git/JARVIS/.claude/hooks/jira_session_enhance.py
```

Verify the JSON still parses:
```bash
venv/bin/python3 -c "import json; json.load(open('.claude/settings.local.json')); print('settings OK')"
```
Expected: `settings OK`.

- [ ] **Step 5: Verify the full suite passes**

Run: `venv/bin/python3 -m pytest tests/test_jira_commit_sync.py -v`
Expected: PASS (24 tests).

- [ ] **Step 6: Safe end-to-end dry-run (no Jira writes)**

Run from repo root:
```bash
venv/bin/python3 .claude/hooks/jira_commit_sync.py --dry-run
```
Expected: one or more `[dry-run] JAR-… ← N commit(s) [scope]: [Label] …` lines derived from the last 5 commits on `HEAD`, and **zero** issues created (confirm on the board if unsure). If creds are unset it prints nothing and exits 0.

- [ ] **Step 7: Live single-commit verification (creates ONE real task)**

> This is the real end-to-end check. It creates a genuine Task on JAR. Do it once, confirm, and note the created key.

```bash
# make a tiny no-op commit on dev, then simulate a push range of just that commit
git commit --allow-empty -m "chore(infra): verify jira pre-push sync"
LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse HEAD~1)
printf "refs/heads/dev %s refs/heads/dev %s\n" "$LOCAL" "$REMOTE" \
  | venv/bin/python3 .claude/hooks/jira_commit_sync.py
```
Expected: a line like `Jira: JAR-XXX ← 1 commit(s) [infra] under JAR-14`. Verify JAR-XXX exists on the board under JAR-14 (Platform), is In Progress, labelled `claude-code`. Confirm `.git/jira-sync-ledger.json` now contains the commit SHA. Re-running the same piped command prints nothing new (dedup).

- [ ] **Step 8: Commit**

```bash
git add .claude/hooks/jira_session_enhance.py .claude/hooks/jira_auto_sync.py.bak \
        .claude/settings.local.json docs/superpowers/plans/2026-07-07-commit-jira-sync.md
git rm --cached .claude/hooks/jira_auto_sync.py 2>/dev/null || true
git commit -m "feat(jira-sync): wire pre-push hook, retire Stop hook, add Layer B stub

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> `.git/hooks/pre-push` is not tracked by git (it lives under `.git/`); document it in the plan and, if you want it version-controlled, additionally copy it to a tracked `scripts/hooks/pre-push` with an install note.

---

## Self-Review

**Spec coverage:**
- Two-layer architecture → Tasks 1–5 (Layer A), Task 6 step 1 (Layer B stub). ✓
- pre-push trigger + per-push batching → Task 5 `get_pushed_commits`, Task 6 hook. ✓
- Epic→Story→Task placement + one task per scope group → Task 2 `group_commits`, Task 4/5. ✓
- Auto-create Story under Workstream → Task 4 `resolve_story`. ✓
- Ledger dedup across dev→staging→main → Task 3 + Task 5 `test_main_creates_tasks_and_dedups`. ✓
- Never block a push / env-guard / merges skipped / create-only → Global Constraints + Task 5 `main` (try/except, env guard), `--no-merges`. ✓
- Scope map (locked decisions: pontaje/sincron/connecteam→JAR-5 auto-create, foi-parcurs→JAR-1) → Task 1 `SCOPE_ROUTES` + `AUTOCREATE_STORY_TITLE`. ✓
- Retire old hook, repoint Stop → Task 6 steps 4. ✓

**Placeholder scan:** No TBD/TODO; every code step is complete. ✓

**Type consistency:** `route_for_scope` returns `(workstream, story)` used consistently by `resolve_story`/`main`; commit dict `{sha,subject,files}` consistent across Tasks 2/5; `transport(method, endpoint, data)` signature consistent in `JiraClient` and `FakeTransport`. ✓
