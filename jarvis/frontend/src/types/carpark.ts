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

// ── Cost & Revenue types ──

export type CostType =
  | 'repair' | 'maintenance' | 'insurance' | 'registration' | 'transport'
  | 'inspection' | 'cleaning' | 'fuel' | 'parking' | 'tax' | 'other'

export type RevenueType =
  | 'sale' | 'rental' | 'lease' | 'commission' | 'refund' | 'other'

export interface VehicleCost {
  id: number
  vehicle_id: number
  cost_type: CostType
  description: string | null
  amount: number
  currency: string
  vat_rate: number
  vat_amount: number
  exchange_rate_eur: number | null
  invoice_number: string | null
  invoice_date: string | null
  invoice_value: number | null
  invoice_id: number | null
  supplier_name: string | null
  radio_cost_type: string | null
  document_file: string | null
  observation: string | null
  date: string
  created_by: number | null
  created_at: string
}

export interface VehicleRevenue {
  id: number
  vehicle_id: number
  revenue_type: RevenueType
  description: string | null
  amount: number
  currency: string
  vat_amount: number
  invoice_number: string | null
  invoice_id: number | null
  client_name: string | null
  date: string
  created_by: number | null
  created_at: string
}

export interface CostTotals {
  by_type: { cost_type: string; count: number; total_amount: number; total_vat: number }[]
  total_amount: number
  total_vat: number
  total_with_vat: number
}

export interface RevenueTotals {
  by_type: { revenue_type: string; count: number; total_amount: number; total_vat: number }[]
  total_amount: number
  total_vat: number
  total_with_vat: number
}

export interface Profitability {
  acquisition_price: number
  total_costs: number
  total_revenues: number
  total_invested: number
  profit: number
  costs_breakdown: { cost_type: string; count: number; total_amount: number; total_vat: number }[]
  revenues_breakdown: { revenue_type: string; count: number; total_amount: number; total_vat: number }[]
}

export const COST_TYPE_LABELS: Record<CostType, string> = {
  repair: 'Reparație',
  maintenance: 'Mentenanță',
  insurance: 'Asigurare',
  registration: 'Înmatriculare',
  transport: 'Transport',
  inspection: 'Inspecție',
  cleaning: 'Curățenie',
  fuel: 'Combustibil',
  parking: 'Parcare',
  tax: 'Taxe',
  other: 'Altele',
}

export const REVENUE_TYPE_LABELS: Record<RevenueType, string> = {
  sale: 'Vânzare',
  rental: 'Închiriere',
  lease: 'Leasing',
  commission: 'Comision',
  refund: 'Ramburs',
  other: 'Altele',
}

// ── Pricing types ──

export type PricingActionType = 'reduce_percent' | 'reduce_amount' | 'set_price' | 'alert_only'
export type PricingFloorType = 'minimum_price' | 'cost_plus_margin' | 'purchase_recovery'
export type PromotionTargetType = 'all' | 'category' | 'brand' | 'specific'
export type PromotionType = 'discount' | 'special_financing' | 'gift' | 'bundle'
export type DiscountType = 'percent' | 'fixed'

