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
