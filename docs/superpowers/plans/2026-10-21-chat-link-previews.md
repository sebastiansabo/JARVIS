# Chat Link Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render WhatsApp-style link-preview cards under chat messages that contain a URL, and make bare URLs clickable, in the JARVIS web chat.

**Architecture:** On post create/edit, the message is stored immediately; a bounded background thread extracts the first URL, resolves a preview (in-house Open-Graph scrape for normal links, Microlink for Facebook/Instagram/TikTok), re-hosts social thumbnails locally, caches by URL, and writes a JSONB snapshot onto the post. The web client already polls every 10s, so the card appears shortly after. The frontend tokenizes message text to render URLs as links and the stored preview as a card.

**Tech Stack:** Python/Flask, psycopg2 raw SQL (no ORM), `requests` + `lxml.html`, `concurrent.futures.ThreadPoolExecutor`; React 19 + Vite + TypeScript + Tailwind 4 + shadcn/ui; pytest (mocked) + vitest.

**Spec:** `docs/superpowers/specs/2026-10-21-chat-link-previews-design.md`

## Global Constraints

- Backend is Flask + raw SQL via psycopg2; **parameterise every value with `%s`, never f-string into SQL**.
- JSONB params must be wrapped with `psycopg2.extras.Json`.
- Migrations live in `jarvis/migrations/domains/schema_digest.py` and must be idempotent **in that file's existing style**: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` (not `DO $$` blocks). This file is protected — change approved in the spec.
- Tests must **never hit the network** (mock `requests`) and **never hit a real DB** (mock the `BaseRepository` accessors / the module `_repo`), matching `tests/test_chat_repository.py`.
- Frontend: target `jarvis/frontend/src/`, React + TS; pure logic goes in `src/lib/*` with a vitest test (pattern: `src/lib/*.test.ts`).
- Exact values: fetch timeout `4`s, max redirects `3`, max body `2 * 1024 * 1024` bytes, success cache TTL `7` days, negative cache TTL `30` min, executor `max_workers=4`. `SOCIAL_DOMAINS = {'facebook.com','fb.watch','fb.me','instagram.com','instagr.am','tiktok.com'}` (match after stripping leading `www.`/`m.`/`vt.`/`vm.`). Microlink: `https://api.microlink.io/?url=<urlencoded>`.
- Pre-push gate (run all, stop on failure): `cd jarvis/frontend && npm run build`; `python -m pytest tests/ -x -q`; `python3 -m py_compile jarvis/app.py`.
- Commit convention: `type(scope): desc`, scope `chat`/`db`/`frontend`.

## Review Focus

- **SSRF — URL pointing at an internal/private host** (`http://169.254.169.254/`, `http://10.0.0.1`, `localhost`): must be refused before any fetch. → Task 3 tests.
- **URL inside image-markdown or a mention** (`![x](https://…)`, `@[Name](5)`): must NOT be extracted server-side nor linkified client-side. → Task 2 + Task 8 tests.
- **Missing/null preview image** (page or Microlink returns no `og:image`): card renders text-only, nothing crashes. → Task 4 + Task 8 tests.
- **Social thumbnail download fails or isn't an image** (expired/404 fbcdn URL, `text/html` body): preview still stored without an image; no stray file written. → Task 6 tests.
- **Oversized / non-HTML / slow response**: bounded by size cap, content-type check, and timeout; the worker never hangs the pool. → Task 3 + Task 7 tests.

---

### Task 1: Schema — `link_preview` column + `digest_link_previews` cache table

**Files:**
- Modify: `jarvis/migrations/domains/schema_digest.py` (inside `create_schema_digest`, after the Posts table/indexes block near line 63)
- Test: `tests/test_schema_digest_link_preview.py`

**Interfaces:**
- Produces: a `digest_posts.link_preview JSONB` column; a `digest_link_previews(url TEXT PRIMARY KEY, data JSONB, fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)` table.

