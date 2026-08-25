import type { FoiContract } from '@/types/foiParcurs'

// The date a session actually drove — departure if recorded, else the row's
// creation time. This is the meaningful, editable "Data" for a Foaie de Parcurs.
export function driveDate(c: FoiContract): string {
  return c.departure_datetime || c.created_at || ''
}

// Flag sessions whose date and/or odometer contradict the physical odometer
// progression. Walking sessions in odometer order (km_start, then km_end):
//   • overlap        — km_start is BELOW the running max km_end of earlier
//                      (lower-odometer) sessions: the car was already past it
//                      (e.g. a new drive started at 1700 while a prior one had
//                      already reached 1730, because it wasn't closed first).
//   • date inversion — the drive date is EARLIER than a lower-odometer session's
//                      date: impossible when the odometer only moves forward.
// Returns id → Romanian reason (for a warning badge + tooltip); a clean session
// is absent from the map.
export function sessionAnomalies(sessions: FoiContract[]): Map<number, string> {
  const out = new Map<number, string>()
  const sorted = [...sessions].sort(
    (a, b) => (a.km_start ?? 0) - (b.km_start ?? 0) || (a.km_end ?? 0) - (b.km_end ?? 0),
  )
  let maxEnd: number | null = null
  let maxDate = ''
  for (const s of sorted) {
    // A no-show ('MISSED') or not-yet-driven ('PLANNED'/'PENDING') session never
    // moved the car: it holds its *planned* date at whatever odometer was current
    // when it was scheduled. Letting it into the walk would flag every real,
    // later-odometer drive that legitimately happened before that planned date
    // (a frozen-odometer/future-date phantom). It can neither be nor cause a real
    // odometer↔date contradiction, so skip it entirely.
    if (s.status === 'MISSED' || s.status === 'PLANNED' || s.status === 'PENDING') continue
    const reasons: string[] = []
    const start = s.km_start ?? 0
    if (maxEnd != null && start < maxEnd) {
      reasons.push(`Kilometraj suprapus: pornire ${start} sub finalul anterior ${maxEnd}`)
    }
    const d = driveDate(s)
    if (d && maxDate && d < maxDate) {
      reasons.push('Data este anterioară unei sesiuni cu kilometraj mai mic')
    }
    if (reasons.length) out.set(s.id, reasons.join(' · '))
    if (s.km_end != null && (maxEnd == null || s.km_end > maxEnd)) maxEnd = s.km_end
    if (d && d > maxDate) maxDate = d
  }
  return out
}
