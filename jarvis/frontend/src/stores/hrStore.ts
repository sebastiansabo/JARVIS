import { create } from 'zustand'
import { createDataTableSlice, type DataTableState } from './dataTableFactory'

interface HrFilters {
  company?: string
  brand?: string
  department?: string
  year?: number
  month?: number
  search?: string
}

const now = new Date()

type HrState = DataTableState<HrFilters>

export const useHrStore = create<HrState>((set) => ({
  ...createDataTableSlice<HrFilters>(
    {
      defaultFilters: { year: now.getFullYear() },
    },
    set,
  ),
}))