- [ ] **Step 1: Write the failing test** — `create_schema_digest` runs the new DDL. Mirror the mock style of `tests/test_chat_repository.py`.

```python
def test_schema_adds_link_preview_column_and_cache_table():
    conn, cursor = MagicMock(), MagicMock()
    from migrations.domains.schema_digest import create_schema_digest
    create_schema_digest(conn, cursor)
    sql = " ".join(c.args[0] for c in cursor.execute.call_args_list)
    assert "ADD COLUMN IF NOT EXISTS link_preview JSONB" in sql
    assert "CREATE TABLE IF NOT EXISTS digest_link_previews" in sql
    assert "url TEXT PRIMARY KEY" in sql
```

- [ ] **Step 2: Run test to verify it fails** — Run: `python -m pytest tests/test_schema_digest_link_preview.py -v` → FAIL (substring absent).
- [ ] **Step 3: Implement** — add `"ALTER TABLE digest_posts ADD COLUMN IF NOT EXISTS link_preview JSONB"` to an ALTER loop (same form as the `digest_channels` loop at lines 133-146), and a `CREATE TABLE IF NOT EXISTS digest_link_previews (...)` with the columns above, before the final `conn.commit()`.
- [ ] **Step 4: Run test to verify it passes** — Run: `python -m pytest tests/test_schema_digest_link_preview.py -v` → PASS.
- [ ] **Step 5: Commit** — `git add` the two files; `git commit -m "feat(db): add chat link_preview column + preview cache table"`.

---

### Task 2: Backend — first-URL extraction

**Files:**
- Create: `jarvis/chat/services/link_preview.py`
- Test: `tests/test_link_preview_extract.py`

**Interfaces:**
- Produces: `extract_first_url(text: str | None) -> str | None`.

- [ ] **Step 1: Write the failing test.**

```python
from chat.services.link_preview import extract_first_url

def test_plain_url_found():
    assert extract_first_url("see https://a.com/x now") == "https://a.com/x"
def test_first_of_several():
    assert extract_first_url("http://a.com and https://b.com") == "http://a.com"
def test_url_inside_image_markdown_ignored():
    assert extract_first_url("![pic](https://cdn/x.png)") is None
def test_url_inside_mention_ignored():
    assert extract_first_url("@[Ana](7) https://real.com") == "https://real.com"
def test_no_url():
    assert extract_first_url("just text") is None
def test_trailing_punctuation_trimmed():
    assert extract_first_url("go to https://a.com.") == "https://a.com"
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_link_preview_extract.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement `extract_first_url`** — first strip spans matching the image/mention token regex (`!\[[^\]]*\]\([^)]+\)` and `@\[[^\]]+\]\(\d+\)`), then find the first `https?://…` match; trim a single trailing `.,;:)]}` char. Return it or `None`.
- [ ] **Step 4: Run to verify it passes** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): extract first unfurlable URL from message text"`.

---

### Task 3: Backend — SSRF guard + in-house Open-Graph scraper

**Files:**
- Modify: `jarvis/chat/services/link_preview.py`
- Test: `tests/test_link_preview_scrape.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `is_safe_url(url: str) -> bool`; `scrape_opengraph(url: str) -> dict | None` returning `{"url","title","description","image","site_name","source":"scrape"}` or `None`.

- [ ] **Step 1: Write the failing test** (mock `requests.get`; never touch the network).

```python
def test_is_safe_url_rejects_private_and_nonhttp():
    for u in ["http://localhost/x","http://127.0.0.1","http://10.0.0.5",
              "http://169.254.169.254/","ftp://a.com","file:///etc/passwd"]:
        assert is_safe_url(u) is False
def test_is_safe_url_accepts_public():  # monkeypatch host resolution to a public IP
    assert is_safe_url("https://example.com/a") is True
def test_scrape_parses_og_tags(monkeypatch):
    html = '<html><head><meta property="og:title" content="T"><meta property="og:image" content="https://cdn/i.jpg"><meta property="og:site_name" content="S"></head></html>'
    # mock requests.get -> 200, content-type text/html, body=html
    r = scrape_opengraph("https://example.com")
    assert r["title"] == "T" and r["image"] == "https://cdn/i.jpg" and r["source"] == "scrape"
