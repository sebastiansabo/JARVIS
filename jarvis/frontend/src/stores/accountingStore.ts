import { create } from 'zustand'
import type { InvoiceFilters } from '../types/invoices'

interface AccountingState {
  filters: InvoiceFilters
  selectedInvoiceIds: number[]
  visibleColumns: string[]
  showRecycleBin: boolean
  setFilters: (filters: InvoiceFilters) => void
  updateFilter: <K extends keyof InvoiceFilters>(key: K, value: InvoiceFilters[K]) => void
  clearFilters: () => void
  setSelectedInvoiceIds: (ids: number[]) => void
  toggleInvoiceSelected: (id: number) => void
  clearSelected: () => void
  setVisibleColumns: (columns: string[]) => void
  setShowRecycleBin: (show: boolean) => void
}

const STORAGE_KEY = 'accounting-columns'

const defaultColumns = [
  'supplier',
  'invoice_number',
  'invoice_date',
  'net_value',
  'invoice_value',
  'company',
  'department',
  'status',
  'payment_status',
  'drive_link',
]

/** Columns that cannot be hidden by the user. */
export const lockedColumns = new Set(['net_value'])

function loadColumns(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const cols: string[] = JSON.parse(raw)
      // Ensure locked columns are always present
      for (const lc of lockedColumns) {
        if (!cols.includes(lc)) cols.push(lc)
      }
      return cols
    }
  } catch { /* ignore */ }
  return defaultColumns
}

function saveColumns(cols: string[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cols)) } catch { /* ignore */ }
}

export const useAccountingStore = create<AccountingState>((set) => ({
  filters: {},
  selectedInvoiceIds: [],
  visibleColumns: loadColumns(),
  showRecycleBin: false,
  setFilters: (filters) => set({ filters }),
  updateFilter: (key, value) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),
  clearFilters: () => set({ filters: {} }),
  setSelectedInvoiceIds: (ids) => set({ selectedInvoiceIds: ids }),
  toggleInvoiceSelected: (id) =>
    set((s) => ({
      selectedInvoiceIds: s.selectedInvoiceIds.includes(id)
        ? s.selectedInvoiceIds.filter((i) => i !== id)
        : [...s.selectedInvoiceIds, id],
    })),
  clearSelected: () => set({ selectedInvoiceIds: [] }),
  setVisibleColumns: (columns) => {
    saveColumns(columns)
    set({ visibleColumns: columns })
  },
  setShowRecycleBin: (show) => set({ showRecycleBin: show, selectedInvoiceIds: [] }),
}))
