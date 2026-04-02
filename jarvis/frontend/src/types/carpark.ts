// CarPark module TypeScript types

export type VehicleCategory = 'NEW' | 'ORD' | 'SH' | 'TD' | 'CUS' | 'SHR' | 'DSP' | 'CON' | 'TI'

export type VehicleStatus =
  | 'ACQUIRED' | 'INSPECTION' | 'RECONDITIONING' | 'READY_FOR_SALE'
  | 'LISTED' | 'RESERVED' | 'SOLD' | 'DELIVERED'
  | 'PRICE_REDUCED' | 'AUCTION_CANDIDATE'
  | 'IN_TRANSIT' | 'AT_BODYSHOP' | 'INSURANCE_CLAIM'
  | 'RETURNED' | 'SCRAPPED' | 'TRANSFERRED'

export interface VehicleCatalogItem {
  id: number
  vin: string
  nr_stoc: string | null
  brand: string
  model: string
  variant: string | null
  category: VehicleCategory
  status: VehicleStatus
  year_of_manufacture: number | null
  fuel_type: string | null
  transmission: string | null
  body_type: string | null
  mileage_km: number
  engine_power_hp: number | null
  color_exterior: string | null
  current_price: number | null
  list_price: number | null
  promotional_price: number | null
  price_currency: string
  acquisition_date: string
  arrival_date: string | null
  is_consignment: boolean
  is_test_drive: boolean
  total_cost: number | null
  location_text: string | null
  company_id: number | null
  days_listed: number
  stationary_days: number
  primary_photo_url: string | null
  photo_count: number
}

export interface Vehicle extends VehicleCatalogItem {
  identification_number: string | null
  registration_number: string | null
  chassis_code: string | null
  emission_code: string | null
  vehicle_type: string | null
  state: string | null
  generation: string | null
  equipment_level: string | null
  first_registration_date: string | null
  color_code: string | null
  color_interior: string | null
  interior_code: string | null
  drive_type: string | null
  engine_displacement_cc: number | null
  engine_power_kw: number | null
  engine_power_electric_hp: number | null
  engine_torque_nm: number | null
  co2_emissions: number | null
  euro_standard: string | null
  max_weight_kg: number | null
  doors: number | null
  seats: number | null
  tire_type: string | null
  fuel_consumption: string | null
  equipment: Record<string, string[]>
  optional_packages: string[]
  has_manufacturer_warranty: boolean
  manufacturer_warranty_date: string | null
  has_dealer_warranty: boolean
  dealer_warranty_months: number | null
  is_registered: boolean
  is_first_owner: boolean
  has_accident_history: boolean
  has_service_book: boolean
  is_electric_vehicle: boolean
  has_tuning: boolean
  youtube_url: string | null
  listing_title: string | null
  listing_description: string | null
  location_id: number | null
  location_name: string | null
  location_code: string | null
  parking_spot: string | null
  source: string | null
  supplier_name: string | null
  supplier_cif: string | null
  purchase_contract_number: string | null
  purchase_contract_date: string | null
  owner_name: string | null
  acquisition_manager_id: number | null
  acquisition_document_number: string | null
  acquisition_value: number | null
  acquisition_vat: number | null
  acquisition_price: number | null
  acquisition_currency: string
  acquisition_exchange_rate: number | null
  purchase_price_net: number | null
  purchase_price_currency: string
  purchase_vat_rate: number | null
  reconditioning_cost: number | null
  transport_cost: number | null
  registration_cost: number | null
  other_costs: number | null
  minimum_price: number | null
  price_includes_vat: boolean
  vat_deductible: boolean
  is_negotiable: boolean
  margin_scheme: boolean
  eligible_for_financing: boolean
  available_for_leasing: boolean
  can_issue_invoice: boolean
  promotion_id: number | null
  service_exchange_vehicle: boolean
  sale_price: number | null
  sale_date: string | null
  buyer_client_id: number | null
  salesperson_user_id: number | null
  ready_for_sale_date: string | null
  listing_date: string | null
  reservation_date: string | null
  delivery_date: string | null
  notes: string | null
  internal_notes: string | null
  created_by: number | null
  updated_by: number | null
  brand_id: number | null
  created_at: string
  updated_at: string
  photos: VehiclePhoto[]
  photo_count: number
}

export interface VehiclePhoto {
  id: number
  vehicle_id: number
  url: string
  thumbnail_url: string | null
  sort_order: number
  is_primary: boolean
  photo_type: 'gallery' | 'interior_360' | 'exterior_360'
  caption: string | null
  file_size: number | null
  created_at: string
}

export interface Location {
  id: number
  name: string
  code: string
  address: string | null
  city: string | null
  type: string | null
  capacity: number
  company_id: number | null
  is_active: boolean
  created_at: string
}

export interface StatusCount {
  status: VehicleStatus
  count: number
}

export interface FilterOptions {
  brands: string[]
  fuel_types: string[]
  body_types: string[]
}

export interface CatalogFilters {
  status?: string
  category?: string
  brand?: string
  model?: string
  fuel_type?: string
  body_type?: string
  year_min?: string
  year_max?: string
  price_min?: string
  price_max?: string
  km_min?: string
  km_max?: string
  company_id?: string
  location_id?: string
  search?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

export interface StatusHistoryEntry {
  id: number
  vehicle_id: number
  old_status: string | null
  new_status: string
  notes: string | null
  changed_by: number | null
  changed_by_name: string | null
  created_at: string
}

export interface ModificationEntry {
  id: number
  vehicle_id: number
  field_name: string
  old_value: string | null
  new_value: string | null
  changed_by: number | null
  user_name: string | null
  created_at: string
}

// Status display config
export const STATUS_LABELS: Record<VehicleStatus, string> = {
  ACQUIRED: 'Achiziționat',
  INSPECTION: 'Inspecție',
  RECONDITIONING: 'Recondiționare',
  READY_FOR_SALE: 'Pregătit vânzare',
  LISTED: 'Listat',
  RESERVED: 'Rezervat',
  SOLD: 'Vândut',
  DELIVERED: 'Livrat',
  PRICE_REDUCED: 'Preț redus',
  AUCTION_CANDIDATE: 'Candidat licitație',
  IN_TRANSIT: 'În tranzit',
  AT_BODYSHOP: 'La caroserie',
  INSURANCE_CLAIM: 'Daună asigurare',
  RETURNED: 'Returnat',
  SCRAPPED: 'Casat',
  TRANSFERRED: 'Transferat',
}

export const CATEGORY_LABELS: Record<VehicleCategory, string> = {
  NEW: 'Nou',
  ORD: 'Comandă',
  SH: 'Second Hand',
  TD: 'Test Drive',
  CUS: 'Custodie',
  SHR: 'Showroom',
  DSP: 'Display Show',
  CON: 'Consemnație',
  TI: 'Trade-In',
}

// Catalog tab order
export const CATALOG_TABS = [
  { key: '', label: 'Toate' },
  { key: 'ACQUIRED', label: 'Active' },
  { key: 'RESERVED', label: 'Rezervate' },
  { key: 'LISTED', label: 'Listate' },
  { key: 'SOLD', label: 'Vândute' },
  { key: 'DELIVERED', label: 'Livrate' },
] as const
