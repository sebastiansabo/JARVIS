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
import { STATUS_LABELS, type DispoRow, type VehicleStatus } from '@/types/carpark'
import { DispoStatusBadge } from './DispoStatusBadge'
import { useDispoInlineSave } from './dispoInlineEdit'
import { safeStatusTransitions } from './statusTransitions'

// Re-exported for existing consumers (e.g. KanbanBoard) that import
// safeStatusTransitions from this module; the canonical definition now
// lives in ./statusTransitions so it can also be shared with Detail.tsx.
export { safeStatusTransitions }

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
