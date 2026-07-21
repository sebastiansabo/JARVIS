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
  let s = String(iso ?? '').replace(' ', 'T')
  // Strip the zone only from the time part (after 'T'), so a date-only value
  // like "2026-08-02" is never mangled (its trailing "-02" is not an offset).
  const t = s.indexOf('T')
  if (t >= 0) {
    s = s.slice(0, t + 1) + s.slice(t + 1).replace(/(?:Z|[+-]\d{2}(?::?\d{2})?)$/, '')
  }
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}
