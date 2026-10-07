import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import type { User } from '@/types'

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/useAuth', () => ({ useAuth }))

vi.mock('@/lib/columnDefaults', () => ({ fetchColumnDefaults: vi.fn() }))

vi.mock('@/components/consents/ConsentGate', () => ({
  default: () => <div data-testid="consent-gate">GATE</div>,
}))

vi.mock('./Sidebar', () => ({ Sidebar: () => <div data-testid="sidebar" /> }))
vi.mock('./NotificationBell', () => ({ NotificationBell: () => <div data-testid="bell" /> }))
vi.mock('./AiAgentWidget', () => ({
  AiAgentWidget: () => <div data-testid="ai-widget" />,
  AiAgentPanel: () => <div data-testid="ai-panel" />,
}))
vi.mock('./ThemeToggle', () => ({ ThemeToggle: () => <div data-testid="theme-toggle" /> }))

import Layout from './Layout'

function baseUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: 'seb@test.com',
    role_name: 'Admin',
    ...overrides,
  } as User
}

beforeAll(() => {
  // Toaster (sonner) reads window.matchMedia for the OS theme (absent in jsdom).
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  })) as unknown as typeof window.matchMedia
})

beforeEach(() => {
  useAuth.mockReset()
  // Layout's heartbeat effect pings /api/heartbeat once mounted.
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
})

describe('Layout consent gate wiring', () => {
  it('renders ConsentGate instead of the app when consents_complete is explicitly false', () => {
    useAuth.mockReturnValue({ user: baseUser({ consents_complete: false }), isLoading: false })
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('consent-gate')).toBeInTheDocument()
    expect(screen.queryByTestId('sidebar')).not.toBeInTheDocument()
  })

  it('renders the normal app when consents_complete is true', () => {
    useAuth.mockReturnValue({ user: baseUser({ consents_complete: true }), isLoading: false })
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('consent-gate')).not.toBeInTheDocument()
    expect(screen.getByTestId('sidebar')).toBeInTheDocument()
  })

  it('renders the normal app when consents_complete is undefined (older cached user / field absent)', () => {
    useAuth.mockReturnValue({ user: baseUser({ consents_complete: undefined }), isLoading: false })
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('consent-gate')).not.toBeInTheDocument()
    expect(screen.getByTestId('sidebar')).toBeInTheDocument()
  })
})

// The mobile header's account menu is the ONLY logout path on mobile: every
// role lands on the Hub there, and Viewers get no hamburger/sidebar — so the
// Logout item inside this menu must always be present.
describe('Layout mobile header account menu', () => {
  function renderLayout() {
    return render(
      <MemoryRouter initialEntries={['/app/hub']}>
        <Routes>
          <Route path="/app" element={<Layout />}>
            <Route path="hub" element={<div>hub content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
  }

  it('exposes a Logout link (href=/logout) and a My Profile link for a Viewer', async () => {
    useAuth.mockReturnValue({ user: baseUser({ role_name: 'Viewer', consents_complete: true }), isLoading: false })
    renderLayout()

    // Radix menu triggers open on pointerdown (button 0), not click.
    fireEvent.pointerDown(screen.getByRole('button', { name: /account menu/i }), { button: 0 })

    const logout = await screen.findByRole('menuitem', { name: /logout/i })
    expect(logout).toHaveAttribute('href', '/logout')
    expect(screen.getByRole('menuitem', { name: /my profile/i })).toBeInTheDocument()
  })

  it('exposes the same Logout link for a non-Viewer', async () => {
    useAuth.mockReturnValue({ user: baseUser({ role_name: 'Admin', consents_complete: true }), isLoading: false })
    renderLayout()

    fireEvent.pointerDown(screen.getByRole('button', { name: /account menu/i }), { button: 0 })

    const logout = await screen.findByRole('menuitem', { name: /logout/i })
    expect(logout).toHaveAttribute('href', '/logout')
  })
})
