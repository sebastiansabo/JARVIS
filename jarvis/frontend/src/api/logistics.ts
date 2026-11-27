import { api } from './client'

// ── Parc register (GET /api/logistics/vehicles) ────────────────────────
// Mirrors jarvis/logistics/repositories/vehicle_repository.py::list_vehicles
// row shape: the 8 display columns (vehicul/comanda/locatie/pozitie/
// destinatie/etapa_parc/predare/vin) plus the raw ids a row-click needs.
export interface ParcVehicleRow {
  id: number
  vehicul: string | null
  comanda: string
  locatie: string | null
  pozitie: string | null
  destinatie: string | null
  etapa_parc: string
  predare: string
  vin: string | null
  location_id: number | null
  position_id: number | null
}

export type ParcSortDir = 'asc' | 'desc'

// Keep in sync with _VEHICLE_SORT_COLUMNS in vehicle_repository.py.
export type ParcSortColumn =
  | 'vehicul'
  | 'comanda'
  | 'locatie'
  | 'pozitie'
  | 'destinatie'
  | 'etapa_parc'
  | 'predare'
  | 'vin'

export interface ListVehiclesFilters {
  q?: string
  location_id?: number
  destinatie?: string
  etapa?: string
  predare?: string
  sort?: ParcSortColumn | string
  dir?: ParcSortDir
}

export const logisticsApi = {
  // company_id is never sent from the client -- the backend resolves the
  // acting company from current_user (see jarvis/logistics/routes/vehicles.py).
  listVehicles: (filters: ListVehiclesFilters = {}) => {
    const params: Record<string, string> = {}
    if (filters.q) params.q = filters.q
    if (filters.location_id != null) params.location_id = String(filters.location_id)
    if (filters.destinatie) params.destinatie = filters.destinatie
    if (filters.etapa) params.etapa = filters.etapa
    if (filters.predare) params.predare = filters.predare
    if (filters.sort) params.sort = filters.sort
    if (filters.dir) params.dir = filters.dir
    return api.get<{ vehicles: ParcVehicleRow[] }>('/api/logistics/vehicles', params)
  },
}
