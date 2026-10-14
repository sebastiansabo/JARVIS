export const BUYBACK_STATUSES = [
  'PENDING_EVALUATION',
  'INITIAL_OFFER',
  'INSPECTION',
  'FINAL_OFFER',
  'BOUGHT',
  'LOST',
  'CANCELLED',
  'ON_HOLD',
] as const

export type BuybackStatus = (typeof BUYBACK_STATUSES)[number]

export interface BuybackRecord {
  id: number
  record_code: string
  company_id: number
  company_name: string | null
  status: BuybackStatus
  acquisition_type: string
  is_trade_in: boolean
  advisor_id: number | null
  advisor_name: string | null
  client_type: string | null
  vat_status: string | null
  client_id: number | null
  seller_name: string | null
  seller_cui: string | null
  seller_phone: string | null
  seller_email: string | null
  brand: string
  model: string
  variant: string | null
  equipment: string | null
  vin: string
  mileage_km: number | null
  engine_capacity_cm3: number | null
  fuel_type: string | null
  transmission: string | null
  gearbox: string | null
  manufacture_date: string | null
  first_registration_date: string | null
  service_history_uptodate: boolean | null
  extra_wheels: boolean | null
  keys_count: number | null
  has_damage: boolean | null
  damage_details: string | null
  general_condition: number | null
  client_asking_price_eur: number | null
  client_source: string | null
  other_details: string | null
  drive_folder_link: string | null
  target_vehicle_text: string | null
  target_carpark_vehicle_id: number | null
  crm_deal_id: number | null
  inspection_report_key: string | null
  inspection_rating: number | null
  reconditioning_cost_eur: number | null
  inspection_notes: string | null
  inspected_by: number | null
  inspected_at: string | null
  purchase_price_eur: number | null
  carpark_vehicle_id: number | null
  bought_at: string | null
  finalized_by: number | null
  lost_reason: string | null
  hold_prior_status: string | null
  hold_reason: string | null
  hold_note: string | null
  held_at: string | null
  held_by: number | null
  created_by: number | null
  created_at: string
  updated_at: string
  closed_at: string | null
}

export interface BuybackOffer {
  id: number
  record_id: number
  offer_type: 'initial' | 'final'
  amount_eur: number
  vat_status: string | null
  valid_until: string | null
  notes: string | null
  created_by: number | null
  created_at: string
  client_decision: 'pending' | 'accepted' | 'declined'
  decided_by: number | null
  decided_at: string | null
  decline_reason: string | null
}

export interface BuybackPhoto {
  id: number
  record_id: number
  url: string
  // Public Spaces CDN edge URL (buyback photos are public-read). Absent when
  // Spaces is not configured (e.g. local dev) → fall back to mediaUrl(url).
  cdn_url?: string | null
  thumbnail_url?: string | null
  sort_order: number
  is_primary: boolean
  photo_type: string | null
  caption: string | null
  file_size: number | null
  created_at: string
  // Document (CIV/talon PDF or other attached doc): photo_type !== 'gallery'.
  // Served privately, so instead of cdn_url it carries an authenticated
  // download_url + a human label. Absent/false for gallery images.
  is_document?: boolean
  download_url?: string
  label?: string
}

export interface BuybackEvent {
  id: number
  record_id: number
  action: string
  actor: number | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface BuybackOption {
  value: string
  label: string
}

export interface BuybackConfig {
  company_id: number
  enabled: boolean
  acquisition_emails: string // comma-separated
  channel_email: boolean
  channel_in_app: boolean
  channel_push: boolean
  notify_new_request: boolean
  notify_milestones: boolean
  notify_inspection: boolean
}

export interface ConsignmentAgreement {
  vehicle_id: number
  owner_price: number | null
  currency: string
  commission_type: 'percent' | 'fixed'
  commission_value: number
  min_sale_price: number | null
  contract_number: string | null
  agreement_date: string | null
  expiry_date: string | null
  created_by: number | null
  created_at: string
}

export interface CustodyAgreementInput {
  owner_price?: number | null
  currency?: string
  commission_type: 'percent' | 'fixed'
  commission_value: number
  min_sale_price?: number | null
  contract_number?: string | null
  agreement_date?: string | null
  expiry_date?: string | null
}
