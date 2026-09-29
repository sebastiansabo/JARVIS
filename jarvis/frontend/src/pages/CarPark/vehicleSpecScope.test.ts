import { describe, test, expect } from 'vitest'
import {
  usesFuelTank,
  usesBattery,
  usesCargo,
  specFieldsToClear,
  TANK_FIELDS,
  BATTERY_FIELDS,
  CARGO_FIELDS,
} from './vehicleSpecScope'

describe('fuel/body predicates', () => {
  test('ethanol is a combustion fuel that uses a tank', () => {
    // Regression: ethanol was previously excluded from the tank set, which
    // wiped its consumption/tank specs on save.
    expect(usesFuelTank('ethanol')).toBe(true)
  })
  test('pure electric has no combustion tank', () => {
    expect(usesFuelTank('electric')).toBe(false)
  })
  test('diesel has no traction battery', () => {
    expect(usesBattery('diesel')).toBe(false)
  })
  test('electric uses a traction battery', () => {
    expect(usesBattery('electric')).toBe(true)
  })
  test('minivan is treated as cargo-capable (not stripped)', () => {
    expect(usesCargo('minivan')).toBe(true)
  })
  test('sedan is not cargo-capable', () => {
    expect(usesCargo('sedan')).toBe(false)
  })
})

describe('specFieldsToClear', () => {
  test('empty fuel_type and body_type clear NOTHING', () => {
    // The core data-loss bug: a blank/unmapped fuel_type must never wipe specs.
    expect(specFieldsToClear('', '')).toEqual([])
  })

  test('unrecognized fuel_type clears no fuel/battery specs', () => {
    // Unknown fuel → preserve tank + battery; sedan is known non-cargo → clear cargo.
    expect(specFieldsToClear('space-fuel', 'sedan')).toEqual([...CARGO_FIELDS])
  })

  test('ethanol keeps tank specs, clears battery specs', () => {
    const cleared = specFieldsToClear('ethanol', 'sedan')
    for (const f of TANK_FIELDS) expect(cleared).not.toContain(f)
    for (const f of BATTERY_FIELDS) expect(cleared).toContain(f)
  })

  test('electric clears tank specs, keeps battery specs', () => {
    const cleared = specFieldsToClear('electric', 'sedan')
    for (const f of TANK_FIELDS) expect(cleared).toContain(f)
    for (const f of BATTERY_FIELDS) expect(cleared).not.toContain(f)
  })

  test('petrol van keeps tank and cargo, clears only battery', () => {
    expect(specFieldsToClear('petrol', 'van').sort()).toEqual([...BATTERY_FIELDS].sort())
  })

  test('minivan cargo specs are preserved (regression)', () => {
    const cleared = specFieldsToClear('diesel', 'minivan')
    for (const f of CARGO_FIELDS) expect(cleared).not.toContain(f)
  })

  test('empty body_type never clears cargo specs', () => {
    const cleared = specFieldsToClear('petrol', '')
    for (const f of CARGO_FIELDS) expect(cleared).not.toContain(f)
  })
})
