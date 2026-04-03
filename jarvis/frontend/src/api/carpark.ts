import { api } from './client'
import type {
  Vehicle,
  VehicleCatalogItem,
  VehiclePhoto,
  VehicleCost,
  VehicleRevenue,
  Location,
  StatusCount,
  FilterOptions,
  CatalogFilters,
  PaginatedResponse,
  StatusHistoryEntry,
  ModificationEntry,
  CostTotals,
  RevenueTotals,
  Profitability,
  PricingRule,
  PricingHistoryEntry,
  Promotion,
  FloorPrice,
  SimulationResult,
  RuleExecutionResult,
  AgingVehicle,
  PublishingPlatform,
  VehicleListing,
  SyncLogEntry,
  DashboardData,
  VehicleLink,
  LinkSearchResult,
  LinkedEntityType,
  PromotionVehicle,
  VehicleCostLine,
} from '../types/carpark'

export const carparkApi = {
  // ── Catalog ──────────────────────────────────────────────
  getCatalog: (filters: CatalogFilters, page = 1, perPage = 25, sort = 'acquisition_date', order = 'desc') => {
    const params: Record<string, string> = {
      page: String(page),
      per_page: String(perPage),
      sort,
      order,
    }
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined && v !== '') params[k] = v
    }
    return api.get<PaginatedResponse<VehicleCatalogItem>>('/api/carpark/vehicles', params)
  },

  getStatusCounts: () =>
    api.get<{ counts: StatusCount[] }>('/api/carpark/vehicles/status-counts'),

  getFilterOptions: () =>
    api.get<FilterOptions>('/api/carpark/vehicles/filter-options'),

  // ── Single vehicle ───────────────────────────────────────
  getVehicle: (id: number) =>
    api.get<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${id}`),

  createVehicle: (data: Partial<Vehicle>) =>
    api.post<{ vehicle: Vehicle }>('/api/carpark/vehicles', data),

  updateVehicle: (id: number, data: Partial<Vehicle>) =>
    api.put<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${id}`, data),

  deleteVehicle: (id: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/vehicles/${id}`),

  // ── Status ───────────────────────────────────────────────
  changeStatus: (id: number, status: string, notes?: string) =>
    api.put<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${id}/status`, { status, notes }),

  getStatusHistory: (id: number) =>
    api.get<{ history: StatusHistoryEntry[] }>(`/api/carpark/vehicles/${id}/status-history`),

  // ── Modifications audit ──────────────────────────────────
  getModifications: (id: number) =>
    api.get<{ modifications: ModificationEntry[] }>(`/api/carpark/vehicles/${id}/modifications`),

  // ── VIN check ────────────────────────────────────────────
  checkVin: (vin: string) =>
    api.get<{ exists: boolean; vehicle_id?: number }>('/api/carpark/vehicles/check-vin', { vin }),

  // ── Photos ───────────────────────────────────────────────
  getPhotos: (vehicleId: number) =>
    api.get<{ photos: VehiclePhoto[] }>(`/api/carpark/vehicles/${vehicleId}/photos`),

  addPhoto: (vehicleId: number, photo: Partial<VehiclePhoto>) =>
    api.post<{ photo: VehiclePhoto }>(`/api/carpark/vehicles/${vehicleId}/photos`, photo),

  addPhotoBatch: (vehicleId: number, photos: Partial<VehiclePhoto>[]) =>
    api.post<{ photos: VehiclePhoto[] }>(`/api/carpark/vehicles/${vehicleId}/photos`, { photos }),

  updatePhoto: (photoId: number, data: Partial<VehiclePhoto>) =>
    api.put<{ photo: VehiclePhoto }>(`/api/carpark/photos/${photoId}`, data),

  reorderPhotos: (vehicleId: number, photoIds: number[]) =>
    api.put<{ success: boolean }>(`/api/carpark/vehicles/${vehicleId}/photos/reorder`, { photo_ids: photoIds }),

  deletePhoto: (photoId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/photos/${photoId}`),

  deleteAllPhotos: (vehicleId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/vehicles/${vehicleId}/photos`),

  // ── Locations ────────────────────────────────────────────
  getLocations: () =>
    api.get<{ locations: Location[] }>('/api/carpark/locations'),

  createLocation: (data: Partial<Location>) =>
    api.post<{ location: Location }>('/api/carpark/locations', data),

  updateLocation: (id: number, data: Partial<Location>) =>
    api.put<{ location: Location }>(`/api/carpark/locations/${id}`, data),

  // ── Costs ──────────────────────────────────────────────
  getCosts: (vehicleId: number) =>
    api.get<{ costs: VehicleCost[] }>(`/api/carpark/vehicles/${vehicleId}/costs`),

  createCost: (vehicleId: number, data: Partial<VehicleCost>) =>
    api.post<{ cost: VehicleCost }>(`/api/carpark/vehicles/${vehicleId}/costs`, data),

  updateCost: (costId: number, data: Partial<VehicleCost>) =>
    api.put<{ cost: VehicleCost }>(`/api/carpark/costs/${costId}`, data),

  deleteCost: (costId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/costs/${costId}`),

  getCostTotals: (vehicleId: number) =>
    api.get<CostTotals>(`/api/carpark/vehicles/${vehicleId}/costs/totals`),

  // ── Cost Lines ───────────────────────────────────────────
  getCostLines: (vehicleId: number) =>
    api.get<{ cost_lines: VehicleCostLine[] }>(`/api/carpark/vehicles/${vehicleId}/cost-lines`),

  createCostLine: (vehicleId: number, data: Partial<VehicleCostLine>) =>
    api.post<{ success: boolean; id: number }>(`/api/carpark/vehicles/${vehicleId}/cost-lines`, data),

  updateCostLine: (lineId: number, data: Partial<VehicleCostLine>) =>
    api.put<{ success: boolean }>(`/api/carpark/cost-lines/${lineId}`, data),

  deleteCostLine: (lineId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/cost-lines/${lineId}`),

  getLineCosts: (lineId: number) =>
    api.get<{ costs: VehicleCost[] }>(`/api/carpark/cost-lines/${lineId}/costs`),

  createLineCost: (lineId: number, data: Partial<VehicleCost>) =>
    api.post<{ success: boolean; id: number }>(`/api/carpark/cost-lines/${lineId}/costs`, data),

  updateLineCost: (costId: number, data: Partial<VehicleCost>) =>
    api.put<{ success: boolean }>(`/api/carpark/line-costs/${costId}`, data),

  deleteLineCost: (costId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/line-costs/${costId}`),

  linkCostInvoice: (costId: number, invoiceId: number | null) =>
    api.put<{ success: boolean }>(`/api/carpark/line-costs/${costId}/link-invoice`, { invoice_id: invoiceId }),

  // ── Revenues ───────────────────────────────────────────
  getRevenues: (vehicleId: number) =>
    api.get<{ revenues: VehicleRevenue[] }>(`/api/carpark/vehicles/${vehicleId}/revenues`),

  createRevenue: (vehicleId: number, data: Partial<VehicleRevenue>) =>
    api.post<{ revenue: VehicleRevenue }>(`/api/carpark/vehicles/${vehicleId}/revenues`, data),

  updateRevenue: (revenueId: number, data: Partial<VehicleRevenue>) =>
    api.put<{ revenue: VehicleRevenue }>(`/api/carpark/revenues/${revenueId}`, data),

  deleteRevenue: (revenueId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/revenues/${revenueId}`),

  getRevenueTotals: (vehicleId: number) =>
    api.get<RevenueTotals>(`/api/carpark/vehicles/${vehicleId}/revenues/totals`),

  // ── Profitability ──────────────────────────────────────
  getProfitability: (vehicleId: number) =>
    api.get<Profitability>(`/api/carpark/vehicles/${vehicleId}/profitability`),

  // ── Pricing Rules ────────────────────────────────────
  getPricingRules: (activeOnly = false) =>
    api.get<{ rules: PricingRule[] }>('/api/carpark/pricing/rules', activeOnly ? { active_only: 'true' } : undefined),

  getPricingRule: (ruleId: number) =>
    api.get<{ rule: PricingRule }>(`/api/carpark/pricing/rules/${ruleId}`),

  createPricingRule: (data: Partial<PricingRule>) =>
    api.post<{ rule: PricingRule }>('/api/carpark/pricing/rules', data),

  updatePricingRule: (ruleId: number, data: Partial<PricingRule>) =>
    api.put<{ rule: PricingRule }>(`/api/carpark/pricing/rules/${ruleId}`, data),

  deletePricingRule: (ruleId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/pricing/rules/${ruleId}`),

  executePricingRule: (ruleId: number, dryRun = false) =>
    api.post<RuleExecutionResult>(`/api/carpark/pricing/rules/${ruleId}/execute`, { dry_run: dryRun }),

  // ── Pricing Simulation ───────────────────────────────
  simulatePricing: (params: { vehicle_id?: number; rule_id?: number }) =>
    api.post<{ simulations: SimulationResult[] }>('/api/carpark/pricing/simulate', params),

  // ── Floor Price ──────────────────────────────────────
  getFloorPrice: (vehicleId: number) =>
    api.get<FloorPrice>(`/api/carpark/vehicles/${vehicleId}/floor-price`),

  // ── Pricing History ──────────────────────────────────
  getPricingHistory: (vehicleId: number) =>
    api.get<{ history: PricingHistoryEntry[] }>(`/api/carpark/vehicles/${vehicleId}/pricing-history`),

  // ── Vehicle Promotions ───────────────────────────────
  getVehiclePromotions: (vehicleId: number) =>
    api.get<{ promotions: Promotion[] }>(`/api/carpark/vehicles/${vehicleId}/promotions`),

  // ── Promotions ───────────────────────────────────────
  getPromotions: (activeOnly = false) =>
    api.get<{ promotions: Promotion[] }>('/api/carpark/promotions', activeOnly ? { active_only: 'true' } : undefined),

  getPromotion: (promoId: number) =>
    api.get<{ promotion: Promotion }>(`/api/carpark/promotions/${promoId}`),

  createPromotion: (data: Partial<Promotion>) =>
    api.post<{ promotion: Promotion }>('/api/carpark/promotions', data),

  updatePromotion: (promoId: number, data: Partial<Promotion>) =>
    api.put<{ promotion: Promotion }>(`/api/carpark/promotions/${promoId}`, data),

  deletePromotion: (promoId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/promotions/${promoId}`),

  // ── Aging Alerts ─────────────────────────────────────
  getAgingVehicles: (minDays?: number) =>
    api.get<{ vehicles: AgingVehicle[]; count: number }>('/api/carpark/pricing/aging', minDays ? { min_days: String(minDays) } : undefined),

  // ── Publishing Platforms ─────────────────────────────
  getPlatforms: (activeOnly = false) =>
    api.get<{ platforms: PublishingPlatform[] }>('/api/carpark/platforms', activeOnly ? { active_only: 'true' } : undefined),

  getPlatform: (platformId: number) =>
    api.get<{ platform: PublishingPlatform }>(`/api/carpark/platforms/${platformId}`),

  createPlatform: (data: Partial<PublishingPlatform>) =>
    api.post<{ platform: PublishingPlatform }>('/api/carpark/platforms', data),

  updatePlatform: (platformId: number, data: Partial<PublishingPlatform>) =>
    api.put<{ platform: PublishingPlatform }>(`/api/carpark/platforms/${platformId}`, data),

  deletePlatform: (platformId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/platforms/${platformId}`),

  // ── Vehicle Listings ─────────────────────────────────
  getVehicleListings: (vehicleId: number) =>
    api.get<{ listings: VehicleListing[] }>(`/api/carpark/vehicles/${vehicleId}/listings`),

  publishVehicle: (vehicleId: number, platformId: number, expiresAt?: string) =>
    api.post<{ listing: VehicleListing; action: string }>(`/api/carpark/vehicles/${vehicleId}/publish`, { platform_id: platformId, expires_at: expiresAt }),

  publishVehicleAll: (vehicleId: number, expiresAt?: string) =>
    api.post<{ results: Array<{ platform_id: number; platform_name: string; action: string }> }>(`/api/carpark/vehicles/${vehicleId}/publish-all`, { expires_at: expiresAt }),

  updateListing: (listingId: number, data: Partial<VehicleListing>) =>
    api.put<{ listing: VehicleListing }>(`/api/carpark/listings/${listingId}`, data),

  activateListing: (listingId: number) =>
    api.post<{ listing: VehicleListing }>(`/api/carpark/listings/${listingId}/activate`, {}),

  deactivateListing: (listingId: number) =>
    api.post<{ listing: VehicleListing }>(`/api/carpark/listings/${listingId}/deactivate`, {}),

  deactivateAllListings: (vehicleId: number) =>
    api.post<{ deactivated: VehicleListing[]; count: number }>(`/api/carpark/vehicles/${vehicleId}/deactivate-all`, {}),

  syncListing: (listingId: number) =>
    api.post<{ listing: VehicleListing }>(`/api/carpark/listings/${listingId}/sync`, {}),

  syncAllStats: () =>
    api.post<{ synced: number; errors: number }>('/api/carpark/publishing/sync', {}),

  // ── Sync Log ─────────────────────────────────────────
  getSyncLog: (vehicleId: number) =>
    api.get<{ log: SyncLogEntry[] }>(`/api/carpark/vehicles/${vehicleId}/sync-log`),

  // ── Analytics / Dashboard ──────────────────────────────
  getDashboard: (period = 90) =>
    api.get<DashboardData>('/api/carpark/analytics/dashboard', { period: String(period) }),

  // ── Vehicle Links ─────────────────────────────────────
  getVehicleLinks: (vehicleId: number, entityType?: LinkedEntityType) =>
    api.get<{ links: VehicleLink[] }>(`/api/carpark/vehicles/${vehicleId}/links`, entityType ? { entity_type: entityType } : undefined),

  linkEntity: (vehicleId: number, data: { entity_type: LinkedEntityType; entity_id: number; notes?: string }) =>
    api.post<{ link: VehicleLink }>(`/api/carpark/vehicles/${vehicleId}/links`, data),

  unlinkEntity: (vehicleId: number, linkId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/vehicles/${vehicleId}/links/${linkId}`),

  searchLinkableEntities: (entityType: LinkedEntityType, q = '', limit = 20) =>
    api.get<{ results: LinkSearchResult[] }>(`/api/carpark/link-search/${entityType}`, { q, limit: String(limit) }),

  // ── Promotion Vehicles ─────────────────────────────────
  getPromotionVehicles: (promoId: number) =>
    api.get<{ vehicles: PromotionVehicle[]; count: number }>(`/api/carpark/promotions/${promoId}/vehicles`),

  addPromotionVehicles: (promoId: number, vehicleIds: number[]) =>
    api.post<{ added: number }>(`/api/carpark/promotions/${promoId}/vehicles`, { vehicle_ids: vehicleIds }),

  removePromotionVehicle: (promoId: number, vehicleId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/promotions/${promoId}/vehicles/${vehicleId}`),
}
