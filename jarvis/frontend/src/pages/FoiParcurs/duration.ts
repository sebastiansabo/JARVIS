import { naiveDate } from '@/lib/naiveDate'

// Compact human duration between a session's departure and return, e.g.
// "1h 57m", "45m", "2h", "2z 3h". Empty string when either end is missing/
// invalid or the interval is non-positive. Both ends are parsed as naive
// wall-clock, so any timezone offset cancels in the subtraction.
export function fmtDuration(departure?: string | null, ret?: string | null): string {
  if (!departure || !ret) return ''
  const a = naiveDate(departure)
  const b = naiveDate(ret)
  if (!a || !b) return ''
  const mins = Math.round((b.getTime() - a.getTime()) / 60000)
  if (mins <= 0) return ''
  const d = Math.floor(mins / 1440)
  const h = Math.floor((mins % 1440) / 60)
  const m = mins % 60
  if (d > 0) return h > 0 ? `${d}z ${h}h` : `${d}z`
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}
