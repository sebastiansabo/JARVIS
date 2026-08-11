import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'
import { carparkApi } from '@/api/carpark'
import { STATUS_LABELS, STATUS_TRANSITIONS, type DispoRow, type VehicleStatus } from '@/types/carpark'
import { DispoStatusBadge } from './DispoStatusBadge'
import { useDispoInlineSave } from './dispoInlineEdit'

// RESERVED/SOLD/DELIVERED carry guarded side effects beyond a plain status
// flip (reservation record, sale fields + margin, delivery doc checks) —
// DispoRowActions' Reserve/Sell/Deliver dialogs own those. This dropdown
// only offers the remaining "safe" direct transitions from
// STATUS_TRANSITIONS, changed via the plain PUT /status endpoint.
const GUARDED_TARGETS = new Set<VehicleStatus>(['RESERVED', 'SOLD', 'DELIVERED'])

// Statuses whose only legal exits carry guarded server-side side effects, so
// the inline (plain PUT /status) dropdown must offer NOTHING and force the
// exit through DispoRowActions' guarded dialogs instead:
//   • SOLD/DELIVERED — STATUS_TRANSITIONS['SOLD'] MINUS the guarded targets
//     still leaves {LISTED}, DELIVERED still leaves {RETURNED}, but both are
//     reversals that clear sale/delivery fields → must go through ReopenDialog.
//   • RESERVED — a plain PUT to LISTED/READY_FOR_SALE would flip the status
//     column WITHOUT closing the active carpark_reservations row (that side
//     effect lives only in DispoService.cancel_reservation), orphaning a
//     stale active reservation. Its legitimate exit is the "Anulează
//     rezervarea" action (DispoRowActions → cancelReservation), which
//     restores the pre-RESERVED status server-side.
const REOPEN_ONLY_STATUSES = new Set<VehicleStatus>(['RESERVED', 'SOLD', 'DELIVERED'])

export function safeStatusTransitions(current: VehicleStatus): VehicleStatus[] {
  if (REOPEN_ONLY_STATUSES.has(current)) return []
  // Defensive `?? []` mirrors DispoStatusBadge's `?? ''`/`?? status`: an
  // out-of-union status (bad server data) yields no options instead of a
  // white-screen crash on `.filter` of undefined.
  return (STATUS_TRANSITIONS[current] ?? []).filter((s) => !GUARDED_TARGETS.has(s))
}

export function StatusEditCell({ row, editable }: { row: DispoRow; editable: boolean }) {
  const [open, setOpen] = useState(false)
  const save = useDispoInlineSave(row.id)
  const safeTargets = safeStatusTransitions(row.status)

  if (!editable || safeTargets.length === 0) {
    return <DispoStatusBadge status={row.status} />
  }

  async function handleSelect(target: VehicleStatus) {
    setOpen(false)
    await save({
      patch: { status: target },
      revert: { status: row.status },
      request: () => carparkApi.changeStatus(row.id, target),
      errorFallback: 'Tranziție interzisă',
    })
  }

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-0.5 rounded-sm outline-none hover:opacity-80 focus-visible:ring-1 focus-visible:ring-ring"
          >
            <DispoStatusBadge status={row.status} />
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {safeTargets.map((s) => (
            <DropdownMenuItem key={s} onClick={() => void handleSelect(s)}>
              {STATUS_LABELS[s]}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="max-w-[220px] whitespace-normal text-[11px] font-normal text-muted-foreground">
            Pentru Rezervare / Vânzare / Livrare folosește meniul ⋯
          </DropdownMenuLabel>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
