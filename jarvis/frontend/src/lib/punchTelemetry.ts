/**
 * Punch-in/out telemetry event taxonomy for the web check-in card. Mirrors the
 * jarvis-mobile-2 taxonomy so web + mobile punches share the same analytics:
 * every tap, every success, every backend rejection lands in `telemetry_events`.
 *
 * Privacy: events carry OUTCOME + distance-from-office + location name only —
 * never raw GPS coordinates.
 *
 * Web vs. mobile: the web flow does not block on a failed GPS fix — it falls
 * back to an IP/WiFi attempt — so instead of a "Punch Blocked" event a missing
 * fix rides as a `gps_unavailable` flag on the *outcome* (Succeeded/Rejected).
 * The tap itself is emitted at press time (before GPS resolves) so an attempt
 * abandoned during GPS acquisition is still recorded.
 *
 * Builders are pure so they can be unit-tested without mocking the emitter.
 */
import { telemetry } from './telemetry'

export type PunchIntent = 'IN' | 'OUT'
export type PunchMethod = 'gps' | 'wifi'

export interface PunchEvent {
  name: string
  props: Record<string, unknown>
}

/** Classify a backend punch rejection from HTTP status + error message. */
function rejectReason(status: number | undefined, message: string | undefined): string {
  if (status === 0 || status == null) return 'network'
  const m = (message || '').toLowerCase()
  if (m.includes('too far')) return 'too_far'
  if (m.includes('duplicate')) return 'duplicate'
  if (m.includes('mapping')) return 'no_mapping'
  if (m.includes('not recognized') || m.includes('no gps')) return 'no_match'
  return 'unknown'
}

export function tappedEvent(intent: PunchIntent, method: PunchMethod): PunchEvent {
  return { name: 'Punch Tapped', props: { intent_direction: intent, method } }
}

export function succeededEvent(args: { direction: PunchIntent; location?: string; distance?: number; durationMs?: number; gpsUnavailable?: boolean }): PunchEvent {
  const props: Record<string, unknown> = {
    direction: args.direction,
    resulting_state: args.direction === 'OUT' ? 'checked_out' : 'checked_in',
  }
  if (args.location != null) props.location_name = args.location
  if (args.distance != null) props.distance_meters = args.distance
  if (args.durationMs != null) props.duration_ms = args.durationMs
  if (args.gpsUnavailable) props.gps_unavailable = true
  return { name: 'Punch Succeeded', props }
}

export function rejectedEvent(args: { status?: number; message?: string; distance?: number; location?: string; allowedRadius?: number; gpsUnavailable?: boolean }): PunchEvent {
  const props: Record<string, unknown> = {
    reason: rejectReason(args.status, args.message),
    api_status: args.status ?? 0,
  }
  if (args.message) props.error_message = args.message.slice(0, 500)
  if (args.distance != null) props.distance_meters = args.distance
  if (args.location != null) props.location_name = args.location
  if (args.allowedRadius != null) props.allowed_radius = args.allowedRadius
  if (args.gpsUnavailable) props.gps_unavailable = true
  return { name: 'Punch Rejected', props }
}

/** Fire-and-forget: hand a built event to the telemetry emitter. */
export function emit(e: PunchEvent): void {
  telemetry.track(e.name, e.props)
}
