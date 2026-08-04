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

  it('updateVisit forwards planned_end_time', async () => {
    await fieldSalesApi.updateVisit(9, { planned_time: '09:00', planned_end_time: '11:00' })
    expect(put).toHaveBeenCalledWith('/api/field-sales/visits/9', { planned_time: '09:00', planned_end_time: '11:00' })
  })
})
