// Human labels (RO) for a session-history action code. The backend writes one
// audit row per mutation (create/activate/return/…); the "Istoric" modal renders
// these. Unknown/future codes fall back to the raw code so nothing renders blank.
export const SESSION_ACTION_LABELS: Record<string, string> = {
  create: 'Creat',
  allocate: 'Client alocat',
  edit_plan: 'Draft editat',
  reschedule: 'Replanificat',
  activate: 'Activat',
  return: 'Retur înregistrat',
  correct: 'Corectat',
  extend: 'Retur prelungit',
  reset: 'Resetat',
  archive: 'Arhivat (ratat)',
}

// Raw status column → localized label (for status-change history rows).
const STATUS_LABELS: Record<string, string> = {
  PLANNED: 'Planificat',
  PENDING: 'Nealocat',
  FILLED: 'În desfășurare',
  COMPLETED: 'Finalizat',
  MISSED: 'Ratat',
}

export function sessionActionLabel(action: string): string {
  // Status transitions are logged as "status:OLD:NEW" — render them as
  // "Status: <old> → <new>" with localized status labels.
  if (action.startsWith('status:')) {
    const [, oldS = '', newS = ''] = action.split(':')
    const lbl = (s: string) => STATUS_LABELS[s] ?? s ?? '—'
    return `Status: ${lbl(oldS)} → ${lbl(newS)}`
  }
  return SESSION_ACTION_LABELS[action] ?? action
}
