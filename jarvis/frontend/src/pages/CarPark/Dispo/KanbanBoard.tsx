import { useCallback, useMemo, useState, type DragEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ExternalLink } from 'lucide-react'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { carparkApi } from '@/api/carpark'
import { carparkDispoApi } from '@/api/carparkDispo'
import {
  DISPO_STAGES,
  STATUS_TRANSITIONS,
  type DispoRow,
  type DispoFilters,
  type DispoStageKey,
  type VehicleStatus,
} from '@/types/carpark'
import { agingClass } from './dispoAging'
import { safeStatusTransitions } from './StatusEditCell'
import { patchDispoRow } from './dispoInlineEdit'
import { apiErrorMessage } from './dispoApiError'
import { ReserveDialog } from './ReserveDialog'
import { SellDialog } from './SellDialog'
import { DeliverDialog } from './DeliverDialog'
import { CancelReservationDialog } from './CancelReservationDialog'

// Large enough to cover a normal Dispo pipeline in one shot (stock rarely
// exceeds a few hundred active vehicles); a column whose real stage_counts
// total exceeds what actually came back shows a "+N mai multe" footer
// instead of silently truncating.
const KANBAN_PER_PAGE = 200

// The 7 real pipeline stages, in DISPO_STAGES order, excluding the '' (TOATE)
// pseudo-stage — one column each. Static/derived from a const array, so a
// module-level constant is fine (no per-render cost).
const STAGE_COLUMNS = DISPO_STAGES.filter((s) => s.key !== '')

// Reverse lookup built once from DISPO_STAGES' statuses lists (every
// VehicleStatus appears in exactly one stage) — used to bucket fetched rows
// into their column without an O(rows × stages) scan, and to detect a
// same-column drop (no-op) during drag-and-drop.
const STATUS_TO_STAGE = new Map<VehicleStatus, string>()
for (const stage of STAGE_COLUMNS) {
  for (const status of stage.statuses) STATUS_TO_STAGE.set(status, stage.key)
}

function Muted() {
  return <span className="text-muted-foreground">—</span>
}

// Promo-price display: a car counts as "promoted" when it has a
// promotional_price strictly below its reference price (list_price, falling
// back to current_price), OR its status is PRICE_REDUCED — mirrors how the
// table/Detail page treat a price cut. All fields are nullable on the wire,
// so every branch is null-guarded; worst case falls back to plain
// current_price (or a muted dash) rather than crashing.
function CardPrice({ row }: { row: DispoRow }) {
  const promo = row.promotional_price
  const original = row.list_price ?? row.current_price
  const isPromoted =
    promo != null && ((original != null && promo < original) || row.status === 'PRICE_REDUCED')

  if (isPromoted && promo != null) {
    return (
      <div className="flex items-baseline gap-1.5">
        {original != null && (
          <span className="text-[11px] text-muted-foreground line-through">
            <CurrencyDisplay value={original} />
          </span>
        )}
        <span className="text-sm font-semibold text-red-600 dark:text-red-400">
          <CurrencyDisplay value={promo} />
        </span>
      </div>
    )
  }

  if (row.current_price != null) {
    return <span className="text-sm font-semibold"><CurrencyDisplay value={row.current_price} /></span>
  }

  return <Muted />
}

function KanbanCard({
  row,
  canViewFinance,
  canDrag,
  isDragging,
  onClick,
  onDragStart,
  onDragEnd,
}: {
  row: DispoRow
  canViewFinance: boolean
  /** Gated on canEdit — a viewer without edit rights can look but not move cards. */
  canDrag: boolean
  isDragging: boolean
  onClick: () => void
  onDragStart: (e: DragEvent<HTMLDivElement>) => void
  onDragEnd: () => void
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      draggable={canDrag}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      className={cn(
        'space-y-1.5 rounded-md border bg-card p-2.5 shadow-sm transition-all hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        canDrag ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer',
        isDragging && 'opacity-40',
      )}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0 flex-1 truncate text-sm leading-tight">
          <span className="text-muted-foreground">{row.brand}</span>{' '}
          <span className="font-semibold">{row.model}</span>
        </div>
        {/* Explicit "open Detail" affordance — cards are now drag handles, so
            a plain click on the body still navigates (native DnD suppresses
            click on an actual drag), but this button is the guaranteed path.
            stopPropagation keeps the click from also bubbling into the
            card's own onClick and double-navigating. */}
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className="-mr-1 -mt-1 shrink-0 text-muted-foreground hover:text-foreground"
          title="Detalii"
          aria-label="Deschide detalii"
          onClick={(e) => {
            e.stopPropagation()
            onClick()
          }}
          onKeyDown={(e) => {
            // The button already fires its own click on Enter/Space; without
            // stopPropagation the keydown also bubbles to the parent card's
            // onKeyDown and navigates a second time (harmless, same route).
            if (e.key === 'Enter' || e.key === ' ') e.stopPropagation()
          }}
        >
          <ExternalLink className="h-3 w-3" />
        </Button>
      </div>
      <div className="truncate font-mono text-[11px] text-muted-foreground" title={row.vin}>
        {row.vin.slice(-6)}
      </div>

      <CardPrice row={row} />

      {canViewFinance && (
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-muted-foreground">Marjă</span>
          <span
            className={cn(
              'font-medium tabular-nums',
              row.gross_margin != null && row.gross_margin < 0 && 'text-red-600 dark:text-red-400',
            )}
          >
            {row.gross_margin != null ? <CurrencyDisplay value={row.gross_margin} /> : <Muted />}
            {row.margin_pct != null && <span className="ml-1 text-muted-foreground">({row.margin_pct.toFixed(1)}%)</span>}
          </span>
        </div>
      )}

      <div className="flex items-center justify-between border-t pt-1 text-[11px]">
        <span className="text-muted-foreground">Zile în stoc</span>
        <span className={cn('font-medium tabular-nums', agingClass(row.days_in_stock, row.status))}>
          {row.days_in_stock}
        </span>
      </div>
    </div>
  )
}

