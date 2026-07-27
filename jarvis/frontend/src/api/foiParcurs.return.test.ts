import { describe, it, expect, vi, beforeEach } from 'vitest'

// Note: the brief's snippet used a plain top-level `const put = ...`
// referenced inside vi.mock's factory. Vitest hoists vi.mock (and this file
// also has a static `import { foiParcursApi } from './foiParcurs'` after it,
// which is itself hoisted per ES module semantics), so the factory runs
// before `put`/`mockPut` would be initialized — throwing "Cannot access
// '...' before initialization" regardless of naming. Using vi.hoisted() is
// the documented, guaranteed-safe way to share a value with a vi.mock
// factory (https://vitest.dev/api/vi.html#vi-hoisted). Test semantics
// (assert PUT called with the return endpoint + payload) are unchanged.
const { mockPut } = vi.hoisted(() => ({
  mockPut: vi.fn().mockResolvedValue({ success: true, contract: { id: 7 } }),
}))
vi.mock('./client', () => ({ api: { put: mockPut, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import { foiParcursApi } from './foiParcurs'
import type { ReturnTestDrivePayload } from '@/types/foiParcurs'

describe('foiParcursApi.submitTestDriveReturn', () => {
  beforeEach(() => mockPut.mockClear())

  it('PUTs to the return endpoint with the payload', async () => {
    const payload: ReturnTestDrivePayload = {
      km_end: 12500,
      fuel_gauge_end_level: '1/2',
      return_damage: [],
      advisor_signature: 'data:image/png;base64,AAA',
      client_signature: 'data:image/png;base64,BBB',
    }
    await foiParcursApi.submitTestDriveReturn(7, payload)
    expect(mockPut).toHaveBeenCalledWith('/api/foi-parcurs/test-drive/7/return', payload)
  })
})
