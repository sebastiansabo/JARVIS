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

# A single trailing punctuation character to trim off a matched URL.
_TRAILING_PUNCTUATION = '.,;:)]}'


def extract_first_url(text):
    """Return the first bare http(s) URL found in `text`, or `None`.

    URLs inside image-markdown (`![alt](url)`) or mention (`@[Name](id)`)
    tokens are skipped — those spans are stripped before searching. A
    single trailing punctuation character (one of `.,;:)]}`) is trimmed
    from the matched URL.
    """
    if not text:
        return None

    stripped = _IMAGE_TOKEN_RE.sub(' ', text)
    stripped = _MENTION_TOKEN_RE.sub(' ', stripped)

    match = _URL_RE.search(stripped)
    if not match:
        return None

    url = match.group(0)
    if url[-1] in _TRAILING_PUNCTUATION:
        url = url[:-1]
    return url
