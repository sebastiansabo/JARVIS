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
  /** Per-car fuel-consumption norm (l/100km); prefills the monthly sheet's Normă. */
  norma_combustibil?: number | null
  /** Per-car energy-consumption norm (kWh/100km) for electric/hybrid cars. */
  norma_energie?: number | null
  /** Vehicle category shown on the Foaie de Parcurs (e.g. "AUTOTURISM M1G"). */
  category?: string | null
  /** Highest known mileage: max(odometer_km, greatest km_end across the car's
   *  non-draft sessions). Drives the TD form's start prefill + "below mileage" warning. */
  mileage_floor?: number | null
  registration_number?: string
  company_id?: number
  company_name?: string
  /** Pool the car belongs to: 'sales' (Vânzări) or 'service' (Mașini de curtoazie). */
  document_type?: 'sales' | 'service'
  // Service (Mașini de curtoazie) per-car price + policy (S6). Null falls back
  // to the company default (fp_company_config.svc_*) — resolved server-side by
  // compute_service_pricing (car value wins, else company default, else null).
  svc_tariff_eur_day?: number | null
  svc_tariff_eur_month?: number | null
  svc_km_included_day?: number | null
  svc_extra_km_eur?: number | null
  svc_deposit_eur?: number | null
  svc_franchise_eur?: number | null
  rental_category_id?: number | null
  // Documents + validity (rovinietă/vignette, ITP, RCA insurance). Docs are
  // base64 (image or PDF data-URL).
  vignette_valid_until?: string | null
  itp_valid_until?: string | null
  insurance_valid_until?: string | null
  insurance_doc?: string | null
  talon_doc?: string | null
  civ_doc?: string | null
  registration_doc?: string | null
  offer_doc?: string | null
  is_active: boolean
  // Lockout — car blocked from the driving park (blocks new sessions).
  locked_out?: boolean
  lockout_category?: string | null
  lockout_note?: string | null
  lockout_until?: string | null
  // Scheduled blocks (to-do #3) — set by the list query's LATERAL joins.
  /** True when a scheduled block window is active today (car un-bookable). */
  blocked_now?: boolean
  active_block_category?: string | null
  active_block_end?: string | null
  next_block_start?: string | null
  next_block_end?: string | null
  // Live-session awareness (set by the list query's LATERAL join): true when the
  // car is currently OUT on a handed-over test drive (FILLED td_form, not yet
  // returned), so the park can show "Pe drum" instead of a false "Disponibil".
  on_drive?: boolean
  on_drive_client?: string | null
  on_drive_until?: string | null
  // Next ≤3 PLANNED sessions for this car (list query's `up` LATERAL) — lets the
  // Driving Park surface upcoming bookings inline without a separate fetch.
  upcoming_planned?: { departure: string | null; client: string | null }[] | null
  // Archival reason — why the car left the fleet (shown on archived rows).
  archive_category?: string | null
  archive_note?: string | null
  archived_at?: string | null
  created_at: string
  updated_at: string
}

// Legacy fallback labels for the four seeded reasons. The live list is now
// configurable (fp_lockout_reasons) and fetched via foiParcursApi.getLockoutReasons;
// this map only backs the label when the reasons query hasn't loaded yet.
export const LOCKOUT_LABELS: Record<string, string> = {
  service: 'În service',
  damage: 'Avariat',
  paperwork: 'Acte lipsă/expirate',
  other: 'Altele',
}

/** A configurable driving-park lockout reason (editable in FP Settings). */
export interface LockoutReason {
  id: number
  slug: string
  label: string
  sort_order: number
  is_active: boolean
}

/** A scheduled block window for a car (to-do #3). `category` is a lockout-reason slug. */
export interface ScheduledBlock {
  id: number
  vehicle_id: number
  category: string | null
  note?: string | null
  start_date: string
  end_date: string
  is_active: boolean
  state: 'active' | 'upcoming' | 'past' | 'cancelled'
}

