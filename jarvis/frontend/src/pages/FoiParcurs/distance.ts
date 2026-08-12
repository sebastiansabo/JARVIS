import type { FoiContract } from '@/types/foiParcurs'
import { sessionStatus } from './sessionStatus'

// Actual distance driven = odometer delta (km_end − km_start). Only meaningful
// once a genuine return odometer exists (Finalizat); otherwise null → render '—'.
export function sessionActualKm(c: FoiContract): number | null {
  if (sessionStatus(c).key !== 'finalizat' || c.km_end == null) return null
  return (c.km_end ?? 0) - (c.km_start ?? 0)
}

// The advisor-entered estimate. Screen-only — never exported.
export function sessionEstimatedKm(c: FoiContract): number {
  return c.distance_km ?? 0
}

// Total physical distance the car moved = odometer span (max km_end − min
// km_start). Authoritative even when individual session ranges overlap.
export function carSpanKm(sessions: FoiContract[]): number {
  if (!sessions.length) return 0
  const starts = sessions.map((x) => x.km_start ?? 0)
  const ends = sessions.map((x) => x.km_end ?? 0)
  return Math.max(...ends) - Math.min(...starts)
}
