import { STATUS_TRANSITIONS, type VehicleStatus } from '@/types/carpark'

// RESERVED/SOLD/DELIVERED carry guarded side effects beyond a plain status
// flip (reservation record, sale fields + margin, delivery doc checks) —
// DispoRowActions' Reserve/Sell/Deliver dialogs (and Detail's Vânzare tab)
// own those. Any "safe" status dropdown (Dispo inline edit, Kanban drag,
// Detail's Change Status dialog) only offers the remaining "safe" direct
// transitions from STATUS_TRANSITIONS, changed via the plain PUT /status
// endpoint.
export const GUARDED_TARGETS = new Set<VehicleStatus>(['RESERVED', 'SOLD', 'DELIVERED'])

// Statuses whose only legal exits carry guarded server-side side effects, so
// any plain-PUT-/status dropdown must offer NOTHING and force the exit
// through the guarded dialogs instead:
//   • SOLD/DELIVERED — STATUS_TRANSITIONS['SOLD'] MINUS the guarded targets
//     still leaves {LISTED}, DELIVERED still leaves {RETURNED}, but both are
//     reversals that clear sale/delivery fields → must go through ReopenDialog.
//   • RESERVED — a plain PUT to LISTED/READY_FOR_SALE would flip the status
//     column WITHOUT closing the active carpark_reservations row (that side
//     effect lives only in DispoService.cancel_reservation), orphaning a
//     stale active reservation. Its legitimate exit is the "Anulează
//     rezervarea" action (DispoRowActions → cancelReservation), which
//     restores the pre-RESERVED status server-side.
export const REOPEN_ONLY_STATUSES = new Set<VehicleStatus>(['RESERVED', 'SOLD', 'DELIVERED'])

// Shared by the Dispo inline editor (StatusEditCell), the Kanban board, and
// the vehicle Detail page's "Change Status" dialog — the single source of
// truth for which direct status transitions are safe to expose outside the
// guarded Reserve/Sell/Deliver/Reopen dialogs.
export function safeStatusTransitions(current: VehicleStatus): VehicleStatus[] {
  if (REOPEN_ONLY_STATUSES.has(current)) return []
  // Defensive `?? []` mirrors DispoStatusBadge's `?? ''`/`?? status`: an
  // out-of-union status (bad server data) yields no options instead of a
  // white-screen crash on `.filter` of undefined.
  return (STATUS_TRANSITIONS[current] ?? []).filter((s) => !GUARDED_TARGETS.has(s))
}
