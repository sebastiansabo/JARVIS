import { api } from './client'
import { buildQs } from './utils'
import type { CostCenter, CostCenterCompany, StructureNodeOption } from '@/types/costCenters'

// The shared `api` client (api/client.ts) returns the parsed response body as-is —
// it does NOT unwrap the backend's {success, data} envelope. So every generic here
// mirrors the real envelope shape; callers read `.data` themselves (see
// pages/Accounting/Controlling/index.tsx's `periodsData?.periods` for the same pattern).
export const costCentersApi = {
  companies: () =>
    api.get<{ success: boolean; data: CostCenterCompany[] }>('/api/cost-centers/companies'),

  list: (companyId: number) =>
    api.get<{ success: boolean; data: CostCenter[] }>(`/api/cost-centers${buildQs({ company_id: companyId })}`),

  structureNodes: (companyId: number) =>
    api.get<{ success: boolean; data: StructureNodeOption[] }>(
      `/api/cost-centers/structure-nodes${buildQs({ company_id: companyId })}`,
    ),

  create: (payload: { company_id: number; code: string; name: string }) =>
    api.post<{ success: boolean; data: { id: number } }>('/api/cost-centers', payload),

  update: (id: number, payload: { code?: string; name?: string; active?: boolean }) =>
    api.patch<{ success: boolean }>(`/api/cost-centers/${id}`, payload),

  remove: (id: number) =>
    api.delete<{ success: boolean }>(`/api/cost-centers/${id}`),

  setMap: (id: number, structureNodeId: number | null) =>
    api.put<{ success: boolean }>(`/api/cost-centers/${id}/map`, { structure_node_id: structureNodeId }),

  seedMapExact: (companyId: number) =>
    api.post<{ success: boolean; data: { inserted: number } }>(
      '/api/cost-centers/seed-map-exact',
      { company_id: companyId },
    ),
}
