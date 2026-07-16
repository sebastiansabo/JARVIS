// ── Fuel Type ──
export type FuelType = 'Benzina' | 'Diesel' | 'Electric' | 'Hybrid'

export const FUEL_TYPE_OPTIONS: { value: FuelType; label: string }[] = [
  { value: 'Benzina', label: 'Benzina' },
  { value: 'Diesel', label: 'Diesel' },
  { value: 'Electric', label: 'Electric' },
  { value: 'Hybrid', label: 'Hybrid' },
]

// Which capacity fields apply to a given fuel type
export function usesFuelTank(fuelType?: FuelType | string): boolean {
  return fuelType === 'Benzina' || fuelType === 'Diesel' || fuelType === 'Hybrid'
}
export function usesBattery(fuelType?: FuelType | string): boolean {
  return fuelType === 'Electric' || fuelType === 'Hybrid'
}

// ── Vehicle (Stock) ──
export interface FpVehicle {
  id: number
  vin: string
  car_id?: string
  mark: string
  brand?: string
  model: string
  color?: string
  fuel_type: FuelType
  fuel_tank_capacity_liters: number | null
  battery_capacity_kwh?: number | null
  odometer_km?: number | null
  registration_number?: string
  company_id?: number
  company_name?: string
  // Documents + validity (rovinietă/vignette, ITP, RCA insurance). Docs are
  // base64 (image or PDF data-URL).
  vignette_valid_until?: string | null
  itp_valid_until?: string | null
  insurance_valid_until?: string | null
  insurance_doc?: string | null
  talon_doc?: string | null
  civ_doc?: string | null
  registration_doc?: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

// ── Fuel Gauge ──
export type FuelGaugeLevel = '1' | '1/2' | '2/3' | '1/4'

export const FUEL_LEVEL_LABELS: Record<FuelGaugeLevel, string> = {
  '1': '1 (Full)',
  '1/2': '1/2 (Half)',
  '2/3': '2/3 (Two-Thirds)',
  '1/4': '1/4 (Quarter)',
}

export const FUEL_LEVEL_OPTIONS: { value: FuelGaugeLevel; label: string }[] = [
  { value: '1', label: '1 (Full)' },
  { value: '1/2', label: '1/2 (Half)' },
  { value: '2/3', label: '2/3 (Two-Thirds)' },
  { value: '1/4', label: '1/4 (Quarter)' },
]

// ── Route Types ──
export type RouteType = 'TD' | 'Comodat'

export type IdDocumentType = 'ID_CARD' | 'PASSPORT' | 'DRIVER_LICENSE'

// ── CRM Client (for foi_parcurs) ──
export interface FoiClient {
  id: number
  name: string
  phone: string
  email?: string
  date_of_birth?: string
  id_document_type: IdDocumentType
  id_document_no: string
  driver_license_combined?: string
  address?: string
  previous_test_drives: number
  previous_comadats: number
  created_at: string
  updated_at: string
}

// ── Batch Config (form input) ──
export interface BatchConfig {
  year: number
  month: number
  company_id: number
  vin: string
  fuel_type: FuelType
  odometer_start: number
  odometer_end: number
  num_clients: number
  num_td: number
  num_comodat: number
  fuel_tank_capacity_liters: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level: FuelGaugeLevel
  total_consumption_period_liters: number
  fuelings?: { date: string; doc_number: string; liters: number }[]
  trips?: { date_from: string; date_to: string; location: string; estimated_km: number }[]
}

// Helper: unit label based on fuel type
export function fuelUnit(fuelType?: FuelType | string): string {
  return fuelType === 'Electric' ? 'kWh' : 'L'
}

// ── Preview Response ──
export interface RouteAssignment {
  slot: number
  route_type: RouteType
  km_start: number
  km_end: number
  distance_km: number
}

export interface FuelClientAllocation {
  fuel_start_liters: number
  fuel_end_liters: number
  fuel_consumed_liters: number
}

export interface PreviewResponse {
  assignments: {
    num_test_drives: number
    num_comadats: number
    total_distance_km: number
    distances: number[]
    clients: RouteAssignment[]
  }
  fuel_distribution: {
    start_liters: number
    end_liters: number
    available_consumption: number
    per_client: FuelClientAllocation[]
  }
}

// ── Contract ──
export interface FoiContract {
  id: number
  contract_id: string
  batch_id?: string
  vin: string
  client_id: number | null
  client_name?: string
  client_phone?: string
  company_id: number
  company_name?: string
  year?: number
  month?: number
  route_type: RouteType
  slot_number: number
  km_start: number
  km_end: number
  distance_km: number
  fuel_tank_capacity_liters: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level: FuelGaugeLevel
  fuel_start_liters: number
  fuel_end_liters: number
  fuel_consumed_liters: number
  itinerary: string
  advisor_name: string
  signature_ai_generated: string
  status: 'PENDING' | 'FILLED' | 'COMPLETED'
  created_at: string
  updated_at: string
}

// ── Create Contract Payload ──
export interface CreateContractPayload {
  vin: string
  company_id: number
  client_id: number
  route_type: RouteType
  km_start: number
  km_end: number
  distance_km: number
  fuel_tank_capacity_liters: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level: FuelGaugeLevel
  fuel_start_liters: number
  fuel_end_liters: number
  fuel_consumed_liters: number
  itinerary: string
  advisor_name: string
  signature_svg: string
  total_consumption_period_liters: number
  assignment_rule: string
  slot_number: number
}

// ── Create Client Payload ──
export interface CreateClientPayload {
  name: string
  phone: string
  email?: string
  company?: string
  date_of_birth: string
  driver_license_combined: string
  address?: string
}

// ── Client Allocation State (per card) ──
export interface ClientAllocationState {
  slot: number
  route_type: RouteType
  km_start: number
  km_end: number
  distance_km: number
  fuel_start_liters: number
  fuel_end_liters: number
  fuel_consumed_liters: number
  client_id: number | null
  client_name: string
  itinerary: string
  advisor_name: string
  signature_svg: string
  signature_variant: number
  filled: boolean
}

// ── Vehicle Inspection ──
export interface FpVehicleInspection {
  id: number
  vehicle_id: number
  vin: string
  inspection_date: string
  condition_notes: string
  photos: string[]
  inspector_name: string
  inspector_signature: string
  created_by: number | null
  created_at: string
}

// ── CRM Client (Test Drive search/create — crm_clients table) ──
export interface CrmClient {
  id: number | string
  display_name?: string | null
  name?: string | null
  phone?: string | null
}

export interface CreateCrmClientPayload {
  display_name: string
  phone: string
  email?: string
  address?: string
  city?: string
  county?: string
  country?: string
}

// ── Driver-license OCR (Claude vision) ──
export interface DriverLicenseOcrData {
  last_name?: string | null
  first_name?: string | null
  full_name?: string | null
  cnp?: string | null
  license_number?: string | null
  birth_date?: string | null
  expiry_date?: string | null
  address?: string | null
  city?: string | null
  county?: string | null
}

// ── Structured vehicle-condition damage (shared departure/return model) ──
export interface TdDamageItem {
  zone: string
  severity: 'minor' | 'moderate' | 'severe'
  note?: string
  photos?: string[]
}

// ── Test Drive Form Payload ──
export interface TestDriveFormPayload {
  company_id: number
  vin: string
  registration_number: string
  client_id: number
  odometer_start: number
  odometer_end?: number
  estimated_km: number
  fuel_tank_capacity_liters?: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level?: FuelGaugeLevel
  fuel_start_liters?: number
  fuel_end_liters?: number
  fuel_consumed_liters?: number
  itinerary?: string
  departure_datetime: string
  return_datetime?: string
  advisor_name: string
  advisor_signature?: string
  client_signature: string
  gdpr_consent: boolean
  inspection_acceptance?: boolean
  inspection_id?: number
  departure_damage?: TdDamageItem[]
  driver_license_photo?: string
  driver_license_number?: string
  driver_license_expiry?: string
}
