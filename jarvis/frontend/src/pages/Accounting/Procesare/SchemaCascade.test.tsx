import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { SchemaCascadeData } from '@/api/suppliers'

const getSchemaCascade = vi.fn()
const saveSchemaCascade = vi.fn()
vi.mock('@/api/suppliers', () => ({
  suppliersApi: {
    getSchemaCascade: (...a: unknown[]) => getSchemaCascade(...a),
    saveSchemaCascade: (...a: unknown[]) => saveSchemaCascade(...a),
  },
}))
// NOTE: explicit .tsx extension is required here — this directory also has a
// sibling `schemaCascade.ts` (helpers) whose name differs from this component's
// file only by the first letter's case. On case-insensitive filesystems (default
// on macOS/Windows), Vite/esbuild's default extension-probe order tries `.ts`
// before `.tsx` and silently resolves the extensionless `./SchemaCascade` to the
// wrong file (the helpers module) instead of this component. See task-6-report.md.
import { SchemaCascade } from './SchemaCascade.tsx'

const DATA: SchemaCascadeData = {
  success: true, supplier_id: 9, company_id: 3,
  presets: [{ id: 5, name: 'A', is_active: true } as never, { id: 6, name: 'B', is_active: false } as never],
  active_id: 5, invoice_konto_config_id: null, per_line: false, mode: 'alloc',
  lines: [{ index: 0, name: 'L0', amount: 100, vat_rate: 19, line_konto_config_id: null, allocations: [
    { id: 11, department: 'X', subdepartment: null, value: 60, konto_config_id: null },
    { id: 12, department: 'Y', subdepartment: null, value: 40, konto_config_id: null }] }],
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('SchemaCascade', () => {
  beforeEach(() => { getSchemaCascade.mockReset(); saveSchemaCascade.mockReset() })

  it('renders one schema picker per allocation zone in alloc mode', async () => {
    getSchemaCascade.mockResolvedValue(DATA)
    wrap(<SchemaCascade invoiceId={42} company="ACME" supplierId={9} companyId={3} onSaved={() => {}} />)
    await screen.findByText('L0')
    expect(screen.getAllByRole('combobox')).toHaveLength(2) // one per zone
    expect(screen.getByText(/X/)).toBeInTheDocument()
    expect(screen.getByText(/Y/)).toBeInTheDocument()
  })

  it('blocks save when a split does not reconcile', async () => {
    getSchemaCascade.mockResolvedValue({ ...DATA, lines: [{ ...DATA.lines[0], amount: 999 }] })
    wrap(<SchemaCascade invoiceId={42} company="ACME" supplierId={9} companyId={3} onSaved={() => {}} />)
    await screen.findByText('L0')
    expect(screen.getByRole('button', { name: /Salveaz/ })).toBeDisabled()
  })
})
