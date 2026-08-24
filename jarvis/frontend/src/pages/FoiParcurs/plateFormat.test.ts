import { describe, it, expect } from 'vitest'
import { formatRoPlate, isValidRoPlate } from './plateFormat'

describe('formatRoPlate', () => {
  it('formats a two-letter county plate with spaces', () => {
    expect(formatRoPlate('cj12abc')).toBe('CJ 12 ABC')
  })
  it('normalizes dashed input to the canonical spaced form', () => {
    expect(formatRoPlate('CJ-12-ABC')).toBe('CJ 12 ABC')
  })
  it('treats a leading B followed by a digit as Bucharest (3 digits allowed)', () => {
    expect(formatRoPlate('b123xyz')).toBe('B 123 XYZ')
  })
  it('treats BH as the Bihor county, not Bucharest', () => {
    expect(formatRoPlate('bh12abc')).toBe('BH 12 ABC')
  })
  it('caps a two-letter county at 2 digits', () => {
    expect(formatRoPlate('CJ123AB')).toBe('CJ 12 AB')
  })
  it('keeps 6 digits for a provisional plate (no letters), capping extras', () => {
    expect(formatRoPlate('cj1234567890')).toBe('CJ 123456')
  })
  it('keeps a 6-digit provisional Bucharest number (no 3-digit cap)', () => {
    expect(formatRoPlate('B123456')).toBe('B 123456')
  })
})

describe('isValidRoPlate', () => {
  it('accepts a canonical county plate', () => {
    expect(isValidRoPlate('CJ 12 ABC')).toBe(true)
  })
  it('accepts a Bucharest 3-digit plate', () => {
    expect(isValidRoPlate('B 123 XYZ')).toBe(true)
  })
  it('rejects a 3-digit two-letter-county plate', () => {
    expect(isValidRoPlate('CJ 123 ABC')).toBe(false)
  })
  it('rejects too-few letters', () => {
    expect(isValidRoPlate('CJ 12 AB')).toBe(false)
  })
  it('accepts a 6-digit provisional plate', () => {
    expect(isValidRoPlate('CJ 123456')).toBe(true)
  })
  it('accepts a 6-digit provisional Bucharest plate', () => {
    expect(isValidRoPlate('B 123456')).toBe(true)
  })
  it('rejects a provisional plate that is not exactly 6 digits', () => {
    expect(isValidRoPlate('CJ 12345')).toBe(false)
    expect(isValidRoPlate('CJ 1234567890')).toBe(false)
  })
  it('still rejects an incomplete standard plate (2 digits, no letters)', () => {
    expect(isValidRoPlate('CJ 02')).toBe(false)
  })
})
