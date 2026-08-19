import { describe, it, expect } from 'vitest'
import { fmtDuration } from './duration'

describe('fmtDuration', () => {
  it('formats hours and minutes', () =>
    expect(fmtDuration('2026-08-19T13:14:00', '2026-08-19T15:11:00')).toBe('1h 57m'))
  it('drops minutes on whole hours', () =>
    expect(fmtDuration('2026-08-19T10:00:00', '2026-08-19T12:00:00')).toBe('2h'))
  it('shows only minutes under an hour', () =>
    expect(fmtDuration('2026-08-19T10:00:00', '2026-08-19T10:45:00')).toBe('45m'))
  it('handles a long same-run interval (<24h) as h+m', () =>
    expect(fmtDuration('2026-08-18T16:00:00', '2026-08-19T15:52:00')).toBe('23h 52m'))
  it('formats multi-day as days + hours', () =>
    expect(fmtDuration('2026-08-18T10:00:00', '2026-08-20T13:00:00')).toBe('2z 3h'))
  it('ignores the timezone offset (naive wall-clock)', () =>
    expect(fmtDuration('2026-08-19T13:00:00+00:00', '2026-08-19T14:30:00+00:00')).toBe('1h 30m'))
  it('is empty when an end is missing', () => {
    expect(fmtDuration(null, '2026-08-19T14:00:00')).toBe('')
    expect(fmtDuration('2026-08-19T14:00:00', null)).toBe('')
  })
  it('is empty for a non-positive interval', () =>
    expect(fmtDuration('2026-08-19T15:00:00', '2026-08-19T14:00:00')).toBe(''))
})
