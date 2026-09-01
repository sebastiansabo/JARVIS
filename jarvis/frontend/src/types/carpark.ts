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
  manufacture_date: string | null
  fuel_type: string | null
  fuel_tank_capacity_liters: number | null
  battery_capacity_kwh: number | null
  norma_combustibil: number | null
  norma_energie: number | null
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
  payload_kg: number | null
  cargo_volume_m3: number | null
  cargo_length_mm: number | null
  cargo_width_mm: number | null
  cargo_height_mm: number | null
  euro_pallets: number | null
  interior_material: string | null
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
  sale_type: SaleType | null
  buyer_name: string | null
  buyer_client_id: number | null
  salesperson_user_id: number | null
  ready_for_sale_date: string | null
  gw_file_number: string | null
  is_impus: boolean
  missing_civ: boolean
  stock_removed: boolean
  stock_removed_date: string | null
  listing_date: string | null
  reservation_date: string | null
  delivery_date: string | null
  // Real carpark_vehicles column (in VEHICLE_UPDATABLE_FIELDS server-side,
  // already typed on DispoRow) that was never added here — needed so
  // AttachDocumentDialog's factura_achizitie → Data plată wiring can PUT it
  // through carparkApi.updateVehicle's Partial<Vehicle> body.
  supplier_payment_date: string | null
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

export interface VehicleCostLine {
  id: number
  vehicle_id: number
  cost_type: CostType
  description: string | null
  planned_amount: number
  spent_amount: number
  currency: string
  notes: string | null
  created_by: number | null
  created_at: string
  updated_at: string | null
  computed_spent?: number
  cost_count?: number
}

export interface VehicleCost {
  id: number
  vehicle_id: number
  cost_line_id: number | null
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
  invoice_number_ref?: string | null
  invoice_supplier_ref?: string | null
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

export type TargetMode = 'criteria' | 'manual' | 'both'
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
  project_id: number | null
  project_name: string | null
  target_mode: TargetMode
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
  approval_request_id: number | null
}

export interface PendingPriceChange {
  id: number
  rule_id: number
  vehicle_id: number
  old_price: number
  new_price: number
  reduction: number
  floor_hit: boolean
  status: 'pending' | 'approved' | 'rejected'
  approval_request_id: number | null
  applied_at: string | null
  applied_by: number | null
  created_by: number
  created_at: string
  vin: string
  brand: string
  model: string
}

