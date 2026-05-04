import { create } from 'zustand'
import { createDataTableSlice, type DataTableState } from './dataTableFactory'

interface HrFilters {
  company?: string
  brand?: string
  department?: string
  year?: number
  month?: number
  search?: string
  // Timesheet tab — persisted across tab switches
  timesheetYear?: number
  timesheetMonth?: number
  timesheetNodeId?: number | null
}

const now = new Date()

type HrState = DataTableState<HrFilters>

export const useHrStore = create<HrState>((set) => ({
  ...createDataTableSlice<HrFilters>(
    {
      defaultFilters: {
        year: now.getFullYear(),
        timesheetYear: now.getFullYear(),
        timesheetMonth: now.getMonth() + 1,
        timesheetNodeId: null,
      },
    },
    set,
  ),
}))
