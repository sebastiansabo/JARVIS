import { describe, it, expect } from 'vitest'
import { leaveRowActions } from './index'

describe('leaveRowActions', () => {
  it('pending → modify + cancel', () => {
    expect(leaveRowActions('flagged')).toEqual({ canModify: true, canCancel: true, canRequestCancel: false })
    expect(leaveRowActions('pending_approval')).toEqual({ canModify: true, canCancel: true, canRequestCancel: false })
  })
  it('approved → request cancel only', () => {
    expect(leaveRowActions('approved')).toEqual({ canModify: false, canCancel: false, canRequestCancel: true })
  })
  it('terminal / in-flight → nothing', () => {
    for (const s of ['cancelled', 'rejected', 'cancellation_pending'])
      expect(leaveRowActions(s)).toEqual({ canModify: false, canCancel: false, canRequestCancel: false })
  })
})