export interface PricingRule {
  id: number
  name: string
  description: string | null
  is_active: boolean
  priority: number
  condition_category: string[] | null
  condition_brand: string[] | null
  condition_min_days: number | null
  condition_max_days: number | null
  condition_min_price: number | null
  condition_max_price: number | null
  action_type: PricingActionType
  action_value: number | null
  action_floor_type: PricingFloorType | null
  action_floor_value: number | null
  frequency: string
  last_executed: string | null
  company_id: number | null
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface PricingHistoryEntry {
  id: number
  vehicle_id: number
  old_price: number | null
  new_price: number | null
  change_reason: string | null
  rule_id: number | null
  rule_name: string | null
  changed_by: number | null
  created_at: string
}

export interface Promotion {
  id: number
  name: string
  description: string | null
  target_type: PromotionTargetType
  target_categories: string[] | null
  target_brands: string[] | null
  target_vehicle_ids: number[] | null
  promo_type: PromotionType
  discount_type: DiscountType | null
  discount_value: number | null
  special_financing_rate: number | null
  gift_description: string | null
  start_date: string
  end_date: string
  is_active: boolean
  budget: number | null
  spent: number | null
  vehicles_sold: number | null
  push_to_platforms: boolean
  platform_badge: string | null
  company_id: number | null
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface FloorPrice {
  floor_price: number
  components: {
    minimum_price: number
    cost_plus_margin: number
    purchase_recovery: number
    total_cost: number
    acquisition_price: number
    min_margin_percent: number
  }
  binding_constraint: 'minimum_price' | 'cost_plus_margin' | 'purchase_recovery'
}

export interface SimulationResult {
  rule_id: number
  rule_name: string
  vehicle_id: number
  vin: string
  brand?: string
  model?: string
  action: string
  current_price: number
  suggested_price: number
  reduction: number
  reduction_percent?: number
  floor_price: number
  floor_hit: boolean
}

export interface RuleExecutionResult {
  rule_id: number
  rule_name: string
  dry_run: boolean
  total_matched: number
  applied_count: number
  pending_approval_count: number
  skipped_count: number
  alert_count: number
  applied: Array<{
    vehicle_id: number
    vin: string
    brand: string
    model: string
    old_price: number
    new_price: number
    reduction: number
    floor_hit: boolean
    needs_approval: boolean
    applied: boolean
  }>
  alerts: Array<{
    vehicle_id: number
    vin: string
    brand: string
    model: string
    days_listed: number
    current_price: number
  }>
}

export interface AgingVehicle {
  vehicle_id: number
  vin: string
  brand: string
  model: string
  status: string
  days_listed: number
  current_price: number
  list_price: number
  category: string
  severity: 'critical' | 'warning' | 'info'
}

export const ACTION_TYPE_LABELS: Record<PricingActionType, string> = {
  reduce_percent: 'Reducere %',
  reduce_amount: 'Reducere sumă',
  set_price: 'Setare preț',
  alert_only: 'Doar alertă',
}

export const PROMO_TYPE_LABELS: Record<PromotionType, string> = {
  discount: 'Discount',
  special_financing: 'Finanțare specială',
  gift: 'Cadou',
  bundle: 'Pachet',
}

export const TARGET_TYPE_LABELS: Record<PromotionTargetType, string> = {
  all: 'Toate vehiculele',
  category: 'După categorie',
  brand: 'După marcă',
  specific: 'Vehicule specifice',
}

// ── Publishing types ──

export type ListingStatus = 'draft' | 'active' | 'inactive' | 'expired' | 'error'
export type PlatformType = 'autovit' | 'website' | 'marketplace' | 'custom'

export interface PublishingPlatform {
  id: number
  name: string
  platform_type: PlatformType | null
  brand_scope: string | null
  api_base_url: string | null
  api_key_encrypted: string | null
  dealer_account_id: string | null
  website_url: string | null
  icon_url: string | null
  is_active: boolean
  company_id: number | null
  config: Record<string, unknown>
  created_at: string
  active_listings?: number
}

export interface VehicleListing {
  id: number
  vehicle_id: number
  platform_id: number
  platform_name?: string
  platform_type?: string
  icon_url?: string | null
  external_listing_id: string | null
  status: ListingStatus
  published_at: string | null
  expires_at: string | null
  external_url: string | null
  views: number
  inquiries: number
  last_sync: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface SyncLogEntry {
  id: number
  vehicle_id: number
  platform_id: number
  platform_name?: string
  action: string
  success: boolean
  http_status: number | null
  error_message: string | null
  created_at: string
}

export const LISTING_STATUS_LABELS: Record<ListingStatus, string> = {
  draft: 'Ciornă',
  active: 'Activ',
  inactive: 'Inactiv',
  expired: 'Expirat',
  error: 'Eroare',
}

export const PLATFORM_TYPE_LABELS: Record<PlatformType, string> = {
  autovit: 'Autovit.ro',
  website: 'Website',
  marketplace: 'Marketplace',
  custom: 'Personalizat',
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

// ── Analytics / Dashboard types ─────────────────────────────

export interface InventorySummary {
  total_vehicles: number
  in_stock: number
  sold_delivered: number
  ready_for_sale: number
  listed: number
  reserved: number
  in_preparation: number
  total_stock_value: number
  total_acquisition_value: number
}

export interface DashboardKpis {
  avg_days_on_lot: number
  aged_count: number
  aged_percent: number
  current_stock: number
  sold_last_30d: number
  sold_last_365d: number
  inventory_turn_rate: number
  stocking_efficiency: number
  groi: number
}

export interface AgingBucket {
  bucket: string
  count: number
  total_value: number
}

export interface ProfitabilityOverview {
  vehicles_sold: number
  total_revenue: number
  total_acquisition: number
  total_costs: number
  total_gross_profit: number
  avg_margin_percent: number
  avg_profit_per_unit: number
  avg_days_to_sell: number
}

export interface BrandBreakdown {
  brand: string
  count: number
  total_value: number
  avg_days: number
}

export interface MonthlySales {
  month: string
  sold: number
  revenue: number
  gross_profit: number
}

export interface PublishingStats {
  vehicles_published: number
  total_listings: number
  total_views: number
  total_inquiries: number
  inquiry_rate: number
}

export interface CostOverviewItem {
  cost_type: string
  entries: number
  vehicles: number
  total_amount: number
}

export interface RecentActivity {
  id: number
  vehicle_id: number
  old_status: string | null
  new_status: string
  changed_at: string
  notes: string | null
  brand: string
  model: string
  vin: string
}

export interface DashboardData {
  summary: InventorySummary
  kpis: DashboardKpis
  aging_distribution: AgingBucket[]
  profitability: ProfitabilityOverview
  brand_breakdown: BrandBreakdown[]
  monthly_sales: MonthlySales[]
  publishing: PublishingStats
  cost_overview: CostOverviewItem[]
  recent_activity: RecentActivity[]
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
