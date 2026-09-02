import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
