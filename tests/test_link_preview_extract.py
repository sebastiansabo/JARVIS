"""Unit tests for link_preview.extract_first_url — finds the first bare
http(s) URL in message text, skipping URLs embedded in image-markdown
`![alt](url)` or mention `@[Name](id)` tokens, and trimming a single
trailing punctuation character.
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

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

def test_balanced_trailing_paren_preserved():
    assert extract_first_url(
        "see https://en.wikipedia.org/wiki/Foo_(bar) now"
    ) == "https://en.wikipedia.org/wiki/Foo_(bar)"

def test_wrapped_in_parens_strips_unbalanced_closer():
    assert extract_first_url("(see https://a.com)") == "https://a.com"
