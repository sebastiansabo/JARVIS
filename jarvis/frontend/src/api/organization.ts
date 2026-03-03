import { api } from './client'
import type { Company, CompanyWithBrands, Brand, Department, DepartmentStructure, StructureNode, StructureNodeMember } from '@/types/organization'

export const organizationApi = {
  // Company lookups
  getCompanies: () => api.get<string[]>('/api/companies'),
  getBrands: (company: string) => api.get<string[]>(`/api/brands/${encodeURIComponent(company)}`),
  getDepartments: (company: string) => api.get<string[]>(`/api/departments/${encodeURIComponent(company)}`),
  getSubdepartments: (company: string, department: string) =>
    api.get<string[]>(`/api/subdepartments/${encodeURIComponent(company)}/${encodeURIComponent(department)}`),
  getCompanyForDepartment: (department: string) =>
    api.get<{ company: string }>(`/api/company-for-department/${encodeURIComponent(department)}`),
  getManager: (params: { company?: string; department?: string; subdepartment?: string; brand?: string }) => {
    const searchParams = new URLSearchParams()
    if (params.company) searchParams.set('company', params.company)
    if (params.department) searchParams.set('department', params.department)
    if (params.subdepartment) searchParams.set('subdepartment', params.subdepartment)
    if (params.brand) searchParams.set('brand', params.brand)
    return api.get<{ manager: string }>(`/api/manager?${searchParams.toString()}`)
  },

  // Company VAT
  getCompaniesVat: () => api.get<Company[]>('/api/companies-vat'),
  addCompanyVat: (data: { company: string; vat: string }) => api.post<{ success: boolean }>('/api/companies-vat', data),
  updateCompanyVat: (company: string, data: { vat: string }) =>
    api.put<{ success: boolean }>(`/api/companies-vat/${encodeURIComponent(company)}`, data),
  deleteCompanyVat: (company: string) =>
    api.delete<{ success: boolean }>(`/api/companies-vat/${encodeURIComponent(company)}`),
  matchVat: (vat: string) => api.get<{ company: string | null }>(`/api/match-vat/${encodeURIComponent(vat)}`),

  // Company Configuration
  getCompaniesConfig: () => api.get<CompanyWithBrands[]>('/api/companies-config'),
  createCompanyConfig: (data: { company: string; vat?: string; parent_company_id?: number | null }) =>
    api.post<{ success: boolean; id: number }>('/api/companies-config', data),
  getCompanyConfig: (id: number) => api.get<CompanyWithBrands>(`/api/companies-config/${id}`),
  updateCompanyConfig: (id: number, data: Partial<Company> & { parent_company_id?: number | null }) =>
    api.put<{ success: boolean }>(`/api/companies-config/${id}`, data),
  deleteCompanyConfig: (id: number) => api.delete<{ success: boolean }>(`/api/companies-config/${id}`),

  // Company responsables
  getCompanyResponsables: (companyId: number) =>
    api.get<{ user_id: number; user_name: string }[]>(`/api/companies-config/${companyId}/responsables`),
  setCompanyResponsables: (companyId: number, userIds: number[]) =>
    api.put<{ success: boolean }>(`/api/companies-config/${companyId}/responsables`, { user_ids: userIds }),

  // Brands
  getAllBrands: () => api.get<Brand[]>('/api/brands-all'),
  createBrand: (name: string) => api.post<{ success: boolean; id: number }>('/api/brands-all', { name }),
  linkBrand: (companyId: number, brandId: number) =>
    api.post<{ success: boolean; id: number }>(`/api/companies-config/${companyId}/brands`, { brand_id: brandId }),
  unlinkBrand: (companyId: number, brandId: number) =>
    api.delete<{ success: boolean }>(`/api/companies-config/${companyId}/brands/${brandId}`),

  // Department Structures
  getDepartmentStructures: () => api.get<DepartmentStructure[]>('/api/department-structures'),
  createDepartmentStructure: (data: Partial<Department>) =>
    api.post<{ success: boolean; id: number }>('/api/department-structures', data),
  getDepartmentStructure: (id: number) => api.get<DepartmentStructure>(`/api/department-structures/${id}`),
  updateDepartmentStructure: (id: number, data: Partial<Department>) =>
    api.put<{ success: boolean }>(`/api/department-structures/${id}`, data),
  deleteDepartmentStructure: (id: number) => api.delete<{ success: boolean }>(`/api/department-structures/${id}`),

  // Structure data
  getStructure: () => api.get<DepartmentStructure[]>('/api/structure'),

  // Structure Nodes (generic tree)
  getStructureNodes: () => api.get<StructureNode[]>('/api/structure-nodes'),
  createStructureNode: (data: { company_id: number; parent_id?: number | null; name: string }) =>
    api.post<{ success: boolean; id: number }>('/api/structure-nodes', data),
  updateStructureNode: (id: number, data: { name?: string; has_team?: boolean }) =>
    api.put<{ success: boolean }>(`/api/structure-nodes/${id}`, data),
  deleteStructureNode: (id: number) =>
    api.delete<{ success: boolean }>(`/api/structure-nodes/${id}`),

  // Structure Node Members
  getNodeMembers: () => api.get<StructureNodeMember[]>('/api/structure-nodes/members'),
  addNodeMember: (nodeId: number, userId: number, role: 'responsable' | 'team') =>
    api.post<{ success: boolean; id: number }>(`/api/structure-nodes/${nodeId}/members`, { user_id: userId, role }),
  removeNodeMember: (nodeId: number, userId: number) =>
    api.delete<{ success: boolean }>(`/api/structure-nodes/${nodeId}/members/${userId}`),
  setNodeMembers: (nodeId: number, role: 'responsable' | 'team', userIds: number[]) =>
    api.post<{ success: boolean }>(`/api/structure-nodes/${nodeId}/members/set`, { role, user_ids: userIds }),
  getCascadeResponsables: (nodeId: number) =>
    api.get<number[]>(`/api/structure-nodes/${nodeId}/cascade-responsables`),
}
