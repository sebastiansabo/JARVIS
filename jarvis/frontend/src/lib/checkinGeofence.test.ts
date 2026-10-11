import { describe, it, expect } from 'vitest'
import { gpsUsable } from './checkinGeofence'

describe('gpsUsable — is a GPS fix good enough to punch with', () => {
  it('true only when the fix is in range AND precise enough to trust', () => {
    // Inside the 150m radius with a tight 20m fix → trust it.
    expect(gpsUsable(30, 150, 20)).toBe(true)
    // Boundary: distance and accuracy exactly at the radius still count.
    expect(gpsUsable(150, 150, 150)).toBe(true)
  })

  it('false when the fix is out of range, however precise', () => {
    // The indoor-showroom case: 709m away, and even a hypothetical tight fix fails.
    expect(gpsUsable(709, 150, 1414)).toBe(false)
    expect(gpsUsable(709, 150, 10)).toBe(false)
  })

  it('false when the fix lands in range but the accuracy is larger than the radius', () => {
    // 30m "inside" but ±1414m uncertainty — being inside is luck, not proof.
    expect(gpsUsable(30, 150, 1414)).toBe(false)
  })

  it('false when any input is missing (no fix / no accuracy / no location)', () => {
    expect(gpsUsable(null, 150, 20)).toBe(false)
    expect(gpsUsable(30, null, 20)).toBe(false)
    expect(gpsUsable(30, 150, null)).toBe(false)
  })
})
