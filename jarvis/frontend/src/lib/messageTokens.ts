// Tokenizes chat message content into renderable pieces: images (![alt](url)),
// mentions (@[Name](id)), bare URLs, and plain text for the gaps between them.
// Shared, pure logic behind PostItem's renderContent so it can be unit-tested
// without React. Ported from the original TOKEN_RE loop in PostItem.tsx.

export type Token =
  | { kind: 'text'; text: string }
  | { kind: 'image'; alt: string; url: string }
  | { kind: 'mention'; name: string; id: string }
  | { kind: 'url'; url: string }

// Alternation order matters: image before mention before url, so a URL that
// appears inside `![alt](url)` is consumed whole by the image branch and
// never separately matched (and re-linkified) by the url branch.
const TOKEN_RE = /!\[([^\]]*)\]\(([^)]+)\)|@\[([^\]]+)\]\((\d+)\)|(https?:\/\/[^\s]+)/g

// Sentence punctuation always trimmed from the tail of a matched URL.
// Mirrors the backend's _SENTENCE_PUNCTUATION (jarvis/chat/services/link_preview.py).
const SENTENCE_PUNCTUATION = '.,;:'

// Closing brackets, mapped to their opener. Only trimmed when unbalanced
// within the matched URL (so real URLs like `.../Foo_(bar)` survive).
// Mirrors the backend's _CLOSERS.
const CLOSERS: Record<string, string> = { ')': '(', ']': '[', '}': '{' }

function countChar(str: string, ch: string): number {
  let count = 0
  for (const c of str) if (c === ch) count++
  return count
}

// Trim trailing noise from a matched URL — the same rule the backend's
// _trim_trailing applies when extracting the URL for link-preview
// resolution, so the <a href> a message renders matches what the backend
// would treat as "the URL" (e.g. `https://a.com.` -> href `https://a.com`,
// `https://en.wikipedia.org/wiki/Foo_(bar)` left intact).
function trimTrailingUrlPunctuation(url: string): string {
  while (url.length > 0) {
    const last = url[url.length - 1]
    if (SENTENCE_PUNCTUATION.includes(last)) {
      url = url.slice(0, -1)
      continue
    }
    const opener = CLOSERS[last]
    if (opener !== undefined && countChar(url, last) > countChar(url, opener)) {
      url = url.slice(0, -1)
      continue
    }
    break
  }
  return url
}

export function tokenizeMessage(content: string): Token[] {
  const tokens: Token[] = []
  let last = 0
  let match: RegExpExecArray | null
  const re = new RegExp(TOKEN_RE)
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) tokens.push({ kind: 'text', text: content.slice(last, match.index) })
    if (match[1] !== undefined || match[2] !== undefined) {
      // Image: ![alt](url)
      tokens.push({ kind: 'image', alt: match[1] ?? '', url: match[2] })
    } else if (match[3] !== undefined || match[4] !== undefined) {
      // Mention: @[Name](id)
      tokens.push({ kind: 'mention', name: match[3], id: match[4] })
    } else {
      // Bare URL — trim trailing punctuation the same way the backend
      // does for the link-preview URL, so the href excludes it. The
      // trimmed suffix is never dropped from the rendered text: it is
      // emitted as a following text token, so the message still reads
      // identically — only the link target shrinks.
      const raw = match[5]
      const trimmed = trimTrailingUrlPunctuation(raw)
      tokens.push({ kind: 'url', url: trimmed })
      if (trimmed.length < raw.length) {
        tokens.push({ kind: 'text', text: raw.slice(trimmed.length) })
      }
    }
    last = re.lastIndex
  }
  if (last < content.length) tokens.push({ kind: 'text', text: content.slice(last) })
  return tokens
}
