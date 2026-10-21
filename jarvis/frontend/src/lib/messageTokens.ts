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
      // Bare URL
      tokens.push({ kind: 'url', url: match[5] })
    }
    last = re.lastIndex
  }
  if (last < content.length) tokens.push({ kind: 'text', text: content.slice(last) })
  return tokens
}
