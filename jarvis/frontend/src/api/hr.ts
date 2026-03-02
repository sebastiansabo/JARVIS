import { api } from './client'
import type {
  EventBonus,
  HrEvent,
  HrEmployee,
  BonusType,
  HrSettings,
  HrPermissions,
  HrSummary,
  LockStatus,
  BonusSummaryByEmployee,
  BonusSummaryByEvent,
  StructureCompany,
  CompanyBrand,
  DepartmentStructure,
  MasterItem,
  OrganigramData,
} from '@/types/hr'

const BASE = '/hr/events/api'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') sp.set(k, String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const hrApi = {
  // Event Bonuses
  getBonuses: (params?: { year?: number; month?: number; employee_id?: number; event_id?: number }) =>
    api.get<EventBonus[]>(`${BASE}/event-bonuses${qs(params ?? {})}`),
  createBonus: (data: Partial<EventBonus>) => api.post<{ success: boolean; id: number }>(`${BASE}/event-bonuses`, data),
  bulkCreateBonuses: (bonuses: Partial<EventBonus>[]) =>
    api.post<{ success: boolean; ids: number[]; count: number }>(`${BASE}/event-bonuses/bulk`, { bonuses }),
  getBonus: (id: number) => api.get<EventBonus>(`${BASE}/event-bonuses/${id}`),
  updateBonus: (id: number, data: Partial<EventBonus>) =>
    api.put<{ success: boolean }>(`${BASE}/event-bonuses/${id}`, data),
  deleteBonus: (id: number) => api.delete<{ success: boolean }>(`${BASE}/event-bonuses/${id}`),
  bulkDeleteBonuses: (ids: number[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/event-bonuses/bulk-delete`, { ids }),
  bulkDeleteByEmployee: (employee_ids: number[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/event-bonuses/bulk-delete-by-employee`, { employee_ids }),
  bulkDeleteByEvent: (selections: { event_id?: number; year: number; month: number }[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/event-bonuses/bulk-delete-by-event`, { selections }),

  // Events
  getEvents: () => api.get<HrEvent[]>(`${BASE}/events`),
  createEvent: (data: Partial<HrEvent>) => api.post<{ success: boolean; id: number }>(`${BASE}/events`, data),
  getEvent: (id: number) => api.get<HrEvent>(`${BASE}/events/${id}`),
  updateEvent: (id: number, data: Partial<HrEvent>) => api.put<{ success: boolean }>(`${BASE}/events/${id}`, data),
  deleteEvent: (id: number) => api.delete<{ success: boolean }>(`${BASE}/events/${id}`),
  bulkDeleteEvents: (ids: number[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/events/bulk-delete`, { ids }),

  // Employees
  getEmployees: (activeOnly = true) =>
    api.get<HrEmployee[]>(`${BASE}/employees${activeOnly ? '?active_only=true' : ''}`),
  searchEmployees: (query: string) =>
    api.get<HrEmployee[]>(`${BASE}/employees/search?q=${encodeURIComponent(query)}`),
  createEmployee: (data: Partial<HrEmployee>) => api.post<{ success: boolean; id: number }>(`${BASE}/employees`, data),
  getEmployee: (id: number) => api.get<HrEmployee>(`${BASE}/employees/${id}`),
  updateEmployee: (id: number, data: Partial<HrEmployee>) =>
    api.put<{ success: boolean }>(`${BASE}/employees/${id}`, data),
  deleteEmployee: (id: number) => api.delete<{ success: boolean }>(`${BASE}/employees/${id}`),

  // Bonus Types
  getBonusTypes: (activeOnly = false) =>
    api.get<BonusType[]>(`${BASE}/bonus-types${activeOnly ? '?active_only=true' : ''}`),
  createBonusType: (data: Partial<BonusType>) => api.post<{ success: boolean; id: number }>(`${BASE}/bonus-types`, data),
  updateBonusType: (id: number, data: Partial<BonusType>) =>
    api.put<{ success: boolean }>(`${BASE}/bonus-types/${id}`, data),
  deleteBonusType: (id: number) => api.delete<{ success: boolean }>(`${BASE}/bonus-types/${id}`),

  // Permissions & Settings & Lock
  getPermissions: () => api.get<HrPermissions>(`${BASE}/permissions`),
  getSettings: async (): Promise<HrSettings> => {
    const res = await api.get<{ settings: HrSettings } | HrSettings>(`${BASE}/hr-settings`)
    return 'settings' in res ? res.settings : res
  },
  updateSettings: (data: HrSettings) => api.put<{ success: boolean }>(`${BASE}/hr-settings`, data),
  getLockStatus: (params?: { year?: number; month?: number }) =>
    api.get<LockStatus>(`${BASE}/lock-status${qs(params ?? {})}`),

  // Summary
  getSummary: (params?: { year?: number }) =>
    api.get<HrSummary>(`${BASE}/summary${qs(params ?? {})}`),
  getSummaryByEmployee: (params?: { year?: number; month?: number }) =>
    api.get<BonusSummaryByEmployee[]>(`${BASE}/summary/by-employee${qs(params ?? {})}`),
  getSummaryByEvent: (params?: { year?: number; month?: number }) =>
    api.get<BonusSummaryByEvent[]>(`${BASE}/summary/by-event${qs(params ?? {})}`),

  // Export
  exportUrl: (params?: { year?: number; month?: number }) => `${BASE}/export${qs(params ?? {})}`,

  // Structure - Companies
  getStructureCompanies: () => api.get<string[]>(`${BASE}/structure/companies`),
  getCompaniesFull: () => api.get<StructureCompany[]>(`${BASE}/structure/companies-full`),
  createCompany: (data: { company: string; vat?: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/structure/companies`, data),
  updateCompany: (id: number, data: { company: string; vat?: string }) =>
    api.put<{ success: boolean }>(`${BASE}/structure/companies/${id}`, data),
  deleteCompany: (id: number) => api.delete<{ success: boolean }>(`${BASE}/structure/companies/${id}`),

  // Structure - Company Brands
  getCompanyBrands: (companyId?: number) =>
    api.get<CompanyBrand[]>(`${BASE}/structure/company-brands${companyId ? `?company_id=${companyId}` : ''}`),
  createCompanyBrand: (data: { company_id: number; brand: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/structure/company-brands`, data),
  updateCompanyBrand: (id: number, data: { company_id?: number; brand: string; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/structure/company-brands/${id}`, data),
  deleteCompanyBrand: (id: number) => api.delete<{ success: boolean }>(`${BASE}/structure/company-brands/${id}`),

  // Structure - Brands for company
  getStructureBrands: (company: string) => api.get<string[]>(`${BASE}/structure/brands/${encodeURIComponent(company)}`),
  getStructureDepartments: (company: string) =>
    api.get<string[]>(`${BASE}/structure/departments/${encodeURIComponent(company)}`),

  // Structure - Departments full
  getDepartmentsFull: () => api.get<DepartmentStructure[]>(`${BASE}/structure/departments-full`),
  createDepartment: (data: Partial<DepartmentStructure>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/structure/departments`, data),
  updateDepartment: (id: number, data: Partial<DepartmentStructure>) =>
    api.put<{ success: boolean }>(`${BASE}/structure/departments/${id}`, data),
  deleteDepartment: (id: number) => api.delete<{ success: boolean }>(`${BASE}/structure/departments/${id}`),

  // Master data
  getMasterBrands: () => api.get<MasterItem[]>(`${BASE}/master/brands`),
  createMasterBrand: (data: { name: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/master/brands`, data),
  updateMasterBrand: (id: number, data: { name: string; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/master/brands/${id}`, data),
  deleteMasterBrand: (id: number) => api.delete<{ success: boolean }>(`${BASE}/master/brands/${id}`),

  getMasterDepartments: () => api.get<MasterItem[]>(`${BASE}/master/departments`),
  createMasterDepartment: (data: { name: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/master/departments`, data),
  updateMasterDepartment: (id: number, data: { name: string; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/master/departments/${id}`, data),
  deleteMasterDepartment: (id: number) => api.delete<{ success: boolean }>(`${BASE}/master/departments/${id}`),

  getMasterSubdepartments: () => api.get<MasterItem[]>(`${BASE}/master/subdepartments`),
  createMasterSubdepartment: (data: { name: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/master/subdepartments`, data),
  updateMasterSubdepartment: (id: number, data: { name: string; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/master/subdepartments/${id}`, data),
  deleteMasterSubdepartment: (id: number) => api.delete<{ success: boolean }>(`${BASE}/master/subdepartments/${id}`),

  // Organigram
  getOrganigram: () => api.get<OrganigramData>(`${BASE}/organigram`),
}
