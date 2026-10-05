import { create } from 'zustand'
import type { MktProjectFilters } from '@/types/marketing'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

/**
 * Default-visible project-table columns, in order. Mirrors the columns the
 * table showed before the column-toggle control existed. `brand_name` and
 * `end_date` are available in the catalog (see MKT_PROJECT_COLUMNS) but hidden
 * by default.
 */
export const defaultColumns = [
  'name', 'company_name', 'project_type', 'status', 'health',
  'total_budget', 'total_spent', 'burn', 'owner_name', 'start_date',
]

/** The project name is the row's identity and can never be hidden. */
export const lockedColumns = new Set(['name'])

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
        locked: lockedColumns,
        pageId: 'marketing',
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
