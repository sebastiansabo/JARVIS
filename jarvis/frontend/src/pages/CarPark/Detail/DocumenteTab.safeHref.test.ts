import { describe, it, expect } from 'vitest'
import { safeHref } from './DocumenteTab'

describe('safeHref', () => {
  it('accepts http URLs', () => {
    expect(safeHref('http://example.com/doc.pdf')).toBe('http://example.com/doc.pdf')
  })
  it('accepts https URLs', () => {
    expect(safeHref('https://drive.google.com/file/d/X/view')).toBe('https://drive.google.com/file/d/X/view')
  })
  it('is case-insensitive on the scheme', () => {
    expect(safeHref('HTTPS://example.com/x')).toBe('HTTPS://example.com/x')
  })
  it('trims surrounding whitespace', () => {
    expect(safeHref('  https://example.com/x  ')).toBe('https://example.com/x')
  })
  it('rejects javascript: URLs (XSS)', () => {
    expect(safeHref('javascript:alert(document.cookie)')).toBeNull()
  })
  it('rejects data: URLs (XSS)', () => {
    expect(safeHref('data:text/html,<script>alert(1)</script>')).toBeNull()
  })
  it('rejects other schemes and relative paths', () => {
    expect(safeHref('ftp://example.com/x')).toBeNull()
    expect(safeHref('/relative/path.pdf')).toBeNull()
    expect(safeHref('example.com/x')).toBeNull()
  })
  it('rejects null/undefined/empty', () => {
    expect(safeHref(null)).toBeNull()
    expect(safeHref(undefined)).toBeNull()
    expect(safeHref('')).toBeNull()
  })
})
