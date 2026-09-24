import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from './client'
import { buybackApi } from './buyback'

vi.mock('./client', () => ({ api: { get: vi.fn(() => Promise.resolve({})), post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})), delete: vi.fn(() => Promise.resolve({})) } }))

describe('buybackApi', () => {
  beforeEach(() => vi.clearAllMocks())
  it('listRecords hits /api/buyback/records with query', () => {
    buybackApi.listRecords({ status: 'BOUGHT', company_id: 3 })
    expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/buyback\/records\?.*status=BOUGHT/))
  })
  it('createRecord POSTs to /api/buyback/records', () => {
    buybackApi.createRecord({ vin: 'X', brand: 'A', model: 'B' } as any)
    expect(api.post).toHaveBeenCalledWith('/api/buyback/records', expect.objectContaining({ vin: 'X' }))
  })
  it('postOffer + decision + finalize hit the right paths', () => {
    buybackApi.postOffer(5, { offer_type: 'initial', amount_eur: 9000 })
    expect(api.post).toHaveBeenCalledWith('/api/buyback/records/5/offers', expect.any(Object))
    buybackApi.recordDecision(5, 7, { decision: 'accepted' })
    expect(api.post).toHaveBeenCalledWith('/api/buyback/records/5/offers/7/decision', expect.any(Object))
    buybackApi.finalize(5)
    expect(api.post).toHaveBeenCalledWith('/api/buyback/records/5/finalize', expect.any(Object))
  })
})
