/**
 * Pure helpers for the Events table quick date filters and date-column sort.
 * Kept separate from EventsTab so the date maths is unit-testable in isolation.
 */

export type EventDateRange = { from: string; to: string }

/** Format a Date as a local YYYY-MM-DD string. */
function fmt(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * Full calendar-month range offset from `now` (0 = this month, -1 = last
 * month). Day 0 of the next month gives the last day of the target month,
 * which also rolls years correctly.
 */
export function monthRange(offsetMonths: number, now: Date = new Date()): EventDateRange {
  const start = new Date(now.getFullYear(), now.getMonth() + offsetMonths, 1)
  const end = new Date(now.getFullYear(), now.getMonth() + offsetMonths + 1, 0)
  return { from: fmt(start), to: fmt(end) }
}

/** Jan 1 → Dec 31 of `now`'s year. */
export function yearRange(now: Date = new Date()): EventDateRange {
  const y = now.getFullYear()
  return { from: `${y}-01-01`, to: `${y}-12-31` }
}

/** The always-visible quick-filter chips, in display order. */
export const EVENT_QUICK_RANGES: ReadonlyArray<{
  key: string
  label: string
  range: (now?: Date) => EventDateRange
}> = [
  { key: 'this_month', label: 'This Month', range: (now) => monthRange(0, now) },
  { key: 'last_month', label: 'Last Month', range: (now) => monthRange(-1, now) },
  { key: 'this_year', label: 'This Year', range: (now) => yearRange(now) },
]

/**
 * Compare two ISO (YYYY-MM-DD) date strings for sorting. Empty/null dates
 * always sort last, regardless of direction.
 */
export function compareEventDates(
  a: string | null | undefined,
  b: string | null | undefined,
  dir: 'asc' | 'desc',
): number {
  const av = a || ''
  const bv = b || ''
  if (!av && !bv) return 0
  if (!av) return 1
  if (!bv) return -1
  const cmp = av < bv ? -1 : av > bv ? 1 : 0
  return dir === 'asc' ? cmp : -cmp
}
