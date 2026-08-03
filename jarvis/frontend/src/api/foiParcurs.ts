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
  PlanTestDrivePayload,
  ActivateTestDrivePayload,
  ReturnTestDrivePayload,
  VehicleConflict,
  CrmClient,
  CreateCrmClientPayload,
  DriverLicenseOcrData,
  MktProject,
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
  }) =>
    api.get<{ contracts: FoiContract[]; total: number; page: number; per_page: number }>(
      `${BASE}/contracts${qs(params ?? {})}`
    ),

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
  getVehicles: (activeOnly = true) =>
    api.get<{ vehicles: FpVehicle[] }>(`${BASE}/vehicles`, { active_only: String(activeOnly) }),

  // Full vehicle incl. document blobs — the list is lean, so the edit form
  // fetches the docs here on demand.
  getVehicle: (id: number) =>
    api.get<{ success: boolean; vehicle: FpVehicle }>(`${BASE}/vehicles/${id}`),

  createVehicle: (data: { vin: string; registration_number?: string; car_id?: string; mark: string; brand?: string; model: string; color?: string; fuel_type: string; fuel_tank_capacity_liters?: number | null; battery_capacity_kwh?: number | null; odometer_km?: number | null; norma_combustibil?: number | null; norma_energie?: number | null; category?: string | null; company_id?: number; vignette_valid_until?: string; itp_valid_until?: string; insurance_valid_until?: string; insurance_doc?: string; talon_doc?: string; civ_doc?: string; registration_doc?: string; offer_doc?: string }) =>
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

  // ── Brands for a company (from the company_brands catalog, not dept structure) ──
  getBrands: (companyId: number) =>
    api.get<{ success: boolean; brands: string[] }>(`${BASE}/brands/${companyId}`),

  // ── Per company+brand dealer config (review link + contact for the email) ──
  getDealerConfig: (companyId: number) =>
    api.get<{ success: boolean; configs: { brand_id: number; brand_name: string; review_url: string | null; address: string | null; phone: string | null; email: string | null; show_in_foi_parcurs: boolean; general_conditions: string | null }[] }>(
      `${BASE}/dealer-config/${companyId}`,
    ),

  updateDealerConfig: (companyId: number, brandId: number, data: { review_url?: string; address?: string; phone?: string; email?: string; show_in_foi_parcurs?: boolean; general_conditions?: string }) =>
    api.put<{ success: boolean }>(`${BASE}/dealer-config/${companyId}/${brandId}`, data),

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

  // ── Company Location Config ──
  getCompanyConfig: (companyId: number) =>
    api.get<{ config: { company_id: number; base_location: string; td_radius_km: number; comodat_avg_km: number } }>(
      `${BASE}/company-config/${companyId}`
    ),

  updateCompanyConfig: (companyId: number, data: { base_location: string; td_radius_km: number; comodat_avg_km: number }) =>
    api.put<{ success: boolean }>(`${BASE}/company-config/${companyId}`, data),

  // ── Test Drive Form ──
  submitTestDrive: (data: TestDriveFormPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Per company+vehicle-brand general-conditions text ('' when unset) ──
  getGeneralConditions: (companyId: number, vin: string) =>
    api.get<{ success: boolean; text: string; brand: string }>(
      `${BASE}/general-conditions?company_id=${companyId}&vin=${encodeURIComponent(vin)}`,
    ),

  // ── Plan a draft TD (status: 'PLANNED') — same endpoint, signature/GDPR/PDF
  //    deferred to activation ──
  planTestDrive: (data: PlanTestDrivePayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Activate a PLANNED draft → FILLED (client signature required) ──
  activateTestDrive: (id: number, data: ActivateTestDrivePayload) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/activate`, data),

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

  // ── Marketing projects (campaign/event) — login-gated type-to-search so a
  //    consilier without marketing access can tie a Test Drive to a campaign ──
  searchMktProjects: (q: string, companyId?: number, limit = 20) =>
    api.get<{ success: boolean; projects: MktProject[] }>(
      `${BASE}/mkt-projects/search${qs({ q, company_id: companyId, limit })}`,
    ),

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
