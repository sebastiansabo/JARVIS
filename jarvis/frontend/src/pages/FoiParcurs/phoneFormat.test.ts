import { describe, it, expect } from 'vitest'
import { composePhone, COUNTRY_DIAL_CODES } from './phoneFormat'

describe('composePhone', () => {
  it('RO number with trunk 0 → strips the 0 and prefixes +40', () =>
    expect(composePhone('+40', '0721234567')).toEqual({ full: '+40721234567', valid: true }))

  it('RO number without trunk 0 → prefixes +40', () =>
    expect(composePhone('+40', '721234567')).toEqual({ full: '+40721234567', valid: true }))

  it('strips spaces and dashes from the number', () =>
    expect(composePhone('+40', '0721 234-567')).toEqual({ full: '+40721234567', valid: true }))

  it('accepts an international number under a foreign dial code', () =>
    expect(composePhone('+49', '1701234567')).toEqual({ full: '+491701234567', valid: true }))

  it('rejects a too-short local number', () =>
    expect(composePhone('+40', '12345')).toEqual({ full: '+4012345', valid: false }))

  it('rejects a non-digit local number', () =>
    expect(composePhone('+40', '72abc123')).toMatchObject({ valid: false }))

  it('empty number → empty + invalid', () =>
    expect(composePhone('+40', '')).toEqual({ full: '', valid: false }))

  it('caps at E.164 length (15 digits total)', () =>
    expect(composePhone('+40', '99999999999999999')).toMatchObject({ valid: false }))
})

describe('COUNTRY_DIAL_CODES', () => {
  it('defaults to Romania first', () =>
    expect(COUNTRY_DIAL_CODES[0].code).toBe('+40'))

  it('includes a non-RO code for international numbers', () =>
    expect(COUNTRY_DIAL_CODES.map((c) => c.code)).toContain('+49'))

  it('every entry carries a flag emoji', () =>
    expect(COUNTRY_DIAL_CODES.every((c) => !!c.flag)).toBe(true))

  it('Romania uses the RO flag', () =>
    expect(COUNTRY_DIAL_CODES[0].flag).toBe('🇷🇴'))

  it('covers a broad set of European countries', () => {
    expect(COUNTRY_DIAL_CODES.length).toBeGreaterThanOrEqual(20)
    const codes = COUNTRY_DIAL_CODES.map((c) => c.code)
    expect(codes).toEqual(expect.arrayContaining(['+48', '+31', '+41', '+380']))
  })
})
