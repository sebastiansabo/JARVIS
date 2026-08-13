// Pin a non-UTC zone BEFORE any Date is constructed. TD departure/return are
// naive Bucharest wall-clock values that the backend serializes as timestamptz
// with a "+00:00" suffix; a viewer in Romania (UTC+2/+3) is where the shift bug
// shows. Node re-reads process.env.TZ per Date op, so setting it here is enough.
process.env.TZ = 'Europe/Bucharest'

import { describe, it, expect } from 'vitest'
import { fmtDateTime } from './DrivingSessionsList'

describe('DrivingSessionsList fmtDateTime', () => {
  it('renders the stored wall-clock hour, not the viewer-tz-shifted hour', () => {
    // Driver entered a 13:00 departure. dict_from_row().isoformat() on the
    // timestamptz column (DB session = UTC) hands the frontend this string:
    const out = fmtDateTime('2026-08-13T13:00:00+00:00')
    expect(out).toContain('13:00')      // as entered / as the desktop module shows
    expect(out).not.toContain('16:00')  // the +3h shift a plain `new Date` produces
  })

  it('returns an em dash for empty input', () => {
    expect(fmtDateTime(null)).toBe('—')
    expect(fmtDateTime(undefined)).toBe('—')
    expect(fmtDateTime('')).toBe('—')
  })
})
