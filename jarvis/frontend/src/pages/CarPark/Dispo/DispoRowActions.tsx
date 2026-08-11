import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MoreHorizontal, BookmarkCheck, DollarSign, PackageCheck, RotateCcw, ExternalLink, XCircle, Paperclip, ArrowRightLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { useAuthStore } from '@/stores/authStore'
import type { DispoRow, VehicleStatus } from '@/types/carpark'
import { ReserveDialog } from './ReserveDialog'
import { SellDialog } from './SellDialog'
import { DeliverDialog } from './DeliverDialog'
import { ReopenDialog } from './ReopenDialog'
import { CancelReservationDialog } from './CancelReservationDialog'
import { AttachDocumentDialog } from './AttachDocumentDialog'
import { TransferDialog } from './TransferDialog'

// A vehicle already RESERVED/SOLD/DELIVERED or in the "iesit" (exited) stage
// (DISPO_STAGES's iesit statuses) can't be reserved again — mirrors
// DispoService.reserve's implicit precondition (it doesn't hard-block on
// status, but re-reserving a sold/delivered/exited car makes no business
// sense) and keeps the menu from offering a dead-end action.
const RESERVE_HIDDEN_STATUSES = new Set<VehicleStatus>([
  'RESERVED', 'SOLD', 'DELIVERED', 'RETURNED', 'SCRAPPED', 'TRANSFERRED', 'INSURANCE_CLAIM',
])

// Statuses DispoService.sell() is meaningfully reachable from — matches the
// 'promovat' + 'in_stoc' + 'rezervat' Dispo stages (DISPO_STAGES).
const SELLABLE_STATUSES = new Set<VehicleStatus>([
  'READY_FOR_SALE', 'LISTED', 'PRICE_REDUCED', 'AUCTION_CANDIDATE', 'RESERVED',
])

// A transfer MOVES the vehicle to another company's pipeline, so it only
// makes sense for a car still "active" here — excludes the terminal/exited
// statuses DispoService.transfer would still technically accept but where
// offering the action would be misleading (already sold/delivered/scrapped/
// returned/insurance-claimed, or already the result of a prior transfer).
const TRANSFER_HIDDEN_STATUSES = new Set<VehicleStatus>([
  'SOLD', 'DELIVERED', 'TRANSFERRED', 'SCRAPPED', 'RETURNED', 'INSURANCE_CLAIM',
])

type DialogKind = 'reserve' | 'sell' | 'deliver' | 'reopen' | 'cancel-reservation' | 'attach-document' | 'transfer' | null

export function DispoRowActions({ row }: { row: DispoRow }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const canEdit = !!user?.can_edit_carpark
  const canDelete = !!user?.can_delete_carpark
  const [dialog, setDialog] = useState<DialogKind>(null)

  const canReserve = canEdit && !RESERVE_HIDDEN_STATUSES.has(row.status)
  const canSell = canEdit && SELLABLE_STATUSES.has(row.status)
  const canDeliver = canEdit && row.status === 'SOLD'
  const canReopen = canDelete && (row.status === 'SOLD' || row.status === 'DELIVERED')
  // The only frontend path to close an active reservation — the inline status
  // dropdown deliberately refuses to move a RESERVED car (StatusEditCell), so
  // this guarded action is its legitimate exit (calls cancel_reservation,
  // which restores the pre-RESERVED status server-side).
  const canCancelReservation = canEdit && row.status === 'RESERVED'
  const canTransfer = canEdit && !TRANSFER_HIDDEN_STATUSES.has(row.status)

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Acțiuni">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {canReserve && (
            <DropdownMenuItem onClick={() => setDialog('reserve')}>
              <BookmarkCheck className="mr-2 h-4 w-4" /> Rezervă
            </DropdownMenuItem>
          )}
          {canSell && (
            <DropdownMenuItem onClick={() => setDialog('sell')}>
              <DollarSign className="mr-2 h-4 w-4" /> Vinde
            </DropdownMenuItem>
          )}
          {canDeliver && (
            <DropdownMenuItem onClick={() => setDialog('deliver')}>
              <PackageCheck className="mr-2 h-4 w-4" /> Livrează
            </DropdownMenuItem>
          )}
          {canCancelReservation && (
            <DropdownMenuItem onClick={() => setDialog('cancel-reservation')}>
              <XCircle className="mr-2 h-4 w-4" /> Anulează rezervarea
            </DropdownMenuItem>
          )}
          {canReopen && (
            <DropdownMenuItem onClick={() => setDialog('reopen')}>
              <RotateCcw className="mr-2 h-4 w-4" /> Redeschide
            </DropdownMenuItem>
          )}
          {canEdit && (
            <DropdownMenuItem onClick={() => setDialog('attach-document')}>
              <Paperclip className="mr-2 h-4 w-4" /> Atașează document
            </DropdownMenuItem>
          )}
          {canTransfer && (
            <DropdownMenuItem onClick={() => setDialog('transfer')}>
              <ArrowRightLeft className="mr-2 h-4 w-4" /> Transferă
            </DropdownMenuItem>
          )}
          {(canReserve || canSell || canDeliver || canCancelReservation || canReopen || canEdit || canTransfer) && <DropdownMenuSeparator />}
          <DropdownMenuItem onClick={() => navigate(`/app/carpark/${row.id}`)}>
            <ExternalLink className="mr-2 h-4 w-4" /> Deschide detalii
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {dialog === 'reserve' && <ReserveDialog row={row} onClose={() => setDialog(null)} />}
      {dialog === 'sell' && <SellDialog row={row} onClose={() => setDialog(null)} />}
      {dialog === 'deliver' && <DeliverDialog row={row} onClose={() => setDialog(null)} />}
      {dialog === 'reopen' && <ReopenDialog row={row} onClose={() => setDialog(null)} />}
      {dialog === 'cancel-reservation' && <CancelReservationDialog row={row} onClose={() => setDialog(null)} />}
      {dialog === 'attach-document' && (
        <AttachDocumentDialog
          vehicleId={row.id}
          open
          onOpenChange={(open) => { if (!open) setDialog(null) }}
        />
      )}
      {dialog === 'transfer' && <TransferDialog row={row} onClose={() => setDialog(null)} />}
    </div>
  )
}
