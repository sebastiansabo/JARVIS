import { useState, useCallback, useRef, useEffect } from 'react'
import { ChevronDown, ChevronRight, Plus, Check, AlertCircle, Merge, Split, Layers } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { type AllocationRow, newRow, AllocationRowComponent } from './AllocationEditor'
import type { LineItem } from '@/types/invoices'

/* ──── Types ──── */

export type LineGroup = number[] // array of line item indices

interface LineItemAllocationsProps {
  lineItems: LineItem[]
  company: string
  companies: string[]
  brands: string[]
  currency: string
  allocations: Map<number, AllocationRow[]>
  onChange: (allocations: Map<number, AllocationRow[]>) => void
  groups: LineGroup[]
  onGroupsChange: (groups: LineGroup[]) => void
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
  groups,
  onGroupsChange,
}: LineItemAllocationsProps) {
  const [expandedItems, setExpandedItems] = useState<Set<number>>(() => new Set([0]))
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const defaultRowsRef = useRef<Map<number, AllocationRow[]>>(new Map())

  const toggleItem = useCallback((key: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  // Clear cached defaults + selection when line items change
  useEffect(() => {
    defaultRowsRef.current.clear()
    setSelected(new Set())
  }, [lineItems])

  // Get group amount (sum of all member amounts)
  const getGroupAmount = useCallback(
    (group: LineGroup) => group.reduce((sum, idx) => sum + (lineItems[idx]?.amount ?? 0), 0),
    [lineItems],
  )

  // Get allocation rows for a group (keyed by first index)
  const getRows = useCallback(
    (groupKey: number, groupAmount: number): AllocationRow[] => {
      const stored = allocations.get(groupKey)
      if (stored) return stored
      if (!defaultRowsRef.current.has(groupKey)) {
        const row = newRow()
        row.value = groupAmount
        defaultRowsRef.current.set(groupKey, [row])
      }
      return defaultRowsRef.current.get(groupKey)!
    },
    [allocations],
  )

  const setGroupRows = useCallback(
    (group: LineGroup, rows: AllocationRow[]) => {
      const next = new Map(allocations)
      const groupKey = group[0]
      next.set(groupKey, rows)

      // Replicate allocation percentages to all other members
      if (group.length > 1) {
        for (let i = 1; i < group.length; i++) {
          const memberIdx = group[i]
          const memberAmount = lineItems[memberIdx]?.amount ?? 0
          next.set(
            memberIdx,
            rows.map((r) => ({
              ...r,
              id: `${r.id}-m${memberIdx}`,
              value: memberAmount * (r.percent / 100),
            })),
          )
        }
      }
      onChange(next)
    },
    [allocations, onChange, lineItems],
  )

  const updateRow = useCallback(
    (group: LineGroup, rowId: string, updates: Partial<AllocationRow>) => {
      const groupKey = group[0]
      const groupAmount = getGroupAmount(group)
      const rows = getRows(groupKey, groupAmount)
      const updated = rows.map((r) => {
        if (r.id !== rowId) return r
        const u = { ...r, ...updates }
        if ('percent' in updates) u.value = groupAmount * (u.percent / 100)
        if ('value' in updates && groupAmount > 0) u.percent = (u.value / groupAmount) * 100
        return u
      })
      setGroupRows(group, updated)
    },
    [getRows, setGroupRows, getGroupAmount],
  )

  const addRow = useCallback(
    (group: LineGroup) => {
      const groupKey = group[0]
      const groupAmount = getGroupAmount(group)
      const rows = getRows(groupKey, groupAmount)
      const totalLocked = rows.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
      const remaining = Math.max(0, 100 - totalLocked)
      const unlocked = rows.filter((r) => !r.locked).length + 1
      const share = remaining / unlocked

      const updated = rows.map((r) =>
        r.locked ? r : { ...r, percent: share, value: groupAmount * (share / 100) },
      )
      const nr = newRow()
      nr.percent = share
      nr.value = groupAmount * (share / 100)
      setGroupRows(group, [...updated, nr])
    },
    [getRows, setGroupRows, getGroupAmount],
  )

  const removeRow = useCallback(
    (group: LineGroup, rowId: string) => {
      const groupKey = group[0]
      const groupAmount = getGroupAmount(group)
      const rows = getRows(groupKey, groupAmount)
      if (rows.length <= 1) return
      const remaining = rows.filter((r) => r.id !== rowId)
      const totalLocked = remaining.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
      const freePercent = Math.max(0, 100 - totalLocked)
      const unlocked = remaining.filter((r) => !r.locked).length
      const share = unlocked > 0 ? freePercent / unlocked : 0

      const updated = remaining.map((r) =>
        r.locked ? r : { ...r, percent: share, value: groupAmount * (share / 100) },
      )
      setGroupRows(group, updated)
    },
    [getRows, setGroupRows, getGroupAmount],
  )

  /* ──── Merge / Split ──── */

  const toggleSelect = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const mergeSelected = () => {
    if (selected.size < 2) return
    const selectedIndices = Array.from(selected).sort((a, b) => a - b)

    // Remove selected items from their current groups
    const newGroups = groups.filter((g) => !g.some((idx) => selected.has(idx)))
    // Add merged group
    newGroups.push(selectedIndices)
    newGroups.sort((a, b) => a[0] - b[0])

    onGroupsChange(newGroups)
    setSelected(new Set())

    // Set up allocation for the new group using first item's existing allocation
    const groupKey = selectedIndices[0]
    const groupAmount = selectedIndices.reduce((sum, idx) => sum + (lineItems[idx]?.amount ?? 0), 0)
    const existingRows = allocations.get(groupKey) ?? defaultRowsRef.current.get(groupKey)
    const baseRows = existingRows?.length
      ? existingRows.map((r) => ({ ...r, value: groupAmount * (r.percent / 100) }))
      : [{ ...newRow(), value: groupAmount }]

    // Store for group key and replicate
    const next = new Map(allocations)
    next.set(groupKey, baseRows)
    for (let i = 1; i < selectedIndices.length; i++) {
      const mIdx = selectedIndices[i]
      const mAmount = lineItems[mIdx]?.amount ?? 0
      next.set(
        mIdx,
        baseRows.map((r) => ({ ...r, id: `${r.id}-m${mIdx}`, value: mAmount * (r.percent / 100) })),
      )
    }
    onChange(next)

    // Expand the merged group
    setExpandedItems((prev) => new Set([...prev, groupKey]))
  }

  const splitGroup = (group: LineGroup) => {
    if (group.length <= 1) return
    const newGroups = groups.flatMap((g) => (g === group ? g.map((idx) => [idx]) : [g]))
    newGroups.sort((a, b) => a[0] - b[0])
    onGroupsChange(newGroups)

    // Expand allocation: copy group allocation to each member with individual amounts
    const groupKey = group[0]
    const groupRows = allocations.get(groupKey)
    if (groupRows) {
      const next = new Map(allocations)
      group.forEach((idx) => {
        const itemAmount = lineItems[idx]?.amount ?? 0
        next.set(
          idx,
          groupRows.map((r) => ({
            ...r,
            id: idx === groupKey ? r.id : crypto.randomUUID(),
            value: itemAmount * (r.percent / 100),
          })),
        )
      })
      onChange(next)
    }
  }

  /* ──── Summary ──── */

  const allocatedCount = lineItems.filter((_, idx) => {
    const rows = allocations.get(idx)
    if (!rows || rows.length === 0) return false
    const total = rows.reduce((s, r) => s + r.percent, 0)
    return Math.abs(total - 100) <= 1
  }).length

  const grandTotal = lineItems.reduce((sum, item) => sum + item.amount, 0)
  const mergedCount = groups.filter((g) => g.length > 1).length

  return (
    <div className="space-y-2">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        {selected.size >= 2 && (
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1.5" onClick={mergeSelected}>
            <Merge className="h-3 w-3" />
            Merge {selected.size} items
          </Button>
        )}
        {selected.size > 0 && selected.size < 2 && (
          <span className="text-xs text-muted-foreground">Select 2+ items to merge</span>
        )}
        {mergedCount > 0 && (
          <span className="text-xs text-muted-foreground ml-auto">
            <Layers className="h-3 w-3 inline mr-1" />
            {mergedCount} merged group{mergedCount > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Groups */}
      <div className="space-y-1">
        {groups.map((group) => {
          const groupKey = group[0]
          const isMerged = group.length > 1
          const groupAmount = getGroupAmount(group)
          const rows = getRows(groupKey, groupAmount)
          const totalPercent = rows.reduce((s, r) => s + r.percent, 0)
          const isValid = Math.abs(totalPercent - 100) <= 1
          const isExpanded = expandedItems.has(groupKey)

          return (
            <div key={groupKey} className={cn('rounded-lg border bg-card', isMerged && 'border-blue-200 dark:border-blue-800')}>
              {/* Header */}
              <div className="flex items-center gap-1 pr-3">
                {/* Checkbox for ungrouped items */}
                {!isMerged && (
                  <div
                    className="pl-2 py-2 shrink-0"
                    onClick={(e) => {
                      e.stopPropagation()
                      toggleSelect(groupKey)
                    }}
                  >
                    <Checkbox
                      checked={selected.has(groupKey)}
                      className="h-3.5 w-3.5"
                    />
                  </div>
                )}
                <button
                  className={cn(
                    'flex flex-1 items-center gap-2 py-2 text-sm hover:bg-muted/50 transition-colors',
                    isMerged ? 'pl-3' : 'pl-1',
                  )}
                  onClick={() => toggleItem(groupKey)}
                >
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  {isMerged ? (
                    <span className="flex-1 text-left">
                      <span className="inline-flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5 text-blue-500" />
                        <span className="font-medium">{group.length} items merged</span>
                      </span>
                    </span>
                  ) : (
                    <span className="flex-1 text-left truncate font-medium">
                      {lineItems[groupKey]?.description}
                    </span>
                  )}
                  <span className="tabular-nums text-muted-foreground shrink-0">
                    {formatNumber(groupAmount)} {currency}
                  </span>
                  {isValid ? (
                    <Check className="h-4 w-4 text-green-600 shrink-0" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
                  )}
                </button>
              </div>

              {/* Expanded content */}
              {isExpanded && (
                <div className="border-t px-3 pb-3 pt-2 space-y-2">
                  {/* Merged items list */}
                  {isMerged && (
                    <div className="rounded-md bg-blue-50 dark:bg-blue-950/30 px-3 py-2 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-blue-700 dark:text-blue-300">Merged items:</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs gap-1 text-blue-600 hover:text-blue-700"
                          onClick={() => splitGroup(group)}
                        >
                          <Split className="h-3 w-3" />
                          Split
                        </Button>
                      </div>
                      {group.map((idx) => (
                        <div key={idx} className="flex items-center justify-between text-xs text-blue-600 dark:text-blue-400">
                          <span className="truncate pr-2">{lineItems[idx]?.description}</span>
                          <span className="tabular-nums shrink-0">
                            {formatNumber(lineItems[idx]?.amount ?? 0)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

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
                      effectiveValue={groupAmount}
                      currency={currency}
                      onUpdate={(updates) => updateRow(group, row.id, updates)}
                      onRemove={() => removeRow(group, row.id)}
                      canRemove={rows.length > 1}
                    />
                  ))}

                  {/* Footer */}
                  <div className="flex items-center justify-between border-t pt-2 px-1">
                    <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={() => addRow(group)}>
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
      </div>

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

/* ──── Helper: Generate merge comment ──── */

export function generateMergeComment(groups: LineGroup[], lineItems: LineItem[]): string {
  const mergedGroups = groups.filter((g) => g.length > 1)
  if (mergedGroups.length === 0) return ''
  const lines = mergedGroups.map((group, i) => {
    const items = group.map((idx) => lineItems[idx]?.description ?? `Item ${idx + 1}`)
    return `Group ${i + 1} (${group.length} items): ${items.join(' + ')}`
  })
  return `[Merged line items]\n${lines.join('\n')}`
}
