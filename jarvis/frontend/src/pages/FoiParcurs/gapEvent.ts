import type { GapFillContract } from '@/api/foiParcurs'

/** {year, month} from an ISO 'YYYY-MM-DD' date, or null when absent/malformed.
 *  Used to derive a gap resolution's foaie period from the entered date — which
 *  is clamped between the two bounding sessions — so it no longer depends on the
 *  table's month filter (0 = "Toate lunile", which the backend rejects). */
export function periodFromISODate(iso: string): { year: number; month: number } | null {
  const m = /^(\d{4})-(\d{2})-\d{2}/.exec(iso || '')
  return m ? { year: Number(m[1]), month: Number(m[2]) } : null
}

export interface EventGapInput {
  eventName: string
  eventDate: string      // interval start → Plecare
  eventEnd?: string      // interval end → Sosire (omit for a same-day event)
  eventDriver?: string
}

/** Build the single gap-fill contract that attributes the WHOLE odometer gap
 *  [kmStart, kmEnd] to a promo event. No client / signature / license — just the
 *  event name (rendered as "participare la {event}" on the sheet), the interval
 *  (start → end) and an optional consilier (Șofer). */
export function buildEventGapContract(
  gap: { kmStart: number; kmEnd: number },
  input: EventGapInput,
): GapFillContract {
  return {
    date: input.eventDate,
    end_date: input.eventEnd?.trim() || undefined,
    event_name: input.eventName.trim(),
    km_start: gap.kmStart,
    km_end: gap.kmEnd,
    advisor_name: input.eventDriver?.trim() || undefined,
  }
}
