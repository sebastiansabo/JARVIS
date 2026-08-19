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

export function sessionActionLabel(action: string): string {
  return SESSION_ACTION_LABELS[action] ?? action
}
