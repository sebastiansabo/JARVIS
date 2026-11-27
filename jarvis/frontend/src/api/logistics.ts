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

// ── Kanban board (GET /api/logistics/board) ─────────────────────────────
// Mirrors jarvis/logistics/repositories/task_repository.py::get_board
// response shape: a dict keyed by the 4 fixed-order statuses (BOARD_STATUSES
// there / KANBAN_STATUSES in Kanban.helpers.ts here), each a list of card
// dicts. Card shape is exactly these 9 fields -- Task 8's move handler
// relies on `id` (plus the column a card is currently rendered under for
// its "current status"), so this must not drift from the backend's SELECT.
export interface KanbanCard {
  id: number
  title: string
  type: string
  vehicle_model: string | null
  order_ref: string
  location_name: string | null
  position_code: string | null
  assignee: string | null
  due_at: string | null
}

export type KanbanBoardStatus = 'De făcut' | 'În lucru' | 'Blocat' | 'Finalizat'

export type KanbanBoardDict = Partial<Record<KanbanBoardStatus, KanbanCard[]>>

export interface GetBoardFilters {
  q?: string
  location_id?: number
  assignee?: string
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

  // Same company-scoping note as listVehicles -- see
  // jarvis/logistics/routes/tasks.py::get_board / _user_company_id.
  getBoard: (filters: GetBoardFilters = {}) => {
    const params: Record<string, string> = {}
    if (filters.q) params.q = filters.q
    if (filters.location_id != null) params.location_id = String(filters.location_id)
    if (filters.assignee) params.assignee = filters.assignee
    return api.get<{ board: KanbanBoardDict }>('/api/logistics/board', params)
  },
}
