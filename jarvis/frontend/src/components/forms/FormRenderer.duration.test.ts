import { describe, it, expect } from 'vitest'
import { applyDurationLinks, durationLinkError, fmtDuration, type DurationLink } from './FormRenderer'

// The Bilet de Invoire "Durată" field is a read-only duration link: it shows the
// span between the start and end time fields, formatted time-wise ("2 h 30 min").
const LINK: DurationLink[] = [{ hours: 'hours', start: 'start', end: 'end' }]

describe('fmtDuration', () => {
  it('formats a minutes-only span', () => expect(fmtDuration(50)).toBe('50 min'))
  it('formats a whole-hour span', () => expect(fmtDuration(120)).toBe('2 h'))
  it('formats an hours-and-minutes span', () => expect(fmtDuration(150)).toBe('2 h 30 min'))
  it('formats a zero span', () => expect(fmtDuration(0)).toBe('0 min'))
})

describe('applyDurationLinks', () => {
  it('computes the duration when the end time changes', () => {
    const next: Record<string, unknown> = { start: '23:00', end: '23:50' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBe('50 min')
  })

  it('computes the duration when the start time changes', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '11:30' }
    applyDurationLinks(LINK, next, 'start')
    expect(next.hours).toBe('2 h 30 min')
  })

  it('formats an exact-hour interval without a minutes part', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '11:00' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBe('2 h')
  })

  it('clears the duration when the end is before the start', () => {
    const next: Record<string, unknown> = { start: '11:00', end: '09:00' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBe('')
  })

  it('clears the duration when a time is unparseable', () => {
    const next: Record<string, unknown> = { start: '9am', end: 'noon' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBe('')
  })

  it('clears the duration while the interval is still incomplete', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '' }
    applyDurationLinks(LINK, next, 'start')
    expect(next.hours).toBe('')
  })

  it('clears the duration for a zero-length interval (end equals start)', () => {
    const next: Record<string, unknown> = { start: '09:00', end: '09:00' }
    applyDurationLinks(LINK, next, 'end')
    expect(next.hours).toBe('')
  })
})

describe('durationLinkError', () => {
  it('flags a start later than the end', () => {
    expect(durationLinkError(LINK[0], { start: '19:00', end: '12:20' }))
      .toBe('Ora de sfârșit trebuie să fie după ora de început.')
  })

  it('flags a zero-length interval', () => {
    expect(durationLinkError(LINK[0], { start: '09:00', end: '09:00' }))
      .toBe('Ora de sfârșit trebuie să fie după ora de început.')
  })

  it('passes a valid interval', () => {
    expect(durationLinkError(LINK[0], { start: '09:00', end: '11:00' })).toBeNull()
  })

  it('does not flag an incomplete interval', () => {
    expect(durationLinkError(LINK[0], { start: '09:00', end: '' })).toBeNull()
  })
})
