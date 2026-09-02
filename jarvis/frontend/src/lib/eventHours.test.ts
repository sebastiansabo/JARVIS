import { describe, it, expect } from 'vitest'
import { eventHoursFromDayHours } from './eventHours'

describe('eventHoursFromDayHours', () => {
  it('is zero for empty or undefined input', () => {
    expect(eventHoursFromDayHours(undefined)).toBe(0)
    expect(eventHoursFromDayHours({})).toBe(0)
  })

  it('sums (end - start) across days with a full interval', () => {
    expect(
      eventHoursFromDayHours({
        '2026-08-28': { start: 10, end: 18 },
        '2026-08-29': { start: 9, end: 17 },
      }),
    ).toBe(16)
  })

  it('ignores days missing a bound or with a non-positive span', () => {
    expect(
      eventHoursFromDayHours({
        '2026-08-28': { start: 10, end: 18 }, // 8h
        '2026-08-29': { start: null, end: 17 }, // no start
        '2026-08-30': { start: 12, end: null }, // no end
        '2026-08-31': { start: 18, end: 10 }, // negative -> ignored
      }),
    ).toBe(8)
  })
})
