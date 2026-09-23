// Rich-text helpers shared by the TD booking admin editor (save-diff) and the
// public thank-you render, so both agree on "empty" and the public page never
// renders unsanitized staff HTML.

const EMPTY_RICH = new Set(['', '<p></p>', '<p><br></p>', '<p><br/></p>'])

/** True when a rich-text HTML string carries no visible content (the various
 *  "empty" shapes TipTap emits). One source of truth so the admin save-diff and
 *  the public render agree on what counts as empty. */
export function isEmptyRichHtml(html?: string | null): boolean {
  return EMPTY_RICH.has((html ?? '').trim())
}

// Tags the RichTextEditor (StarterKit + Underline + Link) can legitimately
// produce; anything else is unwrapped (its text is kept, the tag dropped).
const ALLOWED_TAGS = new Set([
  'P', 'BR', 'STRONG', 'B', 'EM', 'I', 'U', 'S', 'H2', 'H3',
  'UL', 'OL', 'LI', 'BLOCKQUOTE', 'A', 'SPAN', 'CODE', 'PRE',
])
const SAFE_HREF = /^(https?:|mailto:|tel:)/i

/** Allowlist-sanitize staff-authored rich text before it is rendered to the
 *  public. Drops any tag outside ALLOWED_TAGS (keeping its text), strips every
 *  attribute except a safe <a href>, and neutralizes javascript:/data: links.
 *  Browser-only (DOMParser); returns '' when DOMParser is unavailable so
 *  untrusted HTML is never emitted un-sanitized. */
export function sanitizeRichHtml(html: string): string {
  if (!html || typeof DOMParser === 'undefined') return ''
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const scrub = (parent: Element) => {
    for (const el of Array.from(parent.children)) {
      scrub(el) // depth-first: children are clean before we decide about `el`
      if (!ALLOWED_TAGS.has(el.tagName)) {
        el.replaceWith(...Array.from(el.childNodes)) // unwrap, keep text
        continue
      }
      for (const attr of Array.from(el.attributes)) {
        const keepHref = el.tagName === 'A' && attr.name === 'href'
          && SAFE_HREF.test(attr.value.trim())
        if (!keepHref) el.removeAttribute(attr.name)
      }
      if (el.tagName === 'A' && el.getAttribute('href')) {
        el.setAttribute('rel', 'noopener nofollow noreferrer')
        el.setAttribute('target', '_blank')
      }
    }
  }
  scrub(doc.body)
  return doc.body.innerHTML
}
