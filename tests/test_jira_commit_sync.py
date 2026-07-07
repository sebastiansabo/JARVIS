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


ZERO = "0" * 40


def _fake_git(rev_list_map, subjects, files_map):
    """Build a run_git stub. rev_list_map: tuple(args)->newline SHAs."""
    def run_git(args):
        if args[:1] == ["rev-list"]:
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
