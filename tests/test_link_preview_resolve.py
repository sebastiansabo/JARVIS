"""Unit tests for link_preview.is_social_url, fetch_via_microlink, and
resolve_preview (social-link routing + Microlink client + retry orchestration).

The network is always mocked: fetch_via_microlink is exercised through a
mocked `requests.get` (it uses a plain, un-guarded call since
api.microlink.io is a fixed trusted host, not a user-controlled scrape
target), and resolve_preview is exercised by monkeypatching the two
fetchers it dispatches to (`fetch_via_microlink` / `scrape_opengraph`)
plus `time.sleep` (to a no-op, so the retry test runs instantly and
deterministically — no real backoff delay, no randomness).
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.services import link_preview
from chat.services.link_preview import is_social_url, fetch_via_microlink, resolve_preview

SENTINEL = {"url": "https://facebook.com/reel/1", "title": "social", "description": None,
            "image": None, "site_name": None, "source": "microlink"}
SCRAPED = {"url": "https://nytimes.com/a", "title": "scraped", "description": None,
           "image": None, "site_name": None, "source": "scrape"}


def _fake_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


# --- is_social_url -----------------------------------------------------

def test_is_social_url():
    assert is_social_url("https://www.facebook.com/reel/1") is True
    assert is_social_url("https://m.instagram.com/p/x") is True
    assert is_social_url("https://nytimes.com/a") is False


def test_is_social_url_covers_all_domains_and_mobile_prefixes():
    assert is_social_url("https://fb.watch/x") is True
    assert is_social_url("https://fb.me/x") is True
    assert is_social_url("https://instagr.am/p/x") is True
    assert is_social_url("https://vt.tiktok.com/x") is True
    assert is_social_url("https://vm.tiktok.com/x") is True
    assert is_social_url("https://tiktok.com/@u/video/1") is True


# --- fetch_via_microlink -------------------------------------------------

def test_microlink_normalizes(monkeypatch):
    payload = {
        "status": "success",
        "data": {
            "title": "T",
            "description": "D",
            "image": {"url": "https://cdn/i.jpg"},
            "publisher": "facebook.com",
        },
    }
    mock_get = MagicMock(return_value=_fake_response(payload))
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    r = fetch_via_microlink("https://facebook.com/reel/1")

    assert r["title"] == "T"
    assert r["description"] == "D"
    assert r["image"] == "https://cdn/i.jpg"
    assert r["site_name"] == "facebook.com"
    assert r["source"] == "microlink"
    assert r["url"] == "https://facebook.com/reel/1"

    # Fixed trusted host, plain requests.get — not the SSRF-guarded session.
    mock_get.assert_called_once_with(
        "https://api.microlink.io/",
        params={"url": "https://facebook.com/reel/1"},
        timeout=8,
    )


def test_microlink_missing_image_returns_none_image(monkeypatch):
    payload = {"status": "success", "data": {"title": "T", "description": "D",
                                               "image": None, "publisher": "fb"}}
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=_fake_response(payload)))

    r = fetch_via_microlink("https://facebook.com/x")

    assert r["image"] is None


def test_microlink_non_success_returns_none(monkeypatch):
    payload = {"status": "fail", "data": {}}
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=_fake_response(payload)))

    assert fetch_via_microlink("https://facebook.com/x") is None


def test_microlink_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(side_effect=RuntimeError("boom")))

    assert fetch_via_microlink("https://facebook.com/x") is None


# --- resolve_preview ------------------------------------------------------

def test_resolve_routes_social_to_microlink(monkeypatch):
    monkeypatch.setattr(link_preview, "fetch_via_microlink", MagicMock(return_value=SENTINEL))
    monkeypatch.setattr(link_preview, "scrape_opengraph",
                         MagicMock(side_effect=AssertionError("should not run")))

    assert resolve_preview("https://facebook.com/reel/1") is SENTINEL


def test_resolve_routes_normal_to_scrape(monkeypatch):
    monkeypatch.setattr(link_preview, "scrape_opengraph", MagicMock(return_value=SCRAPED))
    monkeypatch.setattr(link_preview, "fetch_via_microlink",
                         MagicMock(side_effect=AssertionError("should not run")))

    assert resolve_preview("https://nytimes.com/a") is SCRAPED


def test_resolve_retries_then_succeeds(monkeypatch):
    ok = {"title": "ok"}
    mock_scrape = MagicMock(side_effect=[RuntimeError("boom"), ok])
    monkeypatch.setattr(link_preview, "scrape_opengraph", mock_scrape)
    monkeypatch.setattr(link_preview.time, "sleep", MagicMock())

    result = resolve_preview("https://nytimes.com/a", attempts=3)

    assert result["title"] == "ok"
    assert mock_scrape.call_count == 2


def test_resolve_returns_none_when_all_attempts_fail(monkeypatch):
    mock_scrape = MagicMock(return_value=None)
    monkeypatch.setattr(link_preview, "scrape_opengraph", mock_scrape)
    monkeypatch.setattr(link_preview.time, "sleep", MagicMock())

    assert resolve_preview("https://nytimes.com/a", attempts=3) is None
    assert mock_scrape.call_count == 3


def test_resolve_backoff_is_fixed_not_random(monkeypatch):
    mock_scrape = MagicMock(side_effect=[RuntimeError("boom"), RuntimeError("boom"), {"title": "ok"}])
    monkeypatch.setattr(link_preview, "scrape_opengraph", mock_scrape)
    mock_sleep = MagicMock()
    monkeypatch.setattr(link_preview.time, "sleep", mock_sleep)

    resolve_preview("https://nytimes.com/a", attempts=3)

    mock_sleep.assert_any_call(0.5)
    mock_sleep.assert_any_call(1.0)
