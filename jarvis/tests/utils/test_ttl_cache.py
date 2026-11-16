"""Unit tests for the tiny per-key TTL cache used to absorb badge pollers."""
from core.utils.ttl_cache import TTLCache


def test_get_or_set_caches_within_ttl(monkeypatch):
    clock = {'t': 1000.0}
    monkeypatch.setattr('core.utils.ttl_cache.time.monotonic', lambda: clock['t'])
    cache = TTLCache(ttl_seconds=15)
    calls = []

    def producer():
        calls.append(1)
        return 7

    assert cache.get_or_set('u1', producer) == 7
    clock['t'] += 10  # still within the 15s TTL
    assert cache.get_or_set('u1', producer) == 7
    assert len(calls) == 1  # producer ran once; second call served from cache


def test_recomputes_after_ttl(monkeypatch):
    clock = {'t': 1000.0}
    monkeypatch.setattr('core.utils.ttl_cache.time.monotonic', lambda: clock['t'])
    cache = TTLCache(ttl_seconds=15)
    calls = []
    cache.get_or_set('u1', lambda: calls.append(1))
    clock['t'] += 16  # past the TTL
    cache.get_or_set('u1', lambda: calls.append(1))
    assert len(calls) == 2


def test_invalidate_forces_recompute(monkeypatch):
    clock = {'t': 1000.0}
    monkeypatch.setattr('core.utils.ttl_cache.time.monotonic', lambda: clock['t'])
    cache = TTLCache(ttl_seconds=15)
    calls = []
    cache.get_or_set('u1', lambda: calls.append(1))
    cache.invalidate('u1')
    cache.get_or_set('u1', lambda: calls.append(1))  # same instant, but invalidated
    assert len(calls) == 2


def test_zero_count_is_cached_not_treated_as_miss(monkeypatch):
    clock = {'t': 1000.0}
    monkeypatch.setattr('core.utils.ttl_cache.time.monotonic', lambda: clock['t'])
    cache = TTLCache(ttl_seconds=15)
    calls = []

    def producer():
        calls.append(1)
        return 0  # a real, cacheable count

    assert cache.get_or_set('u1', producer) == 0
    assert cache.get_or_set('u1', producer) == 0
    assert len(calls) == 1
