import { create } from 'zustand'
import type { DmsFilters } from '@/types/dms'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

const defaultColumns = [
  'title', 'category_name', 'file_count', 'children_count', 'status',
  'expiry_date', 'created_by_name', 'created_at',
]

interface DmsState
  extends DataTableState<DmsFilters>,
    ColumnState {
  viewMode: 'table' | 'cards'
  setViewMode: (mode: 'table' | 'cards') => void
}

export const useDmsStore = create<DmsState>((set) => ({
  ...createDataTableSlice<DmsFilters>(
    {
      defaultFilters: { limit: 50, offset: 0 },
      columns: {
        storageKey: 'dms-document-columns',
        defaults: defaultColumns,
      },
      resetOffsetOnFilter: true,
    },
    set,
  ),
  viewMode:
    (localStorage.getItem('dms-view-mode') as 'table' | 'cards') ||
    'table',
  setViewMode: (mode) => {
    try {
      localStorage.setItem('dms-view-mode', mode)
    } catch {
      /* ignore */
    }
    set({ viewMode: mode })
  },
}))
