import pytest
from core.organization import ghost


@pytest.fixture(autouse=True)
def _clear_cache():
    ghost.invalidate_ghost_cache()
    yield
    ghost.invalidate_ghost_cache()


def _seed(monkeypatch, ghosts, admins):
    monkeypatch.setattr(ghost, '_fetch_ghost_ids', lambda: set(ghosts))
    monkeypatch.setattr(ghost, '_fetch_admin_ids', lambda: set(admins))


def test_hidden_excludes_self(monkeypatch):
    _seed(monkeypatch, ghosts={10, 11}, admins=set())
    # viewer 10 is themselves a ghost → sees self, hidden = {11}
    assert ghost.hidden_ghost_ids(10) == {11}


def test_superadmin_sees_all(monkeypatch):
    _seed(monkeypatch, ghosts={10, 11}, admins={99})
    assert ghost.can_see_ghosts(99) is True
    assert ghost.hidden_ghost_ids(99) == set()


def test_scheduled_job_hides_all(monkeypatch):
    _seed(monkeypatch, ghosts={10, 11}, admins={99})
    assert ghost.hidden_ghost_ids(None) == {10, 11}


def test_clause_present_and_empty(monkeypatch):
    _seed(monkeypatch, ghosts={10}, admins=set())
    frag, params = ghost.ghost_exclude_clause('be.mapped_jarvis_user_id', viewer_id=7)
    assert '<> ALL(%s)' in frag and 'be.mapped_jarvis_user_id' in frag
    assert params == [[10]]
    # no ghosts → no clause
    _seed(monkeypatch, ghosts=set(), admins=set())
    ghost.invalidate_ghost_cache()
    assert ghost.ghost_exclude_clause('u.id', viewer_id=7) == ('', [])


def test_cache_hits_fetch_once(monkeypatch):
    calls = {'n': 0}
    def fetch():
        calls['n'] += 1
        return {10}
    monkeypatch.setattr(ghost, '_fetch_ghost_ids', fetch)
    monkeypatch.setattr(ghost, '_fetch_admin_ids', lambda: set())
    ghost.get_ghost_user_ids(); ghost.get_ghost_user_ids()
    assert calls['n'] == 1
    ghost.invalidate_ghost_cache()
    ghost.get_ghost_user_ids()
    assert calls['n'] == 2
