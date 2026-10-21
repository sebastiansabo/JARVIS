import { describe, it, expect } from 'vitest'
import { tokenizeMessage } from './messageTokens'

describe('tokenizeMessage', () => {
  it('linkifies a bare url', () => {
    const t = tokenizeMessage('see https://a.com x')
    expect(t.some((k) => k.kind === 'url' && k.url === 'https://a.com')).toBe(true)
  })

  it('does not linkify a url inside image markdown', () => {
    const t = tokenizeMessage('![p](https://cdn/x.png)')
    expect(t.some((k) => k.kind === 'url')).toBe(false)
    expect(t.some((k) => k.kind === 'image')).toBe(true)
  })

  it('keeps mentions as mention tokens', () => {
    const t = tokenizeMessage('@[Ana](7) hi')
    expect(t.find((k) => k.kind === 'mention')?.name).toBe('Ana')
  })

  it('emits plain text unchanged when there are no tokens', () => {
    const t = tokenizeMessage('just plain text')
    expect(t).toEqual([{ kind: 'text', text: 'just plain text' }])
  })

  it('returns an empty array for empty content', () => {
    expect(tokenizeMessage('')).toEqual([])
  })

  it('emits text tokens for the gaps around a mix of tokens', () => {
    const t = tokenizeMessage('hi @[Ana](7) check https://a.com ![p](https://cdn/x.png) bye')
    expect(t.map((k) => k.kind)).toEqual(['text', 'mention', 'text', 'url', 'text', 'image', 'text'])
  })

  it('captures the image alt text and url', () => {
    const t = tokenizeMessage('![my alt](https://cdn/x.png)')
    const img = t.find((k) => k.kind === 'image')
    expect(img).toMatchObject({ kind: 'image', alt: 'my alt', url: 'https://cdn/x.png' })
  })

  it('captures the mention name and id', () => {
    const t = tokenizeMessage('@[Ana](7)')
    const mention = t.find((k) => k.kind === 'mention')
    expect(mention).toMatchObject({ kind: 'mention', name: 'Ana', id: '7' })
  })

  it('handles consecutive bare urls separated by whitespace', () => {
    const t = tokenizeMessage('https://a.com https://b.com')
    const urls = t.filter((k) => k.kind === 'url').map((k) => (k as { url: string }).url)
    expect(urls).toEqual(['https://a.com', 'https://b.com'])
  })

  // Trailing-punctuation trimming (consistency with the backend's
  // _trim_trailing in jarvis/chat/services/link_preview.py): the url
  // token's value must exclude trailing sentence punctuation / unbalanced
  // closing brackets, matching what the backend treats as "the URL" —
  // but the raw characters must still render, as a following text token.

  it('strips a trailing period from the url token and keeps it as text', () => {
    const t = tokenizeMessage('see https://a.com.')
    expect(t).toEqual([
      { kind: 'text', text: 'see ' },
      { kind: 'url', url: 'https://a.com' },
      { kind: 'text', text: '.' },
    ])
  })

  it('preserves a balanced closing paren inside a wiki url', () => {
    const t = tokenizeMessage('https://en.wikipedia.org/wiki/Foo_(bar)')
    expect(t).toEqual([
      { kind: 'url', url: 'https://en.wikipedia.org/wiki/Foo_(bar)' },
    ])
  })

  it('strips an unbalanced trailing paren when the url is wrapped in parens', () => {
    const t = tokenizeMessage('(see https://a.com)')
    expect(t).toEqual([
      { kind: 'text', text: '(see ' },
      { kind: 'url', url: 'https://a.com' },
      { kind: 'text', text: ')' },
    ])
  })
})
