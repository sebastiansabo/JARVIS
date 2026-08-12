import { describe, it, expect } from 'vitest'
import { sessionActualKm, sessionEstimatedKm, carSpanKm } from './distance'
import type { FoiContract } from '@/types/foiParcurs'

const s = (o: Partial<FoiContract>): FoiContract => o as FoiContract

describe('sessionActualKm', () => {
  it('odometer delta when finalized', () =>
    expect(sessionActualKm(s({ status: 'COMPLETED', td_status: 'complete', km_start: 1236, km_end: 1258 }))).toBe(22))
  it('null when in progress (no return)', () =>
    expect(sessionActualKm(s({ status: 'FILLED', km_start: 921, km_end: 921 }))).toBeNull())
  it('null when km_end missing', () =>
    expect(sessionActualKm(s({ status: 'COMPLETED', td_status: 'complete', km_start: 1236, km_end: null }))).toBeNull())
})

describe('sessionEstimatedKm', () => {
  it('returns the entered distance_km', () =>
    expect(sessionEstimatedKm(s({ distance_km: 1286 }))).toBe(1286))
})

describe('carSpanKm', () => {
  it('max end − min start', () =>
    expect(carSpanKm([
      s({ km_start: 921, km_end: 921 }),
      s({ km_start: 1236, km_end: 1258 }),
      s({ km_start: 1281, km_end: 1313 }),
      s({ km_start: 1313, km_end: 1335 }),
    ])).toBe(414))
  it('0 when empty', () => expect(carSpanKm([])).toBe(0))
})
