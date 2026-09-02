import { describe, it, expect } from 'vitest'
import { personLabel, timeAgo } from './praiseFormat'

describe('personLabel', () => {
  it('returns the display name when present', () => {
    expect(personLabel('Ion Popescu', 19)).toBe('Ion Popescu')
  })

  it('falls back to #id when the name is null (deleted account)', () => {
    expect(personLabel(null, 19)).toBe('#19')
  })

  it('falls back to #id when the name is blank', () => {
    expect(personLabel('   ', 19)).toBe('#19')
  })

  it('accepts a string id', () => {
    expect(personLabel(null, '42')).toBe('#42')
  })
})

describe('timeAgo', () => {
  const now = Date.now()
  it('shows "acum" under a minute', () => {
    expect(timeAgo(new Date(now - 30_000).toISOString())).toBe('acum')
  })
  it('shows minutes', () => {
    expect(timeAgo(new Date(now - 5 * 60_000).toISOString())).toBe('acum 5 min')
  })
  it('shows hours', () => {
    expect(timeAgo(new Date(now - 3 * 3_600_000).toISOString())).toBe('acum 3 h')
  })
  it('shows days with singular/plural', () => {
    expect(timeAgo(new Date(now - 24 * 3_600_000).toISOString())).toBe('acum 1 zi')
    expect(timeAgo(new Date(now - 5 * 24 * 3_600_000).toISOString())).toBe('acum 5 zile')
  })
})
