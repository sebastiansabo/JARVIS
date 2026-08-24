import { describe, it, expect, beforeAll, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import HappyTransparency from './Transparency'

describe('HappyTransparency', () => {
  beforeAll(() => {
    // PageHeader uses useIsMobile → window.matchMedia (absent in jsdom).
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

  it('renders the title, subtitle and key transparency sections', () => {
    render(
      <MemoryRouter>
        <HappyTransparency />
      </MemoryRouter>,
    )
    expect(screen.getByText('Cum funcționează Happy')).toBeInTheDocument()
    expect(screen.getByText('Transparență privind datele')).toBeInTheDocument()
    expect(screen.getByText('Ce înregistrăm')).toBeInTheDocument()
    expect(screen.getByText('Cât timp păstrăm')).toBeInTheDocument()
    // Verbatim anonymity guarantee for Pulse must be present.
    expect(
      screen.getByText(/răspunsurile sunt anonime — nu stocăm cine a răspuns/),
    ).toBeInTheDocument()
  })
})
