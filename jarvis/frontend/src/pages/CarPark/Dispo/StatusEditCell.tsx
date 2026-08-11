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

// Leaving SOLD or DELIVERED is itself a guarded reversal (clears sale/
// delivery fields) — STATUS_TRANSITIONS['SOLD'] MINUS the guarded targets
// still leaves {LISTED}, and DELIVERED still leaves {RETURNED}, but both
// must route through DispoRowActions' ReopenDialog, not a plain PUT. So
// unlike every other current status, these two force an empty safe set
// regardless of what the plain subtraction would yield.
const REOPEN_ONLY_STATUSES = new Set<VehicleStatus>(['SOLD', 'DELIVERED'])

export function safeStatusTransitions(current: VehicleStatus): VehicleStatus[] {
  if (REOPEN_ONLY_STATUSES.has(current)) return []
  return STATUS_TRANSITIONS[current].filter((s) => !GUARDED_TARGETS.has(s))
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
