import { describe, it, expect } from 'vitest'
import { correctionErrors } from './CorrectSessionDialog'

const st = (o: Partial<{ departure: string; ret: string; kmStart: string; kmEnd: string }> = {}) => ({
  departure: '', ret: '', kmStart: '1000', kmEnd: '1200', ...o,
})

describe('correctionErrors', () => {
  it('blank KM start is invalid — never coerces to 0', () => {
    expect(correctionErrors(st({ kmStart: '' })).km).toMatch(/obligatorii/)
  })
  it('blank KM final is invalid', () => {
    expect(correctionErrors(st({ kmEnd: '' })).km).toMatch(/obligatorii/)
  })
  it('KM final below KM start is invalid', () => {
    expect(correctionErrors(st({ kmStart: '1200', kmEnd: '1000' })).km).toMatch(/mai mic/)
  })
  it('valid KM pair passes', () => {
    expect(correctionErrors(st()).km).toBeNull()
  })
  it('return before departure is invalid', () => {
    expect(correctionErrors(st({ departure: '2026-08-02T10:00', ret: '2026-08-02T09:00' })).date).toMatch(/retur/)
  })
  it('equal departure/return is allowed', () => {
    expect(correctionErrors(st({ departure: '2026-08-02T10:00', ret: '2026-08-02T10:00' })).date).toBeNull()
  })
})
