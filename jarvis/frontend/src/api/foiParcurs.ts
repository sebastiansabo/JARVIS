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
  VehicleConflict,
  CrmClient,
  CreateCrmClientPayload,
  DriverLicenseOcrData,
} from '../types/foiParcurs'

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

  createVehicle: (data: { vin: string; registration_number?: string; car_id?: string; mark: string; brand?: string; model: string; color?: string; fuel_type: string; fuel_tank_capacity_liters?: number | null; battery_capacity_kwh?: number | null; odometer_km?: number | null; company_id?: number; vignette_valid_until?: string; itp_valid_until?: string; insurance_valid_until?: string; insurance_doc?: string; talon_doc?: string; civ_doc?: string; registration_doc?: string; offer_doc?: string }) =>
    api.post<{ success: boolean; vehicle: FpVehicle }>(`${BASE}/vehicles`, data),

  updateVehicle: (id: number, data: Partial<FpVehicle>) =>
    api.put<{ success: boolean; vehicle: FpVehicle }>(`${BASE}/vehicles/${id}`, data),

  deleteVehicle: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/vehicles/${id}`),

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

  // ── Driver-license OCR (Claude vision) ──
  driverLicenseOcr: (image: string) =>
    api.post<{ success: boolean; data: DriverLicenseOcrData }>(`${BASE}/driver-license/ocr`, { image }),

  getTestDrive: (id: number) =>
    api.get<{ success: boolean; contract: FoiContract; inspection: FpVehicleInspection | null }>(`${BASE}/test-drive/${id}`),

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

  // ── Export (session list xlsx / contract PDFs zip) ──
  getExportXlsxUrl: (params: { company_id?: number; date_from?: string; date_to?: string; vin?: string }) =>
    `${BASE}/export/xlsx${qs(params)}`,

  getExportContractsZipUrl: (params: { company_id?: number; date_from?: string; date_to?: string; vin?: string }) =>
    `${BASE}/export/contracts-zip${qs(params)}`,
}