function KanbanColumnSkeleton() {
  return (
    <div className="space-y-2 p-2">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-[104px] w-full rounded-md" />
      ))}
    </div>
  )
}

function KanbanColumn({
  stage,
  cards,
  totalCount,
  isLoading,
  canViewFinance,
  canEdit,
  draggedRowId,
  isDragOver,
  onCardClick,
  onCardDragStart,
  onCardDragEnd,
  onDragOver,
  onDragLeave,
  onDrop,
}: {
  stage: (typeof STAGE_COLUMNS)[number]
  cards: DispoRow[]
  totalCount: number
  isLoading: boolean
  canViewFinance: boolean
  canEdit: boolean
  draggedRowId: number | null
  isDragOver: boolean
  onCardClick: (row: DispoRow) => void
  onCardDragStart: (e: DragEvent<HTMLDivElement>, row: DispoRow) => void
  onCardDragEnd: () => void
  onDragOver: (e: DragEvent<HTMLDivElement>) => void
  onDragLeave: (e: DragEvent<HTMLDivElement>) => void
  onDrop: (e: DragEvent<HTMLDivElement>) => void
}) {
  const hiddenCount = Math.max(0, totalCount - cards.length)

  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        'flex w-[260px] shrink-0 flex-col rounded-lg border bg-muted/30 transition-colors',
        isDragOver && 'border-primary/60 bg-primary/5 ring-2 ring-primary/20',
      )}
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-sm font-semibold">{stage.label}</span>
        <Badge variant="secondary" className="h-5 px-1.5 text-xs tabular-nums">
          {totalCount}
        </Badge>
      </div>
      <div className="max-h-[calc(100vh-24rem)] min-h-[6rem] flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <KanbanColumnSkeleton />
        ) : cards.length === 0 ? (
          <div className={cn('py-6 text-center text-xs text-muted-foreground', isDragOver && 'text-primary')}>
            {isDragOver ? 'Eliberează aici' : '—'}
          </div>
        ) : (
          <div className="space-y-2">
            {cards.map((row) => (
              <KanbanCard
                key={row.id}
                row={row}
                canViewFinance={canViewFinance}
                canDrag={canEdit}
                isDragging={draggedRowId === row.id}
                onClick={() => onCardClick(row)}
                onDragStart={(e) => onCardDragStart(e, row)}
                onDragEnd={onCardDragEnd}
              />
            ))}
            {hiddenCount > 0 && (
              <div className="pt-1 text-center text-[11px] text-muted-foreground">+{hiddenCount} mai multe</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// A card being dragged out of a dialog-guarded stage opens the matching
// guarded dialog instead of moving directly — same dialogs DispoRowActions'
// row menu uses, so the reservation/sale/delivery side effects (and their
// server-side guards) stay centralized in one place.
type PendingDialog =
  | { type: 'reserve'; row: DispoRow }
  | { type: 'sell'; row: DispoRow }
  | { type: 'deliver'; row: DispoRow }
  | { type: 'cancel-reservation'; row: DispoRow }

interface KanbanBoardProps {
  /** Same shape as the table's activeFilters, minus `stage` (caller strips it). */
  filters: DispoFilters
  sortBy: string
  sortDir: 'asc' | 'desc'
  canViewFinance: boolean
  /** Gates drag-and-drop the same way it gates the table's inline editing / row actions. */
  canEdit: boolean
  onCardClick: (row: DispoRow) => void
}

/**
 * Kanban view of the Dispo pipeline — one column per real stage (DISPO_STAGES
 * minus the '' TOATE pseudo-stage), cards grouped by mapping each row's
 * status through the same stage.statuses lists the pipeline tabs use.
 * Fetches a single large page (no server-side stage filter) so every column
 * can render from one request.
 *
 * Cards support native HTML5 drag-and-drop (desktop only — no touch/mobile
 * fallback) to move a vehicle between stages. Status changes are guarded
 * server-side (RESERVED/SOLD/DELIVERED, and leaving RESERVED, carry side
 * effects), so a drop never fires a raw status change into those states —
 * it either routes through the same guarded dialogs DispoRowActions' row
 * menu uses (reserve/sell/deliver/cancel-reservation), or, for the
 * remaining "safe" transitions, calls carparkApi.changeStatus with an
 * optimistic move that reverts on failure. See handleDrop for the full
 * per-target-stage routing.
 */
export function KanbanBoard({ filters, sortBy, sortDir, canViewFinance, canEdit, onCardClick }: KanbanBoardProps) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['carpark', 'dispo', 'summary', 'kanban', filters, sortBy, sortDir],
    queryFn: () => carparkDispoApi.getSummary(filters, 1, KANBAN_PER_PAGE, sortBy, sortDir),
  })

  const grouped = useMemo(() => {
    const map = new Map<string, DispoRow[]>()
    for (const stage of STAGE_COLUMNS) map.set(stage.key, [])
    for (const row of data?.rows ?? []) {
      const stageKey = STATUS_TO_STAGE.get(row.status)
      if (stageKey) map.get(stageKey)?.push(row)
    }
    return map
  }, [data])

  const stageCounts = data?.stage_counts

  // Drag state: the row currently being dragged (source of truth — read by
  // handleDrop) and which column it's currently hovering over (highlight
  // only). Both live in component state rather than dataTransfer alone
  // because dataTransfer's payload isn't readable during dragover/drop in
  // most browsers (only on the actual drop) and we need the full row object,
  // not just its id, to open a dialog or run an optimistic patch.
  const [draggedRow, setDraggedRow] = useState<DispoRow | null>(null)
  const [dragOverStage, setDragOverStage] = useState<DispoStageKey | null>(null)
  const [pendingDialog, setPendingDialog] = useState<PendingDialog | null>(null)

  const invalidateDispo = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
  }, [queryClient])

  const handleCardDragStart = useCallback((e: DragEvent<HTMLDivElement>, row: DispoRow) => {
    setDraggedRow(row)
    e.dataTransfer.effectAllowed = 'move'
    // Firefox refuses to start a drag unless dataTransfer carries data; the
    // id is otherwise unused since `draggedRow` state is the read path.
    e.dataTransfer.setData('text/plain', String(row.id))
  }, [])

  const handleCardDragEnd = useCallback(() => {
    // Fires on drag cancel (dropped outside any valid target) too, so this
    // is the cleanup path even when onDrop never runs.
    setDraggedRow(null)
    setDragOverStage(null)
  }, [])

  const handleColumnDragOver = useCallback(
    (e: DragEvent<HTMLDivElement>, stageKey: DispoStageKey) => {
      // Ignore drags that didn't originate from a card (e.g. an OS-level
      // file/text drag) — without this guard preventDefault() below would
      // make every column a drop target for arbitrary browser drags.
      if (!draggedRow) return
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
      setDragOverStage(stageKey)
    },
    [draggedRow],
  )

  const handleColumnDragLeave = useCallback((e: DragEvent<HTMLDivElement>, stageKey: DispoStageKey) => {
    // dragleave bubbles from every child (each card) as the pointer moves
    // over them, which would otherwise flicker the column highlight on
    // every card boundary crossed — only clear when truly leaving the
    // column (relatedTarget outside currentTarget).
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
    setDragOverStage((cur) => (cur === stageKey ? null : cur))
  }, [])

  // Safe-stage move: transitions that don't carry guarded side effects
  // (mirrors StatusEditCell's inline dropdown). Optimistically patches the
  // cached row so the card jumps columns immediately; reverts + toasts the
  // server's message on failure.
  const runSafeMove = useCallback(
    async (row: DispoRow, targetStatus: VehicleStatus) => {
      patchDispoRow(queryClient, row.id, { status: targetStatus })
      try {
        await carparkApi.changeStatus(row.id, targetStatus)
        invalidateDispo()
      } catch (err) {
        patchDispoRow(queryClient, row.id, { status: row.status })
        toast.error(apiErrorMessage(err, 'Tranziție invalidă'))
      }
    },
    [queryClient, invalidateDispo],
  )

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>, targetStageKey: DispoStageKey) => {
      e.preventDefault()
      setDragOverStage(null)
      const row = draggedRow
      setDraggedRow(null)
      if (!row) return

      const sourceStage = STATUS_TO_STAGE.get(row.status)
      if (sourceStage === targetStageKey) return // dropped back on its own column — no-op

      const current = row.status

      // Target-stage guarded checks run FIRST, before the RESERVED-source
      // cancel branch below — so a RESERVED card dropped onto Vândut routes
      // to SellDialog (RESERVED → SOLD is a valid, common conversion), and
      // onto Livrat toasts (RESERVED is not SOLD), rather than both being
      // swallowed by "leaving RESERVED = cancel the reservation."
      if (targetStageKey === 'rezervat') {
        if (STATUS_TRANSITIONS[current]?.includes('RESERVED')) {
          setPendingDialog({ type: 'reserve', row })
        } else {
          toast.error('Nu se poate rezerva din starea curentă')
        }
        return
      }

      if (targetStageKey === 'vandut') {
        if (STATUS_TRANSITIONS[current]?.includes('SOLD')) {
          setPendingDialog({ type: 'sell', row })
        } else {
          toast.error('Nu se poate marca VÂNDUT din starea curentă')
        }
        return
      }

      if (targetStageKey === 'livrat') {
        // DELIVERED is only reachable from SOLD (STATUS_TRANSITIONS['SOLD']).
        if (current === 'SOLD') {
          setPendingDialog({ type: 'deliver', row })
        } else {
          toast.error('Doar mașinile VÂNDUT pot fi livrate')
        }
        return
      }

      // RESERVED dropped onto a NON-guarded (prep/safe) stage — in_pregatire
      // / in_stoc / promovat / iesit. A RESERVED car carries an active
      // reservation record, so its only legitimate exit toward these stages
      // is cancel_reservation (closes the reservation row + restores the
      // pre-RESERVED status server-side). The card may therefore land back
      // in its prior stage rather than the drop target; that's expected.
      // (Reached only after the rezervat/vandut/livrat targets returned
      // above, so `targetStageKey` here is guaranteed one of the safe stages.)
      if (current === 'RESERVED') {
        setPendingDialog({ type: 'cancel-reservation', row })
        return
      }

      // Remaining stages (in_pregatire / in_stoc / promovat / iesit) only
      // ever need a plain status flip — resolve the first status in the
      // target stage that's also a legal "safe" transition from the
      // current status (excludes RESERVED/SOLD/DELIVERED and anything
      // reversal-only, same set StatusEditCell's inline dropdown offers).
      const targetStage = STAGE_COLUMNS.find((s) => s.key === targetStageKey)
      const safeTargets = safeStatusTransitions(current)
      const targetStatus = targetStage?.statuses.find((s) => safeTargets.includes(s))

      if (!targetStatus) {
        toast.error('Tranziție invalidă')
        return
      }

      void runSafeMove(row, targetStatus)
    },
    [draggedRow, runSafeMove],
  )

  const closeDialog = useCallback(() => setPendingDialog(null), [])
  // The dialogs already invalidate ['carpark','dispo'] themselves on
  // success; this is a redundant-but-cheap extra invalidation so the board
  // refetches even if a dialog's own invalidation key ever narrows.
  const onDialogSuccess = useCallback(() => invalidateDispo(), [invalidateDispo])

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {STAGE_COLUMNS.map((stage) => {
        const cards = grouped.get(stage.key) ?? []
        const totalCount = stageCounts ? (stageCounts[stage.key] ?? cards.length) : cards.length
        return (
          <KanbanColumn
            key={stage.key}
            stage={stage}
            cards={cards}
            totalCount={totalCount}
            isLoading={isLoading}
            canViewFinance={canViewFinance}
            canEdit={canEdit}
            draggedRowId={draggedRow?.id ?? null}
            isDragOver={dragOverStage === stage.key}
            onCardClick={onCardClick}
            onCardDragStart={handleCardDragStart}
            onCardDragEnd={handleCardDragEnd}
            onDragOver={(e) => handleColumnDragOver(e, stage.key)}
            onDragLeave={(e) => handleColumnDragLeave(e, stage.key)}
            onDrop={(e) => handleDrop(e, stage.key)}
          />
        )
      })}

      {pendingDialog?.type === 'reserve' && (
        <ReserveDialog row={pendingDialog.row} onClose={closeDialog} onSuccess={onDialogSuccess} />
      )}
      {pendingDialog?.type === 'sell' && (
        <SellDialog row={pendingDialog.row} onClose={closeDialog} onSuccess={onDialogSuccess} />
      )}
      {pendingDialog?.type === 'deliver' && (
        <DeliverDialog row={pendingDialog.row} onClose={closeDialog} onSuccess={onDialogSuccess} />
      )}
      {pendingDialog?.type === 'cancel-reservation' && (
        <CancelReservationDialog row={pendingDialog.row} onClose={closeDialog} onSuccess={onDialogSuccess} />
      )}
    </div>
  )
}
