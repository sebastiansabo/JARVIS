import { naiveDate } from './naiveDate'

/** Format a BioStar punch timestamp as its Romania-local wall-clock `HH:MM`.
 *
 *  Punch times are stored as local wall-clock values but serialised from a
 *  `timestamptz` column with a `+00:00` zone. Formatting them with a plain
 *  `new Date(...)` re-reads them as UTC and shifts them by the viewer's offset
 *  (+3h in EEST) — see {@link naiveDate}. This strips the zone first so the
 *  displayed time matches what the terminal actually recorded.
 *
 *  Use for punch/attendance times (first_punch, last_punch, adjusted_*,
 *  event_datetime). Do NOT use for true instants (created_at, returned_at).
 */
export function fmtPunchTime(
  dt: string | null | undefined,
  { seconds = false, empty = '—' }: { seconds?: boolean; empty?: string } = {},
): string {
  const d = naiveDate(dt)
  if (!d) return empty
  return d.toLocaleTimeString('ro-RO', {
    hour: '2-digit',
    minute: '2-digit',
    ...(seconds ? { second: '2-digit' } : {}),
  })
}
