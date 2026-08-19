import { describe, it, expect, vi } from 'vitest'

vi.mock('./client', () => ({
  api: {
    post: vi.fn(() => Promise.resolve({ success: true, data: { status: 'cancelled' } })),
    patch: vi.fn(() => Promise.resolve({ success: true, data: { submission_id: 42 } })),
    get: vi.fn(),
  },
}))

import { api } from './client'
import { connecteamApi } from './connecteam'

describe('leave cancel/modify api', () => {
  it('cancel hits the cancel endpoint', async () => {
    await connecteamApi.cancelLeavePermit(42)
    expect(api.post).toHaveBeenCalledWith('/connecteam/api/submissions/leave-permit/42/cancel')
  })

  it('update PATCHes answers', async () => {
    await connecteamApi.updateLeavePermit(42, { f_bi_duration_hours: '1' })
    expect(api.patch).toHaveBeenCalledWith('/connecteam/api/submissions/leave-permit/42', {
      answers: { f_bi_duration_hours: '1' },
    })
  })
})