def test_scrape_missing_image_returns_none_image(monkeypatch):
    # og:title present, no og:image, <title> fallback
    assert scrape_opengraph("https://example.com")["image"] is None
def test_scrape_non_html_returns_none(monkeypatch):  # content-type application/pdf
    assert scrape_opengraph("https://example.com/f.pdf") is None
def test_scrape_private_url_does_not_fetch(monkeypatch):
    called = []  # requests.get should never run
    assert scrape_opengraph("http://10.0.0.1") is None and called == []
```

- [ ] **Step 2: Run to verify it fails** → FAIL.
- [ ] **Step 3: Implement.** `is_safe_url`: scheme in `{"http","https"}`; `socket.getaddrinfo(host, None)`; reject if any resolved IP is `ipaddress.ip_address(...)` with `.is_private/.is_loopback/.is_link_local/.is_reserved/.is_multicast`. `scrape_opengraph`: return `None` if not safe; `requests.get(url, timeout=4, allow_redirects=False, stream=True, headers={"User-Agent": "Mozilla/5.0 (compatible; JarvisBot/1.0)"})`; follow up to 3 redirects manually, re-checking `is_safe_url` on each `Location`; bail if `Content-Type` not `text/html`; read at most 2 MiB; parse with `lxml.html`, pull `og:title`/`og:description`/`og:image`/`og:site_name` with `<title>` and `<meta name=description>` fallbacks and host as `site_name` fallback; return the normalized dict (image may be `None`). Wrap network/parse in try/except → `None`.
- [ ] **Step 4: Run to verify it passes** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): SSRF-guarded Open-Graph scraper for link previews"`.

---

### Task 4: Backend — social routing, Microlink client, resolve orchestration

**Files:**
- Modify: `jarvis/chat/services/link_preview.py`
- Test: `tests/test_link_preview_resolve.py`

**Interfaces:**
- Consumes: `scrape_opengraph` (Task 3).
- Produces: `is_social_url(url) -> bool`; `fetch_via_microlink(url) -> dict | None` (`source:"microlink"`); `resolve_preview(url: str, attempts: int = 3) -> dict | None`.

- [ ] **Step 1: Write the failing test** (mock `requests.get` and/or the two fetchers).

```python
def test_is_social_url():
    assert is_social_url("https://www.facebook.com/reel/1") is True
    assert is_social_url("https://m.instagram.com/p/x") is True
    assert is_social_url("https://nytimes.com/a") is False
def test_microlink_normalizes(monkeypatch):
    payload = {"status":"success","data":{"title":"T","description":"D",
               "image":{"url":"https://cdn/i.jpg"},"publisher":"facebook.com"}}
    # mock requests.get -> json()=payload
    r = fetch_via_microlink("https://facebook.com/reel/1")
    assert r["title"]=="T" and r["image"]=="https://cdn/i.jpg" and r["source"]=="microlink"
def test_microlink_non_success_returns_none(monkeypatch):  # status:"fail"
    assert fetch_via_microlink("https://facebook.com/x") is None
def test_resolve_routes_social_to_microlink(monkeypatch):
    # patch fetch_via_microlink -> sentinel, scrape_opengraph -> should_not_run
    assert resolve_preview("https://facebook.com/reel/1") is SENTINEL
def test_resolve_routes_normal_to_scrape(monkeypatch):
    assert resolve_preview("https://nytimes.com/a") is SCRAPED
def test_resolve_retries_then_succeeds(monkeypatch):
    # side_effect=[RuntimeError, {...}]; attempts=3 -> returns dict, 2 calls
    assert resolve_preview("https://nytimes.com/a", attempts=3)["title"] == "ok"
```

