/** A per-day worked interval in whole hours; either bound may be unset. */
export interface DayInterval {
  start: number | null
  end: number | null
}

export type DayHours = Record<string, DayInterval>

/**
 * Total worked hours for a participant: the sum of `end - start` over every day
 * that has a full, positive interval. Days missing a bound (or with end ≤ start)
 * contribute nothing. Whole hours in, whole hours out.
 */
export function eventHoursFromDayHours(dayHours: DayHours | undefined | null): number {
  if (!dayHours) return 0
  let total = 0
  for (const { start, end } of Object.values(dayHours)) {
    if (start == null || end == null) continue
    if (end > start) total += end - start
  }
  return total
}
