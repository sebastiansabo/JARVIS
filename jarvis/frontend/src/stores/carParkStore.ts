import { create } from 'zustand'
import type { CatalogFilters } from '../types/carpark'
import {
  createDataTableSlice,
  type DataTableState,
  type ColumnState,
} from './dataTableFactory'

const defaultColumns = [
  'photo',
  'brand_model',
  'category',
  'status',
  'year',
  'mileage',
  'fuel_type',
  'current_price',
  'days_listed',
  'location',
]

interface CarParkState extends DataTableState<CatalogFilters>, ColumnState {
  page: number
  perPage: number
  setPage: (page: number) => void
  setPerPage: (perPage: number) => void
  sort: string
  order: 'asc' | 'desc'
  setSort: (sort: string, order: 'asc' | 'desc') => void
}

export const useCarParkStore = create<CarParkState>((set) => ({
  ...createDataTableSlice<CatalogFilters>(
    {
      defaultFilters: {},
      columns: {
        storageKey: 'carpark-columns',
        defaults: defaultColumns,
        locked: new Set(['brand_model']),
        pageId: 'carpark',
      },
    },
    set,
  ),
  page: 1,
  perPage: 25,
  setPage: (page) => set({ page }),
  setPerPage: (perPage) => set({ perPage, page: 1 }),
  sort: 'acquisition_date',
  order: 'desc',
  setSort: (sort, order) => set({ sort, order }),
}))
