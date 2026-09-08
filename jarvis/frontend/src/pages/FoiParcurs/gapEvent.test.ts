import { describe, it, expect } from 'vitest'
import { buildEventGapContract, periodFromISODate } from './gapEvent'

const gap = { kmStart: 7554, kmEnd: 7880 } // 326 km gap

describe('periodFromISODate', () => {
  it('derives {year, month} from an ISO date', () => {
    expect(periodFromISODate('2026-07-28')).toEqual({ year: 2026, month: 7 })
  })
  it('reads the month, not the day', () => {
    expect(periodFromISODate('2026-12-01')).toEqual({ year: 2026, month: 12 })
  })
  it('returns null when absent or malformed', () => {
    expect(periodFromISODate('')).toBeNull()
    expect(periodFromISODate('not-a-date')).toBeNull()
  })
})

describe('buildEventGapContract', () => {
  it('attributes the WHOLE gap to the event', () => {
    const c = buildEventGapContract(gap, { eventName: 'Salon Auto', eventDate: '2026-08-26' })
    expect(c.km_start).toBe(7554)
    expect(c.km_end).toBe(7880)
    expect(c.event_name).toBe('Salon Auto')
    expect(c.date).toBe('2026-08-26')
    expect(c.client_name).toBeUndefined()
  })

  it('trims the event name and consilier', () => {
    const c = buildEventGapContract(gap, { eventName: '  Târg Auto  ', eventDate: '2026-08-26', eventDriver: '  Ion  ' })
    expect(c.event_name).toBe('Târg Auto')
    expect(c.advisor_name).toBe('Ion')
  })

  it('omits the consilier when blank', () => {
    const c = buildEventGapContract(gap, { eventName: 'X', eventDate: '2026-08-26', eventDriver: '   ' })
    expect(c.advisor_name).toBeUndefined()
  })

  it('carries an end date as the interval Sosire when provided', () => {
    const c = buildEventGapContract(gap, { eventName: 'X', eventDate: '2026-08-05', eventEnd: '2026-08-12' })
    expect(c.date).toBe('2026-08-05')
    expect(c.end_date).toBe('2026-08-12')
  })

  it('omits end_date for a same-day event', () => {
    const c = buildEventGapContract(gap, { eventName: 'X', eventDate: '2026-08-05' })
    expect(c.end_date).toBeUndefined()
  })
})
