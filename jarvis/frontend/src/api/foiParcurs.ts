import { api } from './client'
import type {
  BatchConfig,
  PreviewResponse,
  CreateContractPayload,
  FoiContract,
  FoiClient,
  CreateClientPayload,
  FpVehicle,
  FpVehicleInspection,
  TestDriveFormPayload,
  InternalSessionPayload,
  StartInternalSessionPayload,
  PlanTestDrivePayload,
  ActivateTestDrivePayload,
  ReturnTestDrivePayload,
  VehicleConflict,
  CrmClient,
  CreateCrmClientPayload,
  DriverLicenseOcrData,
  MktProject,
  HrEvent,
  ScheduledBlock,
  SessionEvent,
} from '../types/foiParcurs'

export interface RouteSheetAlimentare {
  date: string
  bon: string
  liters: number
  lei?: number
  unit?: 'l' | 'kWh'
}

export interface GapFillContract {
  date: string
  client_name: string
  km_start: number
  km_end: number
  // Optional "client extra" documentation captured in the redistribute dialog.
  advisor_name?: string
  client_signature?: string
  driver_license_photo?: string
  driver_license_number?: string
  driver_license_expiry?: string
}

export interface AbsorbGapMiddle {
  client_name?: string
  km: number
  date?: string
}

export interface AbsorbGapPayload {
  vin: string
  year: number
  month: number
  before_id: number
  after_id: number
  before_km: number
  after_km: number
  middles?: AbsorbGapMiddle[]
}

export interface SessionImportResult {
  success: boolean
  inserted: number
  skipped: number
  cars_created: number
  errors: { row: number; message: string }[]
}

export interface RouteSheetEvent {
  name: string
  start: string
  end: string
}

export interface StoredRouteSheet {
  vin: string
  session_count: number
  total_km: number
  norma_combustibil: number | null
  norma_energie: number | null
  alimentari: RouteSheetAlimentare[] | null
  evenimente: RouteSheetEvent[] | null
  generated_by_name: string | null
  generated_at: string
}

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== null) sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

const BASE = '/api/foi-parcurs'

// ── Reports (Rapoarte tab) ──
export interface ReportKpis {
  total_sessions: number
  total_km: number
  cars_used: number
  avg_km_per_session: number
  completion_rate: number
  test_drives: number
}
export interface ReportsSummary {
  success: boolean
  scope: { company_id: number | null; is_group: boolean; document_type: string }
  kpis: ReportKpis
  sessions_over_time: { bucket: string; count: number }[]
  by_status: { status: string; count: number }[]
  by_type: { type: string; count: number }[]
  client_vs_internal: { segment: string; count: number }[]
  by_brand: { brand: string; count: number }[]
  client_types: { client_type: string; count: number }[]
  top_clients: { client: string; client_type: string; sessions: number; km: number }[]
  top_advisors: { advisor: string; sessions: number; km: number; completion_rate: number }[]
  top_companies: { company_id: number; company: string; sessions: number; km: number }[]
  utilization: { vin: string; registration_number: string; model: string; days_used: number; sessions: number; km: number }[]
  distance_by_brand: { brand: string; km: number }[]
  fuel_composition: { fuel_type: string; count: number }[]
  top_odometer: { vin: string; registration_number: string; model: string; odometer_km: number }[]
  rental: { total_eur: number; sessions: number; by_month: { bucket: string; eur: number }[] } | null
}
export interface ReportSession {
  id: number
  contract_id: string
  date: string
  client: string
  advisor: string | null
  vin: string
  registration_number: string
  model: string
  td_status: string
  km: number
}

