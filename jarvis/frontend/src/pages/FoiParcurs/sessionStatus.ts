import type { FoiContract } from '@/types/foiParcurs'

// Derived 5-state session status for the Sesiuni Driving tab (+ Calendar tab).
// Combines the raw `status` column with the backend-derived `td_status`
// (complete/incomplete/driving). PLANNED is checked FIRST — a draft session
// (Plan a Driving Session) with deferred signature/GDPR/PDF. PENDING is
// checked next: td_status' ELSE branch returns 'driving' even for
// un-allocated PENDING batch slots that were never driven.
export type SessionStatusKey = 'planificat' | 'nealocat' | 'driving' | 'intarziat' | 'finalizat'

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
  if (c.td_status === 'complete' || c.status === 'COMPLETED') {
    return { key: 'finalizat', label: 'Finalizat', badgeClass: 'bg-green-600 text-white', rowClass: 'bg-green-500/5 border-l-4 border-l-green-500/40' }
  }
  if (c.td_status === 'incomplete') {
    return { key: 'intarziat', label: 'Întârziat', badgeClass: 'bg-red-600 text-white', rowClass: 'bg-red-500/10 border-l-4 border-l-red-500/60' }
  }
  return { key: 'driving', label: 'În desfășurare', badgeClass: 'bg-blue-600 text-white', rowClass: 'bg-blue-500/5 border-l-4 border-l-blue-500/40' }
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
}
