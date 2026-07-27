import { describe, it, expect } from 'vitest'
import { applyDurationLinks, type DurationLink } from './FormRenderer'

// The Bilet de Invoire "Număr de ore" field is a duration link between the
// start and end time fields.
const LINK: DurationLink[] = [{ hours: 'hours', start: 'start', end: 'end' }]

describe('applyDurationLinks', () => {
  it('computes hours when the end time changes', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '11:00' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBe('2')
  })

  it('computes hours when the start time changes', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '11:30' }
    applyDurationLinks(LINK, next, 'start')
    expect(next.hours).toBe('2.5')
  })

  it('recomputes the end time when hours is edited', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '11:00', hours: '3' }
    applyDurationLinks(LINK, next, 'hours')
    expect(next.end).toBe('12:00')
  })

  it('supports fractional hours both directions', () => {
    const a: Record<string, unknown> = { start: '09:00', hours: '2.5' }
    applyDurationLinks(LINK, a, 'hours')
    expect(a.end).toBe('11:30')
  })

  it('ignores an end that is before the start (no negative hours)', () => {
    const next: Record<string, unknown> = { start: '11:00', end: '09:00' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBeUndefined()
  })

  it('ignores unparseable times', () => {
    const next: Record<string, unknown> = { start: '9am', end: 'noon' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBeUndefined()
  })
})