- [ ] **Step 2: Run to verify it fails** → FAIL.
- [ ] **Step 3: Implement.** `is_social_url`: parse host, strip leading `www.`/`m.`/`vt.`/`vm.`, membership in `SOCIAL_DOMAINS`. `fetch_via_microlink`: `requests.get("https://api.microlink.io/", params={"url": url}, timeout=8)`, require JSON `status=="success"`, map `data.title/description/(image or {}).get("url")/publisher` → normalized dict. `resolve_preview`: pick `fetch_via_microlink` if social else `scrape_opengraph`; loop up to `attempts`, sleeping a short fixed backoff between tries (`time.sleep(0.5*i)` — do not use random); return the first truthy result or `None`.
- [ ] **Step 4: Run to verify it passes** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): social-link routing via Microlink + resolve with retry"`.

---

### Task 5: Backend — repository methods (cache + persist)

**Files:**
- Modify: `jarvis/chat/repositories/chat_repository.py` (new "Link previews" section)
- Test: `tests/test_chat_repository_link_preview.py`

**Interfaces:**
- Produces: `get_cached_preview(url) -> dict | None` (returns the row `{data, fetched_at}`); `upsert_cached_preview(url, data: dict | None)`; `set_post_link_preview(post_id, data: dict | None)`.

- [ ] **Step 1: Write the failing test** — stub `query_one`/`execute` with `MagicMock` as in `tests/test_chat_repository.py`.

```python
def test_get_cached_preview_queries_by_url():
    repo = _repo(); repo.query_one = MagicMock(return_value={"data":{"title":"T"}})
    repo.get_cached_preview("https://a.com")
    assert repo.query_one.call_args.args[1] == ("https://a.com",)
def test_upsert_uses_on_conflict_and_json():
    repo = _repo(); repo.execute = MagicMock()
    repo.upsert_cached_preview("https://a.com", {"title":"T"})
    sql = repo.execute.call_args.args[0]
    assert "ON CONFLICT (url)" in sql and "digest_link_previews" in sql
def test_set_post_link_preview_updates_column():
    repo = _repo(); repo.execute = MagicMock()
    repo.set_post_link_preview(5, {"title":"T"})
    sql, params = repo.execute.call_args.args[0], repo.execute.call_args.args[1]
    assert "UPDATE digest_posts SET link_preview" in sql and params[1] == 5
```

- [ ] **Step 2: Run to verify it fails** → FAIL.
- [ ] **Step 3: Implement** the three methods with `%s` params, wrapping any dict/None JSONB value in `psycopg2.extras.Json(...)`. `upsert_cached_preview`: `INSERT INTO digest_link_previews (url, data, fetched_at) VALUES (%s,%s,CURRENT_TIMESTAMP) ON CONFLICT (url) DO UPDATE SET data=EXCLUDED.data, fetched_at=CURRENT_TIMESTAMP`. `set_post_link_preview`: `UPDATE digest_posts SET link_preview=%s WHERE id=%s`.
- [ ] **Step 4: Run to verify it passes** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): repo methods for preview cache + post snapshot"`.

---

### Task 6: Backend — social thumbnail re-hosting

**Files:**
- Modify: `jarvis/chat/services/link_preview.py`
- Test: `tests/test_link_preview_rehost.py`

**Interfaces:**
- Produces: `rehost_image(image_url: str, upload_dir: str) -> str | None` returning `/static/uploads/digest/<uuid>.<ext>` or `None`.

- [ ] **Step 1: Write the failing test** (mock `requests.get` + filesystem/`open`).

```python
def test_rehost_saves_image_and_returns_static_url(monkeypatch, tmp_path):
    # requests.get -> 200, content-type image/jpeg, small body
    url = rehost_image("https://cdn/i.jpg", str(tmp_path))
    assert url.startswith("/static/uploads/digest/") and url.endswith(".jpg")
def test_rehost_rejects_non_image(monkeypatch, tmp_path):  # content-type text/html
    assert rehost_image("https://cdn/x", str(tmp_path)) is None
def test_rehost_handles_fetch_failure(monkeypatch, tmp_path):  # requests raises
    assert rehost_image("https://cdn/i.jpg", str(tmp_path)) is None
```

