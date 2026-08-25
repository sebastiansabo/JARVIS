import { describe, it, expect } from 'vitest'
import { quickSessionError, type QuickSessionForm } from './InternalSessionForm'

const valid: QuickSessionForm = {
  vin: 'VF1XXXXXXXX',
  driver: 'Ana Pop',
  departure: '2026-08-19T09:00',
  ret: '2026-08-19T10:00',
  kmStart: '12345',
}

describe('quickSessionError (ported verbatim from mobile QuickSession)', () => {
  it('returns null when every field is valid', () => {
    expect(quickSessionError(valid)).toBeNull()
  })

  it('returns null when the optional return is empty', () => {
    expect(quickSessionError({ ...valid, ret: '' })).toBeNull()
  })

  it('flags a missing vehicle', () => {
    expect(quickSessionError({ ...valid, vin: '' })).toBe('vehicle_required')
  })

  it('flags a missing driver', () => {
    expect(quickSessionError({ ...valid, driver: '' })).toBe('driver_required')
  })

  it('flags a missing departure', () => {
    expect(quickSessionError({ ...valid, departure: '' })).toBe('departure_required')
  })

  it('flags a missing starting km', () => {
    expect(quickSessionError({ ...valid, kmStart: '' })).toBe('km_required')
  })

  it('accepts a starting km of "0" (non-empty string)', () => {
    expect(quickSessionError({ ...valid, kmStart: '0' })).toBeNull()
  })

  it('flags a return before the departure', () => {
    expect(quickSessionError({ ...valid, departure: '2026-08-19T09:00', ret: '2026-08-19T08:00' })).toBe('return_before_departure')
  })

  it('checks fields in priority order: vehicle before driver before departure before km before return', () => {
    expect(quickSessionError({ vin: '', driver: '', departure: '', ret: '', kmStart: '' })).toBe('vehicle_required')
    expect(quickSessionError({ vin: 'X', driver: '', departure: '', ret: '', kmStart: '' })).toBe('driver_required')
    expect(quickSessionError({ vin: 'X', driver: 'Y', departure: '', ret: '', kmStart: '' })).toBe('departure_required')
    expect(quickSessionError({ vin: 'X', driver: 'Y', departure: '2026-08-19T09:00', ret: '', kmStart: '' })).toBe('km_required')
  })
})

describe('quickSessionError in planning mode (km deferred to start)', () => {
  it('does NOT require km when planning', () => {
    expect(quickSessionError({ ...valid, kmStart: '' }, { planning: true })).toBeNull()
  })

  it('still requires vehicle, driver and departure when planning', () => {
    expect(quickSessionError({ ...valid, vin: '', kmStart: '' }, { planning: true })).toBe('vehicle_required')
    expect(quickSessionError({ ...valid, driver: '', kmStart: '' }, { planning: true })).toBe('driver_required')
    expect(quickSessionError({ ...valid, departure: '', kmStart: '' }, { planning: true })).toBe('departure_required')
  })

  it('still rejects a return before departure when planning', () => {
    expect(quickSessionError({ ...valid, departure: '2026-08-19T09:00', ret: '2026-08-19T08:00', kmStart: '' }, { planning: true }))
      .toBe('return_before_departure')
  })
})
