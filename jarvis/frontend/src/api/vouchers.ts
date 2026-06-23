import { api } from './client'
import type { Voucher, VoucherCreatePayload, AccountingListResponse, ServiceCatalogItem } from '@/types/vouchers'

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

  pdfUrl: (id: number) => `/api/vouchers/${id}/pdf`,

  sendToClient: (id: number, email: string) =>
    api.post<{ success: boolean; message: string }>(`/api/vouchers/${id}/send`, { email }),

  getFormId: () => api.get<{ form_id: number }>('/api/vouchers/form-id'),

  exportUrl: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return `/api/vouchers/export${qs}`
  },

  getServiceCatalog: () =>
    api.get<ServiceCatalogItem[]>('/api/vouchers/service-catalog'),

  createService: (data: { name: string; price: number; currency: string; category?: string }) =>
    api.post<ServiceCatalogItem>('/api/vouchers/service-catalog', data),

  updateService: (id: number, data: { name: string; price: number; currency: string; category?: string }) =>
    api.put<ServiceCatalogItem>(`/api/vouchers/service-catalog/${id}`, data),

  deleteService: (id: number) =>
    api.delete<{ success: boolean }>(`/api/vouchers/service-catalog/${id}`),
}