export const foiParcursApi = {
  // ── Preview ──
  preview: (config: BatchConfig) =>
    api.post<PreviewResponse>(`${BASE}/preview`, config),

  // ── Save Batch (preview → persist as PENDING contracts) ──
  saveBatch: (config: BatchConfig, preview: PreviewResponse) =>
    api.post<{ success: boolean; batch_id: string; count: number }>(`${BASE}/batches`, { config, preview }),

  // ── Contracts ──
  createContract: (data: CreateContractPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/contracts`, data),

  getContracts: (params?: {
    vin?: string
    company_id?: number
    status?: string
    batch_id?: string
    route_type?: string
    date_from?: string
    date_to?: string
    page?: number
    per_page?: number
    sort_by?: string
    sort_dir?: string
    document_type?: string
  }) =>
    api.get<{ contracts: FoiContract[]; total: number; page: number; per_page: number }>(
      `${BASE}/contracts${qs(params ?? {})}`
    ),

  // ── Reports (Rapoarte tab) ──
  getReports: (params: {
    company_id?: number
    date_from?: string
    date_to?: string
    document_type?: string
    odo_order?: string
    status?: string
    drive_type?: string
    brand?: string
    top?: number
  }) => api.get<ReportsSummary>(`${BASE}/reports/summary${qs(params)}`),

  getReportSessions: (params: {
    company_id?: number
    date_from?: string
    date_to?: string
    document_type?: string
    advisor?: string
    vin?: string
    status?: string
    drive_type?: string
    client_type?: string
    brand?: string
    fuel_type?: string
  }) => api.get<{ success: boolean; sessions: ReportSession[] }>(`${BASE}/reports/sessions${qs(params)}`),

  allocateClient: (contractId: number, data: { client_id: number; itinerary: string; advisor_name: string; signature_svg?: string }) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/contracts/${contractId}/allocate`, data),

  getContract: (id: number) =>
    api.get<{ contract: FoiContract }>(`${BASE}/contracts/${id}`),

  // Admin-only registration admin actions.
  deleteContract: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/contracts/${id}`),

  resetContract: (id: number) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/contracts/${id}/reset`),

  // ── Signature ──
  generateSignature: (advisorName: string, variant: number) =>
    api.post<{ svg: string }>(`${BASE}/signature`, { advisor_name: advisorName, variant }),

  // ── Clients ──
  searchClients: (q: string, limit = 20) =>
    api.get<{ success: boolean; clients: FoiClient[] }>(`${BASE}/clients/search${qs({ q, limit })}`),

  createClient: (data: CreateClientPayload) =>
    api.post<{ success: boolean; client: FoiClient }>(`${BASE}/clients`, data),

  // ── Vehicles (Stock) ──
  getVehicles: (activeOnly = true, documentType?: string) =>
    api.get<{ vehicles: FpVehicle[] }>(`${BASE}/vehicles`, { active_only: String(activeOnly), ...(documentType ? { document_type: documentType } : {}) }),

  // Full vehicle incl. document blobs — the list is lean, so the edit form
  // fetches the docs here on demand.
  getVehicle: (id: number) =>
    api.get<{ success: boolean; vehicle: FpVehicle }>(`${BASE}/vehicles/${id}`),

  createVehicle: (data: { vin: string; registration_number?: string; car_id?: string; mark: string; brand?: string; model: string; color?: string; fuel_type: string; fuel_tank_capacity_liters?: number | null; battery_capacity_kwh?: number | null; odometer_km?: number | null; norma_combustibil?: number | null; norma_energie?: number | null; category?: string | null; company_id?: number; document_type?: string; svc_tariff_eur_day?: number | null; svc_tariff_eur_month?: number | null; svc_km_included_day?: number | null; svc_extra_km_eur?: number | null; svc_deposit_eur?: number | null; svc_franchise_eur?: number | null; rental_category_id?: number | null; vignette_valid_until?: string; itp_valid_until?: string; insurance_valid_until?: string; insurance_doc?: string; talon_doc?: string; civ_doc?: string; registration_doc?: string; offer_doc?: string }) =>
    api.post<{ success: boolean; vehicle: FpVehicle }>(`${BASE}/vehicles`, data),

  updateVehicle: (id: number, data: Partial<FpVehicle>) =>
    api.put<{ success: boolean; vehicle: FpVehicle }>(`${BASE}/vehicles/${id}`, data),

  deleteVehicle: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/vehicles/${id}`),

  // ── Archive: soft-delete a car with a reason (restorable via updateVehicle) ──
  archiveVehicle: (id: number, data: { category: string; note?: string }) =>
    api.post<{ success: boolean }>(`${BASE}/vehicles/${id}/archive`, data),

  // ── Lockout: block/unblock a car from the driving park ──
  lockVehicle: (id: number, data: { category: string; note?: string; until?: string | null }) =>
    api.post<{ success: boolean }>(`${BASE}/vehicles/${id}/lock`, data),
  unlockVehicle: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/vehicles/${id}/unlock`, {}),

  // ── Lockout reasons (configurable, editable in Settings → Motive blocare) ──
  getLockoutReasons: (activeOnly = false) =>
    api.get<{ success: boolean; reasons: import('@/types/foiParcurs').LockoutReason[] }>(
      `${BASE}/lockout-reasons`, { active_only: String(activeOnly) },
    ),
  createLockoutReason: (data: { label: string; sort_order?: number }) =>
    api.post<{ success: boolean; reason: import('@/types/foiParcurs').LockoutReason }>(`${BASE}/lockout-reasons`, data),
  updateLockoutReason: (id: number, data: { label?: string; sort_order?: number; is_active?: boolean }) =>
    api.put<{ success: boolean; reason: import('@/types/foiParcurs').LockoutReason }>(`${BASE}/lockout-reasons/${id}`, data),

  // ── Scheduled blocks (to-do #3): future auto-block windows ──
  getScheduledBlocks: (vehicleId: number) =>
    api.get<{ success: boolean; blocks: ScheduledBlock[] }>(
      `${BASE}/vehicles/${vehicleId}/scheduled-blocks`,
    ),
  createScheduledBlock: (
    vehicleId: number,
    data: { category: string; start_date: string; end_date: string; note?: string; allow_conflicts?: boolean },
  ) =>
    api.post<{ success: boolean; block?: ScheduledBlock; conflicts?: VehicleConflict[]; error?: string }>(
      `${BASE}/vehicles/${vehicleId}/scheduled-blocks`, data,
    ),
  cancelScheduledBlock: (vehicleId: number, blockId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/vehicles/${vehicleId}/scheduled-blocks/${blockId}`),

  // ── Archive reasons (configurable, editable in Settings → Motive arhivare) ──
  getArchiveReasons: (activeOnly = false) =>
    api.get<{ success: boolean; reasons: import('@/types/foiParcurs').ArchiveReason[] }>(
      `${BASE}/archive-reasons`, { active_only: String(activeOnly) },
    ),
  createArchiveReason: (data: { label: string; sort_order?: number }) =>
    api.post<{ success: boolean; reason: import('@/types/foiParcurs').ArchiveReason }>(`${BASE}/archive-reasons`, data),
  updateArchiveReason: (id: number, data: { label?: string; sort_order?: number; is_active?: boolean }) =>
    api.put<{ success: boolean; reason: import('@/types/foiParcurs').ArchiveReason }>(`${BASE}/archive-reasons/${id}`, data),

  // ── Companies ──
  getCompanies: () =>
    api.get<{ companies: { id: number; company: string }[] }>(`${BASE}/companies`),

  // ── Brands for a company (from the company_brands catalog, not dept structure).
  //    Pass documentType='service' to instead get the distinct brands present in
  //    that company's Service (courtesy) fleet pool, not the sales catalog. ──
  getBrands: (companyId: number, documentType?: string) =>
    api.get<{ success: boolean; brands: string[] }>(
      `${BASE}/brands/${companyId}${documentType ? `?document_type=${documentType}` : ''}`,
    ),

  // ── Every active brand across all companies (any-brand picker for courtesy
  //    cars — e.g. a VW loaner sitting on an Audi dealer's fleet) ──
  getAllBrands: () =>
    api.get<{ success: boolean; brands: string[] }>(`${BASE}/all-brands`),

  // ── Per company+brand dealer config (review link + contact for the email) ──
  getDealerConfig: (companyId: number) =>
    api.get<{ success: boolean; configs: { brand_id: number; brand_name: string; review_url: string | null; address: string | null; phone: string | null; email: string | null; show_in_foi_parcurs: boolean; general_conditions: string | null }[] }>(
      `${BASE}/dealer-config/${companyId}`,
    ),

  updateDealerConfig: (companyId: number, brandId: number, data: { review_url?: string; address?: string; phone?: string; email?: string; show_in_foi_parcurs?: boolean; general_conditions?: string }) =>
    api.put<{ success: boolean }>(`${BASE}/dealer-config/${companyId}/${brandId}`, data),

  // ── Per company+brand contract configs (Service context: title/body/general
  //    conditions template for the generated contract) ──
  getContractConfigs: (companyId: number) =>
    api.get<{ success: boolean; configs: Array<{ brand_id: number; brand_name: string; config_id: number | null; title: string | null; body_template: string | null; general_conditions: string | null; is_active: boolean }> }>(`${BASE}/contract-configs/${companyId}`),

  putContractConfig: (companyId: number, brandId: number, payload: { title: string; body_template: string; general_conditions: string; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/contract-configs/${companyId}/${brandId}`, payload),

  // ── Service context enabled flags (which brands have Service unlocked) ──
  getServiceEnabled: (companyId: number) =>
    api.get<{ success: boolean; enabled: boolean; brands: number[] }>(`${BASE}/service-enabled`, { company_id: String(companyId) }),

  // ── Document types (user-defined per company; a type IS its contract) ──
  getDocumentTypes: (companyId: number, includeInactive = false) =>
    api.get<{ success: boolean; types: Array<{ key: string; label: string; title: string | null; body_template: string | null; general_conditions: string | null; is_rental: boolean; is_active: boolean; is_default: boolean; sort_order: number; has_template: boolean }> }>(
      `${BASE}/document-types`,
      { company_id: String(companyId), ...(includeInactive ? { include_inactive: '1' } : {}) },
    ),
  addDocumentType: (payload: { company_id: number; label: string; is_rental?: boolean }) =>
    api.post<{ success: boolean; key: string }>(`${BASE}/document-types`, payload),
  putDocumentType: (payload: { company_id: number; key: string; label: string; title: string; body_template: string; general_conditions: string; is_rental: boolean; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/document-types`, payload),
  deleteDocumentType: (payload: { company_id: number; key: string }) =>
    api.delete<{ success: boolean }>(`${BASE}/document-types`, payload),

  // ── Rental tariffs (courtesy-car category pricing) ──
  getRentalIntervals: (companyId: number) =>
    api.get<{ success: boolean; intervals: Array<{ id: number; label: string; min_days: number; max_days: number | null; sort_order: number }> }>(
      `${BASE}/rental-tariffs/intervals`, { company_id: String(companyId) }),
  putRentalInterval: (payload: { company_id: number; id?: number; label: string; min_days: number; max_days: number | null; sort_order?: number }) =>
    api.put<{ success: boolean; id: number }>(`${BASE}/rental-tariffs/intervals`, payload),
  deleteRentalInterval: (payload: { company_id: number; id: number }) =>
    api.delete<{ success: boolean }>(`${BASE}/rental-tariffs/intervals`, payload),
  getRentalCategories: (companyId: number, active = false) =>
    api.get<{ success: boolean; categories: Array<{ id: number; name: string; models_note: string | null; franchise_eur: number | null; extra_km_eur: number | null; sort_order: number; is_active: boolean; prices: Record<number, number> }> }>(
      `${BASE}/rental-tariffs/categories`, { company_id: String(companyId), ...(active ? { active: '1' } : {}) }),
  addRentalCategory: (payload: { company_id: number; name: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/rental-tariffs/categories`, payload),
  putRentalCategory: (payload: { company_id: number; id: number; name: string; models_note: string | null; franchise_eur: number | null; extra_km_eur: number | null; sort_order?: number; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/rental-tariffs/categories`, payload),
  deleteRentalCategory: (payload: { company_id: number; id: number }) =>
    api.delete<{ success: boolean }>(`${BASE}/rental-tariffs/categories`, payload),
  setRentalPrice: (payload: { company_id: number; category_id: number; interval_id: number; eur_per_day: number | null }) =>
    api.put<{ success: boolean }>(`${BASE}/rental-tariffs/prices`, payload),

  // ── KM Configs (Settings) ──
  getKmConfigs: () =>
    api.get<{ configs: { company_id: number; td_km_min: number; td_km_max: number; comodat_km_min: number; comodat_km_max: number; km_gap: number }[] }>(`${BASE}/km-configs`),

  updateKmConfig: (companyId: number, data: { td_km_min: number; td_km_max: number; comodat_km_min: number; comodat_km_max: number; km_gap: number }) =>
    api.put<{ success: boolean }>(`${BASE}/km-configs/${companyId}`, data),

  // ── Routes (per-company itineraries, per route type) ──
  getRoutes: (companyId: number, routeType?: 'TD' | 'Comodat') =>
    api.get<{ routes: { id: number; company_id: number; route_type: 'TD' | 'Comodat'; itinerary: string; estimated_km?: number }[] }>(
      `${BASE}/routes/${companyId}${routeType ? `?route_type=${routeType}` : ''}`
    ),

  addRoute: (companyId: number, data: { route_type: 'TD' | 'Comodat'; itinerary: string; estimated_km?: number }) =>
    api.post<{ success: boolean; route: { id: number; company_id: number; route_type: 'TD' | 'Comodat'; itinerary: string; estimated_km?: number } }>(
      `${BASE}/routes/${companyId}`, data
    ),

  deleteRoute: (routeId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/routes/${routeId}`),

  // ── AI Itinerary Generation ──
  generateItinerary: (companyId: number, routeType: 'TD' | 'Comodat', distanceKm: number) =>
    api.post<{ itinerary: string }>(`${BASE}/generate-itinerary`, { company_id: companyId, route_type: routeType, distance_km: distanceKm }),

  // ── Company Location Config (+ Service default rental-pricing policy) ──
  getCompanyConfig: (companyId: number) =>
    api.get<{ config: {
      company_id: number; base_location: string; td_radius_km: number; comodat_avg_km: number
      // Service (Mașini de curtoazie) default policy — fallback for any
      // per-car svc_* field left NULL (see fp_vehicles / compute_service_pricing).
      svc_km_included_day: number | null; svc_extra_km_eur: number | null
      svc_deposit_eur: number | null; svc_franchise_eur: number | null
    } }>(`${BASE}/company-config/${companyId}`),

  updateCompanyConfig: (companyId: number, data: {
    base_location: string; td_radius_km: number; comodat_avg_km: number
    svc_km_included_day?: number | null; svc_extra_km_eur?: number | null
    svc_deposit_eur?: number | null; svc_franchise_eur?: number | null
  }) =>
    api.put<{ success: boolean }>(`${BASE}/company-config/${companyId}`, data),

  // ── Service rental-pricing preview (session form auto-fill; pure preview,
  //    never persists — see GET /api/foi-parcurs/service-pricing) ──
  getServicePricing: (companyId: number, vin: string, departure: string, returnDt: string) =>
    api.get<{ success: boolean; pricing: {
      svc_rate_basis: 'day' | 'month'
      svc_tariff_eur: number
      svc_units: number
      svc_total_eur: number
      svc_km_included_day: number | null
      svc_extra_km_eur: number | null
      svc_garantie_eur: number | null
      svc_fransiza_eur: number | null
    } }>(`${BASE}/service-pricing`, { company_id: String(companyId), vin, departure, return_dt: returnDt }),

  // ── Test Drive Form ──
  submitTestDrive: (data: TestDriveFormPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Internal driving-log session (Client/Intern chooser → "Intern") — same
  //    endpoint as submitTestDrive, tagged is_internal:true; no PDFs/signature ──
  submitInternalSession: (data: InternalSessionPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Start a PLANNED internal draft → FILLED (no client/signature/PDF) ──
  startInternalSession: (id: number, data: StartInternalSessionPayload) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/start`, data),

  // ── Per company+vehicle-brand general-conditions text ('' when unset) ──
  getGeneralConditions: (companyId: number, vin: string, documentType?: string) =>
    api.get<{ success: boolean; text: string; brand: string }>(
      `${BASE}/general-conditions?company_id=${companyId}&vin=${encodeURIComponent(vin)}&document_type=${documentType ?? 'sales'}`,
    ),

  // ── Plan a draft TD (status: 'PLANNED') — same endpoint, signature/GDPR/PDF
  //    deferred to activation ──
  planTestDrive: (data: PlanTestDrivePayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Activate a PLANNED draft → FILLED (client signature required) ──
  activateTestDrive: (id: number, data: ActivateTestDrivePayload) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/activate`, data),

  // ── Edit a PLANNED draft in place (Corectează on a not-started session):
  //    full-form edit without starting it; PLANNED-only server-side ──
  updatePlan: (id: number, data: Partial<TestDriveFormPayload>) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/plan`, data),

  // ── Reschedule a PLANNED/MISSED session to a new time (drag-to-move in the
  //    calendar); backend guards to those statuses + rejects past dates ──
  rescheduleTestDrive: (id: number, data: { departure_datetime: string; return_datetime?: string }) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/reschedule`, data),

  // Admin-only: correct a session's drive date(s) and/or odometer to fix
  // data-entry anomalies (wrong date, overlapping km). Any status; status unchanged.
  correctSession: (
    id: number,
    data: {
      departure_datetime?: string | null
      return_datetime?: string | null
      km_start?: number | null
      km_end?: number | null
      advisor_name?: string
    },
  ) => api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/contracts/${id}/correct`, data),

  // Advisor extends an OPEN test drive's return time (any logged-in user).
  extendReturn: (id: number, data: { return_datetime: string }) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/extend`, data),

  // Session audit trail (newest first) for the "Istoric" modal.
  getSessionHistory: (id: number) =>
    api.get<{ success: boolean; events: SessionEvent[] }>(`${BASE}/test-drive/${id}/history`),

  // ── Discard a PLANNED draft (PLANNED-only; 409 otherwise) ──
  discardTestDrive: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/test-drive/${id}`),

  // ── Overlapping PLANNED/live sessions for a VIN in [from, to] — soft-block
  //    double-booking a car (never hard-blocks) ──
  getVehicleConflicts: (vin: string, params: { from: string; to: string; exclude_id?: number }) =>
    api.get<{ success: boolean; conflicts: VehicleConflict[] }>(`${BASE}/vehicles/${vin}/conflicts${qs(params)}`),

  // ── CRM clients (Test Drive: search + inline create) — login-gated search so
  //    consilieri without full CRM access can find existing clients ──
  searchCrmClients: (q: string, limit = 20) =>
    api.get<{ clients: CrmClient[] }>(`${BASE}/crm-clients/search${qs({ q, limit })}`),

  createCrmClient: (data: CreateCrmClientPayload) =>
    api.post<{ success: boolean; client: CrmClient }>(`${BASE}/crm-clients`, data),

  // Login-gated partial update of the selected client (fiscal identity + address
  // + contact details) from the Test Drive Client card — so a consilier can fix
  // e.g. a missing CUI without full CRM access.
  updateCrmClient: (id: number, data: Partial<CrmClient>) =>
    api.patch<{ success: boolean; client: CrmClient }>(`${BASE}/crm-clients/${id}`, data),

  // ── Marketing projects (campaign/event) — login-gated type-to-search so a
  //    consilier without marketing access can tie a Test Drive to a campaign ──
  searchMktProjects: (q: string, companyId?: number, limit = 20) =>
    api.get<{ success: boolean; projects: MktProject[] }>(
      `${BASE}/mkt-projects/search${qs({ q, company_id: companyId, limit })}`,
    ),

  // HR events (Task 15) - distinct from a marketing project/campaign; type-to-
  // search + inline create so an advisor can tie a Test Drive to an HR event
  // without full HR/marketing access. These two hit non-foi-parcurs blueprints
  // directly (not under BASE) and can 403 for an advisor lacking HR/marketing
  // permissions - callers must handle that gracefully.
  // NB: the HR-event endpoints live under their blueprints' prefixes — search is
  // on marketing_bp (/marketing) and create is on events_bp under hr_bp
  // (/hr/events). The bare /api/... paths hit the auth audit-log route (405) or
  // 404, so the full prefixed URLs are required.
  searchHrEvents: (q: string, limit = 20) =>
    api.get<{ events: HrEvent[] }>(`/marketing/api/hr-events/search${qs({ q, limit })}`),

  createHrEvent: (data: { name: string; start_date: string; end_date: string; company?: string; brand?: string }) =>
    api.post<{ success: boolean; id: number }>(`/hr/events/api/events`, data),

  // ── Driver-license OCR (Claude vision) ──
  driverLicenseOcr: (image: string) =>
    api.post<{ success: boolean; data: DriverLicenseOcrData }>(`${BASE}/driver-license/ocr`, { image }),

  getTestDrive: (id: number) =>
    api.get<{ success: boolean; contract: FoiContract; inspection: FpVehicleInspection | null }>(`${BASE}/test-drive/${id}`),

  // ── Record vehicle return → complete a test drive (PLANNED/FILLED → COMPLETED) ──
  submitTestDriveReturn: (id: number, data: ReturnTestDrivePayload) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/return`, data),

  // ── Vehicle Inspections ──
  getInspections: (vehicleId: number) =>
    api.get<{ inspections: FpVehicleInspection[] }>(`${BASE}/vehicles/${vehicleId}/inspections`),

  createInspection: (vehicleId: number, data: Partial<FpVehicleInspection>) =>
    api.post<{ success: boolean; inspection: FpVehicleInspection }>(`${BASE}/vehicles/${vehicleId}/inspections`, data),

  getLatestInspection: (vehicleId: number) =>
    api.get<{ inspection: FpVehicleInspection | null }>(`${BASE}/vehicles/${vehicleId}/inspections/latest`),

  deleteInspection: (inspectionId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/inspections/${inspectionId}`),

  // ── PDF Downloads ──
  getContractPdfUrl: (contractId: number, type: 'legal' | 'custom') =>
    `${BASE}/contracts/${contractId}/pdf/${type}`,

  // ── Monthly Foaie de Parcurs (per car × month) ──
  // AI-drafted PDF returned inline for preview — raw fetch so we get the blob
  // (the shared api client force-parses JSON). norma (l/100km) + alimentari are
  // user-entered fuel data; regenerate rebuilds + overwrites the stored copy.
  generateRouteSheetPdf: async (
    vin: string, year: number, month: number,
    opts: { regenerate?: boolean; norma?: number | null; norma_energie?: number | null; alimentari?: RouteSheetAlimentare[]; events?: RouteSheetEvent[] } = {},
  ): Promise<Blob> => {
    const res = await fetch(`${BASE}/route-sheet/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ vin, year, month, regenerate: !!opts.regenerate, norma: opts.norma ?? null, norma_energie: opts.norma_energie ?? null, alimentari: opts.alimentari ?? [], events: opts.events ?? [] }),
    })
    if (!res.ok) {
      let msg = 'Generarea foii de parcurs a eșuat'
      try { const j = await res.json(); msg = j.error || msg } catch { /* non-JSON error body */ }
      throw new Error(msg)
    }
    return res.blob()
  },

  getRouteSheetXlsxUrl: (vin: string, year: number, month: number) =>
    `${BASE}/route-sheet/xlsx${qs({ vin, year, month })}`,

  // Stored sheets for the period — badge + modal prefill (norma/alimentari).
  listRouteSheets: (companyId: number, year: number, month: number) =>
    api.get<{ success: boolean; sheets: StoredRouteSheet[] }>(
      `${BASE}/route-sheets${qs({ company_id: companyId || undefined, year, month })}`,
    ),

  // Redistribute an odometer gap by documenting a "client extra" — a synthetic
  // gap-fill session that may carry consilier / license photo / signature.
  redistributeGap: (vin: string, year: number, month: number, contracts: GapFillContract[]) =>
    api.post<{ success: boolean; inserted: number }>(
      `${BASE}/route-sheet/redistribute-gap`, { vin, year, month, contracts },
    ),

  // Close an odometer gap by tiling it across the two bounding sessions and up
  // to 3 documented middle entries. before_km + Σmiddles + after_km == gap.
  absorbGap: (payload: AbsorbGapPayload) =>
    api.post<{ success: boolean; before_id: number; after_id: number; before_km: number; after_km: number; middles_inserted: number; gap: number }>(
      `${BASE}/route-sheet/absorb-gap`, payload,
    ),

  // Distribute a gap across a window of EXISTING sessions (no new rows): each
  // allocation gives a session its new distance; the window re-tiles contiguously.
  retileGap: (payload: { vin: string; year: number; month: number; allocations: { id: number; distance: number }[] }) =>
    api.post<{ success: boolean; sessions: number; span: number }>(
      `${BASE}/route-sheet/retile-gap`, payload,
    ),

  // ── Bulk session import (tenant-scoped Excel) ──
  getSessionImportTemplateUrl: (companyId: number) =>
    `${BASE}/sessions/import-template${qs({ company_id: companyId })}`,

  importSessions: async (companyId: number, file: File): Promise<SessionImportResult> => {
    const fd = new FormData()
    fd.append('company_id', String(companyId))
    fd.append('file', file)
    const res = await fetch(`${BASE}/sessions/import`, {
      method: 'POST', credentials: 'same-origin', body: fd,
    })
    if (!res.ok) {
      let msg = 'Importul a eșuat'
      try { const j = await res.json(); msg = j.error || msg } catch { /* non-JSON */ }
      throw new Error(msg)
    }
    return res.json()
  },

  // ── Export (session list xlsx / contract PDFs zip) ──
  getExportXlsxUrl: (params: { company_id?: number; date_from?: string; date_to?: string; vin?: string }) =>
    `${BASE}/export/xlsx${qs(params)}`,

  getExportContractsZipUrl: (params: { company_id?: number; date_from?: string; date_to?: string; vin?: string }) =>
    `${BASE}/export/contracts-zip${qs(params)}`,
}
