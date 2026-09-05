import { create } from 'zustand'
import type { InvoiceFilters } from '../types/invoices'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

/** Columns that cannot be hidden by the user. */
export const lockedColumns = new Set(['net_value'])

// ── Accounting section tenant switcher: the acting company shared across accounting pages
// (Invoices, Procesare, Controlling…). null = "Toate companiile" (all companies). Persisted to
// localStorage so the choice sticks across pages/reloads (mirrors the CarPark tenant switcher).
const SELECTED_COMPANY_KEY = 'accounting-selected-company-id'

function loadSelectedCompanyId(): number | null {
  try {
    const raw = localStorage.getItem(SELECTED_COMPANY_KEY)
    if (raw != null && raw !== '') {
      const n = Number(raw)
      if (!Number.isNaN(n)) return n
    }
  } catch {
    /* ignore */
  }
  return null
}

function saveSelectedCompanyId(companyId: number | null) {
  try {
    localStorage.setItem(SELECTED_COMPANY_KEY, companyId == null ? '' : String(companyId))
  } catch {
    /* ignore */
  }
}

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

interface AccountingState
  extends DataTableState<InvoiceFilters>,
    ColumnState {
  showRecycleBin: boolean
  setShowRecycleBin: (show: boolean) => void
  /** Tenant switcher: acting company shared across accounting pages (null = "Toate companiile"). */
  selectedCompanyId: number | null
  setSelectedCompanyId: (companyId: number | null) => void
}

export const useAccountingStore = create<AccountingState>((set) => ({
  ...createDataTableSlice<InvoiceFilters>(
    {
      defaultFilters: {},
      columns: {
        storageKey: 'accounting-columns',
        defaults: defaultColumns,
        locked: lockedColumns,
        pageId: 'accounting',
      },
    },
    set,
  ),
  showRecycleBin: false,
  setShowRecycleBin: (show) => set({ showRecycleBin: show, selectedIds: [] }),
  selectedCompanyId: loadSelectedCompanyId(),
  setSelectedCompanyId: (companyId) => {
    saveSelectedCompanyId(companyId)
    set({ selectedCompanyId: companyId })
  },
}))
