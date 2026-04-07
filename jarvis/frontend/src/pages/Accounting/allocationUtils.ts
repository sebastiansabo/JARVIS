import type { Allocation } from '@/types/invoices'

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
