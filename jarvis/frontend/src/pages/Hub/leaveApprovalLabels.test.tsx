import { describe, it, expect } from 'vitest'
import { leaveApprovalLabels } from './index'

describe('leaveApprovalLabels', () => {
  it('grant request → neutral labels, no badge', () => {
    expect(leaveApprovalLabels(false)).toEqual({
      badge: null,
      approve: 'Aprobă',
      reject: 'Respinge',
      confirmReject: 'Confirmă respingerea',
    })
  })

  it('cancellation request → distinguishing badge + relabeled actions', () => {
    const labels = leaveApprovalLabels(true)
    expect(labels.badge).toBe('Cerere de anulare')
    expect(labels.approve).toBe('Aprobă anularea')
    expect(labels.reject).toBe('Respinge anularea')
    expect(labels.confirmReject).toBe('Confirmă respingerea anulării')
  })

  it('cancellation and grant labels never collide (manager cannot mistake one for the other)', () => {
    const grant = leaveApprovalLabels(false)
    const cancellation = leaveApprovalLabels(true)
    expect(grant.approve).not.toBe(cancellation.approve)
    expect(grant.reject).not.toBe(cancellation.reject)
  })
})