/** A configurable vehicle-archival reason (editable in FP Settings → Motive arhivare). */
export interface ArchiveReason {
  id: number
  slug: string
  label: string
  sort_order: number
  is_active: boolean
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
  // The client's OWN company (crm_clients.company_name) — distinct from
  // company_name (the dealership/car owner). Shown on cards as the driver's company.
  client_company?: string | null
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
  general_observation?: string | null
  advisor_name: string
  signature_ai_generated: string
  // Internal driving-log session (QuickSession) — no customer/signature. For
  // these, `itinerary` carries the form's free-text "Comentariu" (not a route).
  is_internal?: boolean
  // 'PLANNED' — draft session created ahead of time (Plan a Driving Session,
  // Phase 1 backend). Signature/GDPR/PDF are deferred; activated into
  // 'FILLED' when the client arrives (PUT /test-drive/{id}/activate).
  status: 'PENDING' | 'PLANNED' | 'FILLED' | 'COMPLETED' | 'MISSED'
  created_at: string
  updated_at: string
  // Returned by get_contracts (fp.* + _TD_STATUS_SQL) but previously undeclared:
  td_status?: 'complete' | 'incomplete' | 'driving' | 'missed' | 'late' | 'planned'
  departure_datetime?: string | null
  return_datetime?: string | null
  returned_at?: string | null
  // Set when an admin corrected the session or an advisor extended its return
  // → drives the "Modificat" badge + who/when tooltip.
  corrected_at?: string | null
  corrected_by?: string | null
  departure_damage?: TdDamageItem[] | null
  // Optional marketing project (campaign/event) this session is tied to.
  mkt_project_id?: number | null
  mkt_project_name?: string | null
  // Snapshot of the actual driver (Task 10) — set on company sessions where
  // the client is the company and a gate-valid contact person drove.
  driver_name?: string | null
  driver_contact_id?: number | null
  event_id?: number | null
  // Joined HR event name (Task 15) — LEFT JOIN hr.events he ON he.id =
  // fp.event_id in get_contracts; populates the "Eveniment" list/detail badge.
  event_name?: string | null
  // Service (Mașini de curtoazie) rental-pricing snapshot columns (S6b) —
  // present on `fp.*` for a Service-context contract; used to restore the
  // frozen/overridden price when activating a PLANNED draft (see
  // TestDriveForm's draft-prefill effect) instead of silently recomputing it.
  document_type?: string | null
  svc_rate_basis?: 'day' | 'month' | null
  svc_tariff_eur?: number | null
  svc_units?: number | null
  svc_total_eur?: number | null
  svc_km_included_day?: number | null
  svc_extra_km_eur?: number | null
  svc_garantie_eur?: number | null
  svc_fransiza_eur?: number | null
}

// ── Marketing project (campaign/event) a Test Drive can optionally be tied to.
// Backed by GET /api/foi-parcurs/mkt-projects/search. ──
export interface MktProject {
  id: number | string
  name?: string | null
  status?: string | null
  company_id?: number | null
  brand_id?: number | null
}

// ── HR event (hr.events) a Test Drive can optionally be tied to (Task 15) —
// distinct from a marketing project/campaign; mutually exclusive in the UI.
// Backed by GET /api/hr-events/search + POST /api/events. ──
export interface HrEvent {
  id: number
  name: string
  start_date?: string | null
  end_date?: string | null
  company?: string | null
  brand?: string | null
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
  email?: string | null
  /** Fiscal code (Cod Unic de Înregistrare) — required for a company TD. */
  cui?: string | null
  /** Trade-register number (Nr. Registrul Comerțului) — distinct from cui. */
  nr_reg?: string | null
  /** Address parts — shown/edited in the Driving Hub Client card. */
  street?: string | null
  city?: string | null
  region?: string | null
  company_name?: string | null
  /** 'company' | 'person' — a company client never drives itself; the TD form
   *  gates submit/activate on a gate-valid contact person (see ClientContact). */
  client_type?: string | null
  /** Driving license kept on the client for reuse (a duplicate suggestion hands
   *  it back; the front-end checks expiry). */
  driver_license_number?: string | null
  driver_license_expiry?: string | null
}

export interface CreateCrmClientPayload {
  display_name: string
  phone: string
  email?: string
  address?: string
  city?: string
  county?: string
  country?: string
  /** Company (persoană juridică) fields — backend sets client_type='company'. */
  is_company?: boolean
  company_name?: string
  cui?: string
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
  general_observation?: string
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
  general_conditions_accepted?: boolean
  /** Optional marketing project (campaign/event) this Test Drive is tied to. */
  mkt_project_id?: number
  /** Company-client driver gate (Task 11): the gate-valid contact person who
   *  actually drives, required server-side for a live FILLED submit against a
   *  company client. driver_license_serie may come from the contact or the
   *  standalone license field. */
  driver_contact_id?: number
  driver_license_serie?: string
  /** Optional HR event this Test Drive is tied to (Task 15) — mutually
   *  exclusive with mkt_project_id in the UI (Eveniment checkbox). */
  event_id?: number
  /** Override the driving-park lockout block, set after the user confirms. */
  allow_locked?: boolean
  allow_open_session?: boolean
  /** Service context (Task 13): which flow this session belongs to
   *  ('sales' | 'service'); service_order_ref is Service-only. */
  document_type?: string
  service_order_ref?: string
  /** Service rental-pricing snapshot (S6b) — auto-computed by
   *  GET .../service-pricing and shown in the session's "Sumar închiriere"
   *  card; the advisor may edit before submit. Backend treats any non-null
   *  value here as a per-key override of its own compute_service_pricing
   *  result (see _resolve_service_pricing in routes/test_drive.py). Ignored
   *  server-side unless document_type === 'service'. */
  svc_rate_basis?: 'day' | 'month'
  svc_tariff_eur?: number
  svc_units?: number
  svc_total_eur?: number
  svc_km_included_day?: number
  svc_extra_km_eur?: number
  svc_garantie_eur?: number
  svc_fransiza_eur?: number
}

