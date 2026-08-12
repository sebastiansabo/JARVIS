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
  /** Tenant switcher: acting company (null = use the current user's own company). */
  selectedCompanyId: number | null
  setSelectedCompanyId: (companyId: number | null) => void
  /** Tenant switcher: brand narrowing within the acting company ('' = All). */
  selectedBrand: string
  setSelectedBrand: (brand: string) => void
}

// ---- Tenant switcher persistence (mirrors loadColumns/saveColumns above) ----
const SELECTED_COMPANY_KEY = 'carpark-selected-company-id'
const SELECTED_BRAND_KEY = 'carpark-selected-brand'

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
    if (companyId == null) localStorage.removeItem(SELECTED_COMPANY_KEY)
    else localStorage.setItem(SELECTED_COMPANY_KEY, String(companyId))
  } catch {
    /* ignore */
  }
}

function loadSelectedBrand(): string {
  try {
    return localStorage.getItem(SELECTED_BRAND_KEY) ?? ''
  } catch {
    return ''
  }
}

function saveSelectedBrand(brand: string) {
  try {
    localStorage.setItem(SELECTED_BRAND_KEY, brand)
  } catch {
    /* ignore */
  }
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
  selectedCompanyId: loadSelectedCompanyId(),
  setSelectedCompanyId: (companyId) => {
    saveSelectedCompanyId(companyId)
    set({ selectedCompanyId: companyId })
  },
  selectedBrand: loadSelectedBrand(),
  setSelectedBrand: (brand) => {
    saveSelectedBrand(brand)
    set({ selectedBrand: brand })
  },
}))
