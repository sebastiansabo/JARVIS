import React, { useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, Layers, Pencil } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import type { Allocation, Invoice } from '@/types/invoices'
import { buildAllocationDisplayGroups } from './allocationUtils'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'

interface LineItemAllocationsViewProps {
  invoice: Invoice
  onEdit?: () => void
  canEdit?: boolean
}

const formatNumber = (n: number) =>
  new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)

/**
 * Read-only counterpart of {@link LineItemAllocations}. Renders merged line
 * item groups with a collapsible "N items merged" header (matching the editor
 * UX) and each group's deduped allocations underneath.
 *
 * Groups are detected from the invoice's allocations by line_item_index +
 * fingerprint, so merged-in-editor invoices restore their parent-child
 * structure on display.
 */
export function LineItemAllocationsView({ invoice, onEdit, canEdit }: LineItemAllocationsViewProps) {
  const groups = buildAllocationDisplayGroups(invoice)
  const currency = invoice.currency

  // Track expanded groups (default: first group expanded)
  const [expanded, setExpanded] = useState<Set<number>>(() => {
    const first = groups[0]?.groupKey
    return first != null ? new Set([first]) : new Set()
  })

  const toggle = useCallback((key: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  if (groups.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-muted-foreground/80 uppercase tracking-wider font-medium">
          Line item allocations
        </div>
        {canEdit && onEdit && (
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onEdit} title="Edit allocations">
            <Pencil className="h-3 w-3" />
          </Button>
        )}
      </div>

      <div className="space-y-1">
        {groups.map((group) => {
          const isMerged = group.lineIndices.length > 1
          const isExpanded = expanded.has(group.groupKey)

          return (
            <div
              key={group.groupKey}
              className={cn(
                'rounded-lg border bg-card',
                isMerged && 'border-blue-200 dark:border-blue-800',
              )}
            >
              {/* Header */}
              <button
                type="button"
                className="flex w-full items-center gap-2 py-2 pl-3 pr-3 text-sm hover:bg-muted/50 transition-colors min-w-0"
                onClick={() => toggle(group.groupKey)}
              >
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                {isMerged ? (
                  <span className="flex-1 text-left min-w-0">
                    <span className="inline-flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5 text-blue-500" />
                      <span className="font-medium">{group.lineIndices.length} items merged</span>
                    </span>
                  </span>
                ) : (
                  <span className="flex-1 text-left truncate font-medium min-w-0">
                    {group.lineItems[0]?.description ?? `Line ${group.groupKey + 1}`}
                  </span>
                )}
                <span className="tabular-nums text-muted-foreground shrink-0 ml-auto">
                  {formatNumber(group.groupAmount)} {currency}
                </span>
              </button>

              {/* Expanded content */}
              {isExpanded && (
                <div className="border-t px-3 pb-3 pt-2 space-y-2">
                  {/* Merged items list */}
                  {isMerged && (
                    <div className="rounded-md bg-blue-50 dark:bg-blue-950/30 px-3 py-2 space-y-1">
                      <div className="text-xs font-medium text-blue-700 dark:text-blue-300">
                        Merged items:
                      </div>
                      {group.lineIndices.map((idx, i) => {
                        const li = group.lineItems[i]
                        if (!li) return null
                        return (
                          <div
                            key={idx}
                            className="flex items-center justify-between text-xs text-blue-600 dark:text-blue-400"
                          >
                            <span className="truncate pr-2">{li.description}</span>
                            <span className="tabular-nums shrink-0">
                              {formatNumber(li.amount || 0)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* Allocations table */}
                  <AllocationTable allocations={group.allocations} currency={currency} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface AllocationTableProps {
  allocations: Allocation[]
  currency: string
}

function AllocationTable({ allocations, currency }: AllocationTableProps) {
  if (allocations.length === 0) return null

  const allRows = allocations.flatMap((a) => [a, ...(a.reinvoice_destinations ?? [])])
  const hasBrand = allRows.some((r) => !!(r as Record<string, unknown>).brand)
  const hasSubdept = allRows.some((r) => !!(r as Record<string, unknown>).subdepartment)
  const hasComment = allocations.some((a) => !!a.comment)

  return (
    <table className="text-xs w-full">
      <thead>
        <tr className="text-[10px] text-muted-foreground/70 uppercase tracking-wider">
          <th className="py-1 pr-4 text-left font-medium">Company</th>
          {hasBrand && <th className="py-1 pr-4 text-left font-medium">Brand</th>}
          <th className="py-1 pr-4 text-left font-medium">Department</th>
          {hasSubdept && <th className="py-1 pr-4 text-left font-medium">Sub-dept</th>}
          <th className="py-1 pr-4 text-left font-medium">Responsible</th>
          <th className="py-1 pr-4 text-right font-medium">Amount</th>
          <th className="py-1 pr-4 text-right font-medium w-14">%</th>
          {hasComment && <th className="py-1 text-left font-medium">Comment</th>}
        </tr>
      </thead>
      <tbody>
        {allocations.map((alloc) => {
          const hasReinvoice = (alloc.reinvoice_destinations?.length ?? 0) > 0
          return (
            <React.Fragment key={alloc.id}>
              <tr
                className={cn(
                  'border-t border-border/50',
                  hasReinvoice && 'text-muted-foreground/50',
                )}
              >
                <td className="py-1 pr-4">{alloc.company}</td>
                {hasBrand && <td className="py-1 pr-4">{alloc.brand || '-'}</td>}
                <td className="py-1 pr-4">{alloc.department}</td>
                {hasSubdept && <td className="py-1 pr-4">{alloc.subdepartment || '-'}</td>}
                <td className="py-1 pr-4 text-muted-foreground">{alloc.responsible || '-'}</td>
                <td
                  className={cn(
                    'py-1 pr-4 text-right tabular-nums',
                    hasReinvoice && 'opacity-40',
                  )}
                >
                  <CurrencyDisplay value={alloc.allocation_value} currency={currency} />
                </td>
                <td className="py-1 pr-4 text-right tabular-nums">
                  {alloc.allocation_percent}%
                </td>
                {hasComment && (
                  <td className="py-1 text-muted-foreground max-w-[150px] truncate">
                    {alloc.comment ? (
                      <TooltipProvider delayDuration={200}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-default">{alloc.comment}</span>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[400px] whitespace-pre-wrap">
                            {alloc.comment}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ) : (
                      ''
                    )}
                  </td>
                )}
              </tr>
              {hasReinvoice &&
                alloc.reinvoice_destinations!.map((rd) => (
                  <tr key={`${alloc.id}-rd-${rd.id}`} className="text-[11px]">
                    <td className="py-0.5 pl-6 pr-4 text-foreground">{rd.company}</td>
                    {hasBrand && (
                      <td className="py-0.5 pr-4 text-foreground">{rd.brand || '-'}</td>
                    )}
                    <td className="py-0.5 pr-4 text-foreground">{rd.department}</td>
                    {hasSubdept && (
                      <td className="py-0.5 pr-4 text-foreground">{rd.subdepartment || '-'}</td>
                    )}
                    <td className="py-0.5 pr-4 text-muted-foreground italic">reinvoiced</td>
                    <td className="py-0.5 pr-4 text-right text-foreground tabular-nums">
                      <CurrencyDisplay value={rd.value} currency={currency} />
                    </td>
                    <td className="py-0.5 pr-4 text-right text-foreground tabular-nums">
                      {rd.percentage}%
                    </td>
                    {hasComment && (
                      <td className="py-0.5 text-muted-foreground italic">reinvoiced</td>
                    )}
                  </tr>
                ))}
            </React.Fragment>
          )
        })}
      </tbody>
    </table>
  )
}
