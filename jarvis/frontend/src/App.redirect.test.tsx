import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// Admin with dashboard access, desktop → DefaultRedirect targets the dashboard.
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (sel: (s: unknown) => unknown) =>
    sel({ user: { role_name: 'Admin', can_access_dashboard: true }, isLoading: false }),
}))
vi.mock('@/lib/utils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils')>()),
  useIsMobile: () => false,
}))

import { DefaultRedirect } from './App'

describe('DefaultRedirect (the /app catch-all)', () => {
  // Mount DefaultRedirect at a deep path and give BOTH the correct (absolute
  // /app/dashboard) and the buggy (relative-appended) targets a terminal route,
  // so the redirect lands once and stops — no infinite loop, fails fast on
  // regression. A relative <Navigate to="dashboard"> would land on the appended
  // path; the absolute target lands on /app/dashboard.
  it('redirects a deep unmatched /app path to the ABSOLUTE /app/dashboard', async () => {
    render(
      <MemoryRouter initialEntries={['/app/buyback/zzz/yyy']}>
        <Routes>
          <Route path="/app/dashboard" element={<div>ABS-dashboard</div>} />
          <Route path="/app/buyback/zzz/yyy" element={<DefaultRedirect />} />
          <Route path="/app/buyback/zzz/yyy/dashboard" element={<div>REL-appended</div>} />
        </Routes>
      </MemoryRouter>
    )
    expect(await screen.findByText('ABS-dashboard')).toBeInTheDocument()
    expect(screen.queryByText('REL-appended')).not.toBeInTheDocument()
  })
})