export interface RuleVehicle {
  id: number
  rule_id: number
  vehicle_id: number
  added_by: number
  added_by_name: string | null
  created_at: string
  vin: string
  brand: string
  model: string
  current_price: number | null
  status: string
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

// Mirrors carpark/services/vehicle_service.py's TRANSITIONS dict exactly
// (the single source of truth behind is_valid_transition, enforced
// server-side on PUT /vehicles/<id>/status — this copy is UI-only, used to
// decide which targets are worth offering, never to bypass the server
// check). Keep in sync if TRANSITIONS changes.
export const STATUS_TRANSITIONS: Record<VehicleStatus, VehicleStatus[]> = {
  ACQUIRED: ['IN_TRANSIT', 'INSPECTION', 'READY_FOR_SALE', 'RETURNED', 'TRANSFERRED'],
  IN_TRANSIT: ['INSPECTION', 'ACQUIRED'],
  INSPECTION: ['RECONDITIONING', 'READY_FOR_SALE', 'AT_BODYSHOP', 'INSURANCE_CLAIM'],
  RECONDITIONING: ['READY_FOR_SALE', 'AT_BODYSHOP', 'INSPECTION'],
  AT_BODYSHOP: ['RECONDITIONING', 'READY_FOR_SALE', 'INSURANCE_CLAIM'],
  INSURANCE_CLAIM: ['RECONDITIONING', 'READY_FOR_SALE', 'SCRAPPED'],
  READY_FOR_SALE: ['LISTED', 'RESERVED', 'SOLD', 'TRANSFERRED', 'RECONDITIONING'],
  LISTED: ['PRICE_REDUCED', 'AUCTION_CANDIDATE', 'RESERVED', 'SOLD', 'READY_FOR_SALE'],
  PRICE_REDUCED: ['AUCTION_CANDIDATE', 'RESERVED', 'SOLD', 'LISTED'],
  AUCTION_CANDIDATE: ['RESERVED', 'SOLD', 'LISTED', 'TRANSFERRED'],
  RESERVED: ['SOLD', 'LISTED', 'READY_FOR_SALE'],
  SOLD: ['DELIVERED', 'RESERVED', 'LISTED'],
  DELIVERED: ['RETURNED'],
  RETURNED: ['INSPECTION', 'READY_FOR_SALE'],
  SCRAPPED: [],
  TRANSFERRED: [],
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

// ── Vehicle Links ──

export type LinkedEntityType = 'invoice' | 'dms_document' | 'dms_folder' | 'project' | 'hr_event' | 'crm_deal' | 'crm_client'

export interface VehicleLink {
  id: number
  vehicle_id: number
  linked_entity_type: LinkedEntityType
  linked_entity_id: number
  notes: string | null
  linked_by: number
  linked_by_name: string | null
  created_at: string
  entity_label: string
  entity_sublabel: string | null
}

export interface LinkSearchResult {
  id: number
  label: string
  sublabel: string | null
}

export const ENTITY_TYPE_LABELS: Record<LinkedEntityType, string> = {
  invoice: 'Facturi',
  dms_document: 'Documente',
  dms_folder: 'Dosare',
  project: 'Proiecte',
  hr_event: 'Evenimente HR',
  crm_deal: 'Dealuri CRM',
  crm_client: 'Clienti CRM',
}

// ── Promotion Vehicles ──

export interface PromotionVehicle {
  id: number
  promotion_id: number
  vehicle_id: number
  added_by: number
  added_by_name: string | null
  created_at: string
  vin: string
  brand: string
  model: string
  current_price: number | null
  status: string
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

// ── VIN Decoder Types ────────────────────────────────────

export interface VINDecodedSpecs {
  vin: string
  brand: string
  model: string
  variant: string
  generation: string
  model_year: number
  manufacture_year: number
  body_type: string
  doors: number
  seats: number
  fuel_type: string
  engine_displacement_cc: number
  engine_power_hp: number
  engine_power_kw: number
  engine_code: string
  cylinders: number
  transmission: string
  transmission_detail: string
  drive_type: string
  gears: number
  length_mm: number
  width_mm: number
  height_mm: number
  wheelbase_mm: number
  curb_weight_kg: number
  gross_weight_kg: number
  max_speed_kmh: number
  co2_emissions: number
  euro_standard: string
  battery_capacity_kwh: number
  manufacturer: string
  plant_country: string
  plant_city: string
  confidence_score: number
  fields_decoded: number
  fields_total: number
  decoded_at: string
  provider: string
}

export interface VINDecodeResult {
  specs: VINDecodedSpecs
  vehicle_fields: Partial<Vehicle>
  provider: string
  confidence: number
}

export interface VINValidation {
  valid: boolean
  vin: string
  wmi: string
  vds: string
  vis: string
  check_digit_valid: boolean
  errors: string[]
}

export interface VINProviderStatus {
  name: string
  available: boolean
  remaining_quota: number | null
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

// ═══════════════════════════════════════════════
// DISPO — pipeline dashboard (see carpark/routes/dispo.py,
// carpark/repositories/dispo_repository.py, carpark/services/dispo_service.py)
// ═══════════════════════════════════════════════

// Pipeline stage tabs, mirroring DispoRepository.STAGE_STATUS_MAP exactly
// (every VehicleStatus appears in exactly one stage's `statuses`, plus the
// '' (TOATE) pseudo-stage which means "no stage filter").
export const DISPO_STAGES = [
  { key: '', label: 'Toate', statuses: [] },
  { key: 'in_pregatire', label: 'În pregătire', statuses: ['ACQUIRED', 'IN_TRANSIT', 'INSPECTION', 'RECONDITIONING', 'AT_BODYSHOP'] },
  { key: 'in_stoc', label: 'Pregătit Vânzare', statuses: ['READY_FOR_SALE'] },
  { key: 'promovat', label: 'Promovat', statuses: ['LISTED', 'PRICE_REDUCED', 'AUCTION_CANDIDATE'] },
  { key: 'rezervat', label: 'Rezervat', statuses: ['RESERVED'] },
  { key: 'vandut', label: 'Vândut', statuses: ['SOLD'] },
  { key: 'livrat', label: 'Livrat', statuses: ['DELIVERED'] },
  { key: 'iesit', label: 'Ieșit', statuses: ['RETURNED', 'SCRAPPED', 'TRANSFERRED', 'INSURANCE_CLAIM'] },
] as const satisfies { key: string; label: string; statuses: VehicleStatus[] }[]

export type DispoStageKey = (typeof DISPO_STAGES)[number]['key']

// Sale financing/payment type recorded on a sold vehicle (carpark_vehicles.
// sale_type is a free VARCHAR(30) — the literals below are the values in
// use today; `string & {}` keeps free-text values assignable without
// widening the type to a bare `string` (which would drop autocomplete).
export type SaleType =
  | 'PLR' | 'CASH' | 'CREDIT PLR' | 'BT LEASING' | 'BRD' | 'BCR' | 'AW NEXT'
  | (string & {})

// Document types a vehicle document may be tagged with (matches
// documents.py's VALID_DOCUMENT_TYPES exactly).
export type DocumentType =
  | 'pv_intrare' | 'contract_achizitie' | 'civ' | 'talon' | 'factura_achizitie'
  | 'contract_vanzare' | 'factura_vanzare' | 'pv_livrare' | 'dosar_gw'
  | 'asigurare' | 'itp' | 'mandat' | 'altele' | 'factura_transfer'

export const DOCUMENT_TYPES: DocumentType[] = [
  'pv_intrare', 'contract_achizitie', 'civ', 'talon', 'factura_achizitie',
  'contract_vanzare', 'factura_vanzare', 'pv_livrare', 'dosar_gw',
  'asigurare', 'itp', 'mandat', 'altele', 'factura_transfer',
]

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  pv_intrare: 'PV intrare',
  contract_achizitie: 'Contract achiziție',
  civ: 'CIV',
  talon: 'Talon',
  factura_achizitie: 'Factură achiziție',
  contract_vanzare: 'Contract vânzare',
  factura_vanzare: 'Factură vânzare',
  pv_livrare: 'PV livrare',
  dosar_gw: 'Dosar GW',
  asigurare: 'Asigurare',
  itp: 'ITP',
  mandat: 'Mandat',
  altele: 'Altele',
  factura_transfer: 'Factură transfer',
}

// One row of GET /dispo/summary's `rows` (DispoRepository.summary — v.*
// plus computed cost/reservation/doc-type columns). The five money fields
// are optional: dispo.py's _strip_finance() pops them from every row for
// callers without can_view_carpark_finance, so they're simply absent from
// the JSON rather than null.
export interface DispoRow {
  id: number
  vin: string
  nr_stoc: string | null
  brand: string
  model: string
  variant: string | null
  status: VehicleStatus
  source: string | null
  location_text: string | null
  sale_type: SaleType | null
  salesperson_user_id: number | null
  acquisition_manager_id: number | null
  acquisition_date: string | null
  listing_date: string | null
  sale_date: string | null
  delivery_date: string | null
  supplier_payment_date: string | null
  stock_removed_date: string | null
  days_in_stock: number
  current_price: number | null
  // Not finance-gated (absent from dispo.py's _FINANCE_ROW_FIELDS) — v.*
  // selects every carpark_vehicles column, these two just weren't typed
  // before nothing read them. Used by the Kanban card's promo-price display.
  list_price: number | null
  promotional_price: number | null
  sale_price: number | null
  gw_file_number: string | null
  is_impus: boolean
  missing_civ: boolean
  stock_removed: boolean
  buyer_name: string | null
  // Present on the wire (summary() selects `v.*`, and neither buyer_client_id
  // nor company_id is finance-gated) even though the API route only strips
  // named finance fields — just wasn't previously typed since nothing read it.
  buyer_client_id: number | null
  company_id: number | null
  // Set by DispoService.transfer on the destination side (see
  // dispo_service.py's transfer()) — non-null marks this vehicle as a
  // fresh intake that landed here via an inter-company transfer rather than
  // a normal acquisition. Not finance-gated (absent from dispo.py's
  // _FINANCE_ROW_FIELDS), always present on the wire like buyer_client_id.
  transferred_from_company_id: number | null
  reservation_id: number | null
  reservation_end: string | null
  reservation_client_name: string | null
  reservation_deposit_amount: number | null
  reservation_deposit_paid: boolean | null
  doc_types: DocumentType[]
  // ── Finance-gated (carpark.view_finance) — absent entirely otherwise ──
  acquisition_price?: number | null
  total_costs?: number
  gross_margin?: number | null
  margin_pct?: number | null
  bonus_leasing?: number
}

// SUM(...) block across the full filtered set — null entirely for callers
// without can_view_carpark_finance (dispo.py sets result['totals'] = None).
export interface DispoTotals {
  acquisition_price: number
  total_costs: number
  sale_price: number
  gross_margin: number
}

export interface DispoSummaryResponse {
  rows: DispoRow[]
  stage_counts: Record<string, number>
  totals: DispoTotals | null
  total: number
  page: number
  per_page: number
}

// GET /dispo/kpis. gross_margin_mtd is finance-gated (popped for callers
// without can_view_carpark_finance — see dispo.py's _FINANCE_KPI_FIELDS).
export interface DispoKpis {
  cars_in_stock: number
  reserved: number
  sold_this_month: number
  delivered_this_month: number
  avg_days_in_stock: number
  aged_over_60: number
  gross_margin_mtd?: number
}

// Query filters accepted by GET /dispo/summary (dispo.py's
// _SUMMARY_FILTER_KEYS) — every value ends up as a query-string param.
export interface DispoFilters {
  stage?: string
  brand?: string
  location_id?: string
  salesperson_user_id?: string
  source?: string
  sale_type?: string
  date_from?: string
  date_to?: string
  sale_date_from?: string
  sale_date_to?: string
  search?: string
  stock_removed?: boolean
}

// GET /vehicles/:id/timeline — merged status-history + lifecycle-date +
// document events (DispoRepository.timeline). `meta` fields are a union of
// what each of the three source queries attaches; only the ones matching
// `type` will actually be populated on a given event.
export type TimelineEventType = 'status_change' | 'vehicle_date' | 'document'

export interface TimelineEvent {
  type: TimelineEventType
  label: string
  date: string
  meta: {
    old_status?: string | null
    new_status?: string
    notes?: string | null
    changed_by?: number | null
    field?: string
    id?: number
    document_type?: string
    title?: string | null
  }
}

// GET /vehicles/:id/documents/checklist (DispoService.checklist).
export interface DocumentChecklist {
  required: DocumentType[]
  present: DocumentType[]
  missing: DocumentType[]
  blocks_delivery: boolean
}

// A row from carpark_vehicle_documents (DocumentRepository).
export interface DispoDocument {
  id: number
  vehicle_id: number
  document_type: DocumentType
  title: string | null
  file_url: string | null
  dms_document_id: number | null
  file_size: number | null
  mime_type: string | null
  notes: string | null
  uploaded_by: number | null
  upload_date: string
  created_at: string
}

// Body for POST /vehicles/:id/documents in LINK MODE (JSON, no file part).
export interface DispoDocumentLinkBody {
  document_type: DocumentType
  file_url?: string
  dms_document_id?: number | string
  title?: string
  mime_type?: string
  file_size?: number
  notes?: string
}

// ── Inter-company transfer (AutoWorld group) ────────────────────────────

// GET /vehicles/transfer-destinations item (TransferRepository.group_companies
// — `companies` table columns, id + display name only).
export interface TransferDestination {
  id: number
  company: string
}

// A carpark_transfers row (transfer_repository.py's TRANSFER_FIELDS + id/
// created_at), as returned by POST /vehicles/:id/transfer's `transfer` key
// and by GET /vehicles/transfers-out's `transfers` list. list_outbound joins
// in the vehicle's identifying fields + destination company name; those are
// therefore only guaranteed present on transfers-out rows, not on the bare
// record POST /transfer returns — hence optional here.
export interface TransferOut {
  id: number
  vehicle_id: number
  from_company_id: number
  to_company_id: number
  transfer_price: number | null
  transfer_currency: string | null
  transfer_date: string
  document_id: number | null
  notes: string | null
  created_by: number | null
  created_at?: string
  // list_outbound joins only:
  vin?: string
  brand?: string
  model?: string
  nr_stoc?: string | null
  to_company_name?: string | null
}

// Body for POST /vehicles/:id/transfer in LINK MODE (JSON, no file part) —
// mirrors DispoDocumentLinkBody's file_url/dms_document_id split but for the
// transfer route's own field names (transfers.py's _create_transfer_document_via_link
// reads document_file_url OR file_url; both accepted, file_url sent here).
export interface TransferBody {
  to_company_id: number
  transfer_price: number
  transfer_date?: string
  transfer_currency?: string
  notes?: string
  file_url?: string
  dms_document_id?: number | string
  document_title?: string
}

// A row from carpark_reservations (ReservationRepository).
export interface DispoReservation {
  id: number
  vehicle_id: number
  client_id: number | null
  client_name: string | null
  client_company: string | null
  client_phone: string | null
  client_email: string | null
  user_id: number | null
  reservation_start: string
  reservation_end: string | null
  deposit_amount: number
  deposit_paid: boolean
  status: 'active' | 'cancelled' | 'converted' | (string & {})
  notes: string | null
  created_by: number | null
  created_at: string
  updated_at: string
}
