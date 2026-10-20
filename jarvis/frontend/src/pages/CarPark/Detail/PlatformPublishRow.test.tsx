import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PlatformPublishRow } from './PlatformPublishRow'

// Radix's DropdownMenuTrigger opens on `pointerdown` (not `click` — click is
// reserved for selecting items), so a plain fireEvent.click never opens it.
function openMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /mai multe|opțiuni|⋯/i }), {
    button: 0,
    ctrlKey: false,
  })
}

function baseProps(overrides: Partial<React.ComponentProps<typeof PlatformPublishRow>> = {}) {
  return {
    logo: <span data-testid="logo">L</span>,
    name: 'Autovit',
    freshness: 'stale' as const,
    externalLinkLabel: 'Vezi anunțul',
    autoEnabled: true,
    busy: false,
    canEdit: true,
    onPrimary: vi.fn(),
    onVerify: vi.fn(),
    onToggleAuto: vi.fn(),
    onDeactivate: vi.fn(),
    ...overrides,
  }
}

describe('PlatformPublishRow', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders the primary action for a stale listing', () => {
    render(<PlatformPublishRow {...baseProps()} />)
    expect(screen.getByRole('button', { name: /actualizează acum/i })).toBeInTheDocument()
  })

  it('does not show "Șterge definitiv" when onDelete is not provided', () => {
    render(<PlatformPublishRow {...baseProps()} />)
    openMenu()
    expect(screen.queryByText('Șterge definitiv')).not.toBeInTheDocument()
  })

  it('shows "Șterge definitiv" when onDelete is provided and confirms before calling it', () => {
    const onDelete = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<PlatformPublishRow {...baseProps({ onDelete })} />)
    openMenu()
    fireEvent.click(screen.getByText('Șterge definitiv'))
    expect(window.confirm).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('does not delete when the confirm dialog is cancelled', () => {
    const onDelete = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<PlatformPublishRow {...baseProps({ onDelete })} />)
    openMenu()
    fireEvent.click(screen.getByText('Șterge definitiv'))
    expect(onDelete).not.toHaveBeenCalled()
  })

  it('toggling the Auto-actualizare switch in the menu calls onToggleAuto(false)', () => {
    const onToggleAuto = vi.fn()
    render(<PlatformPublishRow {...baseProps({ autoEnabled: true, onToggleAuto })} />)
    openMenu()
    fireEvent.click(screen.getByRole('switch'))
    expect(onToggleAuto).toHaveBeenCalledWith(false)
  })

  it('calling "Verifică status acum" invokes onVerify', () => {
    const onVerify = vi.fn()
    render(<PlatformPublishRow {...baseProps({ onVerify })} />)
    openMenu()
    fireEvent.click(screen.getByText('Verifică status acum'))
    expect(onVerify).toHaveBeenCalledTimes(1)
  })

  it('calling "Dezactivează anunțul" invokes onDeactivate', () => {
    const onDeactivate = vi.fn()
    render(<PlatformPublishRow {...baseProps({ onDeactivate })} />)
    openMenu()
    fireEvent.click(screen.getByText('Dezactivează anunțul'))
    expect(onDeactivate).toHaveBeenCalledTimes(1)
  })

  it('hides "Dezactivează anunțul" for a not_published listing (nothing to deactivate)', () => {
    render(<PlatformPublishRow {...baseProps({ freshness: 'not_published' })} />)
    openMenu()
    expect(screen.queryByText('Dezactivează anunțul')).not.toBeInTheDocument()
  })

  it('hides the primary action and "Dezactivează anunțul" when canEdit is false', () => {
    render(<PlatformPublishRow {...baseProps({ canEdit: false })} />)
    expect(screen.queryByRole('button', { name: /actualizează acum/i })).not.toBeInTheDocument()
    openMenu()
    expect(screen.queryByText('Dezactivează anunțul')).not.toBeInTheDocument()
  })

  it('gates "Șterge definitiv" on canEdit even when onDelete is provided', () => {
    // A viewer (canEdit=false) handed an onDelete must never see a live,
    // clickable destructive delete — the row gates it defensively rather than
    // trusting every caller to also condition onDelete on canEdit.
    render(<PlatformPublishRow {...baseProps({ canEdit: false, onDelete: vi.fn() })} />)
    expect(screen.queryByRole('button', { name: /actualizează acum/i })).not.toBeInTheDocument()
    openMenu()
    expect(screen.queryByText('Șterge definitiv')).not.toBeInTheDocument()
    expect(screen.queryByText('Dezactivează anunțul')).not.toBeInTheDocument()
    // Read-only verify stays available regardless of edit rights.
    expect(screen.getByText('Verifică status acum')).toBeInTheDocument()
  })

  it('renders an external link when externalUrl is provided', () => {
    render(
      <PlatformPublishRow
        {...baseProps({ externalUrl: 'https://example.com/listing', externalLinkLabel: 'Vezi anunțul' })}
      />,
    )
    const link = screen.getByRole('link', { name: /vezi anunțul/i })
    expect(link).toHaveAttribute('href', 'https://example.com/listing')
  })

  it('shows the "se actualizează automat" helper text when freshness is stale and auto is enabled', () => {
    render(<PlatformPublishRow {...baseProps({ freshness: 'stale', autoEnabled: true })} />)
    expect(screen.getByText(/se actualizează automat/i)).toBeInTheDocument()
  })

  it('shows no primary action for moderation/expired states', () => {
    render(<PlatformPublishRow {...baseProps({ freshness: 'moderation' })} />)
    expect(screen.queryByRole('button', { name: /actualizează|publică|reactivează|reîncearcă/i })).not.toBeInTheDocument()
  })
})
