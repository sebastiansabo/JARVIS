import { describe, it, expect } from 'vitest'
import { tappedEvent, succeededEvent, rejectedEvent } from './punchTelemetry'

describe('punch telemetry event builders (web)', () => {
  it('Punch Tapped carries intent direction and method, always at tap time', () => {
    expect(tappedEvent('IN', 'gps')).toEqual({
      name: 'Punch Tapped',
      props: { intent_direction: 'IN', method: 'gps' },
    })
    expect(tappedEvent('OUT', 'wifi').props.method).toBe('wifi')
    // Tapped is emitted before GPS resolves, so it never carries the GPS outcome.
    expect(tappedEvent('IN', 'gps').props).not.toHaveProperty('gps_unavailable')
  })

  it('the GPS-fallback flag rides on the outcome, not the tap', () => {
    // A missing fix falls back to IP; the fact is recorded on whatever outcome follows.
    expect(succeededEvent({ direction: 'IN', gpsUnavailable: true }).props.gps_unavailable).toBe(true)
    expect(rejectedEvent({ status: 400, message: 'Too far', gpsUnavailable: true }).props.gps_unavailable).toBe(true)
    // Absent when GPS was available.
    expect(succeededEvent({ direction: 'IN' }).props).not.toHaveProperty('gps_unavailable')
    expect(rejectedEvent({ status: 0, message: 'x' }).props).not.toHaveProperty('gps_unavailable')
  })

  it('Punch Succeeded derives resulting_state and omits empty optionals', () => {
    expect(succeededEvent({ direction: 'IN', location: 'Autoworld Toyota', distance: 19.2 }).props).toMatchObject({
      direction: 'IN',
      location_name: 'Autoworld Toyota',
      distance_meters: 19.2,
      resulting_state: 'checked_in',
    })
    expect(succeededEvent({ direction: 'OUT' }).props.resulting_state).toBe('checked_out')
    expect(succeededEvent({ direction: 'OUT' }).props).not.toHaveProperty('distance_meters')
  })

  it('Punch Succeeded never carries raw coordinates', () => {
    const e = succeededEvent({ direction: 'IN', location: 'X', distance: 5 })
    expect(e.props).not.toHaveProperty('latitude')
    expect(e.props).not.toHaveProperty('longitude')
  })

  it('Punch Rejected classifies reason and carries structured distance/location/radius', () => {
    expect(rejectedEvent({ status: 400, message: 'Too far from Autoworld Toyota (150m away, max 100m)', distance: 150, location: 'Autoworld Toyota', allowedRadius: 100 }).props).toMatchObject({
      reason: 'too_far',
      api_status: 400,
      distance_meters: 150,
      location_name: 'Autoworld Toyota',
      allowed_radius: 100,
    })
    expect(rejectedEvent({ status: 400, message: 'Duplicate punch. Try again in a minute.' }).props.reason).toBe('duplicate')
    expect(rejectedEvent({ status: 400, message: 'No BioStar employee mapping found. Contact HR.' }).props.reason).toBe('no_mapping')
    expect(rejectedEvent({ status: 400, message: 'No GPS and your network is not recognized as an office network.' }).props.reason).toBe('no_match')
    expect(rejectedEvent({ status: 0, message: 'network' }).props.reason).toBe('network')
    expect(rejectedEvent({ status: 500, message: 'boom' }).props.reason).toBe('unknown')
  })
})
