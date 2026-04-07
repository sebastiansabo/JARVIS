import type { Allocation, Invoice, LineItem } from '@/types/invoices'
import { type AllocationRow, allocationsToRows } from './AllocationEditor'
import { autoGroupLineItems, type LineGroup } from './LineItemAllocations'

/**
 * Deduplicate allocations from a per-line invoice: when multiple line items are
 * merged in the editor, the same allocation (company / brand / department /
 * subdept / responsible / percent / comment) is replicated per line_item_index
 * with only the allocation_value differing. Collapse them back into a single
 * row summing the values — matching the legacy expand/collapse behavior.
 */
export function dedupeMergedAllocations(allocations: Allocation[]): Allocation[] {
  const keyFn = (a: Allocation) => {
    // Include reinvoice destinations in the key so allocations with different
    // reinvoice paths stay as separate rows (otherwise the dedup would collapse
    // them and silently drop all but the first reinvoice destination).
    const reinvoice = (a.reinvoice_destinations ?? [])
      .map(
        (r) =>
          `${r.company}|${r.brand ?? ''}|${r.department}|${r.subdepartment ?? ''}|${r.percentage}`,
      )
      .sort()
      .join(';')
    return [
      a.company,
      a.brand ?? '',
      a.department,
      a.subdepartment ?? '',
      a.responsible ?? '',
      a.allocation_percent,
      a.comment ?? '',
      reinvoice,
    ].join('|')
  }

  const grouped = new Map<string, Allocation>()
  const order: string[] = []
  for (const alloc of allocations) {
    const key = keyFn(alloc)
    const existing = grouped.get(key)
    if (existing) {
      // Sum the parent allocation_value and the reinvoice destination values
      // so the displayed total matches the merged group amount.
      const mergedReinvoice = (existing.reinvoice_destinations ?? []).map((rd, idx) => {
        const otherRd = alloc.reinvoice_destinations?.[idx]
        return otherRd ? { ...rd, value: (rd.value || 0) + (otherRd.value || 0) } : rd
      })
      grouped.set(key, {
        ...existing,
        allocation_value: (existing.allocation_value || 0) + (alloc.allocation_value || 0),
        reinvoice_destinations: mergedReinvoice,
      })
    } else {
      grouped.set(key, alloc)
      order.push(key)
    }
  }
  return order.map((k) => grouped.get(k)!)
}

/**
 * Build a stable fingerprint for a line's allocations, ignoring per-line value
 * differences. Two lines with the same fingerprint were merged together — they
 * have identical company / brand / department / subdepartment / percent /
 * comment / reinvoice destinations.
 */
export function lineAllocationsFingerprint(allocs: NonNullable<Invoice['allocations']>): string {
  return [...allocs]
    .map((a) => {
      const reinvoice = (a.reinvoice_destinations ?? [])
        .map(
          (r) =>
            `${r.company}|${r.brand ?? ''}|${r.department}|${r.subdepartment ?? ''}|${r.percentage}`,
        )
        .sort()
        .join(';')
      return [
        a.company,
        a.brand ?? '',
        a.department,
        a.subdepartment ?? '',
        a.allocation_percent,
        a.comment ?? '',
        reinvoice,
      ].join('|')
    })
    .sort()
    .join('||')
}

/**
 * Detect merged line groups from existing per-line allocations.
 *
 * When a user merges line items in the editor, the same allocation is
 * replicated across each line_item_index. On reload, group line indices that
 * share an identical allocation fingerprint back into the same merged group.
 *
 * Falls back to {@link autoGroupLineItems} (Meta-campaign template grouping)
 * for lines that have no allocations yet (e.g. brand new invoice).
 */
