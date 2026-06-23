export interface Voucher {
  id: number
  company_id: number
  voucher_code: string
  client_name: string
  contract_number: string
  car_vin: string
  validity_months: number
  expires_at: string | null
  issued_at: string | null
  issued_by_user_id: number
  issued_by_name: string | null
  voucher_type: 'value' | 'accessory_discount_code' | 'accessory_percentage' | 'service_items'
  value_lei: number | null
  discount_code: string | null
  discount_percentage: number | null
  service_items: string[] | null
  status: 'draft' | 'pending_approval' | 'approved' | 'active' | 'rejected' | 'redeemed' | 'expired'
  approver_user_id: number | null
  approver_name: string | null
  approval_request_id: number | null
  redeemed_at: string | null
  redeemed_by_user_id: number | null
  redeemed_by_name: string | null
  redemption_notes: string | null
  notes: string | null
  days_remaining: number | null
  benefit_display: string
  created_at: string
  updated_at: string
}

export interface VoucherCreatePayload {
  client_name: string
  contract_number: string
  car_vin: string
  validity_months: number
  voucher_type: string
  value_lei?: number | null
  discount_code?: string | null
  discount_percentage?: number | null
  service_items?: string[] | null
  approver_user_id?: number | null
  notes?: string | null
}

export interface VoucherSummary {
  active_count: number
  expiring_soon_count: number
  redeemed_this_month: number
  expired_count: number
  total_active_value: number
}

export interface AccountingListResponse {
  vouchers: Voucher[]
  summary: VoucherSummary
}

export interface ServiceCatalogItem {
  id: number
  name: string
  price: number
  currency: string
  category: string | null
  is_active: boolean
}
