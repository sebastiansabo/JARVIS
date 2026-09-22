import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
const post = vi.fn()
vi.mock('./client', () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }))

import { tdApi } from './td'

describe('tdApi', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    get.mockResolvedValue({})
    post.mockResolvedValue({})
  })

  it('getPage fetches the public page by slug', async () => {
    const page = {
      page: { title: 'Test Drive BMW', company_name: 'Autoworld' },
      cars: [{ id: 1, vin: 'VIN123' }],
      slots: [{ id: 10, car_id: 1, vin: 'VIN123', starts_at: '2026-09-25T09:00:00Z', ends_at: '2026-09-25T09:30:00Z' }],
    }
    get.mockResolvedValueOnce(page)
    const res = await tdApi.getPage('bmw-td')
    expect(get).toHaveBeenCalledWith('/api/td/pages/bmw-td')
    expect(res).toEqual(page)
    expect(res.page.company_name).toBe('Autoworld')
  })

  it('submitBooking posts the booking payload to the page bookings route', async () => {
    post.mockResolvedValueOnce({ booking_id: 42, status: 'pending' })
    const body = { slot_id: 10, name: 'Ion Pop', phone: '0722111222', email: 'ion@example.com' }
    const res = await tdApi.submitBooking('bmw-td', body)
    expect(post).toHaveBeenCalledWith('/api/td/pages/bmw-td/bookings', body)
    expect(res).toEqual({ booking_id: 42, status: 'pending' })
  })

  it('submitBooking forwards optional utm data', async () => {
    const body = { slot_id: 10, name: 'Ion Pop', phone: '0722111222', email: 'ion@example.com', utm: { utm_source: 'facebook' } }
    await tdApi.submitBooking('bmw-td', body)
    expect(post).toHaveBeenCalledWith('/api/td/pages/bmw-td/bookings', body)
  })

  it('confirm posts the token to the confirm route', async () => {
    post.mockResolvedValueOnce({ status: 'confirmed', fp_id: 7 })
    const res = await tdApi.confirm('tok-abc')
    expect(post).toHaveBeenCalledWith('/api/td/bookings/confirm', { token: 'tok-abc' })
    expect(res).toEqual({ status: 'confirmed', fp_id: 7 })
  })

  it('cancel posts the token to the cancel route', async () => {
    post.mockResolvedValueOnce({ status: 'cancelled' })
    const res = await tdApi.cancel('tok-abc')
    expect(post).toHaveBeenCalledWith('/api/td/bookings/cancel', { token: 'tok-abc' })
    expect(res).toEqual({ status: 'cancelled' })
  })
})
