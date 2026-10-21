"""Link-preview helpers for the Chat module.

Extracts the first unfurlable URL from message text so a link preview can
be generated for it. URLs embedded in markdown image tokens (`![alt](url)`)
or mention tokens (`@[Name](id)`) are not real links posted by the author
and are excluded from consideration.
"""

import re

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
