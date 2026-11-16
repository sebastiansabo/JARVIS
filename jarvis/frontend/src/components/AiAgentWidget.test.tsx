import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mutable permission flag, hoisted so the vi.mock factory can read it.
const h = vi.hoisted(() => ({ canAccess: false }))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (sel: (s: unknown) => unknown) =>
    sel({ user: { can_access_ai_agent: h.canAccess }, isLoading: false }),
}))
vi.mock('@/stores/aiAgentStore', () => ({
  useAiAgentStore: (sel: (s: unknown) => unknown) =>
    sel({ isWidgetOpen: false, setWidgetOpen: vi.fn() }),
}))
vi.mock('@/hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useLocation: () => ({ pathname: '/app/dashboard' }),
}))
vi.mock('./EphemeralChatPopup', () => ({ EphemeralChatPopup: () => null }))

import { AiAgentWidget } from './AiAgentWidget'

describe('AiAgentWidget permission gate', () => {
  beforeEach(() => {
    h.canAccess = false
  })

  it('does NOT render the Bot trigger for users without can_access_ai_agent', () => {
    // The floating widget mounts globally (Layout), so a role without AI access
    // used to see the Bot button, click it, and hit a 403 on /ai-agent/api/models.
    h.canAccess = false
    render(<AiAgentWidget />)
    expect(screen.queryByLabelText('Open AI Agent')).toBeNull()
  })

  it('renders the Bot trigger for users with can_access_ai_agent', () => {
    h.canAccess = true
    render(<AiAgentWidget />)
    expect(screen.queryByLabelText('Open AI Agent')).not.toBeNull()
  })
})
