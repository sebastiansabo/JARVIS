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
