import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { carparkDispoApi } from '@/api/carparkDispo'
import { DISPO_STAGES, type DispoRow, type DispoFilters, type VehicleStatus } from '@/types/carpark'
import { agingClass } from './dispoAging'

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
// into their column without an O(rows × stages) scan.
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
  onClick,
}: {
  row: DispoRow
  canViewFinance: boolean
  onClick: () => void
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      className="cursor-pointer space-y-1.5 rounded-md border bg-card p-2.5 shadow-sm transition-all hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="truncate text-sm leading-tight">
        <span className="text-muted-foreground">{row.brand}</span>{' '}
        <span className="font-semibold">{row.model}</span>
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
  onCardClick,
}: {
  stage: (typeof STAGE_COLUMNS)[number]
  cards: DispoRow[]
  totalCount: number
  isLoading: boolean
  canViewFinance: boolean
  onCardClick: (row: DispoRow) => void
}) {
  const hiddenCount = Math.max(0, totalCount - cards.length)

  return (
    <div className="flex w-[260px] shrink-0 flex-col rounded-lg border bg-muted/30">
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
          <div className="py-6 text-center text-xs text-muted-foreground">—</div>
        ) : (
          <div className="space-y-2">
            {cards.map((row) => (
              <KanbanCard key={row.id} row={row} canViewFinance={canViewFinance} onClick={() => onCardClick(row)} />
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

interface KanbanBoardProps {
  /** Same shape as the table's activeFilters, minus `stage` (caller strips it). */
  filters: DispoFilters
  sortBy: string
  sortDir: 'asc' | 'desc'
  canViewFinance: boolean
  onCardClick: (row: DispoRow) => void
}

/**
 * Read-only Kanban view of the Dispo pipeline — one column per real stage
 * (DISPO_STAGES minus the '' TOATE pseudo-stage), cards grouped by mapping
 * each row's status through the same stage.statuses lists the pipeline tabs
 * use. Fetches a single large page (no server-side stage filter) so every
 * column can render from one request; status changes stay gated behind the
 * table/Detail page's guarded actions — clicking a card just navigates.
 */
export function KanbanBoard({ filters, sortBy, sortDir, canViewFinance, onCardClick }: KanbanBoardProps) {
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
            onCardClick={onCardClick}
          />
        )
      })}
    </div>
  )
}
