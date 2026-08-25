import { describe, it, expect } from 'vitest'
import { sessionAnomalies, driveDate } from './anomalies'
import type { FoiContract } from '@/types/foiParcurs'

const s = (o: Partial<FoiContract>): FoiContract => o as FoiContract

describe('driveDate', () => {
  it('prefers departure_datetime', () =>
    expect(driveDate(s({ departure_datetime: '2026-08-06T09:00', created_at: '2026-08-01T00:00' }))).toBe('2026-08-06T09:00'))
  it('falls back to created_at when departure is missing', () =>
    expect(driveDate(s({ departure_datetime: null, created_at: '2026-08-01T00:00' }))).toBe('2026-08-01T00:00'))
})

describe('sessionAnomalies', () => {
  it('flags an odometer overlap (a session starting below a prior end)', () => {
    // The T-Roc case: 1602→1730 finalized, then a new drive starts at 1700 (< 1730).
    const a = sessionAnomalies([
      s({ id: 1, km_start: 1602, km_end: 1730, departure_datetime: '2026-08-10T09:00' }),
      s({ id: 2, km_start: 1700, km_end: 1800, departure_datetime: '2026-08-11T09:00' }),
    ])
    expect(a.has(2)).toBe(true)
    expect(a.get(2)).toMatch(/suprapus/)
    expect(a.has(1)).toBe(false)
  })

  it('flags a date inversion (earlier date at higher odometer)', () => {
    // The Tiguan case: Oasis@921 dated 04.08 sits below Soare@1236 dated 03.08.
    const a = sessionAnomalies([
      s({ id: 1, km_start: 1236, km_end: 1258, departure_datetime: '2026-08-03T09:00' }),
      s({ id: 2, km_start: 921, km_end: 921, departure_datetime: '2026-08-04T09:00' }),
    ])
    // odometer order id2(921) then id1(1236); id1's date 08-03 precedes id2's 08-04.
    expect(a.has(1)).toBe(true)
    expect(a.get(1)).toMatch(/Data/)
  })

  it('returns no anomalies when date and odometer both increase', () => {
    const a = sessionAnomalies([
      s({ id: 1, km_start: 1000, km_end: 1100, departure_datetime: '2026-08-01T09:00' }),
      s({ id: 2, km_start: 1100, km_end: 1200, departure_datetime: '2026-08-02T09:00' }),
      s({ id: 3, km_start: 1200, km_end: 1300, departure_datetime: '2026-08-03T09:00' }),
    ])
    expect(a.size).toBe(0)
  })

  it('does not flag an in-progress placeholder (km_end == km_start) as overlap by itself', () => {
    const a = sessionAnomalies([
      s({ id: 1, km_start: 1000, km_end: 1100, departure_datetime: '2026-08-01T09:00' }),
      s({ id: 2, km_start: 1100, km_end: 1100, departure_datetime: '2026-08-02T09:00' }),
    ])
    expect(a.size).toBe(0)
  })

  it('ignores a MISSED no-show that holds a planned date at a frozen odometer', () => {
    // Real MG4 (VIN …037508) case: session 311 is a no-show (MISSED) parked at
    // km 6749 with a *planned* date of 22.08, while the real drives at 6801→6914
    // legitimately happened 19–21.08. The no-show never moved the car, so it must
    // not flag every earlier-dated, higher-odometer real drive above it.
    const a = sessionAnomalies([
      s({ id: 311, status: 'MISSED', km_start: 6749, km_end: 6749, departure_datetime: '2026-08-22T11:30' }),
      s({ id: 322, status: 'COMPLETED', km_start: 6801, km_end: 6814, departure_datetime: '2026-08-19T12:11' }),
      s({ id: 352, status: 'COMPLETED', km_start: 6872, km_end: 6892, departure_datetime: '2026-08-21T12:56' }),
      s({ id: 363, status: 'COMPLETED', km_start: 6925, km_end: 6947, departure_datetime: '2026-08-22T12:37' }),
    ])
    expect(a.size).toBe(0)
  })

  it('still flags a real (non-MISSED) date inversion at a frozen odometer', () => {
    // Guard must be status-scoped, not km-scoped: the Tiguan-style inversion
    // (a genuine zero-km session dated after a higher-odometer one) must survive.
    const a = sessionAnomalies([
      s({ id: 1, status: 'COMPLETED', km_start: 1236, km_end: 1258, departure_datetime: '2026-08-03T09:00' }),
      s({ id: 2, status: 'COMPLETED', km_start: 921, km_end: 921, departure_datetime: '2026-08-04T09:00' }),
    ])
    expect(a.has(1)).toBe(true)
  })
})
