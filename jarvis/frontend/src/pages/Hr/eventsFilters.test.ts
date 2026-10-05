import { describe, it, expect } from 'vitest'
import { monthRange, yearRange, compareEventDates, EVENT_QUICK_RANGES } from './eventsFilters'

describe('eventsFilters — preset ranges', () => {
  it('this month spans the full current month', () => {
    expect(monthRange(0, new Date(2026, 2, 15))).toEqual({ from: '2026-03-01', to: '2026-03-31' })
  })

  it('last month handles the previous month (non-leap Feb)', () => {
    expect(monthRange(-1, new Date(2026, 2, 15))).toEqual({ from: '2026-02-01', to: '2026-02-28' })
  })

  it('last month rolls back across the year boundary', () => {
    expect(monthRange(-1, new Date(2026, 0, 10))).toEqual({ from: '2025-12-01', to: '2025-12-31' })
  })

  it('this year spans Jan 1 to Dec 31', () => {
    expect(yearRange(new Date(2026, 6, 1))).toEqual({ from: '2026-01-01', to: '2026-12-31' })
  })

  it('exposes exactly the three requested quick ranges', () => {
    expect(EVENT_QUICK_RANGES.map((r) => r.key)).toEqual(['this_month', 'last_month', 'this_year'])
  })
})

describe('eventsFilters — compareEventDates', () => {
  it('sorts ascending by date string', () => {
    expect(compareEventDates('2026-01-01', '2026-02-01', 'asc')).toBeLessThan(0)
    expect(compareEventDates('2026-03-01', '2026-02-01', 'asc')).toBeGreaterThan(0)
  })

  it('sorts descending by date string', () => {
    expect(compareEventDates('2026-01-01', '2026-02-01', 'desc')).toBeGreaterThan(0)
  })

  it('keeps null/empty dates last regardless of direction', () => {
    expect(compareEventDates(null, '2026-01-01', 'asc')).toBeGreaterThan(0)
    expect(compareEventDates(null, '2026-01-01', 'desc')).toBeGreaterThan(0)
    expect(compareEventDates('2026-01-01', '', 'asc')).toBeLessThan(0)
    expect(compareEventDates('', null, 'asc')).toBe(0)
  })
})
