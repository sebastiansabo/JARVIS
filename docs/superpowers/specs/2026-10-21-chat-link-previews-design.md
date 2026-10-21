# Chat Link Previews (WhatsApp-style)

**Date:** 2026-10-21
**Module:** Chat (a.k.a. Digest — `digest_` in the DB)
**Status:** Design — awaiting approval
**Feasibility:** Validated. The exact Facebook reel from the triggering
message was unfurled successfully through Microlink's free keyless API —
title, description, publisher, and thumbnail all returned.

## Intent & why

When someone pastes a URL into a chat message (e.g. a Facebook reel for a
marketing-share push, as in the request that triggered this), it currently
renders as inert gray text — not even clickable. We want WhatsApp-style
behaviour: a preview card hangs under the message showing the page's
thumbnail image, title, a line or two of description, and the site name, and
tapping it opens the link. As a direct side effect, bare URLs also become
clickable inline (they aren't today).

The value is engagement and clarity: shared links (marketing videos, articles,
listings) become visible and inviting instead of a wall of raw URLs.

## Goals

- A message containing a URL shows a preview card below the text: image, title,
  description, site name; the whole card is a link that opens the URL.
- Bare URLs in message text become clickable `<a>` links (today they are plain
  text).
- Previews work for the common case (news, blogs, YouTube, listing sites) AND
  for Facebook / Instagram / TikTok — the social links that block ordinary
  server-side scraping — so the originating Facebook-reel example actually
  previews.
- Posting a message stays fast — fetching a preview must not block the send.
- Fetching arbitrary user-supplied URLs server-side is done safely (no SSRF, no
  unbounded downloads).

## Non-goals / anti-goals

- **No inline playable video / autoplay embeds.** The card is a static
  thumbnail that links out, exactly like WhatsApp. (Avoids heavy embeds,
  autoplay, and third-party iframes in the chat.)
- **Not mobile (yet).** The mobile chat lives in separate repos
  (`jarvis-mobile-2`, `jarvis-mobile-chat`) and today renders messages as plain
  text with no image/link rendering at all. Mobile is a deliberate follow-up,
  out of scope here.
- **One card per message** (the first URL), matching WhatsApp. Not every link.
- Not a general bookmarking/reading-list feature. Just the inline card.

## Decisions made (the "how", as decided)

### Fetch strategy — Hybrid (user decision)
- **Normal links** → fetched **in-house** with `requests` + `lxml.html`,
  parsing Open Graph tags. Fast, free, and nothing leaves our infrastructure
  (keeps internal/private links private).
- **Social links** (Facebook, Instagram, TikTok — which serve a login wall to
  outside scrapers) → fetched via an **external unfurl service**:
  **Microlink hosted, free/keyless** (`https://api.microlink.io/?url=...`), no
  API key, swappable behind an interface. Only social domains hit the external
  service, which bounds external call volume and cost. (User decision: hosted
  free over self-hosting — self-hosted unfurlers typically can't defeat the
  social login walls, which would break the motivating case. A paid API key is
  a later upgrade, added only if the free tier's ~50/day limit actually bites;
  the cache below softens this.)
- **Governance note:** social URLs people paste are sent to Microlink (a
  third-party SaaS). Normal/internal links never leave our infrastructure
  (in-house path). Accepted as part of the Hybrid choice.
- Domain routing list (builder's call, start here): `facebook.com`, `fb.watch`,
  `fb.me`, `m.facebook.com`, `instagram.com`, `instagr.am`, `tiktok.com`,
  `vt.tiktok.com`, `vm.tiktok.com`. Everything else → in-house.

### Scope — Web first (user decision)
- Web chat only (`jarvis/frontend/src/pages/Digest/`). Mobile deferred.

### Storage
- New nullable column **`digest_posts.link_preview JSONB`** added to
  `jarvis/migrations/domains/schema_digest.py`, guarded idempotently with the
  project's `DO $$ ... information_schema ...` ALTER pattern (not a bare
  `ADD COLUMN IF NOT EXISTS`). **This file is in the protected migrations area —
  the change needs explicit sign-off before it's written.** Holds a snapshot so
  historical messages keep their preview even if the source page later changes:
  ```json
  {
    "url": "https://…",
    "title": "…",
    "description": "…",
    "image": "https://…",   // may be null; for social links this is a
                             //   locally re-hosted copy, not the source URL
    "site_name": "…",         // e.g. "Facebook", "YouTube"
    "source": "scrape" | "microlink"
  }
  ```
  `NULL` = no preview (no URL, or fetch failed after retries). The frontend
  simply renders no card when it's null.
- **Social thumbnails are re-hosted locally.** Facebook/Instagram CDN image
  URLs are signed and expire (confirmed in the feasibility test — the fbcdn URL
  carried an expiry), so for social-source previews the worker downloads the
  thumbnail once and stores it via the existing upload path
  (`static/uploads/digest/`, same as `routes.py:390` image upload), then stores
  that local URL in `image`. Non-social (in-house) images are referenced
  directly — their URLs are stable.
- New cache table **`digest_link_previews`** keyed by URL so the same link
  pasted repeatedly is fetched once:
  `url TEXT PRIMARY KEY, data JSONB, fetched_at TIMESTAMPTZ`. Success rows TTL
  ~7 days; a stale row is re-fetched. This also caps how often we call the
  external service. **Negative caching:** a failed fetch is cached with a short
  TTL (~30 min) as `data = NULL`, so dead/transient URLs aren't re-hammered on
  every repost but *do* get retried later rather than being failed forever.

### When previews are generated — async, non-blocking
- `create_post` inserts the message **immediately** (no added latency), then
  kicks off preview resolution in a **background thread** (fire-and-forget).
  The thread: extracts the first URL (mirroring the existing `_MENTION_RE`
  extraction in `chat_service.py`), checks the cache, fetches in-house or via
  the external service as routed, writes the cache row, and `UPDATE`s
  `digest_posts.link_preview` for that post. The worker uses `ChatRepository()`,
  which draws its own connection from the existing `ThreadedConnectionPool`
  (`database.py:38`) via `BaseRepository` — no manual raw connection needed.
  This mirrors the established daemon-thread pattern (`jarvis/tasks/
  listing_autosync.py`, `core/auth/routes.py:496`). One ops caveat: gunicorn
  runs `gthread` (few workers × few threads, single instance), so cap concurrent
  preview threads with a small bounded executor rather than spawning one per post
  unboundedly.
- **Retry:** the worker retries the fetch ~2–3 times with short backoff before
  giving up, so a transient Microlink/network blip doesn't permanently lose the
  card. On final failure it writes a short-TTL negative-cache row (above).
- **The card appears within ~10s automatically** — `ChannelView.tsx:90` already
  polls the post list on a 10s `refetchInterval`. No websocket/new mechanism
  needed.
- **Edit path:** `update_post` (`chat_service.py:294`) also triggers resolution —
  if the first URL changed it re-resolves; if the message no longer has a URL,
  the stored preview is cleared.
- **Applies everywhere:** previews + clickable URLs are universal across channels
  (including announcement channels and DMs), matching WhatsApp. No new
  per-channel toggle (contrast the existing `allow_images` flag) unless you later
  ask for one.
- URL extraction regex lives server-side next to `_MENTION_RE`
  (`jarvis/chat/services/chat_service.py:11`). It must **skip URLs already inside
  `![alt](url)` image-markdown and `@[name](id)` mentions** so uploaded-image
  URLs aren't unfurled. The frontend `TOKEN_RE` must do the same.

### Security (fetching user-supplied URLs)
- **SSRF guard:** resolve the target host; reject loopback, private
  (RFC1918), link-local, and reserved IP ranges; reject any non-`http(s)`
  scheme; re-validate after each redirect.
- **Bounded fetch:** connect/read timeout ~4s; max ~3 redirects; cap response
  body (~2 MB) and only parse `Content-Type: text/html`.
- **Browser-like User-Agent** so sites that vary output for bots still return OG
  tags.
- **XSS:** title/description/site are rendered as React text (auto-escaped). The
  image is loaded via `<img src>` only after validating an `http(s)` scheme.
  (Loading the remote image directly leaks the viewer's IP to the image host; an
  image proxy is noted as future hardening, not v1.)

### Backend shape
- New module `jarvis/chat/services/link_preview.py`:
  - `extract_first_url(text) -> str | None`
  - `resolve_preview(url) -> dict | None` (cache lookup → route in-house vs.
    external → normalize to the stored shape)
  - in-house scraper (`requests` + `lxml.html`, OG tags with `<title>` / meta
    description / favicon fallbacks) and an external-service client, both behind
    a common return shape.
- `chat_service.create_post` (`jarvis/chat/services/chat_service.py:160`) spawns
  the background resolution after insert.
- `chat_service.get_posts` / `get_post` enrichment
  (`chat_service.py:144-158`) already shapes the response — include
  `link_preview` from the row.
- New repo methods in `jarvis/chat/repositories/chat_repository.py` (using the
  `query_one`/`execute` helpers, `%s` params — never f-string a URL into SQL):
  `set_post_link_preview(post_id, data)`, `get_cached_preview(url)`,
  `upsert_cached_preview(url, data)`.
- No new HTTP route needed: `link_preview` rides on the existing
  `get_posts`/`get_post` response (the `{success, data}` envelope). The social
  thumbnail is served as a normal static upload URL.
- Both the `link_preview` column and the `digest_link_previews` cache table live
  in the protected `schema_digest.py` — same sign-off gate as above.

### Frontend shape (web)
- `DigestPost` type (`jarvis/frontend/src/types/digest.ts:47-65`) gains
  `link_preview?: LinkPreview | null`.
- `PostItem.tsx` (`renderContent` / `TOKEN_RE` at `:26-58`): extend tokenizing
  to also detect bare URLs and render them as `<a>` (opens in new tab,
  `rel="noopener noreferrer"`). Below the message body, render a
  `<LinkPreviewCard>` when `link_preview` is present.
- New `LinkPreviewCard` component: thumbnail (left or top), bold title (clamped),
  description (1–2 lines, clamped), site name; entire card is an `<a>`. Graceful
  when `image` is null (text-only card). Styled to match existing Digest
  components.

## What's left to the builder

- Exact Tailwind/styling of the card to match the Digest look (image placement,
  clamping, dark-mode), using Tailwind 4 + shadcn/ui as the rest of the SPA does.
- Final social-domain routing list and the OG-tag fallback chain.
- Cache TTL tuning (success ~7d, failure ~30m are starting points) and whether to
  also fall back to the external service when in-house scraping returns nothing
  for a non-social link (default: no, to bound external usage).
- Bounded-executor sizing for the preview workers.
- Tests: URL extraction (incl. skipping markdown-image/mention URLs), SSRF guard
  rejects private hosts, in-house parser against a fixture HTML, external-client
  normalization (mocked — never hit real Microlink/Facebook in tests), repo
  round-trip, and a frontend render test of the card.

## Resolved during the builder-check (not open)

- **Feasibility of social unfurling** — validated live: Microlink's free keyless
  API returned a full preview for the exact Facebook reel. Chosen deployment:
  Microlink hosted/free (user decision); paid key is a later upgrade only if the
  rate limit bites.
- **Client refresh** — no new mechanism; `ChannelView.tsx:90` already polls every
  10s, so the card appears shortly after the worker finishes.
- **Background mechanism + worker DB connection** — established daemon-thread
  pattern + `ThreadedConnectionPool`; worker just uses `ChatRepository()`.
- **Retry / failure semantics** — in-thread retries + short-TTL negative cache
  (builder's call, settled above).
- **Edit path & per-channel gating** — edits re-resolve; previews are universal,
  no new toggle (builder's calls, settled above).
- **Dependencies** — `requests` and `lxml>=5.0.0` are already in
  `requirements.txt`.

## Open questions (for the human)

None outstanding. The one decision that was yours — hosted vs. self-hosted
unfurling — is answered (Microlink hosted/free). The only gate left is approval
to touch the protected `schema_digest.py` migration for the new column + cache
table, which is part of approving this design.
