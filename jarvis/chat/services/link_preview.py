"""Link-preview helpers for the Chat module.

Extracts the first unfurlable URL from message text so a link preview can
be generated for it. URLs embedded in markdown image tokens (`![alt](url)`)
or mention tokens (`@[Name](id)`) are not real links posted by the author
and are excluded from consideration.
"""

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
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
# ---------------------------------------------------------------------------

_SAFE_SCHEMES = {"http", "https"}

_FETCH_TIMEOUT_SECONDS = 4
_MAX_REDIRECTS = 3
_MAX_BODY_BYTES = 2 * 1024 * 1024
_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JarvisBot/1.0)"}


def is_safe_url(url):
    """Return True iff `url` is safe for the server to fetch.

    Safe means: scheme is http or https, and every IP the host resolves
    to is a public, routable address — never loopback (127.0.0.1),
    private (10.0.0.5), link-local (169.254.169.254, the common cloud
    metadata address), reserved, or multicast. This is the SSRF guard;
    callers must check it before making any network request.
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
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return False

    return True


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

    No fetch is attempted for a URL that fails the guard. Redirects are
    followed manually (`allow_redirects=False`) so that every `Location`
    can be re-validated against the guard before it is followed — up to
    `_MAX_REDIRECTS` hops. The body is read in streamed chunks capped at
    `_MAX_BODY_BYTES` so an oversized response can't exhaust memory.
    """
    if not is_safe_url(url):
        return None

    try:
        current_url = url
        response = None

        for hop in range(_MAX_REDIRECTS + 1):
            response = requests.get(
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
