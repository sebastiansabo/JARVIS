import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'

// Mock the HTTP client so we assert WHICH endpoint the wrapper targets,
// independent of the network. The bug this guards: the Test Drive form
// hydrated a selected client via the @crm_required /api/crm/clients/:id, which
// 403s for the Viewer (consilier) role. Hydration must use the login-gated
// foi-parcurs endpoint instead.
vi.mock('./client', () => ({
  api: {
    get: vi.fn(() => Promise.resolve({ success: true, client: { id: 5 } })),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from './client'
import { foiParcursApi } from './foiParcurs'

describe('foiParcursApi.getCrmClient', () => {
  beforeEach(() => vi.clearAllMocks())

  it('hydrates a client via the login-gated foi-parcurs endpoint', async () => {
    await foiParcursApi.getCrmClient(5)
    expect(api.get).toHaveBeenCalledWith('/api/foi-parcurs/crm-clients/5')
  })

  it('does not use the @crm_required CRM endpoint (403 for Viewers)', async () => {
    await foiParcursApi.getCrmClient(5)
    const path = (api.get as Mock).mock.calls[0][0] as string
    expect(path).not.toContain('/api/crm/clients/')
  })
})
