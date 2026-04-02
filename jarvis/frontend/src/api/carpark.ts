import { api } from './client'
import type {
  Vehicle,
  VehicleCatalogItem,
  VehiclePhoto,
  Location,
  StatusCount,
  FilterOptions,
  CatalogFilters,
  PaginatedResponse,
  StatusHistoryEntry,
  ModificationEntry,
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
}
