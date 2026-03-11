import { useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, Plus, Check, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { type AllocationRow, newRow, AllocationRowComponent } from './AllocationEditor'
import type { LineItem } from '@/types/invoices'

/* ──── Types ──── */

interface LineItemAllocationsProps {
  lineItems: LineItem[]
  company: string
  companies: string[]
  brands: string[]
  currency: string
  allocations: Map<number, AllocationRow[]>
  onChange: (allocations: Map<number, AllocationRow[]>) => void
}

const formatNumber = (n: number) =>
  new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)

/* ──── Main Component ──── */

export function LineItemAllocations({
  lineItems,
  company,
  companies,
  brands,
  currency,
  allocations,
  onChange,
}: LineItemAllocationsProps) {
  const [expandedItems, setExpandedItems] = useState<Set<number>>(() => new Set([0]))

  const toggleItem = useCallback((idx: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }, [])

  const getRows = useCallback(
    (idx: number): AllocationRow[] => {
      return allocations.get(idx) ?? [newRow()]
    },
    [allocations],
  )

  const setRows = useCallback(
    (idx: number, rows: AllocationRow[]) => {
      const next = new Map(allocations)
      next.set(idx, rows)
      onChange(next)
    },
    [allocations, onChange],
  )

  const updateRow = useCallback(
    (lineIdx: number, rowId: string, updates: Partial<AllocationRow>) => {
      const rows = getRows(lineIdx)
      const lineAmount = lineItems[lineIdx].amount
      const updated = rows.map((r) => {
        if (r.id !== rowId) return r
        const u = { ...r, ...updates }
        if ('percent' in updates) u.value = lineAmount * (u.percent / 100)
        if ('value' in updates && lineAmount > 0) u.percent = (u.value / lineAmount) * 100
        return u
      })
      setRows(lineIdx, updated)
    },
    [getRows, setRows, lineItems],
  )

  const addRow = useCallback(
    (lineIdx: number) => {
      const rows = getRows(lineIdx)
      const lineAmount = lineItems[lineIdx].amount
      const totalLocked = rows.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
      const remaining = Math.max(0, 100 - totalLocked)
      const unlocked = rows.filter((r) => !r.locked).length + 1
      const share = remaining / unlocked

      const updated = rows.map((r) =>
        r.locked ? r : { ...r, percent: share, value: lineAmount * (share / 100) },
      )
      const nr = newRow()
      nr.percent = share
      nr.value = lineAmount * (share / 100)
      setRows(lineIdx, [...updated, nr])
    },
    [getRows, setRows, lineItems],
  )

  const removeRow = useCallback(
    (lineIdx: number, rowId: string) => {
      const rows = getRows(lineIdx)
      if (rows.length <= 1) return
      const lineAmount = lineItems[lineIdx].amount
      const remaining = rows.filter((r) => r.id !== rowId)
      const totalLocked = remaining.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
      const freePercent = Math.max(0, 100 - totalLocked)
      const unlocked = remaining.filter((r) => !r.locked).length
      const share = unlocked > 0 ? freePercent / unlocked : 0

      const updated = remaining.map((r) =>
        r.locked ? r : { ...r, percent: share, value: lineAmount * (share / 100) },
      )
      setRows(lineIdx, updated)
    },
    [getRows, setRows, lineItems],
  )

  // Summary
  const allocatedCount = lineItems.filter((_, idx) => {
    const rows = allocations.get(idx)
    if (!rows || rows.length === 0) return false
    const total = rows.reduce((s, r) => s + r.percent, 0)
    return Math.abs(total - 100) <= 1
  }).length

  const grandTotal = lineItems.reduce((sum, item) => sum + item.amount, 0)

  return (
    <div className="space-y-1">
      {lineItems.map((item, idx) => {
        const rows = getRows(idx)
        const totalPercent = rows.reduce((s, r) => s + r.percent, 0)
        const isValid = Math.abs(totalPercent - 100) <= 1
        const isExpanded = expandedItems.has(idx)

        return (
          <div key={idx} className="rounded-lg border bg-card">
            {/* Header */}
            <button
              className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50 transition-colors"
              onClick={() => toggleItem(idx)}
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span className="flex-1 text-left truncate font-medium">{item.description}</span>
              <span className="tabular-nums text-muted-foreground">
                {formatNumber(item.amount)} {currency}
              </span>
              {isValid ? (
                <Check className="h-4 w-4 text-green-600 shrink-0" />
              ) : (
                <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
              )}
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div className="border-t px-3 pb-3 pt-2 space-y-2">
                {/* Column headers */}
                <div className="grid grid-cols-12 gap-2 text-xs font-medium text-muted-foreground px-1">
                  {brands.length > 0 && <div className="col-span-2">Department</div>}
                  <div className={brands.length > 0 ? 'col-span-3' : 'col-span-4'}>Subdivision</div>
                  <div className="col-span-2">Detail</div>
                  <div className="col-span-1 text-right">%</div>
                  <div className="col-span-2 text-right">Value ({currency})</div>
                  <div className={brands.length > 0 ? 'col-span-2' : 'col-span-3'}></div>
                </div>

                {rows.map((row) => (
                  <AllocationRowComponent
                    key={row.id}
                    row={row}
                    company={company}
                    allCompanies={companies}
                    brands={brands}
                    effectiveValue={item.amount}
                    currency={currency}
                    onUpdate={(updates) => updateRow(idx, row.id, updates)}
                    onRemove={() => removeRow(idx, row.id)}
                    canRemove={rows.length > 1}
                  />
                ))}

                {/* Footer: add row + total */}
                <div className="flex items-center justify-between border-t pt-2 px-1">
                  <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={() => addRow(idx)}>
                    <Plus className="h-3 w-3" />
                    Add Row
                  </Button>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-muted-foreground">Total:</span>
                    <span className={cn('font-medium tabular-nums', isValid ? 'text-green-600' : 'text-destructive')}>
                      {totalPercent.toFixed(1)}%
                    </span>
                    <span className="font-medium tabular-nums">
                      {formatNumber(rows.reduce((s, r) => s + r.value, 0))} {currency}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )
      })}

      {/* Grand total summary */}
      <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-4 py-2.5 text-sm">
        <span className="font-medium">
          {allocatedCount}/{lineItems.length} lines allocated
        </span>
        <span className="font-medium tabular-nums">
          Grand Total: {formatNumber(grandTotal)} {currency}
        </span>
      </div>
    </div>
  )
}
