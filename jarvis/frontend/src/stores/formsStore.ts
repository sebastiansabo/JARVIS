import { create } from 'zustand'
import type { FormFilters } from '@/types/forms'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

const defaultColumns = [
  'name', 'company_name', 'status', 'submission_count', 'published_at', 'created_at',
]

interface FormsState
  extends DataTableState<FormFilters>,
    ColumnState {
  viewMode: 'table' | 'cards'
  setViewMode: (mode: 'table' | 'cards') => void
}

export const useFormsStore = create<FormsState>((set) => ({
  ...createDataTableSlice<FormFilters>(
    {
      defaultFilters: { limit: 50, offset: 0 },
      columns: {
        storageKey: 'forms-columns',
        defaults: defaultColumns,
        pageId: 'forms',
      },
      resetOffsetOnFilter: true,
    },
    set,
  ),
  viewMode:
    (localStorage.getItem('forms-view-mode') as 'table' | 'cards') || 'table',
  setViewMode: (mode) => {
    try {
      localStorage.setItem('forms-view-mode', mode)
    } catch {
      /* ignore */
    }
    set({ viewMode: mode })
  },
}))
