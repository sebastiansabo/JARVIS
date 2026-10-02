import type { FoiContract } from '@/types/foiParcurs'
import { driveDate } from './anomalies'

// Order a car's sessions by odometer and insert synthetic "gap" rows wherever
// the odometer jumps between logged sessions (km the car moved without a logged
// drive). Gap rows carry only the distance + the date the gap was spotted (the
// session that revealed it) — no client/traseu — as a legal continuity marker.
export type GapNeighbor = { id: number; client: string; kmStart: number; kmEnd: number }
export type GapRow = {
  id: string; date: string; dateFrom: string; dateTo: string
  kmStart: number; kmEnd: number; distance: number
  // The two logged sessions the gap sits between — targets for "absorb".
  before: GapNeighbor; after: GapNeighbor
}
export type DetailRow =
  | { gap: false; session: FoiContract }
  | ({ gap: true } & GapRow)

// PLANNED sessions are future bookings that haven't driven yet (odometer 0-0).
// They carry no real reading, so they must never anchor the odometer chain — the
// backend's odometer math filters `status <> 'PLANNED'` for the same reason. If
// they did, the jump from their 0 up to the first real drive would surface as a
// phantom "Gap kilometraj (nejustificat)". They still render as list rows.
export function isPlanned(c: FoiContract): boolean {
  return c.status === 'PLANNED'
}

// The sheet's real odometer span (kmMin/kmMax), excluding PLANNED bookings.
// Returns Infinity/-Infinity when the sheet has no real reading yet — callers
// guard with Number.isFinite before using the edges.
export function sheetKmSpan(sessions: FoiContract[]): { kmMin: number; kmMax: number } {
  let kmMin = Infinity
  let kmMax = -Infinity
  for (const c of sessions) {
    if (isPlanned(c)) continue
    if (c.km_start != null) kmMin = Math.min(kmMin, c.km_start)
    if (c.km_end != null) kmMax = Math.max(kmMax, c.km_end)
  }
  return { kmMin, kmMax }
}

// `kmMin`/`kmMax` are the month's full odometer span (including internal drives
// that aren't listed as trips). When a client trip doesn't reach that edge, the
// leftover KM (an internal drive at the month boundary) shows as a leading or
// trailing gap — attributed to the adjacent client so it can be redistributed.
export function withGaps(sessions: FoiContract[], kmMin?: number, kmMax?: number): DetailRow[] {
  const sorted = [...sessions].sort(
    (a, b) => (a.km_start ?? 0) - (b.km_start ?? 0) || (a.km_end ?? 0) - (b.km_end ?? 0),
  )
  const rows: DetailRow[] = []
  const neighbor = (s: FoiContract): GapNeighbor => ({
    id: s.id, client: s.client_name || s.advisor_name || '—',
    kmStart: s.km_start ?? 0, kmEnd: s.km_end ?? 0,
  })
  // Anchor the leading gap on the first REAL drive, not a PLANNED 0-0 booking.
  const first = sorted.find((s) => !isPlanned(s))
  if (first && kmMin != null && Number.isFinite(kmMin) && (first.km_start ?? 0) > kmMin) {
    const n = neighbor(first)
    rows.push({
      gap: true, id: `gap-lead-${first.id}`, date: first.created_at,
      dateFrom: driveDate(first), dateTo: driveDate(first),
      kmStart: kmMin, kmEnd: first.km_start ?? 0, distance: (first.km_start ?? 0) - kmMin,
      before: n, after: n,
    })
  }
  let prevEnd: number | null = null
  let prevSession: FoiContract | null = null
  for (const c of sorted) {
    // Render PLANNED bookings as rows, but keep them out of the odometer chain.
    if (isPlanned(c)) { rows.push({ gap: false, session: c }); continue }
    const start = c.km_start ?? 0
    if (prevEnd != null && start > prevEnd && prevSession) {
      rows.push({
        gap: true, id: `gap-${c.id}`, date: c.created_at,
        // Window follows the DRIVE dates (departure), not created_at, so a gap
        // between corrected sessions offers the real interval (e.g. a bounding
        // TD moved to 03.08 lets the client-extra date start there).
        dateFrom: driveDate(prevSession), dateTo: driveDate(c),
        kmStart: prevEnd, kmEnd: start, distance: start - prevEnd,
        before: neighbor(prevSession), after: neighbor(c),
      })
    }
    rows.push({ gap: false, session: c })
    if (prevEnd == null || (c.km_end ?? 0) > prevEnd) { prevEnd = c.km_end ?? 0; prevSession = c }
  }
  if (prevSession && prevEnd != null && kmMax != null && Number.isFinite(kmMax) && kmMax > prevEnd) {
    const n = neighbor(prevSession)
    rows.push({
      gap: true, id: `gap-trail-${prevSession.id}`, date: prevSession.created_at,
      dateFrom: driveDate(prevSession), dateTo: driveDate(prevSession),
      kmStart: prevEnd, kmEnd: kmMax, distance: kmMax - prevEnd,
      before: n, after: n,
    })
  }
  return rows
}
