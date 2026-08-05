import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
vi.mock('./client', () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a), put: (...a: unknown[]) => put(...a) } }))

import { fieldSalesApi } from './fieldSales'

describe('fieldSalesApi daily-driver wrappers', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); put.mockReset(); get.mockResolvedValue({}); post.mockResolvedValue({}); put.mockResolvedValue({}) })

  it('getTodayVisits hits the today route with the date param', async () => {
    await fieldSalesApi.getTodayVisits('2026-08-04')
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/today', { date: '2026-08-04' })
  })

  it('getMyVisits hits the mine route with date range params', async () => {
    await fieldSalesApi.getMyVisits('2026-08-01', '2026-08-31')
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/mine', { date_from: '2026-08-01', date_to: '2026-08-31' })
  })

  it('checkin posts coords to the checkin route', async () => {
    await fieldSalesApi.checkin(9, { lat: 46.7, lng: 23.6 })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits/9/checkin', { lat: 46.7, lng: 23.6 })
  })

  it('checkout posts the outcome', async () => {
    await fieldSalesApi.checkout(9, { outcome: 'completed' })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits/9/checkout', { outcome: 'completed' })
  })

  it('addNote posts the raw note', async () => {
    await fieldSalesApi.addNote(9, { raw_note: 'ok' })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits/9/note', { raw_note: 'ok' })
  })

  it('getClient360 fetches the 360 route', async () => {
    await fieldSalesApi.getClient360(760)
    expect(get).toHaveBeenCalledWith('/api/field-sales/clients/760/360')
  })

  it('refreshFiscal posts to the refresh-fiscal route', async () => {
    await fieldSalesApi.refreshFiscal(760)
    expect(post).toHaveBeenCalledWith('/api/field-sales/clients/760/refresh-fiscal')
  })

  it('createVisit forwards planned_end_time', async () => {
    await fieldSalesApi.createVisit({ client_id: 1, planned_date: '2026-08-05', planned_time: '09:00', planned_end_time: '10:00' })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits', { client_id: 1, planned_date: '2026-08-05', planned_time: '09:00', planned_end_time: '10:00' })
  })

  it('createVisit forwards company_id (the active tenant the visit belongs to)', async () => {
    await fieldSalesApi.createVisit({ client_id: 1, planned_date: '2026-08-05', company_id: 20 })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits', { client_id: 1, planned_date: '2026-08-05', company_id: 20 })
  })

  it('updateVisit forwards planned_end_time', async () => {
    await fieldSalesApi.updateVisit(9, { planned_time: '09:00', planned_end_time: '11:00' })
    expect(put).toHaveBeenCalledWith('/api/field-sales/visits/9', { planned_time: '09:00', planned_end_time: '11:00' })
  })
})

describe('fieldSalesApi company-scoping wrappers', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); put.mockReset(); get.mockResolvedValue({}); post.mockResolvedValue({}); put.mockResolvedValue({}) })

  it('getFieldSalesCompanies hits the companies route', async () => {
    await fieldSalesApi.getFieldSalesCompanies()
    expect(get).toHaveBeenCalledWith('/api/field-sales/companies')
  })

  it('getTodayVisits includes company_id when companyId > 0', async () => {
    await fieldSalesApi.getTodayVisits('2026-08-04', 3)
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/today', { date: '2026-08-04', company_id: '3' })
  })

  it('getTodayVisits omits company_id when companyId is 0', async () => {
    await fieldSalesApi.getTodayVisits('2026-08-04', 0)
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/today', { date: '2026-08-04' })
  })

  it('getTodayVisits omits company_id when companyId is undefined', async () => {
    await fieldSalesApi.getTodayVisits('2026-08-04')
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/today', { date: '2026-08-04' })
  })

  it('getMyVisits includes company_id when companyId > 0', async () => {
    await fieldSalesApi.getMyVisits('2026-08-01', '2026-08-31', 5)
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/mine', { date_from: '2026-08-01', date_to: '2026-08-31', company_id: '5' })
  })

  it('getMyVisits omits company_id when not provided', async () => {
    await fieldSalesApi.getMyVisits('2026-08-01', '2026-08-31')
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/mine', { date_from: '2026-08-01', date_to: '2026-08-31' })
  })

  it('searchClients includes company_id when companyId > 0', async () => {
    await fieldSalesApi.searchClients('acme', 7)
    expect(get).toHaveBeenCalledWith('/api/field-sales/clients/search', { q: 'acme', company_id: '7' })
  })

  it('searchClients omits company_id when companyId is 0', async () => {
    await fieldSalesApi.searchClients('acme', 0)
    expect(get).toHaveBeenCalledWith('/api/field-sales/clients/search', { q: 'acme' })
  })

  it('getManagerOverview includes company_id when companyId > 0, alongside kam_id', async () => {
    await fieldSalesApi.getManagerOverview('2026-08-01', '2026-08-31', 12, 4)
    expect(get).toHaveBeenCalledWith('/api/field-sales/manager/overview', { date_from: '2026-08-01', date_to: '2026-08-31', kam_id: '12', company_id: '4' })
  })

  it('getManagerOverview omits company_id when not provided', async () => {
    await fieldSalesApi.getManagerOverview('2026-08-01', '2026-08-31')
    expect(get).toHaveBeenCalledWith('/api/field-sales/manager/overview', { date_from: '2026-08-01', date_to: '2026-08-31' })
  })

  it('updateClient PUTs the field-sales client route with the given fields', async () => {
    await fieldSalesApi.updateClient(760, { phone: '0722111222', city: 'Cluj' })
    expect(put).toHaveBeenCalledWith('/api/field-sales/clients/760', { phone: '0722111222', city: 'Cluj' })
  })

  it('getClient360 surfaces the raw client row', async () => {
    get.mockResolvedValueOnce({ client: { id: 760, display_name: 'ACME', phone: '0722000000' }, profile: null })
    const res = await fieldSalesApi.getClient360(760)
    expect(res.client).toEqual({ id: 760, display_name: 'ACME', phone: '0722000000' })
  })
})
