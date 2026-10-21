"""Link-preview helpers for the Chat module.

Extracts the first unfurlable URL from message text so a link preview can
be generated for it. URLs embedded in markdown image tokens (`![alt](url)`)
or mention tokens (`@[Name](id)`) are not real links posted by the author
and are excluded from consideration.
"""

import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlparse

import requests
import urllib3.connection
import urllib3.connectionpool
import urllib3.poolmanager
from lxml import html as lxml_html

# Markdown image token, e.g. ![pic](https://cdn/x.png)
_IMAGE_TOKEN_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')

# Mention token, e.g. @[Ana](7)
_MENTION_TOKEN_RE = re.compile(r'@\[[^\]]+\]\(\d+\)')

# Bare http(s) URL — run of non-whitespace characters.
_URL_RE = re.compile(r'https?://\S+')

# Sentence punctuation always trimmed from the tail of a matched URL.
_SENTENCE_PUNCTUATION = '.,;:'

# Closing brackets, mapped to their opener. Only trimmed when unbalanced
# within the extracted URL (so real URLs like `.../Foo_(bar)` survive).
_CLOSERS = {')': '(', ']': '[', '}': '{'}


def _trim_trailing(url):
    """Trim trailing noise from a matched URL.

    Sentence punctuation (`.,;:`) is always stripped. A closing bracket
    (`)`, `]`, `}`) is stripped only when it is unbalanced within the URL
    — i.e. the URL has more of that closer than its matching opener — so
    that e.g. `.../Foo_(bar)` is left intact while a URL wrapped in
    `(... )` loses its dangling closer. Trimming repeats from the tail,
    so mixed trailers like `...a.com).` resolve correctly.
    """
    while url:
        last = url[-1]
        if last in _SENTENCE_PUNCTUATION:
            url = url[:-1]
            continue
        opener = _CLOSERS.get(last)
        if opener is not None and url.count(last) > url.count(opener):
            url = url[:-1]
            continue
        break
    return url


def extract_first_url(text):
    """Return the first bare http(s) URL found in `text`, or `None`.

    URLs inside image-markdown (`![alt](url)`) or mention (`@[Name](id)`)
    tokens are skipped — those spans are stripped before searching.
    Trailing sentence punctuation and dangling (unbalanced) closing
    brackets are trimmed from the matched URL (see `_trim_trailing`).
    """
    if not text:
        return None

    stripped = _IMAGE_TOKEN_RE.sub(' ', text)
    stripped = _MENTION_TOKEN_RE.sub(' ', stripped)

    match = _URL_RE.search(stripped)
    if not match:
        return None

    return _trim_trailing(match.group(0))


# ---------------------------------------------------------------------------
# SSRF guard + in-house Open Graph scraper
#
# scrape_opengraph fetches an arbitrary, user-supplied URL server-side to
# build a link preview. Without a guard that is an SSRF hole: a message
# could contain a link that redirects the server into hitting internal
# services (http://10.0.0.5/admin) or a cloud metadata endpoint
# (http://169.254.169.254/latest/meta-data) and reflect the response back
# to the poster. is_safe_url is the guard: it resolves the URL's host and
# rejects anything that isn't a plain http(s) URL pointing at a public,
# routable IP. scrape_opengraph re-applies the guard before the initial
# fetch AND before following each redirect hop, since a host can resolve
# safely yet redirect somewhere unsafe.
#
# The hostname guard alone is still vulnerable to DNS rebinding / TOCTOU:
# requests re-resolves the host when it actually connects, so a host that
# answers with a public IP during is_safe_url can flip to a private IP a
# moment later at connect time. _GUARDED_SESSION closes that window — its
# custom transport re-checks the REAL connected peer IP (sock.getpeername)
# against the same rules in connect(), before any request bytes are sent,
# and refuses the connection otherwise. TLS stays hostname-based (SNI and
# certificate validation are unchanged — the URL is never rewritten to an
# IP), so only the peer-IP safety check is added.
# ---------------------------------------------------------------------------

_SAFE_SCHEMES = {"http", "https"}

_FETCH_TIMEOUT_SECONDS = 4
_MAX_REDIRECTS = 3
_MAX_BODY_BYTES = 2 * 1024 * 1024
_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JarvisBot/1.0)"}


def _ip_is_safe(ip_text):
    """Return True iff `ip_text` is a public, routable address safe to
    connect to. Rejects anything that is not globally reachable
    (`not is_global` — this also covers RFC 6598 CGNAT `100.64.0.0/10`,
    used by Tailscale and some clouds, which the category flags below miss)
    plus the explicit private/loopback/link-local/reserved/multicast
    categories (multicast is kept because `224.0.0.0/4` reports
    `is_global == True`).
    """
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    if not ip.is_global:
        return False
    if (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast):
        return False
    return True


