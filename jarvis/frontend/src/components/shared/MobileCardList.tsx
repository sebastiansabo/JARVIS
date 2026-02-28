import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export interface MobileCardField<T> {
  key: string
  label: string
  render: (row: T) => React.ReactNode
  /** Display as card title line */
  isPrimary?: boolean
  /** Display as subtitle line (below title) */
  isSecondary?: boolean
  /** Only show when card is expanded */
  expandOnly?: boolean
  /** Right-align on the primary row (e.g. amounts) */
  alignRight?: boolean
}

interface MobileCardListProps<T> {
  data: T[]
  fields: MobileCardField<T>[]
  getRowId: (row: T) => number
  onRowClick?: (row: T) => void
  selectable?: boolean
  selectedIds?: Set<number> | number[]
  onToggleSelect?: (id: number) => void
  actions?: (row: T) => React.ReactNode
  emptyMessage?: string
  isLoading?: boolean
}

export function MobileCardList<T>({
  data,
  fields,
  getRowId,
  onRowClick,
  selectable,
  selectedIds,
  onToggleSelect,
  actions,
  emptyMessage = 'No data found.',
  isLoading,
}: MobileCardListProps<T>) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const selectedSet = selectedIds instanceof Set
    ? selectedIds
    : new Set(selectedIds ?? [])

  const primaryFields = fields.filter((f) => f.isPrimary)
  const primaryRight = primaryFields.filter((f) => f.alignRight)
  const primaryLeft = primaryFields.filter((f) => !f.alignRight)
  const secondaryFields = fields.filter((f) => f.isSecondary)
  const bodyFields = fields.filter((f) => !f.isPrimary && !f.isSecondary && !f.expandOnly)
  const expandFields = fields.filter((f) => f.expandOnly)
  const hasExpandable = expandFields.length > 0

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="rounded-xl border bg-card px-3.5 py-3 space-y-2">
            <div className="flex items-center justify-between">
              <Skeleton className="h-[18px] w-2/5" />
              <Skeleton className="h-[18px] w-20" />
            </div>
            <div className="flex items-center justify-between">
              <Skeleton className="h-3.5 w-3/5" />
              <Skeleton className="h-3.5 w-14" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    )
  }

  // Indent for secondary/body/expand rows when checkbox is present
  const indent = selectable ? 'ml-[30px]' : ''

  return (
    <div className="space-y-1.5">
      {data.map((row) => {
        const id = getRowId(row)
        const isExpanded = expandedIds.has(id)
        const isSelected = selectedSet.has(id)

        return (
          <div
            key={id}
            className={cn(
              'rounded-xl border bg-card px-3.5 py-3 transition-colors',
              isSelected && 'border-primary/50 bg-primary/5',
              onRowClick && 'cursor-pointer active:bg-accent/50',
            )}
            onClick={() => {
              if (onRowClick) onRowClick(row)
              else if (hasExpandable) toggleExpand(id)
            }}
          >
            {/* Row 1: Checkbox + Primary left + Primary right */}
            <div className="flex items-center gap-2.5">
              {selectable && (
                <div className="-m-2 p-2" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={isSelected}
                    onCheckedChange={() => onToggleSelect?.(id)}
                  />
                </div>
              )}
              <div className="min-w-0 flex-1">
                {primaryLeft.map((f) => (
                  <span key={f.key} className="truncate text-[15px] font-semibold leading-tight block">
                    {f.render(row)}
                  </span>
                ))}
              </div>
              {primaryRight.map((f) => (
                <span key={f.key} className="shrink-0 text-[15px] font-semibold tabular-nums">
                  {f.render(row)}
                </span>
              ))}
              {/* Expand chevron */}
              {hasExpandable && !onRowClick && (
                <button
                  onClick={(e) => { e.stopPropagation(); toggleExpand(id) }}
                  className="shrink-0 -m-1 p-1 text-muted-foreground"
                  aria-label={isExpanded ? 'Collapse' : 'Expand'}
                >
                  {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
              )}
            </div>

            {/* Row 2: Secondary line */}
            {secondaryFields.length > 0 && (
              <div className={cn('mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground', indent)}>
                {secondaryFields.map((f) => (
                  <span key={f.key}>{f.render(row)}</span>
                ))}
              </div>
            )}

            {/* Body fields — compact 2-col grid */}
            {bodyFields.length > 0 && (
              <div className={cn('mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1', indent)}>
                {bodyFields.map((f) => (
                  <div key={f.key} className="min-w-0">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {f.label}
                    </span>
                    <div className="truncate text-xs">{f.render(row)}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Expanded fields */}
            {isExpanded && expandFields.length > 0 && (
              <div className={cn('mt-1.5 border-t pt-1.5', indent)}>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                  {expandFields.map((f) => (
                    <div key={f.key} className="min-w-0">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        {f.label}
                      </span>
                      <div className="truncate text-xs">{f.render(row)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Actions row */}
            {actions && (
              <div className={cn('mt-1.5 flex items-center justify-end gap-1 border-t pt-1.5', indent)} onClick={(e) => e.stopPropagation()}>
                {actions(row)}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