// ── Internal driving-log session — POST /test-drive with is_internal:true
// (see foi_parcurs/routes/test_drive.py's `is_internal` branch). Slim payload:
// no client/signature/GDPR/fuel/damage — just the car, the driver, the times
// and the starting km. Returns via the SAME existing TestDriveReturn flow. ──
export interface InternalSessionPayload {
  is_internal: true
  company_id: number
  vin: string
  advisor_name: string
  departure_datetime: string
  return_datetime?: string
  /** Deferred (omitted) when planning for later — captured at start instead. */
  odometer_start?: number
  itinerary?: string
  /** 'PLANNED' plans a draft internal session (started later via /start);
   *  omitted creates a live FILLED session immediately (start-now). */
  status?: 'PLANNED'
  /** Override the driving-park lockout block, set after the user confirms. */
  allow_locked?: boolean
  allow_open_session?: boolean
}

// ── Start a PLANNED internal draft — PUT /test-drive/{id}/start. The internal
// counterpart to activate: no client/signature, just the real km plecare. ──
export interface StartInternalSessionPayload {
  odometer_start?: number
  departure_datetime?: string
  return_datetime?: string
  allow_locked?: boolean
  allow_open_session?: boolean
}

// ── Plan (draft) Test Drive Payload — POST /test-drive with status:'PLANNED'.
// Same shape as TestDriveFormPayload except client_signature/gdpr_consent are
// deferred to activation (backend only requires them when status is
// absent/'FILLED' — see api_submit_test_drive's `is_draft` branch). ──
export type PlanTestDrivePayload = Omit<TestDriveFormPayload, 'client_signature' | 'gdpr_consent'> & {
  status: 'PLANNED'
  client_signature?: string
  gdpr_consent?: boolean
}

// ── Activate a PLANNED draft — PUT /test-drive/{id}/activate. Only
// client_signature is required by the backend; everything else is an
// optional handover edit (unset fields keep the PLANNED row's existing
// values). ──
export interface ActivateTestDrivePayload {
  /** The (possibly changed) client selected at activation — the backend
   *  validates the driver contact against it and persists the switch. */
  client_id?: number
  client_signature: string
  advisor_signature?: string
  gdpr_consent?: boolean
  general_conditions_accepted?: boolean
  odometer_start?: number
  fuel_gauge_start_level?: FuelGaugeLevel
  fuel_tank_capacity_liters?: number
  departure_datetime?: string
  return_datetime?: string
  departure_damage?: TdDamageItem[]
  general_observation?: string
  /** Optional marketing project (campaign/event) this Test Drive is tied to. */
  mkt_project_id?: number
  /** Optional HR event (Task 15) — mutually exclusive with mkt_project_id in the UI. */
  event_id?: number
  /** Company-client driver gate (Task 11) — see TestDriveFormPayload. */
  driver_contact_id?: number
  /** Override the driving-park lockout block, set after the user confirms. */
  allow_locked?: boolean
  allow_open_session?: boolean
  /** Service rental-pricing snapshot (S6b) — see TestDriveFormPayload. A
   *  PLANNED draft may be activated once departure/return are both finally
   *  known, so this is (re)computed at activation unless overridden here. */
  svc_rate_basis?: 'day' | 'month'
  svc_tariff_eur?: number
  svc_units?: number
  svc_total_eur?: number
  svc_km_included_day?: number
  svc_extra_km_eur?: number
  svc_garantie_eur?: number
  svc_fransiza_eur?: number
}

// ── Return (completion) Test Drive Payload — PUT /test-drive/:id/return.
// Fuel level uses the return gauge set (Gol…Plin), distinct from departure. ──
export type ReturnFuelLevel = 'Gol' | '1/4' | '1/2' | '3/4' | 'Plin'

export interface ReturnTestDrivePayload {
  km_end: number
  fuel_gauge_end_level: ReturnFuelLevel
  return_damage: TdDamageItem[]
  return_notes?: string
  advisor_signature: string
  client_signature: string
  return_datetime?: string
}

// ── Vehicle conflict — GET /vehicles/{vin}/conflicts response row. Matches
// FoiParcursRepository.find_conflicts()'s SELECT list exactly (no td_status —
// the backend query doesn't derive/select it). ──
export interface VehicleConflict {
  id: number
  contract_id: string
  status: 'PLANNED' | 'FILLED' | 'COMPLETED'
  departure_datetime: string | null
  return_datetime: string | null
  client_name: string | null
  advisor_name: string
}

// One row of a session's audit trail (foi_parcurs_session_events), shown in the
// "Istoric" modal. `actor` is the acting user's name (or email); null for system
// actions. `created_at` is a real server timestamp — render with new Date().
export interface SessionEvent {
  id: number
  action: string
  actor: string | null
  created_at: string
}
