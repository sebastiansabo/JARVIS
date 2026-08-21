import type { FoiContract } from '@/types/foiParcurs'

// Derived 5-state session status for the Sesiuni Driving tab (+ Calendar tab).
// Combines the raw `status` column with the backend-derived `td_status`
// (complete/incomplete/driving). PLANNED is checked FIRST — a draft session
// (Plan a Driving Session) with deferred signature/GDPR/PDF. PENDING is
// checked next: td_status' ELSE branch returns 'driving' even for
// un-allocated PENDING batch slots that were never driven.
export type SessionStatusKey = 'planificat' | 'nealocat' | 'driving' | 'intarziat' | 'finalizat' | 'ratat'

export function sessionStatus(c: FoiContract): {
  key: SessionStatusKey
  label: string
  badgeClass: string
  rowClass: string
} {
  if (c.status === 'PLANNED') {
    return { key: 'planificat', label: 'Planificat', badgeClass: 'bg-indigo-600 text-white', rowClass: 'bg-indigo-500/5 border-l-4 border-l-indigo-500/40' }
  }
  if (c.status === 'PENDING') {
    return { key: 'nealocat', label: 'Nealocat', badgeClass: 'bg-muted text-muted-foreground', rowClass: '' }
  }
  // A planned drive whose due passed without being driven — the lifecycle marks it
  // MISSED (a no-show). Distinct from Întârziat (a handed-over drive not yet returned).
  if (c.status === 'MISSED') {
    return { key: 'ratat', label: 'Ratat', badgeClass: 'bg-red-500 text-white', rowClass: 'bg-red-500/5 border-l-4 border-l-red-500/40' }
  }
  if (c.td_status === 'complete' || c.status === 'COMPLETED') {
    return { key: 'finalizat', label: 'Finalizat', badgeClass: 'bg-green-600 text-white', rowClass: 'bg-green-500/5 border-l-4 border-l-green-500/40' }
  }
  if (c.td_status === 'incomplete') {
    return { key: 'intarziat', label: 'Întârziat', badgeClass: 'bg-red-600 text-white', rowClass: 'bg-red-500/10 border-l-4 border-l-red-500/60' }
  }
  return { key: 'driving', label: 'În desfășurare', badgeClass: 'bg-blue-600 text-white', rowClass: 'bg-blue-500/5 border-l-4 border-l-blue-500/40' }
}

// The free-text comment on an internal driving session (QuickSession). It's the
// form's "Comentariu"/"Observații" field, stored in `itinerary`. Returns the
// trimmed comment, or null for a regular test drive (where `itinerary` means the
// driving route, not a comment) or an internal session with no comment written.
export function internalComment(c: FoiContract): string | null {
  if (!c.is_internal) return null
  const t = c.itinerary?.trim()
  return t || null
}

// Stable pastel colour per car (VIN), so a car's sessions read the same across
// the week and different cars are easy to tell apart. Deterministic hash → a
// fixed palette (light + dark variants).
const CAR_PALETTE = [
  'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200',
  'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200',
  'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-200',
  'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200',
  'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-200',
  'bg-lime-100 text-lime-800 dark:bg-lime-900/40 dark:text-lime-200',
  'bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/40 dark:text-fuchsia-200',
  'bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-200',
  'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
  'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-200',
  'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-200',
]
export function carColor(vin?: string | null): string {
  if (!vin) return CAR_PALETTE[0]
  let h = 0
  for (let i = 0; i < vin.length; i++) h = (h * 31 + vin.charCodeAt(i)) >>> 0
  return CAR_PALETTE[h % CAR_PALETTE.length]
}

// Pastel block colours for the Week/Day time-grid (shared by the Hub
// DrivingCalendar and the desktop CalendarTab) — matched to the Field Sales
// calendar's soft-tint blocks rather than the saturated pill `badgeClass`, so a
// full-height block reads as a calm event card, not a loud chip.
export const SESSION_BLOCK_COLOR: Record<SessionStatusKey, string> = {
  planificat: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
  driving: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  intarziat: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  finalizat: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  nealocat: 'bg-muted text-muted-foreground',
  ratat: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}
