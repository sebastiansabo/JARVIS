import { api } from './client'
import type { Voucher, VoucherCreatePayload, AccountingListResponse, ServiceCatalogItem, ServiceCatalogCompanyItem, ServicePricing } from '@/types/vouchers'

export const vouchersApi = {
  create: (data: VoucherCreatePayload) =>
    api.post<{ success: boolean; voucher: { id: number; voucher_code: string; status: string; approver_name: string } }>('/api/vouchers', data),

  list: (params?: Record<string, string>) =>
    api.get<Voucher[]>('/api/vouchers', params),

  getById: (id: number) =>
    api.get<Voucher>(`/api/vouchers/${id}`),

  myVouchers: (params?: Record<string, string>) =>
    api.get<Voucher[]>('/api/vouchers/my', params),

  accountingList: (params?: Record<string, string>) =>
    api.get<AccountingListResponse>('/api/vouchers/accounting', params),

  redeem: (id: number, notes?: string) =>
    api.patch<{ success: boolean; voucher: Voucher }>(`/api/vouchers/${id}/redeem`, { redemption_notes: notes }),

  editVoucher: (id: number, data: { client_name?: string; contract_number?: string; car_vin?: string; notes?: string }) =>
    api.patch<{ success: boolean; voucher: Voucher }>(`/api/vouchers/${id}/edit`, data),

  reissueVoucher: (id: number) =>
    api.post<{ success: boolean; voucher: Voucher }>(`/api/vouchers/${id}/reissue`),

  deleteVoucher: (id: number) =>
    api.delete<{ success: boolean }>(`/api/vouchers/${id}`),

  pdfUrl: (id: number) => `/api/vouchers/${id}/pdf`,

  sendToClient: (id: number, email: string) =>
    api.post<{ success: boolean; message: string }>(`/api/vouchers/${id}/send`, { email }),

  getFormId: () => api.get<{ form_id: number }>('/api/vouchers/form-id'),

  getFormSchema: () => api.get<{ id: number; slug: string; schema: import('@/types/forms').FormField[]; published_schema?: import('@/types/forms').FormField[] }>('/api/vouchers/form-schema'),

  exportUrl: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return `/api/vouchers/export${qs}`
  },

  // Master service catalog (all services + all company pricing)
  getServiceCatalog: () =>
    api.get<ServiceCatalogItem[]>('/api/vouchers/service-catalog'),

  // Company-filtered flat list (for voucher form)
  getServiceCatalogCompany: () =>
    api.get<ServiceCatalogCompanyItem[]>('/api/vouchers/service-catalog/company'),

  // Master service CRUD
  createService: (data: { name: string; category?: string; sort_order?: number }) =>
    api.post<{ success: boolean; item: ServiceCatalogItem }>('/api/vouchers/service-catalog', data),

  updateService: (id: number, data: { name?: string; category?: string; sort_order?: number; is_active?: boolean }) =>
    api.put<{ success: boolean; item: ServiceCatalogItem }>(`/api/vouchers/service-catalog/${id}`, data),

  deleteService: (id: number) =>
    api.delete<{ success: boolean }>(`/api/vouchers/service-catalog/${id}`),

  // Pricing CRUD
  createPricing: (serviceId: number, data: { company_id: number; department?: string; service_code?: string; price: number; currency?: string }) =>
    api.post<{ success: boolean; item: ServicePricing }>(`/api/vouchers/service-catalog/${serviceId}/pricing`, data),

  updatePricing: (pricingId: number, data: { department?: string; service_code?: string; price?: number; currency?: string; is_active?: boolean }) =>
    api.put<{ success: boolean; item: ServicePricing }>(`/api/vouchers/service-catalog/pricing/${pricingId}`, data),

  deletePricing: (pricingId: number) =>
    api.delete<{ success: boolean }>(`/api/vouchers/service-catalog/pricing/${pricingId}`),
}
