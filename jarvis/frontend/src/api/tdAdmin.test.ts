import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()
const del = vi.fn()
vi.mock('./client', () => ({
  api: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    patch: (...a: unknown[]) => patch(...a),
    delete: (...a: unknown[]) => del(...a),
  },
}))

import { tdAdminApi } from './tdAdmin'

describe('tdAdminApi', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    patch.mockReset()
    del.mockReset()
    get.mockResolvedValue({})
    post.mockResolvedValue({})
    patch.mockResolvedValue({})
    del.mockResolvedValue({})
  })

  it('listPages fetches all pages when no company is given', async () => {
    get.mockResolvedValueOnce({ pages: [] })
    const res = await tdAdminApi.listPages()
    expect(get).toHaveBeenCalledWith('/marketing/api/td/pages')
    expect(res).toEqual({ pages: [] })
  })

  it('listPages scopes to a company id when given', async () => {
    await tdAdminApi.listPages(7)
    expect(get).toHaveBeenCalledWith('/marketing/api/td/pages?company_id=7')
  })

  it('createPage posts the page payload', async () => {
    const body = { company_id: 7, slug: 'bmw-x5-td', title: 'BMW X5 Test Drive' }
    post.mockResolvedValueOnce({ id: 1, ...body })
    const res = await tdAdminApi.createPage(body)
    expect(post).toHaveBeenCalledWith('/marketing/api/td/pages', body)
    expect(res).toEqual({ id: 1, ...body })
  })

  it('updatePage patches the page by id', async () => {
    const body = { title: 'New title' }
    await tdAdminApi.updatePage(5, body)
    expect(patch).toHaveBeenCalledWith('/marketing/api/td/pages/5', body)
  })

  it('setStatus posts the new status to the status route', async () => {
    await tdAdminApi.setStatus(5, 'open')
    expect(post).toHaveBeenCalledWith('/marketing/api/td/pages/5/status', { status: 'open' })
  })

  it('addCar posts the car payload to the page cars route', async () => {
    const body = { vin: 'VIN123', default_advisor_user_id: 3 }
    post.mockResolvedValueOnce({ id: 10, ...body })
    const res = await tdAdminApi.addCar(5, body)
    expect(post).toHaveBeenCalledWith('/marketing/api/td/pages/5/cars', body)
    expect(res).toEqual({ id: 10, ...body })
  })

  it('removeCar deletes the car by id', async () => {
    await tdAdminApi.removeCar(10)
    expect(del).toHaveBeenCalledWith('/marketing/api/td/cars/10')
  })

  it('listCars fetches the cars for a page', async () => {
    get.mockResolvedValueOnce({ cars: [] })
    const res = await tdAdminApi.listCars(5)
    expect(get).toHaveBeenCalledWith('/marketing/api/td/pages/5/cars')
    expect(res).toEqual({ cars: [] })
  })

  it('addWindow posts the window payload to the page windows route', async () => {
    const body = { window_date: '2026-10-01', start_time: '09:00', end_time: '17:00' }
    post.mockResolvedValueOnce({ id: 20, ...body })
    const res = await tdAdminApi.addWindow(5, body)
    expect(post).toHaveBeenCalledWith('/marketing/api/td/pages/5/windows', body)
    expect(res).toEqual({ id: 20, ...body })
  })

  it('listWindows fetches the windows for a page', async () => {
    get.mockResolvedValueOnce({ windows: [] })
    const res = await tdAdminApi.listWindows(5)
    expect(get).toHaveBeenCalledWith('/marketing/api/td/pages/5/windows')
    expect(res).toEqual({ windows: [] })
  })

  it('materialize posts to the materialize route with no body', async () => {
    post.mockResolvedValueOnce({ inserted: 12 })
    const res = await tdAdminApi.materialize(5)
    expect(post).toHaveBeenCalledWith('/marketing/api/td/pages/5/materialize', {})
    expect(res).toEqual({ inserted: 12 })
  })

  it('listBookings fetches all bookings for a page when no status given', async () => {
    get.mockResolvedValueOnce({ bookings: [] })
    const res = await tdAdminApi.listBookings(5)
    expect(get).toHaveBeenCalledWith('/marketing/api/td/pages/5/bookings')
    expect(res).toEqual({ bookings: [] })
  })

  it('listBookings scopes to a status when given', async () => {
    await tdAdminApi.listBookings(5, 'confirmed')
    expect(get).toHaveBeenCalledWith('/marketing/api/td/pages/5/bookings?status=confirmed')
  })

  it('reassignAdvisor patches the advisor route with the new advisor id', async () => {
    await tdAdminApi.reassignAdvisor(30, 9)
    expect(patch).toHaveBeenCalledWith('/marketing/api/td/bookings/30/advisor', { advisor_user_id: 9 })
  })
})
