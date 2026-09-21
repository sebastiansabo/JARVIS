import { describe, test, expect } from 'vitest'
import { toCanonical, netLeiFromCanonical, netLeiFromGrossEur } from './acquisitionCanonical'

describe('toCanonical', () => {
  test('net LEI + VAT + kurs → gross EUR acquisition + net EUR ppn', () => {
    // 40000 net LEI, 19% VAT, kurs 5.0 → gross LEI 47600 → gross EUR 9520; net EUR 8000
    expect(toCanonical({ netLei: 40000, vatRate: 19, kurs: 5 }))
      .toEqual({ acquisition_price: 9520, purchase_price_net: 8000 })
  })
  test('zero VAT → gross == net', () => {
    expect(toCanonical({ netLei: 25000, vatRate: 0, kurs: 5 }))
      .toEqual({ acquisition_price: 5000, purchase_price_net: 5000 })
  })
  test('missing kurs → nulls', () => {
    expect(toCanonical({ netLei: 40000, vatRate: 19, kurs: 0 }))
      .toEqual({ acquisition_price: null, purchase_price_net: null })
  })
})

describe('netLeiFromCanonical', () => {
  test('net EUR × kurs → net LEI', () => {
    expect(netLeiFromCanonical({ purchase_price_net: 8000, kurs: 5 })).toBe(40000)
  })
  test('missing inputs → null', () => {
    expect(netLeiFromCanonical({ purchase_price_net: null, kurs: 5 })).toBeNull()
  })
})

describe('netLeiFromGrossEur', () => {
  test('gross EUR + VAT + kurs → net LEI (inverse of toCanonical)', () => {
    // 9520 gross EUR, 19% VAT, kurs 5 → gross LEI 47600 → net LEI 40000
    expect(netLeiFromGrossEur({ grossEur: 9520, vatRate: 19, kurs: 5 })).toBe(40000)
  })
  test('zero VAT → gross LEI == net LEI', () => {
    expect(netLeiFromGrossEur({ grossEur: 5000, vatRate: 0, kurs: 5 })).toBe(25000)
  })
  test('missing kurs → null', () => {
    expect(netLeiFromGrossEur({ grossEur: 9520, vatRate: 19, kurs: 0 })).toBeNull()
  })
  test('missing grossEur → null', () => {
    expect(netLeiFromGrossEur({ grossEur: null, vatRate: 19, kurs: 5 })).toBeNull()
  })
})
