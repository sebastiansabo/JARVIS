import type { SchemaCascadeLine } from '@/api/suppliers'

export function zonesSum(line: SchemaCascadeLine): number {
  return line.allocations.reduce((s, a) => s + (a.value ?? 0), 0)
}

/** A line reconciles unless it is split into ≥2 zones whose values don't sum to the line net. */
export function lineReconciles(line: SchemaCascadeLine): boolean {
  if (line.allocations.length <= 1) return true
  return Math.abs(zonesSum(line) - (line.amount ?? 0)) <= 0.01
}

export function cascadeReconciles(lines: SchemaCascadeLine[]): boolean {
  return lines.every(lineReconciles)
}

export function buildSavePayload(
  mode: 'alloc' | 'line', lines: SchemaCascadeLine[], supplierId: number, companyId: number,
) {
  if (mode === 'alloc') {
    const alloc_map: Record<string, number | null> = {}
    for (const l of lines) for (const a of l.allocations) alloc_map[String(a.id)] = a.konto_config_id
    return { mode, supplier_id: supplierId, company_id: companyId, alloc_map }
  }
  const line_map: Record<string, number | null> = {}
  for (const l of lines) line_map[String(l.index)] = l.line_konto_config_id
  return { mode, supplier_id: supplierId, company_id: companyId, line_map }
}