export function detectMergedGroupsFromAllocations(invoice: Invoice): LineGroup[] {
  const lineItems = invoice.line_items ?? []
  if (lineItems.length === 0) return []

  const allocations = invoice.allocations ?? []
  if (allocations.length === 0) return autoGroupLineItems(lineItems)

  // Bucket allocations by line_item_index
  const allocsByLine = new Map<number, NonNullable<Invoice['allocations']>>()
  for (const alloc of allocations) {
    const idx = alloc.line_item_index ?? -1
    if (idx < 0) continue
    const arr = allocsByLine.get(idx) ?? []
    arr.push(alloc)
    allocsByLine.set(idx, arr)
  }

  // If nothing has a line_item_index (legacy whole-invoice mode), fall back
  if (allocsByLine.size === 0) return autoGroupLineItems(lineItems)

  // Group line indices by their allocation fingerprint
  const fingerprintToLines = new Map<string, number[]>()
  const ungrouped: number[] = []
  for (let i = 0; i < lineItems.length; i++) {
    const allocs = allocsByLine.get(i)
    if (!allocs || allocs.length === 0) {
      ungrouped.push(i)
      continue
    }
    const fp = lineAllocationsFingerprint(allocs)
    const arr = fingerprintToLines.get(fp) ?? []
    arr.push(i)
    fingerprintToLines.set(fp, arr)
  }

  const groups: LineGroup[] = []
  for (const lines of fingerprintToLines.values()) {
    groups.push([...lines].sort((a, b) => a - b))
  }
  for (const idx of ungrouped) {
    groups.push([idx])
  }
  groups.sort((a, b) => a[0] - b[0])
  return groups
}

/**
 * Build the per-line AllocationRow map used by LineItemAllocations from an
 * existing invoice's allocations. Mirrors EditInvoiceDialog's initialization
 * so the inline editor restores the exact merge state on entry.
 */
export function buildInitialLineAllocations(
  invoice: Invoice,
  effectiveValue: number,
): Map<number, AllocationRow[]> {
  const map = new Map<number, AllocationRow[]>()
  if (!invoice.allocations) return map

  const grouped = new Map<number, NonNullable<Invoice['allocations']>>()
  for (const alloc of invoice.allocations) {
    const idx = alloc.line_item_index ?? -1
    if (idx < 0) continue
    const existing = grouped.get(idx) ?? []
    existing.push(alloc)
    grouped.set(idx, existing)
  }

  for (const [idx, allocs] of grouped) {
    const lineAmount = invoice.line_items?.[idx]?.amount ?? effectiveValue
    map.set(idx, allocationsToRows(allocs, lineAmount))
  }

  return map
}

/* ──── Read-only display grouping ──── */

/**
 * A merged group of line items together with the deduped allocations that
 * apply to them, ready for read-only display.
 */
export interface AllocationDisplayGroup {
  groupKey: number
  lineIndices: number[]
  lineItems: LineItem[]
  groupAmount: number
  allocations: Allocation[]
}

/**
 * Build the grouped display structure shown in the inline allocation panel.
 *
 * Groups are derived from line item indices that share an identical allocation
 * fingerprint (i.e. the user merged them in the editor). Each group's
 * allocations are deduped (one row per logical destination) and the values are
 * summed across the merged line indices so the displayed totals match the
 * group's actual amount.
 */
export function buildAllocationDisplayGroups(invoice: Invoice): AllocationDisplayGroup[] {
  const lineItems = invoice.line_items ?? []
  const allocations = invoice.allocations ?? []
  if (lineItems.length === 0 || allocations.length === 0) return []

  const groups = detectMergedGroupsFromAllocations(invoice)

  // Bucket allocations by line_item_index for fast lookup
  const allocsByLine = new Map<number, Allocation[]>()
  for (const a of allocations) {
    const idx = a.line_item_index ?? -1
    if (idx < 0) continue
    const arr = allocsByLine.get(idx) ?? []
    arr.push(a)
    allocsByLine.set(idx, arr)
  }

  return groups.map((group) => {
    const groupKey = group[0]
    const groupItems = group.map((idx) => lineItems[idx]).filter(Boolean) as LineItem[]
    const groupAmount = groupItems.reduce((s, li) => s + (li.amount || 0), 0)
    // Concatenate allocations from every line in the group, then dedupe so
    // logically-identical destinations collapse to a single row with their
    // values summed across the merged lines.
    const merged: Allocation[] = []
    for (const idx of group) {
      const arr = allocsByLine.get(idx) ?? []
      merged.push(...arr)
    }
    return {
      groupKey,
      lineIndices: group,
      lineItems: groupItems,
      groupAmount,
      allocations: dedupeMergedAllocations(merged),
    }
  })
}
