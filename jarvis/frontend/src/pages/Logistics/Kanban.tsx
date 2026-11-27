import { useMemo, useState, type DragEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { GripVertical, MoreVertical } from 'lucide-react'

import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { logisticsApi, type KanbanBoardStatus, type KanbanCard } from '@/api/logistics'
import {
  EMPTY_KANBAN_FILTERS,
  groupBoardIntoColumns,
  moveTargets,
  formatLocationBay,
  formatDueTime,
  toGetBoardFilters,
  filterBoardByLocation,
  distinctAssignees,
  distinctLocationNames,
  isBlockFormValid,
  buildMoveContext,
  type KanbanFiltersState,
} from './Kanban.helpers'
import { extractErrorMessage } from './Parc.helpers'

/** The card + target status currently pending the "Blocat" dialog's
 * Responsabil/Următoarea acțiune input -- null when the dialog is closed. */
interface PendingBlock {
  card: KanbanCard
}

function BlockTaskDialog({
  pending,
  responsible,
  nextAction,
  isPending,
  onResponsibleChange,
  onNextActionChange,
  onCancel,
  onConfirm,
}: {
  pending: PendingBlock | null
  responsible: string
  nextAction: string
  isPending: boolean
  onResponsibleChange: (value: string) => void
  onNextActionChange: (value: string) => void
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog open={pending !== null} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Blochează task-ul</DialogTitle>
        </DialogHeader>

        {pending && (
          <p className="-mt-2 text-xs text-muted-foreground">
            {pending.card.vehicle_model ?? pending.card.order_ref} · {pending.card.title}
          </p>
        )}

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="block-responsible">Responsabil</Label>
            <Input
              id="block-responsible"
              value={responsible}
              onChange={(e) => onResponsibleChange(e.target.value)}
              placeholder="Cine se ocupă de deblocare"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="block-next-action">Următoarea acțiune</Label>
            <Textarea
              id="block-next-action"
              value={nextAction}
              onChange={(e) => onNextActionChange(e.target.value)}
              placeholder="Ce trebuie făcut pentru a debloca task-ul"
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={isPending}>
            Anulează
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={!isBlockFormValid(responsible, nextAction) || isPending}
          >
            Blochează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TypeBadge({ type }: { type: string }) {
  return <Badge variant="outline" className="shrink-0 text-[10px]">{type}</Badge>
}

function KanbanTaskCard({
  card,
  currentStatus,
  isDragging,
  onDragStart,
  onDragEnd,
  onMove,
}: {
  card: KanbanCard
  currentStatus: KanbanBoardStatus
  isDragging: boolean
  onDragStart: (e: DragEvent<HTMLDivElement>) => void
  onDragEnd: () => void
  onMove: (card: KanbanCard, toStatus: KanbanBoardStatus) => void
}) {
  const targets = moveTargets(currentStatus)

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={cn(
        'space-y-1.5 rounded-md border bg-card p-2.5 shadow-sm transition-all hover:border-primary/40 hover:shadow-md',
        'cursor-grab active:cursor-grabbing',
        isDragging && 'opacity-40',
      )}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="flex min-w-0 items-center gap-1 text-muted-foreground">
          <GripVertical className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate text-sm font-medium text-foreground">{card.title}</span>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="-mr-1 -mt-1 shrink-0 text-muted-foreground hover:text-foreground"
              title="Mută"
              aria-label="Mută task-ul"
            >
              <MoreVertical className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel>Mută în</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {targets.map((target) => (
              <DropdownMenuItem key={target} onSelect={() => onMove(card, target)}>
                {target}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="truncate text-xs text-muted-foreground">
        {card.vehicle_model || '—'} <span className="text-muted-foreground/60">·</span> {card.order_ref}
      </div>

      <div className="truncate text-xs text-muted-foreground">
        {formatLocationBay(card.location_name, card.position_code)}
      </div>

      <div className="flex items-center justify-between gap-2 border-t pt-1.5">
        <TypeBadge type={card.type} />
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="truncate">{card.assignee || '—'}</span>
          <span className="tabular-nums">{formatDueTime(card.due_at)}</span>
        </div>
      </div>
    </div>
  )
}

function ColumnSkeleton() {
  return (
    <div className="space-y-2 p-2">
      {[0, 1, 2].map((i) => <Skeleton key={i} className="h-[108px] w-full rounded-md" />)}
    </div>
  )
}

function KanbanColumn({
  status,
  cards,
  count,
  isLoading,
  draggedCardId,
  isDragOver,
  onCardDragStart,
  onCardDragEnd,
  onDragOver,
  onDragLeave,
  onDrop,
  onMove,
}: {
  status: KanbanBoardStatus
  cards: KanbanCard[]
  count: number
  isLoading: boolean
  draggedCardId: number | null
  isDragOver: boolean
  onCardDragStart: (e: DragEvent<HTMLDivElement>, card: KanbanCard) => void
  onCardDragEnd: () => void
  onDragOver: (e: DragEvent<HTMLDivElement>) => void
  onDragLeave: (e: DragEvent<HTMLDivElement>) => void
  onDrop: (e: DragEvent<HTMLDivElement>) => void
  onMove: (card: KanbanCard, toStatus: KanbanBoardStatus) => void
}) {
  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        'flex w-[280px] shrink-0 flex-col rounded-lg border bg-muted/30 transition-colors',
        isDragOver && 'border-primary/60 bg-primary/5 ring-2 ring-primary/20',
      )}
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-sm font-semibold">{status}</span>
        <Badge variant="secondary" className="h-5 px-1.5 text-xs tabular-nums">{count}</Badge>
      </div>
      <div className="max-h-[calc(100vh-22rem)] min-h-[6rem] flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <ColumnSkeleton />
        ) : cards.length === 0 ? (
          <div className={cn('py-6 text-center text-xs text-muted-foreground', isDragOver && 'text-primary')}>
            {isDragOver ? 'Eliberează aici' : '—'}
          </div>
        ) : (
          <div className="space-y-2">
            {cards.map((card) => (
              <KanbanTaskCard
                key={card.id}
                card={card}
                currentStatus={status}
                isDragging={draggedCardId === card.id}
                onDragStart={(e) => onCardDragStart(e, card)}
                onDragEnd={onCardDragEnd}
                onMove={onMove}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Kanban() {
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<KanbanFiltersState>(EMPTY_KANBAN_FILTERS)
  const apiFilters = useMemo(() => toGetBoardFilters(filters), [filters])

  const { data, isFetching, error } = useQuery({
    queryKey: ['logistics', 'board', apiFilters],
    queryFn: () => logisticsApi.getBoard(apiFilters),
  })

  // Separate, unfiltered (company-wide) fetch purely to populate the
  // Locație/Responsabil dropdown options -- same reason Parc.tsx keeps a
  // second unfiltered fetch for its Locație dropdown (Task 6): deriving
  // options from the already-filtered board would make a selected
  // assignee/location narrow its OWN dropdown down to just itself.
  const { data: allData } = useQuery({
    queryKey: ['logistics', 'board', 'all-for-filter-options'],
    queryFn: () => logisticsApi.getBoard({}),
  })

  const rawBoard = data?.board
  // Locație is a client-side-only filter (see Kanban.helpers.ts's
  // filterBoardByLocation docstring for why -- no location_id on a card).
  const visibleBoard = useMemo(() => filterBoardByLocation(rawBoard, filters.location), [rawBoard, filters.location])
  const columns = useMemo(() => groupBoardIntoColumns(visibleBoard), [visibleBoard])

  const assigneeOptions = useMemo(() => distinctAssignees(allData?.board), [allData])
  const locationOptions = useMemo(() => distinctLocationNames(allData?.board), [allData])

  function updateFilters(patch: Partial<KanbanFiltersState>) {
    setFilters((prev) => ({ ...prev, ...patch }))
  }

  function handleReset() {
    setFilters(EMPTY_KANBAN_FILTERS)
  }

  // ── Move engine (Task 8) ────────────────────────────────────────────────
  // The single write path every "Mută" affordance (dropdown + drag) calls
  // into. Moving to 'Blocat' needs a Responsabil + Următoarea acțiune first
  // (the backend gate in jarvis/logistics/services/moves.py rejects a bare
  // move), so that transition opens a small dialog instead of mutating
  // immediately; every other transition mutates straight away.
  const [pendingBlock, setPendingBlock] = useState<PendingBlock | null>(null)
  const [blockResponsible, setBlockResponsible] = useState('')
  const [blockNextAction, setBlockNextAction] = useState('')

  const moveMutation = useMutation({
    mutationFn: ({ card, toStatus, ctx }: {
      card: KanbanCard
      toStatus: KanbanBoardStatus
      ctx: ReturnType<typeof buildMoveContext>
    }) => logisticsApi.moveTask(card.id, toStatus, ctx),
    onSuccess: () => {
      // Refetch instead of a local patch -- a move can change which column
      // (and, via Task 9/10's later gates, which vehicle fields) a card
      // belongs to, so the board query is the single source of truth.
      queryClient.invalidateQueries({ queryKey: ['logistics', 'board'] })
      setPendingBlock(null)
      setBlockResponsible('')
      setBlockNextAction('')
    },
    onError: (err) => {
      toast.error(extractErrorMessage(err))
    },
  })

  function onMove(card: KanbanCard, toStatus: KanbanBoardStatus) {
    if (toStatus === 'Blocat') {
      setBlockResponsible('')
      setBlockNextAction('')
      setPendingBlock({ card })
      return
    }
    moveMutation.mutate({ card, toStatus, ctx: buildMoveContext(toStatus, { responsible: '', nextAction: '' }) })
  }

  function handleBlockCancel() {
    setPendingBlock(null)
  }

  function handleBlockConfirm() {
    if (!pendingBlock || !isBlockFormValid(blockResponsible, blockNextAction)) return
    moveMutation.mutate({
      card: pendingBlock.card,
      toStatus: 'Blocat',
      ctx: buildMoveContext('Blocat', { responsible: blockResponsible, nextAction: blockNextAction }),
    })
  }

  // Drag state -- the card currently being dragged (read by handleDrop) and
  // which column it's hovering over (highlight only). Mirrors
  // CarPark/Dispo/KanbanBoard.tsx's established pattern.
  const [draggedCard, setDraggedCard] = useState<KanbanCard | null>(null)
  const [dragOverStatus, setDragOverStatus] = useState<KanbanBoardStatus | null>(null)

  function handleCardDragStart(e: DragEvent<HTMLDivElement>, card: KanbanCard) {
    setDraggedCard(card)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(card.id))
  }

  function handleCardDragEnd() {
    setDraggedCard(null)
    setDragOverStatus(null)
  }

  function handleColumnDragOver(e: DragEvent<HTMLDivElement>, status: KanbanBoardStatus) {
    if (!draggedCard) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverStatus(status)
  }

  function handleColumnDragLeave(e: DragEvent<HTMLDivElement>, status: KanbanBoardStatus) {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
    setDragOverStatus((cur) => (cur === status ? null : cur))
  }

  function handleDrop(e: DragEvent<HTMLDivElement>, targetStatus: KanbanBoardStatus) {
    e.preventDefault()
    setDragOverStatus(null)
    const card = draggedCard
    setDraggedCard(null)
    if (!card) return
    // Find which column this card is currently rendered under -- the
    // card itself doesn't carry a `status` field (see api/logistics.ts),
    // the column it's in IS its current status.
    const sourceStatus = columns.find((col) => col.cards.some((c) => c.id === card.id))?.key
    if (sourceStatus === targetStatus) return // dropped back on its own column -- no-op
    onMove(card, targetStatus)
  }

  const totalCount = columns.reduce((sum, col) => sum + col.count, 0)

  return (
    <div className="space-y-4">
      <PageHeader title="Kanban" description="Panou de lucru — activitățile pe fiecare mașină" />

      <div className="flex flex-wrap items-end gap-2">
        <SearchInput
          value={filters.q}
          onChange={(q) => updateFilters({ q })}
          placeholder="Vehicul sau comandă..."
          className="w-full sm:w-64"
        />

        <Select
          value={filters.location || 'all'}
          onValueChange={(v) => updateFilters({ location: v === 'all' ? '' : v })}
        >
          <SelectTrigger className="w-full sm:w-44" aria-label="Locație">
            <SelectValue placeholder="Locație" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate locațiile</SelectItem>
            {locationOptions.map((loc) => <SelectItem key={loc} value={loc}>{loc}</SelectItem>)}
          </SelectContent>
        </Select>

        <Select
          value={filters.assignee || 'all'}
          onValueChange={(v) => updateFilters({ assignee: v === 'all' ? '' : v })}
        >
          <SelectTrigger className="w-full sm:w-44" aria-label="Responsabil">
            <SelectValue placeholder="Responsabil" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toți responsabilii</SelectItem>
            {assigneeOptions.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>

        <Button variant="outline" onClick={handleReset}>Resetează</Button>
      </div>

      {error ? (
        <EmptyState title="Eroare la încărcare" description={extractErrorMessage(error)} />
      ) : !isFetching && totalCount === 0 ? (
        <EmptyState
          title="Niciun task"
          description="Niciun task nu corespunde filtrelor curente."
        />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {columns.map((column) => (
            <KanbanColumn
              key={column.key}
              status={column.key}
              cards={column.cards}
              count={column.count}
              isLoading={isFetching && !data}
              draggedCardId={draggedCard?.id ?? null}
              isDragOver={dragOverStatus === column.key}
              onCardDragStart={handleCardDragStart}
              onCardDragEnd={handleCardDragEnd}
              onDragOver={(e) => handleColumnDragOver(e, column.key)}
              onDragLeave={(e) => handleColumnDragLeave(e, column.key)}
              onDrop={(e) => handleDrop(e, column.key)}
              onMove={onMove}
            />
          ))}
        </div>
      )}

      <BlockTaskDialog
        pending={pendingBlock}
        responsible={blockResponsible}
        nextAction={blockNextAction}
        isPending={moveMutation.isPending}
        onResponsibleChange={setBlockResponsible}
        onNextActionChange={setBlockNextAction}
        onCancel={handleBlockCancel}
        onConfirm={handleBlockConfirm}
      />
    </div>
  )
}