def is_safe_url(url):
    """Return True iff `url` is safe for the server to fetch.

    Safe means: scheme is http or https, and every IP the host resolves
    to is a public, routable address — never loopback (127.0.0.1),
    private (10.0.0.5), CGNAT (100.64.0.0/10), link-local (169.254.169.254,
    the common cloud metadata address), reserved, or multicast. This is the
    SSRF guard; callers must check it before making any network request.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return False

    if parsed.scheme not in _SAFE_SCHEMES:
        return False

    if not host:
        return False

    try:
        addrinfo = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    if not addrinfo:
        return False

    for info in addrinfo:
        if not _ip_is_safe(info[4][0]):
            return False

    return True


class _UnsafePeerError(Exception):
    """Raised at connect time when the actual peer IP fails the SSRF guard."""


def _assert_peer_is_safe(sock):
    """Raise `_UnsafePeerError` unless the socket's connected peer IP is a
    public, routable address. This is the TOCTOU/DNS-rebinding backstop:
    it validates the IP we really connected to, not the one DNS returned
    during is_safe_url. The underlying socket connection is established
    (incl. the TLS handshake for https) but no request bytes have been
    sent yet when this fires.
    """
    try:
        peer_ip = sock.getpeername()[0]
    except OSError as exc:
        raise _UnsafePeerError(f"cannot determine peer address: {exc}")
    if not _ip_is_safe(peer_ip):
        raise _UnsafePeerError(f"refusing connection to non-public peer {peer_ip}")


class _GuardedHTTPConnection(urllib3.connection.HTTPConnection):
    def connect(self):
        super().connect()
        _assert_peer_is_safe(self.sock)


class _GuardedHTTPSConnection(urllib3.connection.HTTPSConnection):
    def connect(self):
        super().connect()
        _assert_peer_is_safe(self.sock)


class _GuardedHTTPConnectionPool(urllib3.connectionpool.HTTPConnectionPool):
    ConnectionCls = _GuardedHTTPConnection


class _GuardedHTTPSConnectionPool(urllib3.connectionpool.HTTPSConnectionPool):
    ConnectionCls = _GuardedHTTPSConnection


class _GuardedPoolManager(urllib3.poolmanager.PoolManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pool_classes_by_scheme = {
            "http": _GuardedHTTPConnectionPool,
            "https": _GuardedHTTPSConnectionPool,
        }


class _GuardedHTTPAdapter(requests.adapters.HTTPAdapter):
    """requests adapter whose pool manager uses connections that re-check
    the real peer IP in connect(). Mounted on `_GUARDED_SESSION`."""

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = _GuardedPoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs
        )


def _build_guarded_session():
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# Module-level session: the peer-IP guard lives on its mounted adapter, so
# all scrape fetches must go through it (not bare requests.get).
_GUARDED_SESSION = _build_guarded_session()


def _read_body(response, max_bytes=_MAX_BODY_BYTES):
    """Read at most `max_bytes` from a streamed response body, stopping
    as soon as the cap is hit instead of buffering the whole thing."""
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_bytes:
            break
    return b"".join(chunks)[:max_bytes]


def _first_text(values):
    if not values:
        return None
    value = values[0].strip()
    return value or None


def scrape_opengraph(url):
    """Fetch `url` server-side and pull Open Graph metadata from its HTML.

    Returns the normalized preview dict
    `{"url", "title", "description", "image", "site_name", "source": "scrape"}`
    (any field but `source` may be `None`), or `None` if the URL fails the
    SSRF guard (`is_safe_url`), the response isn't `text/html`, or
    anything else goes wrong — network error, non-HTML, unparseable body.

    No fetch is attempted for a URL that fails the guard. The fetch goes
    through `_GUARDED_SESSION`, whose transport re-checks the real peer IP
    at connect time (TOCTOU backstop). Redirects are followed manually
    (`allow_redirects=False`) so that every `Location` can be re-validated
    against the guard before it is followed — up to `_MAX_REDIRECTS` hops.
    The body is read in streamed chunks capped at `_MAX_BODY_BYTES` so an
    oversized response can't exhaust memory. The streamed response is
    closed on every return path so connections are returned to the pool.
    """
    if not is_safe_url(url):
        return None

    response = None
    try:
        current_url = url

        for hop in range(_MAX_REDIRECTS + 1):
            response = _GUARDED_SESSION.get(
                current_url,
                timeout=_FETCH_TIMEOUT_SECONDS,
                allow_redirects=False,
                stream=True,
                headers=_REQUEST_HEADERS,
            )

            if response.status_code not in _REDIRECT_STATUS_CODES:
                break

            if hop == _MAX_REDIRECTS:
                return None  # redirect budget exhausted, still redirecting

            location = response.headers.get("Location")
            if not location:
                return None

            next_url = urljoin(current_url, location)
            if not is_safe_url(next_url):
                return None  # re-validated guard: redirect target is unsafe

            current_url = next_url
            response.close()  # redirect followed; release before next hop
            response = None

        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "text/html":
            return None

        body = _read_body(response)
        tree = lxml_html.fromstring(body)

        og_title = _first_text(tree.xpath('//meta[@property="og:title"]/@content'))
        og_description = _first_text(tree.xpath('//meta[@property="og:description"]/@content'))
        og_image = _first_text(tree.xpath('//meta[@property="og:image"]/@content'))
        og_site_name = _first_text(tree.xpath('//meta[@property="og:site_name"]/@content'))

        title_fallback = _first_text(tree.xpath('//title/text()'))
        description_fallback = _first_text(tree.xpath('//meta[@name="description"]/@content'))

        return {
            "url": url,
            "title": og_title or title_fallback,
            "description": og_description or description_fallback,
            "image": og_image,
            "site_name": og_site_name or urlparse(url).hostname,
            "source": "scrape",
        }
    except Exception:
        return None
    finally:
        if response is not None:
            response.close()


# ---------------------------------------------------------------------------
# Social-link routing + Microlink client + resolve orchestration
#
# Social platforms (Facebook, Instagram, TikTok, ...) block or heavily
# rate-limit the in-house scraper's plain server-side fetch, so their posts
# never yield usable Open Graph tags that way. is_social_url detects links
# to those platforms so resolve_preview can route them to Microlink (a
# third-party unfurl API) instead of scrape_opengraph. Microlink is a fixed,
# trusted host — not a user-controlled fetch target — so fetch_via_microlink
# calls it with a plain `requests.get`, not the SSRF-guarded session that
# scrape_opengraph must use for arbitrary poster-supplied URLs.
# ---------------------------------------------------------------------------

SOCIAL_DOMAINS = {
    'facebook.com', 'fb.watch', 'fb.me',
    'instagram.com', 'instagr.am',
    'tiktok.com',
}

_SOCIAL_HOST_PREFIXES = ('www.', 'm.', 'vt.', 'vm.')

_MICROLINK_TIMEOUT_SECONDS = 8
_RETRY_BACKOFF_SECONDS = 0.5


def is_social_url(url):
    """Return True iff `url`'s host is a known social platform domain.

    A single leading mobile/www subdomain prefix (`www.`, `m.`, `vt.`,
    `vm.`) is stripped before the `SOCIAL_DOMAINS` membership check, so
    e.g. `m.instagram.com` and `vt.tiktok.com` both match.
    """
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    if not host:
        return False

    host = host.lower()
    for prefix in _SOCIAL_HOST_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix):]
            break

    return host in SOCIAL_DOMAINS


def fetch_via_microlink(url):
    """Fetch a link preview for `url` via the Microlink unfurl API.

    Microlink is a fixed, trusted host (`api.microlink.io`) — unlike
    scrape_opengraph's target, `url` here is never dereferenced by this
    process directly, so this uses a plain `requests.get`, not the
    SSRF-guarded session.

    Returns the normalized preview dict
    `{"url", "title", "description", "image", "site_name", "source": "microlink"}`
    (any field but `source`/`url` may be `None`), or `None` if the response
    JSON's `status` isn't `"success"` or anything else goes wrong —
    network error, timeout, malformed JSON.
    """
    try:
        response = requests.get(
            "https://api.microlink.io/",
            params={"url": url},
            timeout=_MICROLINK_TIMEOUT_SECONDS,
        )
        payload = response.json()
        if payload.get("status") != "success":
            return None

        data = payload.get("data") or {}
        image = (data.get("image") or {}).get("url")

        return {
            "url": url,
            "title": data.get("title"),
            "description": data.get("description"),
            "image": image,
            "site_name": data.get("publisher"),
            "source": "microlink",
        }
    except Exception:
        return None


def resolve_preview(url, attempts=3):
    """Resolve a link preview for `url`, routing social links to Microlink
    and everything else to the in-house scraper, with retries.

    Social-platform URLs (`is_social_url`) are fetched via
    `fetch_via_microlink`; all other URLs go through `scrape_opengraph`.
    The chosen fetcher is tried up to `attempts` times, returning the
    first truthy result. Between tries — whether the fetcher raised or
    simply returned a falsy result (`None`) — this sleeps a short fixed
    backoff (`0.5 * attempt_index` seconds, no randomness) before
    retrying. Returns `None` if every attempt fails.
    """
    fetch = fetch_via_microlink if is_social_url(url) else scrape_opengraph

    for attempt in range(1, attempts + 1):
        try:
            result = fetch(url)
        except Exception:
            result = None

        if result:
            return result

        if attempt < attempts:
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)

    return None
