import { describe, it, expect } from 'vitest'
import { zonesSum, lineReconciles, cascadeReconciles, buildSavePayload } from './schemaCascade'
import type { SchemaCascadeLine } from '@/api/suppliers'

const line = (over: Partial<SchemaCascadeLine>): SchemaCascadeLine => ({
  index: 0, name: 'L', amount: 100, vat_rate: 19, line_konto_config_id: null, allocations: [], ...over,
})

describe('reconciliation', () => {
  it('single/zero-zone lines always reconcile', () => {
    expect(lineReconciles(line({ allocations: [] }))).toBe(true)
    expect(lineReconciles(line({ allocations: [{ id: 1, department: 'X', subdepartment: null, value: 40, konto_config_id: null }] }))).toBe(true)
  })
  it('multi-zone line reconciles only when zones sum to net (±0.01)', () => {
    const zones = [
      { id: 1, department: 'X', subdepartment: null, value: 60, konto_config_id: null },
      { id: 2, department: 'Y', subdepartment: null, value: 40, konto_config_id: null },
    ]
    expect(zonesSum(line({ allocations: zones }))).toBe(100)
    expect(lineReconciles(line({ amount: 100, allocations: zones }))).toBe(true)
    expect(lineReconciles(line({ amount: 101, allocations: zones }))).toBe(false)
  })
})

describe('buildSavePayload', () => {
  it('alloc mode emits alloc_map keyed by allocation id', () => {
    const lines = [line({ index: 0, allocations: [
      { id: 11, department: 'X', subdepartment: null, value: 60, konto_config_id: 5 },
      { id: 12, department: 'Y', subdepartment: null, value: 40, konto_config_id: null }] })]
    expect(buildSavePayload('alloc', lines, 9, 3)).toEqual({
      mode: 'alloc', supplier_id: 9, company_id: 3, alloc_map: { '11': 5, '12': null } })
  })
  it('line mode emits line_map keyed by line index', () => {
    const lines = [line({ index: 0, line_konto_config_id: 5 }), line({ index: 1, line_konto_config_id: null })]
    expect(buildSavePayload('line', lines, 9, 3)).toEqual({
      mode: 'line', supplier_id: 9, company_id: 3, line_map: { '0': 5, '1': null } })
  })
})
