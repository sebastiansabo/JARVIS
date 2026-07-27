import { describe, it, expect } from 'vitest'
import {
  seedReturnDamage, kmEndError, returnMissing, isReturnValid, buildReturnPayload,
  type ReturnFormState,
} from './returnLogic'
import { makeEmptyDamageState } from './testDriveDamage'

const base: ReturnFormState = {
  kmEnd: '', fuel: null, damage: makeEmptyDamageState(),
  notes: '', advisorSignature: '', clientSignature: '',
}

describe('kmEndError', () => {
  it('no error when empty (untouched)', () => expect(kmEndError('', 100)).toBeNull())
  it('errors when below km_start', () => expect(kmEndError('90', 100)).toMatch(/≥ km plecare/))
  it('ok when >= km_start', () => expect(kmEndError('120', 100)).toBeNull())
  it('errors on non-numeric', () => expect(kmEndError('abc', 100)).toMatch(/invalid/))
})

describe('returnMissing / isReturnValid', () => {
  it('everything missing on a blank form', () => {
    const m = returnMissing(base, 100)
    expect(m).toEqual({ km: true, fuel: true, advisorSig: true, clientSig: true })
    expect(isReturnValid(base, 100)).toBe(false)
  })
  it('valid once km/fuel/both sigs present', () => {
    const s: ReturnFormState = { ...base, kmEnd: '150', fuel: '1/2', advisorSignature: 'a', clientSignature: 'b' }
    expect(isReturnValid(s, 100)).toBe(true)
  })
  it('km below start keeps it invalid', () => {
    const s: ReturnFormState = { ...base, kmEnd: '50', fuel: '1/2', advisorSignature: 'a', clientSignature: 'b' }
    expect(isReturnValid(s, 100)).toBe(false)
  })
})

describe('seedReturnDamage', () => {
  it('seeds from departure_damage when present', () => {
    const { damage, seeded } = seedReturnDamage({ departure_damage: [{ zone: 'Față', severity: 'minor', note: 'zgârietură' }] })
    expect(seeded).toBe(true)
    expect(damage['Față'].severity).toBe('Minor')
  })
  it('empty state when no departure damage', () => {
    const { seeded } = seedReturnDamage({ departure_damage: null })
    expect(seeded).toBe(false)
  })
})

describe('buildReturnPayload', () => {
  it('builds the API payload, omitting empty notes', () => {
    const s: ReturnFormState = { ...base, kmEnd: '150', fuel: 'Plin', advisorSignature: 'a', clientSignature: 'b', notes: '  ' }
    const p = buildReturnPayload(s)
    expect(p).toEqual({ km_end: 150, fuel_gauge_end_level: 'Plin', return_damage: [], advisor_signature: 'a', client_signature: 'b' })
  })
})