- [ ] **Step 2: Run to verify it fails** → FAIL.
- [ ] **Step 3: Implement** — `requests.get(image_url, timeout=4, stream=True)`; require `Content-Type` startswith `image/`; map subtype→ext (`jpeg→.jpg`, else `.<subtype>` limited to the upload whitelist `{jpg,jpeg,png,gif,webp}`); read ≤2 MiB; `os.makedirs(upload_dir, exist_ok=True)`; write `uuid4().hex+ext`; return the `/static/uploads/digest/<name>` URL. try/except → `None`.
- [ ] **Step 4: Run to verify it passes** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): re-host social preview thumbnails locally"`.

---

### Task 7: Backend — resolution worker + wire into create/update

**Files:**
- Modify: `jarvis/chat/services/link_preview.py` (worker + executor + `schedule_preview`)
- Modify: `jarvis/chat/services/chat_service.py` (`create_post` ~line 172, `update_post` ~line 294)
- Test: `tests/test_link_preview_worker.py`

**Interfaces:**
- Consumes: `extract_first_url`, `resolve_preview`, `rehost_image`, `is_social_url`, and repo `get_cached_preview`/`upsert_cached_preview`/`set_post_link_preview`.
- Produces: `schedule_preview(post_id: int, content: str, upload_dir: str) -> None`; internal `_resolve_and_store(post_id, content, upload_dir)`.

- [ ] **Step 1: Write the failing test** — call `_resolve_and_store` directly (synchronous), patching the repo + `resolve_preview` + `rehost_image`.

```python
def test_no_url_clears_preview(monkeypatch):
    # content without URL -> set_post_link_preview(post_id, None), no resolve
def test_normal_url_stores_scraped(monkeypatch):
    # resolve_preview -> {source:"scrape",image:"https://cdn/i.jpg",...}
    # set_post_link_preview called with that dict; rehost NOT called
def test_social_url_rehosts_then_stores(monkeypatch):
    # resolve_preview -> {source:"microlink",image:"https://fbcdn/x"}; rehost -> "/static/..jpg"
    # stored dict["image"] == "/static/..jpg"
def test_cache_hit_skips_resolve(monkeypatch):
    # get_cached_preview -> fresh row; resolve_preview must NOT be called
def test_failure_writes_negative_cache(monkeypatch):
    # resolve_preview -> None; upsert_cached_preview(url, None) called; post preview set None
```

- [ ] **Step 2: Run to verify it fails** → FAIL.
- [ ] **Step 3: Implement.** `_resolve_and_store`: `url = extract_first_url(content)`; if no url → `repo.set_post_link_preview(post_id, None)` and return. Check `get_cached_preview(url)`: if present and fresh (success row within 7d, or negative row within 30m) use it (its `data`, possibly `None`) without fetching. Else `data = resolve_preview(url)`; if `data` and `is_social_url(url)` and `data.get("image")`: `data["image"] = rehost_image(data["image"], upload_dir) or None`; `upsert_cached_preview(url, data)` (data may be `None` = negative). Finally `repo.set_post_link_preview(post_id, data)`. Wrap body in try/except + `logger.exception`. `schedule_preview`: submit `_resolve_and_store` to a module `ThreadPoolExecutor(max_workers=4)` (daemon threads). In `chat_service.create_post`, after the notify block, `if extract_first_url(content): link_preview.schedule_preview(post['id'], content, _upload_dir())` where `_upload_dir()` = `os.path.join(current_app.static_folder, 'uploads', 'digest')`; guard in try/except so it never breaks posting. In `chat_service.update_post`, after a successful `_repo.update_post`, call `link_preview.schedule_preview(post_id, content, _upload_dir())` unconditionally (worker clears when no URL).
- [ ] **Step 4: Run to verify it passes** — Run: `python -m pytest tests/test_link_preview_worker.py -v` → PASS. Then full suite `python -m pytest tests/ -x -q` → green.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): background preview resolution on post create/edit"`.

