import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
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
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i} className="gap-0 py-0">
            <CardContent className="space-y-2 px-3 py-2.5">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
              </div>
            </CardContent>
          </Card>
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

  return (
    <div className="space-y-2">
      {data.map((row) => {
        const id = getRowId(row)
        const isExpanded = expandedIds.has(id)
        const isSelected = selectedSet.has(id)

        return (
          <Card
            key={id}
            className={cn(
              'gap-0 py-0 transition-colors',
              isSelected && 'border-primary/50 bg-primary/5',
              onRowClick && 'cursor-pointer active:bg-accent/50',
            )}
            onClick={() => {
              if (onRowClick) onRowClick(row)
              else if (hasExpandable) toggleExpand(id)
            }}
          >
            <CardContent className="px-3 py-2.5">
              {/* Header: primary + checkbox */}
              <div className="flex items-start gap-2">
                {selectable && (
                  <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => onToggleSelect?.(id)}
                      className="touch-target flex items-center justify-center"
                    />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  {/* Primary line */}
                  {primaryFields.length > 0 && (
                    <div className="flex items-center gap-2">
                      {primaryFields.map((f) => (
                        <span key={f.key} className="truncate text-sm font-medium">
                          {f.render(row)}
                        </span>
                      ))}
                    </div>
                  )}
                  {/* Secondary line */}
                  {secondaryFields.length > 0 && (
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                      {secondaryFields.map((f) => (
                        <span key={f.key}>{f.render(row)}</span>
                      ))}
                    </div>
                  )}
                </div>
                {/* Expand toggle */}
                {hasExpandable && !onRowClick && (
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleExpand(id) }}
                    className="shrink-0 p-1 text-muted-foreground"
                    aria-label={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                )}
              </div>

              {/* Body fields — 2-column grid */}
              {bodyFields.length > 0 && (
                <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5">
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
                <div className="mt-1.5 border-t pt-1.5">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
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
                <div className="mt-1.5 flex items-center justify-end gap-1 border-t pt-1.5" onClick={(e) => e.stopPropagation()}>
                  {actions(row)}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
