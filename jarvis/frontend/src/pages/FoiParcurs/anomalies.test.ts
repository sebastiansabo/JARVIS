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
})