---

### Task 8: Frontend — type, tokenizer, card, PostItem wiring

**Files:**
- Modify: `jarvis/frontend/src/types/digest.ts` (add `LinkPreview` + `DigestPost.link_preview`)
- Create: `jarvis/frontend/src/lib/messageTokens.ts` + `jarvis/frontend/src/lib/messageTokens.test.ts`
- Create: `jarvis/frontend/src/pages/Digest/LinkPreviewCard.tsx`
- Modify: `jarvis/frontend/src/pages/Digest/PostItem.tsx` (`renderContent` ~26-58, content block ~216-224)

**Interfaces:**
- Produces: `LinkPreview` type `{url:string; title:string|null; description:string|null; image:string|null; site_name:string|null; source:string}`; `tokenizeMessage(content: string): Token[]` where `Token = {kind:'text'|'image'|'mention'|'url', ...}`.

- [ ] **Step 1: Write the failing vitest** for `tokenizeMessage`.

```ts
import { tokenizeMessage } from './messageTokens'
it('linkifies a bare url', () => {
  const t = tokenizeMessage('see https://a.com x')
  expect(t.some(k => k.kind==='url' && k.url==='https://a.com')).toBe(true)
})
it('does not linkify a url inside image markdown', () => {
  const t = tokenizeMessage('![p](https://cdn/x.png)')
  expect(t.some(k => k.kind==='url')).toBe(false)
  expect(t.some(k => k.kind==='image')).toBe(true)
})
it('keeps mentions as mention tokens', () => {
  const t = tokenizeMessage('@[Ana](7) hi')
  expect(t.find(k=>k.kind==='mention')?.name).toBe('Ana')
})
```

- [ ] **Step 2: Run to verify it fails** — Run: `cd jarvis/frontend && npx vitest run src/lib/messageTokens.test.ts` → FAIL.
- [ ] **Step 3: Implement `tokenizeMessage`** — one combined regex, alternation ordered image → mention → url (`https?:\/\/[^\s]+`), emitting typed tokens for matches and `text` tokens for the gaps (port the existing `TOKEN_RE` loop logic from `PostItem.renderContent`, adding the url branch). Add the `LinkPreview` type + `link_preview?: LinkPreview | null` to `DigestPost`.
- [ ] **Step 4: Run to verify it passes** → PASS.
- [ ] **Step 5: Build `LinkPreviewCard.tsx` and wire `PostItem`** — `LinkPreviewCard({preview}: {preview: LinkPreview})`: an `<a href=preview.url target="_blank" rel="noopener noreferrer">` card styled with Tailwind/shadcn to match the Digest bubbles (dark-mode aware); render `preview.image` in an `<img>` only when non-null, title bold (line-clamp-2), description (line-clamp-2), `site_name` muted. In `PostItem`, replace `renderContent` internals to map `tokenizeMessage(post.content)` to elements (url token → `<a target=_blank rel=noopener noreferrer>`), and render `{post.link_preview && <LinkPreviewCard preview={post.link_preview} />}` just below the content `<div>` (~line 218).
- [ ] **Step 6: Verify build + tests** — Run: `cd jarvis/frontend && npm run build` → exit 0, zero TS errors; `npx vitest run src/lib/messageTokens.test.ts` → PASS.
- [ ] **Step 7: Commit** — `git commit -m "feat(frontend): clickable URLs + link-preview card in chat"`.

---

## Notes for the executor

- Work on a branch off `staging` (e.g. `feat/chat-link-previews`); never push to `main`.
- `get_posts`/`get_post` already `SELECT p.*`, so `link_preview` surfaces automatically once the column exists — no read-path change needed.
- Final gate before handing back: `cd jarvis/frontend && npm run build`; `python -m pytest tests/ -x -q`; `python3 -m py_compile jarvis/app.py`.
