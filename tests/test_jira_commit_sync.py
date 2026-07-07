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
