import { describe, it, expect } from 'vitest'
import { isEmptyRichHtml, sanitizeRichHtml } from './richText'

describe('isEmptyRichHtml', () => {
  it('treats every editor "empty" shape (and null) as empty', () => {
    for (const s of ['', '  ', '<p></p>', '<p><br></p>', '<p><br/></p>']) {
      expect(isEmptyRichHtml(s)).toBe(true)
    }
    expect(isEmptyRichHtml(null)).toBe(true)
    expect(isEmptyRichHtml(undefined)).toBe(true)
    expect(isEmptyRichHtml('<p>Hi</p>')).toBe(false)
  })
})

describe('sanitizeRichHtml', () => {
  it('keeps allowed formatting tags', () => {
    const out = sanitizeRichHtml('<p>Hi <strong>there</strong> <em>x</em></p><ul><li>a</li></ul>')
    expect(out).toContain('<strong>there</strong>')
    expect(out).toContain('<li>a</li>')
  })

  it('drops <script> (keeping only inert text)', () => {
    const out = sanitizeRichHtml('<p>ok</p><script>alert(1)</script>')
    expect(out).not.toContain('<script')
    expect(out).toContain('<p>ok</p>')
  })

  it('strips event-handler and style attributes', () => {
    const out = sanitizeRichHtml('<p onclick="evil()" style="color:red">hi</p>')
    expect(out).not.toContain('onclick')
    expect(out).not.toContain('style')
    expect(out).toContain('hi')
  })

  it('neutralizes javascript: hrefs but keeps safe links', () => {
    const bad = sanitizeRichHtml('<a href="javascript:alert(1)">x</a>')
    expect(bad).not.toContain('javascript:')
    const good = sanitizeRichHtml('<a href="https://example.com">x</a>')
    expect(good).toContain('href="https://example.com"')
    expect(good).toContain('rel="noopener')
  })

  it('unwraps <img onerror> payloads entirely', () => {
    const out = sanitizeRichHtml('<p>a</p><img src=x onerror="evil()">')
    expect(out).not.toContain('<img')
    expect(out).not.toContain('onerror')
  })
})
