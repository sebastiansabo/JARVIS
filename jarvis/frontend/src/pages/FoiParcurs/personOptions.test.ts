import { describe, it, expect } from 'vitest'
import { mergePersonOptions } from './personOptions'

const clients = [
  { id: 1, name: 'Ion Popescu', phone: '0721000111' },
  { id: 2, name: 'Maria Ionescu', phone: '0722000222' },
]
const users = [
  { id: 10, name: 'Sebastian Sabo', phone: '0730111222' },
  { id: 11, name: 'Ana Consilier', phone: null },
]

describe('mergePersonOptions', () => {
  it('lists CRM clients (already server-filtered) then query-matching users', () => {
    const out = mergePersonOptions('sab', clients, users)
    // clients come through as-is (pre-filtered by server); users filtered by query
    expect(out.map((o) => o.name)).toEqual(['Ion Popescu', 'Maria Ionescu', 'Sebastian Sabo'])
    expect(out.find((o) => o.name === 'Sebastian Sabo')?.kind).toBe('user')
    expect(out.find((o) => o.name === 'Ion Popescu')?.kind).toBe('client')
  })

  it('matches users by phone too', () => {
    const out = mergePersonOptions('0730', [], users)
    expect(out.map((o) => o.name)).toEqual(['Sebastian Sabo'])
  })

  it('dedupes by name across sources, client wins', () => {
    const dup = [{ id: 99, name: 'Ana Consilier', phone: '0700' }]
    const out = mergePersonOptions('ana', dup, users)
    const anas = out.filter((o) => o.name === 'Ana Consilier')
    expect(anas).toHaveLength(1)
    expect(anas[0].kind).toBe('client')
  })

  it('honors the sources option (clients only)', () => {
    const out = mergePersonOptions('sab', clients, users, { sources: ['clients'] })
    expect(out.some((o) => o.kind === 'user')).toBe(false)
  })

  it('caps to the limit', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ id: i, name: `Client ${i}`, phone: '' }))
    expect(mergePersonOptions('client', many, [], { limit: 5 })).toHaveLength(5)
  })
})
