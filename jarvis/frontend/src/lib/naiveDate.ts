/** Parse a backend datetime as a *naive wall-clock* time — dropping any timezone
 *  designator so it is read exactly as stored, not shifted to the viewer's zone.
 *
 *  TD departure/return times are wall-clock local values (e.g. "13:00"), but the
 *  backend column is `timestamptz` and serializes them with a `+00:00` zone
 *  (session tz = GMT). `new Date("…T13:00:00+00:00")` renders as 16:00 in Romania
 *  (UTC+3). Stripping the zone makes `new Date` treat it as local, so 13:00 stays
 *  13:00. Returns null for empty/invalid input.
 *
 *  Do NOT use for true instants (created_at, returned_at) — those should convert
 *  to local normally.
 */
export function naiveDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const s = String(iso)
    .replace(' ', 'T')
    .replace(/(?:Z|[+-]\d{2}(?::?\d{2})?)$/, '') // strip Z / +HH / +HHMM / +HH:MM
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}
