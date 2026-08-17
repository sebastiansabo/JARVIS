import { describe, it, expect } from 'vitest'
import { fmtPunchTime } from './punchTime'

// BioStar punch timestamps are Romania-local wall-clock values, but the backend
// serialises them from a `timestamptz` column with a `+00:00` zone. `new Date()`
// then re-reads them as UTC and shifts them by the viewer's offset (+3h in EEST).
// fmtPunchTime must show the wall-clock exactly as stored, ignoring any zone.
describe('fmtPunchTime', () => {
  it('shows the stored wall-clock for a +00:00 timestamp (no +3h shift)', () => {
    expect(fmtPunchTime('2026-08-17T07:52:00+00:00')).toBe('07:52')
  })

  it('ignores the zone offset — TZ-independent (the actual bug)', () => {
    // A non-UTC offset would move the wall-clock under `new Date`, regardless of
    // the runner's own timezone. Stripping the zone keeps 07:52 → 07:52.
    expect(fmtPunchTime('2026-08-17T07:52:00+05:00')).toBe('07:52')
  })

  it('handles a trailing Z designator', () => {
    expect(fmtPunchTime('2026-08-17T07:52:00Z')).toBe('07:52')
  })

  it('handles a space-separated timestamp (str(datetime) form)', () => {
    expect(fmtPunchTime('2026-08-17 10:52:00+00:00')).toBe('10:52')
  })

  it('handles a naive timestamp with no zone', () => {
    expect(fmtPunchTime('2026-08-17T07:52:00')).toBe('07:52')
  })

  it('includes seconds when requested', () => {
    expect(fmtPunchTime('2026-08-17T07:52:09+00:00', { seconds: true })).toBe('07:52:09')
  })

  it('returns the placeholder for empty/invalid input', () => {
    expect(fmtPunchTime(null)).toBe('—')
    expect(fmtPunchTime('')).toBe('—')
    expect(fmtPunchTime('not-a-date')).toBe('—')
  })

  it('accepts a custom placeholder', () => {
    expect(fmtPunchTime(null, { empty: '-' })).toBe('-')
  })
})
