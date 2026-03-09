import { create } from 'zustand'
import type { MktProjectFilters } from '@/types/marketing'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

const defaultColumns = [
  'name', 'company_name', 'brand_name', 'project_type', 'status',
  'total_budget', 'total_spent', 'owner_name', 'start_date', 'end_date',
]

interface MarketingState
  extends DataTableState<MktProjectFilters>,
    ColumnState {
  viewMode: 'table' | 'cards' | 'kanban'
  setViewMode: (mode: 'table' | 'cards' | 'kanban') => void
}

export const useMarketingStore = create<MarketingState>((set) => ({
  ...createDataTableSlice<MktProjectFilters>(
    {
      defaultFilters: { limit: 50, offset: 0 },
      columns: {
        storageKey: 'marketing-project-columns',
        defaults: defaultColumns,
      },
      resetOffsetOnFilter: true,
    },
    set,
  ),
  viewMode:
    (localStorage.getItem('marketing-view-mode') as 'table' | 'cards' | 'kanban') ||
    'table',
  setViewMode: (mode) => {
    try {
      localStorage.setItem('marketing-view-mode', mode)
    } catch {
      /* ignore */
    }
    set({ viewMode: mode })
  },
}))
