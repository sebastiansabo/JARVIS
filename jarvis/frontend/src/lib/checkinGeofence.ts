// Geofence decision helpers for GPS check-in (pure, unit-tested).

/**
 * Whether a GPS fix is good enough to punch with.
 *
 * A fix is usable only when it is both *in range* (the server will accept it:
 * distance within the location radius) and *precise enough to trust* (the
 * accuracy radius is no larger than the geofence — otherwise landing "inside"
 * is luck, not proof). Indoors, phones fall back to cell/WiFi positioning and
 * report huge accuracy, so this gates them out and the UI steers to WiFi/QR.
 */
export function gpsUsable(
  nearestDist: number | null,
  nearestRadius: number | null,
  accuracy: number | null,
): boolean {
  if (nearestDist === null || nearestRadius === null || accuracy === null) return false
  return nearestDist <= nearestRadius && accuracy <= nearestRadius
}
