import { create } from 'zustand'
import type { InvoiceFilters } from '../types/invoices'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

/** Columns that cannot be hidden by the user. */
export const lockedColumns = new Set(['net_value'])

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
}))
