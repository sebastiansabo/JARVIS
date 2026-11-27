// Pure search/sort/filter mapping logic for the Parc register table,
// extracted out of Parc.tsx so it can be unit-tested without mounting React
// (Parc.helpers.test.ts). No side effects, no imports from '../../api' —
// just URLSearchParams <-> plain-object mapping and small derivations.
import type { ListVehiclesFilters, ParcSortDir, ParcVehicleRow } from '@/api/logistics'

export interface ParcFiltersState {
  q: string
  location_id: string // kept as the <select> string value; '' = "Toate"
  destinatie: string
  etapa: string
  predare: string
  sort: string
  dir: ParcSortDir
}

export const EMPTY_PARC_FILTERS: ParcFiltersState = {
  q: '',
  location_id: '',
  destinatie: '',
  etapa: '',
  predare: '',
  sort: '',
  dir: 'asc',
}

/** Read filters+sort back out of a querystring (e.g. `location.search`,
 * `?q=AW&etapa=%C3%8En+stoc&sort=comanda&dir=desc`) -- the "Back restores
 * filters + sort" requirement. Unknown/missing keys fall back to empty. */
export function parseParcFiltersFromSearch(search: string): ParcFiltersState {
  const params = new URLSearchParams(search)
  return {
    q: params.get('q') ?? '',
    location_id: params.get('location_id') ?? '',
    destinatie: params.get('destinatie') ?? '',
    etapa: params.get('etapa') ?? '',
    predare: params.get('predare') ?? '',
    sort: params.get('sort') ?? '',
    dir: params.get('dir') === 'desc' ? 'desc' : 'asc',
  }
}

/** The inverse: current filters+sort -> a URLSearchParams with only the
 * non-empty keys set (so the querystring stays clean, e.g. no `dir=asc` when
 * there's no `sort` to apply it to). Used both to sync the address bar and
 * to build the "preserve search/sort" link to the detail page. */
export function buildParcSearchParams(filters: ParcFiltersState): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.location_id) params.set('location_id', filters.location_id)
  if (filters.destinatie) params.set('destinatie', filters.destinatie)
  if (filters.etapa) params.set('etapa', filters.etapa)
  if (filters.predare) params.set('predare', filters.predare)
  if (filters.sort) {
    params.set('sort', filters.sort)
    if (filters.dir === 'desc') params.set('dir', filters.dir)
  }
  return params
}

/** Filters-state -> the shape the API client/backend expects (location_id
 * coerced to a number; dir only sent alongside a sort column). */
export function toListVehiclesFilters(filters: ParcFiltersState): ListVehiclesFilters {
  const result: ListVehiclesFilters = {}
  if (filters.q) result.q = filters.q
  if (filters.location_id) result.location_id = Number(filters.location_id)
  if (filters.destinatie) result.destinatie = filters.destinatie
  if (filters.etapa) result.etapa = filters.etapa
  if (filters.predare) result.predare = filters.predare
  if (filters.sort) {
    result.sort = filters.sort
    result.dir = filters.dir
  }
  return result
}

/** Clicking a column header: same column -> flip direction; different
 * column -> that column, ascending. */
export function nextSort(
  current: Pick<ParcFiltersState, 'sort' | 'dir'>,
  column: string,
): { sort: string; dir: ParcSortDir } {
  if (current.sort !== column) return { sort: column, dir: 'asc' }
  return { sort: column, dir: current.dir === 'asc' ? 'desc' : 'asc' }
}

export interface LocationOption {
  id: number
  name: string
}

/** Distinct {id, name} pairs present in a set of rows, sorted by name --
 * used to populate the Locație filter dropdown from whatever's already
 * loaded (no separate /locations endpoint in this phase). Rows with no
 * location (location_id/locatie both null -- not yet positioned) are
 * excluded, since they can't be filtered on. */
export function distinctLocationOptions(rows: ParcVehicleRow[]): LocationOption[] {
  const byId = new Map<number, string>()
  for (const row of rows) {
    if (row.location_id != null && row.locatie) {
      byId.set(row.location_id, row.locatie)
    }
  }
  return Array.from(byId, ([id, name]) => ({ id, name })).sort((a, b) =>
    a.name.localeCompare(b.name),
  )
}

/** Fetch-client error shape is `{status, data: {error?}, message}` (see
 * api/client.ts ApiError) -- surface the backend's message, else the
 * generic Error message, else a RO fallback. Never throws. */
export function extractErrorMessage(err: unknown): string {
  if (err && typeof err === 'object') {
    const asRecord = err as { data?: unknown; message?: unknown }
    const data = asRecord.data
    if (data && typeof data === 'object' && 'error' in data) {
      const backendError = (data as { error?: unknown }).error
      if (backendError) return String(backendError)
    }
    if (typeof asRecord.message === 'string' && asRecord.message) {
      return asRecord.message
    }
  }
  return 'A apărut o eroare necunoscută.'
}
