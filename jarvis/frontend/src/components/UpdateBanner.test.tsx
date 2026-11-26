import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UpdateBanner } from './UpdateBanner'
import { useVersionCheck } from '@/hooks/useVersionCheck'

vi.mock('@/hooks/useVersionCheck', () => ({ useVersionCheck: vi.fn() }))

describe('UpdateBanner', () => {
  beforeEach(() => vi.mocked(useVersionCheck).mockReset())

  it('renders nothing when no newer version', () => {
    vi.mocked(useVersionCheck).mockReturnValue(false)
    const { container } = render(<UpdateBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('shows the reload prompt (manual, no auto-reload) when an update is available', () => {
    vi.mocked(useVersionCheck).mockReturnValue(true)
    render(<UpdateBanner />)
    expect(screen.getByText('Versiune nouă disponibilă')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reîncarcă' })).toBeInTheDocument()
  })

  it('hides after dismiss', () => {
    vi.mocked(useVersionCheck).mockReturnValue(true)
    render(<UpdateBanner />)
    fireEvent.click(screen.getByRole('button', { name: 'Închide' }))
    expect(screen.queryByText('Versiune nouă disponibilă')).not.toBeInTheDocument()
  })
})
