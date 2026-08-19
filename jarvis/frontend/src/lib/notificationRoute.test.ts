import { describe, it, expect } from 'vitest'
import { resolveNotificationRoute } from './notificationRoute'

describe('resolveNotificationRoute', () => {
  it('maps the backend approval deep-link to the leave-approvals view', () => {
    // In-app the bell navigates with React Router, which has no /go/approval
    // route — resolve it to where the approver can actually act.
    expect(resolveNotificationRoute('/go/approval/123')).toBe(
      '/app/hub?module=hr&hrtab=leave-approvals',
    )
  })

  it('passes normal SPA links through unchanged', () => {
    expect(resolveNotificationRoute('/app/approvals')).toBe('/app/approvals')
    expect(resolveNotificationRoute('/app/accounting/invoices/7')).toBe(
      '/app/accounting/invoices/7',
    )
  })

  it('returns null for a missing link', () => {
    expect(resolveNotificationRoute(null)).toBeNull()
    expect(resolveNotificationRoute('')).toBeNull()
  })
})
