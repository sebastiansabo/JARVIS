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
})
