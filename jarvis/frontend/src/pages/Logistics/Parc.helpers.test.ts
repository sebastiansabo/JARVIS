import { describe, it, expect } from 'vitest'
import {
  EMPTY_PARC_FILTERS,
  parseParcFiltersFromSearch,
  buildParcSearchParams,
  toListVehiclesFilters,
  nextSort,
  distinctLocationOptions,
  extractErrorMessage,
  type ParcFiltersState,
} from './Parc.helpers'
import type { ParcVehicleRow } from '@/api/logistics'

describe('parseParcFiltersFromSearch', () => {
  it('reads every filter + sort key out of a querystring', () => {
    const search = '?q=AW-TEST&location_id=3&destinatie=Intern&etapa=%C3%8En+stoc&predare=Blocat&sort=comanda&dir=desc'
    expect(parseParcFiltersFromSearch(search)).toEqual({
      q: 'AW-TEST',
      location_id: '3',
      destinatie: 'Intern',
      etapa: 'În stoc',
      predare: 'Blocat',
      sort: 'comanda',
      dir: 'desc',
    })
  })

  it('falls back to EMPTY_PARC_FILTERS-equivalent values for an empty querystring', () => {
    expect(parseParcFiltersFromSearch('')).toEqual(EMPTY_PARC_FILTERS)
  })

  it('defaults dir to asc for anything other than the literal "desc"', () => {
    expect(parseParcFiltersFromSearch('?sort=comanda&dir=bogus').dir).toBe('asc')
    expect(parseParcFiltersFromSearch('?sort=comanda').dir).toBe('asc')
  })
})

describe('buildParcSearchParams', () => {
  it('round-trips through parseParcFiltersFromSearch', () => {
    const filters: ParcFiltersState = {
      q: 'VIN123', location_id: '7', destinatie: 'AAP', etapa: 'Expunere',
      predare: 'Predat', sort: 'vehicul', dir: 'desc',
    }
    const roundTripped = parseParcFiltersFromSearch(`?${buildParcSearchParams(filters).toString()}`)
    expect(roundTripped).toEqual(filters)
  })

  it('omits dir when there is no sort column, so the querystring stays clean', () => {
    const params = buildParcSearchParams({ ...EMPTY_PARC_FILTERS, dir: 'desc' })
    expect(params.has('dir')).toBe(false)
    expect(params.toString()).toBe('')
  })

  it('omits dir=asc (the default) even when a sort column is set', () => {
    const params = buildParcSearchParams({ ...EMPTY_PARC_FILTERS, sort: 'comanda', dir: 'asc' })
    expect(params.get('sort')).toBe('comanda')
    expect(params.has('dir')).toBe(false)
  })
})

describe('toListVehiclesFilters', () => {
  it('maps only the non-empty fields, coercing location_id to a number', () => {
    const filters: ParcFiltersState = {
      ...EMPTY_PARC_FILTERS, q: 'AW-1', location_id: '5', sort: 'etapa_parc', dir: 'desc',
    }
    expect(toListVehiclesFilters(filters)).toEqual({
      q: 'AW-1', location_id: 5, sort: 'etapa_parc', dir: 'desc',
    })
  })

  it('sends neither sort nor dir when no column is selected', () => {
    expect(toListVehiclesFilters(EMPTY_PARC_FILTERS)).toEqual({})
  })
})

describe('nextSort', () => {
  it('starts a new column ascending', () => {
    expect(nextSort({ sort: '', dir: 'asc' }, 'comanda')).toEqual({ sort: 'comanda', dir: 'asc' })
    expect(nextSort({ sort: 'vehicul', dir: 'desc' }, 'comanda')).toEqual({ sort: 'comanda', dir: 'asc' })
  })

  it('flips direction when clicking the already-active column', () => {
    expect(nextSort({ sort: 'comanda', dir: 'asc' }, 'comanda')).toEqual({ sort: 'comanda', dir: 'desc' })
    expect(nextSort({ sort: 'comanda', dir: 'desc' }, 'comanda')).toEqual({ sort: 'comanda', dir: 'asc' })
  })
})

describe('distinctLocationOptions', () => {
  const row = (overrides: Partial<ParcVehicleRow>): ParcVehicleRow => ({
    id: 1, vehicul: 'Audi A4', comanda: 'AW-1', locatie: 'Rampă Nord', pozitie: 'A-01',
    destinatie: 'Intern', etapa_parc: 'În stoc', predare: 'În așteptare', vin: null,
    location_id: 1, position_id: 1, ...overrides,
  })

  it('dedupes by location_id and sorts by name', () => {
    const rows = [
      row({ id: 1, location_id: 2, locatie: 'Rampă Sud' }),
      row({ id: 2, location_id: 1, locatie: 'Atelier' }),
      row({ id: 3, location_id: 2, locatie: 'Rampă Sud' }), // same location as row 1
    ]
    expect(distinctLocationOptions(rows)).toEqual([
      { id: 1, name: 'Atelier' },
      { id: 2, name: 'Rampă Sud' },
    ])
  })

  it('excludes rows with no location assigned yet', () => {
    const rows = [row({ location_id: null, locatie: null })]
    expect(distinctLocationOptions(rows)).toEqual([])
  })
})

describe('extractErrorMessage', () => {
  it('prefers the backend error message (ApiError-shaped: {data: {error}})', () => {
    expect(extractErrorMessage({ status: 400, data: { error: 'company_id lipsă' }, message: 'API Error 400' }))
      .toBe('company_id lipsă')
  })

  it('falls back to .message when there is no data.error', () => {
    expect(extractErrorMessage(new Error('Network error'))).toBe('Network error')
  })

  it('falls back to a RO-language default for anything unrecognizable', () => {
    expect(extractErrorMessage('plain string')).toBe('A apărut o eroare necunoscută.')
    expect(extractErrorMessage(null)).toBe('A apărut o eroare necunoscută.')
  })
})
